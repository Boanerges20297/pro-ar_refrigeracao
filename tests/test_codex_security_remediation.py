"""Regression checks for the November 2026 Codex security findings.

These use the isolated ContractCase database and never contact production.
"""
import io
import struct
import zlib
from unittest.mock import patch

from PIL import Image
from werkzeug.datastructures import FileStorage

from app import db
from app.models.finance import FinancialTransaction
from app.models.push_notification import PushSubscription
from app.models.user import User
from app.models.workorder import WorkOrder
from app.models.workorder_expense import WorkOrderExpense
from app.routes.auth import account_rate_limit_key, confirm_reset_token, generate_reset_token
from app.utils.images import save_and_resize_image
from app.utils.push_security import is_trusted_push_endpoint
from contract_support import ContractCase


class CodexSecurityRemediationContracts(ContractCase):
    def _edit_workorder(self, data):
        oid = self.ids['workorder']
        return self.http.post(
            f'/services/edit/{oid}', data=data,
            headers={'Referer': f'http://localhost/services/edit/{oid}'},
        )

    def test_technician_normal_edit_never_zeros_financial_fields(self):
        self.login('user')
        response = self._edit_workorder({
            'status': 'In Progress', 'description': 'Visita realizada',
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            order = db.session.get(WorkOrder, self.ids['workorder'])
            self.assertEqual(order.status, 'In Progress')
            self.assertEqual(order.description, 'Visita realizada')
            self.assertEqual(order.total_value, 100.0)
            self.assertFalse(order.is_paid)

    def test_forged_financial_fields_are_ignored_for_technician_and_secretary(self):
        for level in ('user', 'secretary'):
            with self.subTest(role=level):
                self.login(level)
                response = self._edit_workorder({
                    'status': 'In Progress', 'description': level,
                    'total_value': '99999.99', 'is_paid': 'on',
                })
                self.assertEqual(response.status_code, 302)
                with self.app.app_context():
                    order = db.session.get(WorkOrder, self.ids['workorder'])
                    self.assertEqual(order.total_value, 100.0)
                    self.assertFalse(order.is_paid)
                    revenue = FinancialTransaction.query.filter_by(
                        work_order_id=order.id, is_automated=True,
                        work_order_expense_id=None,
                    ).one()
                    self.assertEqual(revenue.amount, 100.0)
                    self.assertEqual(revenue.status, 'pending')

    def test_admin_still_updates_money_and_rejects_invalid_amount(self):
        self.login('admin')
        for invalid in ('nan', 'inf', '-1', 'garbage'):
            response = self._edit_workorder({
                'status': 'In Progress', 'total_value': invalid,
                'is_paid': 'on',
            })
            self.assertEqual(response.status_code, 302)
            with self.app.app_context():
                order = db.session.get(WorkOrder, self.ids['workorder'])
                self.assertEqual(order.total_value, 100.0)
                self.assertFalse(order.is_paid)
        valid = self._edit_workorder({
            'status': 'In Progress', 'description': 'Aprovado',
            'total_value': '230.50', 'is_paid': 'on',
        })
        self.assertEqual(valid.status_code, 302)
        with self.app.app_context():
            order = db.session.get(WorkOrder, self.ids['workorder'])
            self.assertEqual(order.total_value, 230.5)
            self.assertTrue(order.is_paid)

    def test_expenses_cannot_be_read_or_forged_by_technician_or_secretary(self):
        path = f"/services/edit/{self.ids['workorder']}/expenses"
        for role in ('user', 'secretary'):
            with self.subTest(role=role):
                self.login(role)
                self.assertEqual(self.http.get(path).status_code, 302)
                denied = self.http.post(path + '/add', json={
                    'description': 'Despesa forjada', 'quantity': 1,
                    'unit_price': 99999,
                })
                self.assertEqual(denied.status_code, 302)
                with self.app.app_context():
                    self.assertEqual(WorkOrderExpense.query.count(), 0)
                    self.assertEqual(FinancialTransaction.query.count(), 1)

    def test_admin_expense_validates_numbers_and_syncs_finance(self):
        self.login('admin')
        path = f"/services/edit/{self.ids['workorder']}/expenses/add"
        for amount in ('nan', 'inf', '-1', 'not-a-number'):
            with self.subTest(amount=amount):
                rejected = self.http.post(path, json={
                    'description': 'Valor invalido', 'quantity': 1,
                    'unit_price': amount,
                })
                self.assertEqual(rejected.status_code, 400)
        valid = self.http.post(path, json={
            'description': 'Peca autorizada', 'quantity': 2,
            'unit_price': 25.50,
        })
        self.assertEqual(valid.status_code, 201)
        with self.app.app_context():
            self.assertEqual(WorkOrderExpense.query.count(), 1)
            expense = WorkOrderExpense.query.one()
            self.assertEqual(expense.total, 51.0)
            self.assertEqual(FinancialTransaction.query.filter_by(
                work_order_expense_id=expense.id).count(), 1)

    def test_secretary_add_uses_catalog_price_and_hides_financial_inputs(self):
        self.login('secretary')
        page = self.http.get('/services/add')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'Valor Cobrado (R$', page.data)
        response = self.http.post('/services/add', data={
            'client_id': str(self.ids['client']),
            'service_id': str(self.ids['service']),
            'scheduled_date': '2026-12-15T09:00',
            'total_value': '99999',
        })
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            orders = WorkOrder.query.order_by(WorkOrder.id).all()
            self.assertEqual(len(orders), 2)
            self.assertEqual(orders[-1].total_value, 100.0)

    def test_secretary_cannot_upload_photos_and_technician_can_see_fields(self):
        photo = io.BytesIO()
        Image.new('RGB', (4, 4), (12, 34, 56)).save(photo, 'PNG')
        raw = photo.getvalue()
        oid = self.ids['workorder']
        self.login('secretary')
        page = self.http.get(f'/services/edit/{oid}')
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(b'name="photo_after"', page.data)
        attempt = self.http.post(f'/services/edit/{oid}', data={
            'status': 'In Progress',
            'description': 'Sem permissao',
            'photo_after': (io.BytesIO(raw), 'photo.png'),
        }, content_type='multipart/form-data')
        self.assertEqual(attempt.status_code, 302)
        with self.app.app_context():
            order = db.session.get(WorkOrder, oid)
            self.assertIsNone(order.photo_after)
            self.assertEqual(order.description, None)
        self.login('user')
        page = self.http.get(f'/services/edit/{oid}')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="photo_after"', page.data)

    def test_reset_link_consumed_once_and_no_automatic_login(self):
        with self.app.app_context():
            token = generate_reset_token('admin@contract.local')
        first = self.http.post(f'/auth/reset-password/{token}', data={
            'password': 'NovaSenha987', 'confirm_password': 'NovaSenha987',
        })
        self.assertEqual(first.status_code, 302)
        self.assertIn('/auth/login', first.headers['Location'])
        self.assertFalse(any('access_token_cookie=' in c for c in first.headers.getlist('Set-Cookie')
                             if 'access_token_cookie=;' not in c))
        self.assertNotEqual(self.http.get('/admin/dashboard').status_code, 200)
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            self.assertTrue(user.check_password('NovaSenha987'))
            self.assertFalse(confirm_reset_token(token))
        reused = self.http.post(f'/auth/reset-password/{token}', data={
            'password': 'SegundaSenha987', 'confirm_password': 'SegundaSenha987',
        })
        self.assertEqual(reused.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            self.assertFalse(user.check_password('SegundaSenha987'))

    def test_mandatory_password_change_flow_remains_available(self):
        with self.app.app_context():
            user = User.query.filter_by(email='admin@contract.local').one()
            user.must_change_password = True
            db.session.commit()
        response = self.http.post('/auth/login', data={
            'email': 'admin@contract.local', 'password': 'Teste12345',
        })
        self.assertEqual(response.status_code, 302)
        reset_path = response.headers['Location']
        self.assertIn('/auth/reset-password/', reset_path)
        self.assertEqual(self.http.get(reset_path).status_code, 200)
        changed = self.http.post(reset_path, data={
            'password': 'NovaSenha987', 'confirm_password': 'NovaSenha987',
        })
        self.assertEqual(changed.status_code, 302)
        self.assertNotEqual(self.http.get('/admin/dashboard').status_code, 200)
        login = self.http.post('/auth/login', data={
            'email': 'admin@contract.local', 'password': 'NovaSenha987',
        })
        self.assertEqual(login.status_code, 302)
        self.assertEqual(self.http.get('/admin/dashboard').status_code, 200)

    def test_password_email_origin_ignores_attacker_host(self):
        self.app.config['PUBLIC_BASE_URL'] = 'https://www.prontoar-servicos.com.br'
        with patch('app.routes.auth.send_password_reset_email', return_value=(True, None)) as mail:
            response = self.http.post('/auth/forgot-password', data={
                'email': 'admin@contract.local',
            }, base_url='http://attacker.invalid')
            self.assertEqual(response.status_code, 302)
            mail.assert_called_once()
            reset_url = mail.call_args.args[1]
            self.assertTrue(reset_url.startswith(
                'https://www.prontoar-servicos.com.br/auth/reset-password/'))
            self.assertNotIn('attacker.invalid', reset_url)

    def test_insecure_public_origin_never_sends_email(self):
        self.app.config['PUBLIC_BASE_URL'] = 'http://attacker.invalid'
        with patch('app.routes.auth.send_password_reset_email') as mail:
            response = self.http.post('/auth/forgot-password', data={
                'email': 'admin@contract.local',
            })
            self.assertEqual(response.status_code, 302)
            mail.assert_not_called()

    def test_login_account_limit_key_is_case_insensitive_and_separate(self):
        with self.app.test_request_context('/auth/login', method='POST',
                                           data={'email': 'ADMIN@Contract.Local '}):
            first = account_rate_limit_key()
        with self.app.test_request_context('/auth/login', method='POST',
                                           data={'email': 'admin@contract.local'}):
            second = account_rate_limit_key()
        with self.app.test_request_context('/auth/login', method='POST',
                                           data={'email': 'other@contract.local'}):
            other = account_rate_limit_key()
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertNotIn('admin@', first)

    def test_push_subscribe_rejects_local_network_and_accepts_browser_provider(self):
        self.app.config['VAPID_PUBLIC_KEY'] = 'test-public'
        self.app.config['VAPID_PRIVATE_KEY'] = 'test-private'
        self.login('admin')
        keys = {'p256dh': 'test', 'auth': 'test'}
        for endpoint in (
            'http://127.0.0.1/internal',
            'https://127.0.0.1/internal',
            'https://[::1]/internal',
            'https://169.254.169.254/latest/meta-data/',
            'https://fcm.googleapis.com.attacker.invalid/something',
            'https://fcm.googleapis.com@attacker.invalid/something',
        ):
            with self.subTest(endpoint=endpoint):
                response = self.http.post('/notifications/subscribe',
                    json={'subscription': {'endpoint': endpoint, 'keys': keys}})
                self.assertEqual(response.status_code, 400)
        endpoint = 'https://fcm.googleapis.com/fcm/send/valid-test'
        valid = self.http.post('/notifications/subscribe',
            json={'subscription': {'endpoint': endpoint, 'keys': keys}})
        self.assertEqual(valid.status_code, 200)
        with self.app.app_context():
            self.assertEqual(PushSubscription.query.count(), 1)
        self.assertTrue(is_trusted_push_endpoint('https://web.push.apple.com/Q123'))
        self.assertTrue(is_trusted_push_endpoint(
            'https://updates.push.services.mozilla.com/wpush/v2/abc'))
        self.assertFalse(is_trusted_push_endpoint('https://foo.push.apple.com.attacker.test/Q'))

    def test_image_header_with_too_many_pixels_is_rejected_before_decode(self):
        with self.app.app_context():
            tiny = io.BytesIO()
            Image.new('RGB', (1, 1), (10, 20, 30)).save(tiny, format='PNG')
            data = bytearray(tiny.getvalue())
            data[16:24] = struct.pack('>II', 9000, 9000)
            data[29:33] = struct.pack('>I', zlib.crc32(data[12:29]) & 0xffffffff)
            with self.assertRaises(ValueError):
                save_and_resize_image(
                    FileStorage(stream=io.BytesIO(data), filename='large.png'),
                    'work_orders',
                )
