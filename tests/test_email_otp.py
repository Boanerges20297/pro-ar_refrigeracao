"""Isolated OTP and trusted-device login regressions; never send mail or call production."""
import re
from hashlib import sha256
from unittest.mock import patch

from redis.exceptions import RedisError

from app import db
from app.models.user import User
from app.utils.login_otp import (
    TRUST_COOKIE_NAME, CHALLENGE_PREFIX, RESEND_PREFIX,
    validate_trusted_device, revoke_all_trusted_devices,
    issue_trusted_device, rotate_trusted_device, revoke_trusted_device,
)
from contract_support import ContractCase


class FakePipeline:
    def __init__(self, store):
        self.store, self.operations = store, []

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.operations.append((name, args, kwargs))
            return self
        return record

    def execute(self):
        results = [getattr(self.store, name)(*args, **kwargs)
                   for name, args, kwargs in self.operations]
        self.operations.clear()
        return results


class FakeRedis:
    def __init__(self):
        self.hashes, self.sorted_sets, self.strings = {}, {}, {}

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    def hset(self, key, name=None, value=None, mapping=None):
        item = self.hashes.setdefault(key, {})
        if mapping is not None:
            item.update({k: str(v) for k, v in mapping.items()})
        else:
            item[name] = str(value)
        return 1

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, key, seconds):
        return True

    def delete(self, key):
        return int(bool(self.hashes.pop(key, None) is not None or
                        self.sorted_sets.pop(key, None) is not None or
                        self.strings.pop(key, None) is not None))

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.strings:
            return False
        self.strings[key] = str(value)
        return True

    def get(self, key):
        return self.strings.get(key)

    def incr(self, key):
        value = int(self.strings.get(key, '0')) + 1
        self.strings[key] = str(value)
        return value

    def zadd(self, key, mapping):
        self.sorted_sets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def zrange(self, key, start, end):
        ordered = [item for item, _ in sorted(
            self.sorted_sets.get(key, {}).items(), key=lambda kv: kv[1])]
        if end < 0:
            end = len(ordered) + end
        return ordered[start:end + 1] if end >= start else []

    def zscore(self, key, member):
        return self.sorted_sets.get(key, {}).get(member)

    def zrem(self, key, member):
        return int(self.sorted_sets.get(key, {}).pop(member, None) is not None)

    def eval(self, script, numkeys, *args):
        if numkeys == 4:
            (old_key, new_key, index, epoch_key, old_digest,
             new_digest, uid, pwdv, role, emailv, now) = args
            record = self.hashes.get(old_key)
            if (not record or self.zscore(index, old_digest) is None
                    or record.get('uid') != uid or record.get('pwdv') != pwdv
                    or record.get('role') != role or record.get('emailv') != emailv
                    or record.get('epoch') != (self.get(epoch_key) or '0')
                    or int(record.get('expires_at', '0')) <= int(now)):
                return 0
            self.hset(new_key, mapping=dict(record, last_seen_at=now))
            self.delete(old_key)
            self.zrem(index, old_digest)
            self.zadd(index, {new_digest: int(now)})
            return 3600  # Simulated remaining TTL in seconds.
        if numkeys == 2 and len(args) == 3:
            key, index, digest = args
            if self.zscore(index, digest) is None:
                return 0
            self.delete(key)
            self.zrem(index, digest)
            return 1
        assert numkeys == 2
        key, epoch_key, digest, uid, pwdv, role, emailv = args
        record = self.hashes.get(key)
        if not record:
            return -1
        if (record.get('uid') != uid or record.get('pwdv') != pwdv
                or record.get('role') != role
                or record.get('emailv') != emailv
                or record.get('epoch') != (self.get(epoch_key) or '0')):
            self.delete(key)
            return -1
        record['attempts'] = str(int(record['attempts']) + 1)
        if int(record['attempts']) > 5:
            self.delete(key)
            return -2
        if record.get('digest') == digest:
            self.delete(key)
            return 1
        if int(record['attempts']) >= 5:
            self.delete(key)
            return -2
        return 0


class EmailOtpContracts(ContractCase):
    def setUp(self):
        super().setUp()
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.app.config['EMAIL_OTP_ENABLED'] = True
        self.app.config['SECURITY_JWT_SERVER_SESSIONS'] = True
        self.app.config['SECURITY_BIND_JWT_SESSION_NONCE'] = True
        self.backend = FakeRedis()
        self.app.extensions['login_otp_store'] = self.backend
        self.app.extensions['jwt_session_store'] = self.backend
        self.sent = []
        self.sender = patch('app.routes.auth.send_dynamic_email', side_effect=self._send)
        self.sender.start()

    def tearDown(self):
        self.sender.stop()
        super().tearDown()

    def _send(self, address, subject, template, **kwargs):
        self.sent.append((address, kwargs.get('code')))
        return True, 'delivered'

    @staticmethod
    def _token(page):
        match = re.search(rb'name="csrf_token"\s+value="([^"]+)"', page.data)
        assert match, 'expected a real Flask-WTF token'
        return match.group(1).decode('ascii')

    def _start(self, client=None, email='admin@contract.local', password='Teste12345'):
        client = client or self.http
        token = self._token(client.get('/auth/login'))
        response = client.post('/auth/login', data={
            'email': email, 'password': password, 'csrf_token': token,
        })
        return client, response, token

    def _complete(self, client, remember=False):
        otp = self.sent[-1][1]
        token = self._token(client.get('/auth/otp'))
        result = client.post('/auth/otp', data={
            'otp_code': otp, 'csrf_token': token,
            'remember_device': 'on' if remember else '',
        })
        return result, token

    def test_password_alone_never_creates_jwt_and_valid_otp_does(self):
        client, password, _ = self._start()
        self.assertEqual(password.status_code, 302)
        self.assertIn('/auth/otp', password.headers['Location'])
        self.assertFalse(any('access_token_cookie=' in item
                             for item in password.headers.getlist('Set-Cookie')
                             if 'access_token_cookie=;' not in item))
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        result, _ = self._complete(client)
        self.assertEqual(result.status_code, 302)
        self.assertIn('/admin/dashboard', result.headers['Location'])
        self.assertEqual(client.get('/admin/dashboard').status_code, 200)
        with self.app.app_context():
            from app.models.audit_log import AuditLog
            successes = AuditLog.query.filter_by(action='LOGIN', status='success').count()
            self.assertEqual(successes, 1)

    def test_wrong_password_and_missing_or_forged_csrf_never_send(self):
        client, rejected, _ = self._start(password='wrong-password')
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(self.sent, [])
        missing = client.post('/auth/otp', data={'otp_code': '123456'})
        self.assertEqual(missing.status_code, 400)
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)

    def test_wrong_codes_are_limited_and_consumed(self):
        client, _, _ = self._start()
        otp = self.sent[-1][1]
        wrong = '000000' if otp != '000000' else '111111'
        token = self._token(client.get('/auth/otp'))
        for _ in range(4):
            bad = client.post('/auth/otp', data={'csrf_token': token, 'otp_code': wrong})
            self.assertEqual(bad.status_code, 200)
        locked = client.post('/auth/otp', data={'csrf_token': token, 'otp_code': wrong})
        self.assertEqual(locked.status_code, 302)
        self.assertIn('/auth/login', locked.headers['Location'])
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        replay = client.post('/auth/otp', data={'csrf_token': token, 'otp_code': otp})
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        self.assertEqual(replay.status_code, 302)

    def test_reused_or_expired_code_fails_closed(self):
        client, _, _ = self._start()
        result, token = self._complete(client)
        self.assertEqual(result.status_code, 302)
        used_code = self.sent[-1][1]
        replay = client.post('/auth/otp', data={'csrf_token': token, 'otp_code': used_code})
        self.assertEqual(replay.status_code, 302)
        other = self.app.test_client()
        other, _, _ = self._start(other)
        self.backend.hashes.clear()
        expired = other.get('/auth/otp')
        self.assertEqual(expired.status_code, 302)
        self.assertNotEqual(other.get('/admin/dashboard').status_code, 200)

    def test_resend_limits_and_invalidates_old_code(self):
        client, _, token = self._start()
        original_code = self.sent[-1][1]
        blocked = client.post('/auth/otp/resend', data={'csrf_token': token})
        self.assertEqual(blocked.status_code, 302)
        self.assertEqual(len(self.sent), 1)
        self.backend.strings.clear()  # Simulate the 60-second cooldown passing.
        sent = client.post('/auth/otp/resend', data={'csrf_token': token})
        self.assertEqual(sent.status_code, 302)
        self.assertEqual(len(self.sent), 2)
        code = self.sent[-1][1]
        check_token = self._token(client.get('/auth/otp'))
        bad = client.post('/auth/otp', data={'csrf_token': check_token, 'otp_code': original_code})
        self.assertEqual(bad.status_code, 200)
        good = client.post('/auth/otp', data={'csrf_token': check_token, 'otp_code': code})
        self.assertEqual(good.status_code, 302)
        self.assertEqual(client.get('/admin/dashboard').status_code, 200)

    def test_remember_device_works_and_revocation_restores_otp(self):
        client, _, _ = self._start()
        result, token = self._complete(client, remember=True)
        self.assertEqual(result.status_code, 302)
        trust_header = next(x for x in result.headers.getlist('Set-Cookie') if x.startswith(TRUST_COOKIE_NAME + '='))
        for expected in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/auth'):
            self.assertIn(expected, trust_header)
        devices = client.get('/auth/trusted-devices')
        self.assertEqual(devices.status_code, 200)
        self.assertIn(b'Revogar', devices.data)
        self.assertEqual(len(self.backend.sorted_sets), 1)
        cookie = client.get_cookie(TRUST_COOKIE_NAME, path='/auth')
        self.assertIsNotNone(cookie)

        client.post('/auth/logout', data={'csrf_token': token})
        second, response, _ = self._start(client)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/dashboard', response.headers['Location'])
        self.assertEqual(len(self.sent), 1)

        listed = client.get('/auth/trusted-devices')
        url = re.search(rb'action="(/auth/trusted-devices/revoke/[0-9a-f]{64})"', listed.data)
        self.assertIsNotNone(url)
        revoke_token = self._token(listed)
        revoked = client.post(url.group(1).decode(), data={'csrf_token': revoke_token})
        self.assertEqual(revoked.status_code, 302)
        self.assertIsNone(client.get_cookie(TRUST_COOKIE_NAME, path='/auth'))
        client.post('/auth/logout', data={'csrf_token': revoke_token})
        _, new, _ = self._start(client)
        self.assertIn('/auth/otp', new.headers['Location'])

    def test_each_account_role_requires_and_completes_otp(self):
        # The client portal requires a real client association in addition
        # to successful authentication; wire the test fixture accordingly.
        with self.app.app_context():
            from app.models.client import Client
            customer = User.query.filter_by(email='client@contract.local').one()
            customer.clients.append(Client.query.first())
            from app.models.workorder import WorkOrder
            WorkOrder.query.first().description = 'Ordem de serviço de teste'
            db.session.commit()
        destinations = {
            'secretary': '/secretary/dashboard',
            'user': '/tech/dashboard',
            'client': '/client/dashboard',
            'common': '/common/dashboard',
        }
        for role, dashboard in destinations.items():
            with self.subTest(role=role):
                browser = self.app.test_client()
                browser, entered, _ = self._start(
                    browser, email=f'{role}@contract.local')
                self.assertIn('/auth/otp', entered.headers['Location'])
                self.assertNotEqual(browser.get(dashboard).status_code, 200)
                complete, _ = self._complete(browser)
                self.assertEqual(complete.status_code, 302)
                self.assertEqual(browser.get(dashboard).status_code, 200)

    def test_individual_revocation_is_atomic_against_rotation(self):
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            uid = user.id
            first = issue_trusted_device(user, 'Test browser')
            first_id = sha256(first.encode('ascii')).hexdigest()
            self.assertTrue(revoke_trusted_device(uid, first_id))
            self.assertIsNone(rotate_trusted_device(user, first))

            second = issue_trusted_device(user, 'Test browser')
            second_id = sha256(second.encode('ascii')).hexdigest()
            rotated = rotate_trusted_device(user, second)
            self.assertIsNotNone(rotated)
            # If rotation won the race, revoking a stale ID must not lie.
            self.assertFalse(revoke_trusted_device(uid, second_id))
            self.assertTrue(validate_trusted_device(user, rotated[0]))

    def test_jwt_registration_failure_never_audits_success(self):
        browser, _, _ = self._start()
        with patch.object(self.backend, 'set', side_effect=RedisError('unavailable')):
            rejected, _ = self._complete(browser)
        self.assertIn('/auth/login', rejected.headers['Location'])
        self.assertNotEqual(browser.get('/admin/dashboard').status_code, 200)
        with self.app.app_context():
            from app.models.audit_log import AuditLog
            successes = AuditLog.query.filter_by(action='LOGIN', status='success').count()
            self.assertEqual(successes, 0)

    def test_jwt_requires_browser_session_and_captured_token_dies_on_logout(self):
        client, _, _ = self._start()
        result, csrf = self._complete(client)
        self.assertEqual(result.status_code, 302)
        jwt_cookie = client.get_cookie('access_token_cookie')
        session_cookie = client.get_cookie('session')
        self.assertIsNotNone(jwt_cookie)
        self.assertIsNotNone(session_cookie)

        # JWT alone must not authenticate a different browser/session.
        token_only = self.app.test_client()
        token_only.set_cookie('access_token_cookie', jwt_cookie.value, path='/')
        self.assertNotEqual(token_only.get('/admin/dashboard').status_code, 200)

        # A full stolen browser session is valid until actively revoked.
        copied_session = self.app.test_client()
        copied_session.set_cookie('access_token_cookie', jwt_cookie.value, path='/')
        copied_session.set_cookie('session', session_cookie.value, path='/')
        self.assertEqual(copied_session.get('/admin/dashboard').status_code, 200)

        logged_out = client.post('/auth/logout', data={'csrf_token': csrf})
        self.assertEqual(logged_out.status_code, 302)
        self.assertNotEqual(copied_session.get('/admin/dashboard').status_code, 200)

    def test_trusted_cookie_is_single_use_and_rotates_on_login(self):
        client, _, _ = self._start()
        completed, _ = self._complete(client, remember=True)
        self.assertEqual(completed.status_code, 302)
        original = client.get_cookie(TRUST_COOKIE_NAME, path='/auth').value

        login_csrf = self._token(client.get('/auth/login'))
        # Logout does not delete trust; this is an intentional user opt-in.
        client.post('/auth/logout', data={'csrf_token': login_csrf})
        _, trusted_login, _ = self._start(client)
        self.assertIn('/admin/dashboard', trusted_login.headers['Location'])
        replacement = client.get_cookie(TRUST_COOKIE_NAME, path='/auth').value
        self.assertNotEqual(original, replacement)
        self.assertEqual(len(self.sent), 1)

        replay_client = self.app.test_client()
        replay_client.set_cookie(TRUST_COOKIE_NAME, original, path='/auth')
        _, replay_login, _ = self._start(replay_client)
        self.assertIn('/auth/otp', replay_login.headers['Location'])
        self.assertEqual(len(self.sent), 2)

    def test_admin_account_edits_revoke_devices_even_after_values_revert(self):
        staff_client = self.app.test_client()
        self._start(staff_client, email='secretary@contract.local')
        self._complete(staff_client, remember=True)
        with self.app.app_context():
            staff_id = User.query.filter_by(email='secretary@contract.local').one().id

        admin_client, _, _ = self._start()
        self._complete(admin_client)
        csrf = self._token(admin_client.get('/auth/login'))
        form = {
            'name': 'Teste secretary', 'email': 'novo@contract.local',
            'permission_level': 'secretary', 'job_title': 'Atendente',
            'is_active': 'on', 'cpf': '12345678901', 'phone': '85999999999',
            'csrf_token': csrf,
        }
        first = admin_client.post(f'/tech/edit/{staff_id}', data=form)
        self.assertEqual(first.status_code, 302)
        with self.app.app_context():
            self.assertEqual(User.query.get(staff_id).email, 'novo@contract.local')
        # Changing only the email terminates the prior JWT immediately.
        self.assertNotEqual(staff_client.get('/secretary/dashboard').status_code, 200)
        form['email'] = 'secretary@contract.local'
        second = admin_client.post(f'/tech/edit/{staff_id}', data=form)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(self.backend.get('prontoar:mfa:account-epoch:' + str(staff_id)), '2')

        _, attempted, _ = self._start(staff_client, email='secretary@contract.local')
        self.assertIn('/auth/otp', attempted.headers['Location'])

    def test_revocation_epoch_prevents_email_role_roundtrip_reuse(self):
        client, _, _ = self._start()
        self._complete(client, remember=True)
        token = client.get_cookie(TRUST_COOKIE_NAME, path='/auth').value
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            uid = user.id
            user.email = 'other@contract.local'
            user.permission_level = 'user'
            db.session.commit()
            revoke_all_trusted_devices(uid)
            user.email = 'admin@contract.local'
            user.permission_level = 'admin'
            db.session.commit()
            self.assertFalse(validate_trusted_device(user, token))

        self.assertEqual(self.backend.get('prontoar:mfa:account-epoch:' + str(uid)), '1')
        client.get('/auth/login')
        _, rejected_reuse, _ = self._start(client)
        self.assertIn('/auth/otp', rejected_reuse.headers['Location'])

    def test_pending_otp_is_invalidated_by_email_update(self):
        client, _, _ = self._start()
        code = self.sent[-1][1]
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            user.email = 'new-mail@contract.local'
            db.session.commit()
        redirected = client.get('/auth/otp')
        self.assertIn('/auth/login', redirected.headers['Location'])
        csrf = self._token(client.get('/auth/login'))
        replay = client.post('/auth/otp', data={
            'csrf_token': csrf, 'otp_code': code,
        })
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        self.assertEqual(replay.status_code, 302)

    def test_password_email_and_role_changes_revoke_trust(self):
        client, _, _ = self._start()
        self._complete(client, remember=True)
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            user.email = 'alterado@contract.local'
            db.session.commit()
        client.get('/auth/trusted-devices')  # Existing JWT still works; trust must not.
        token = self._token(client.get('/auth/login'))
        changed = client.post('/auth/login', data={
            'email': 'alterado@contract.local',
            'password': 'Teste12345', 'csrf_token': token,
        })
        self.assertIn('/auth/otp', changed.headers['Location'])

    def test_first_login_password_change_requires_otp_before_reset(self):
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            user.must_change_password = True
            db.session.commit()
        client, response, _ = self._start()
        self.assertIn('/auth/otp', response.headers['Location'])
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        validated, _ = self._complete(client, remember=True)
        self.assertIn('/auth/reset-password/', validated.headers['Location'])
        self.assertNotIn(TRUST_COOKIE_NAME + '=', ''.join(validated.headers.getlist('Set-Cookie')))

    def test_smtp_and_redis_failure_fail_closed(self):
        self.sender.stop()
        with patch('app.routes.auth.send_dynamic_email', return_value=(False, 'SMTP failure')):
            client, failed, _ = self._start()
            self.assertEqual(failed.status_code, 302)
            self.assertIn('/auth/login', failed.headers['Location'])
            self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        self.backend.hashes.clear()
        with patch.object(self.backend, 'pipeline', side_effect=RedisError('down')):
            client, failed, _ = self._start()
            self.assertEqual(failed.status_code, 302)
            self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
        self.sender.start()
