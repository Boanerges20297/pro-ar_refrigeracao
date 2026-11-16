"""Email OTP and revocable trusted-device state, shared across Gunicorn workers.

Security properties: no plaintext OTP or device token at rest; Redis TTLs;
atomic OTP consumption; no in-memory fallback when Redis is unavailable.
"""
from datetime import datetime, timezone
from hashlib import sha256
from hmac import new as hmac_new
import re
import secrets
import time

from flask import current_app
from redis import Redis
from redis.exceptions import RedisError

from app.utils.security import build_password_version


class OTPStoreUnavailable(RuntimeError):
    """The shared authentication state is unavailable; fail closed."""


OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
TRUST_SECONDS = 30 * 24 * 60 * 60
TRUST_COOKIE_NAME = 'pa_trusted_device'
TRUST_PREFIX = 'prontoar:mfa:trusted:'
CHALLENGE_PREFIX = 'prontoar:mfa:challenge:'
TRUST_INDEX_PREFIX = 'prontoar:mfa:trusted-user:'
TRUST_EPOCH_PREFIX = 'prontoar:mfa:account-epoch:'
RESEND_PREFIX = 'prontoar:mfa:resend:'

_VERIFY_SCRIPT = """
local key = KEYS[1]
local uid = redis.call('HGET', key, 'uid')
local epoch = redis.call('GET', KEYS[2]) or '0'
if not uid then return -1 end
if uid ~= ARGV[2] or redis.call('HGET', key, 'pwdv') ~= ARGV[3]
   or redis.call('HGET', key, 'role') ~= ARGV[4]
   or redis.call('HGET', key, 'emailv') ~= ARGV[5]
   or redis.call('HGET', key, 'epoch') ~= epoch then
  redis.call('DEL', key)
  return -1
end
local attempts = redis.call('HINCRBY', key, 'attempts', 1)
if attempts > 5 then
  redis.call('DEL', key)
  return -2
end
if redis.call('HGET', key, 'digest') == ARGV[1] then
  redis.call('DEL', key)
  return 1
end
if attempts >= 5 then
  redis.call('DEL', key)
  return -2
end
return 0
"""


_ROTATE_SCRIPT = """
-- Atomic one-time use of a trusted-browser credential: replace it with
-- a new random credential, keeping the original trust expiry.
local old_key, new_key, index, epoch_key = KEYS[1], KEYS[2], KEYS[3], KEYS[4]
local old_digest, new_digest, uid, pwdv, role, emailv, now =
  ARGV[1], ARGV[2], ARGV[3], ARGV[4], ARGV[5], ARGV[6], tonumber(ARGV[7])
if not redis.call('ZSCORE', index, old_digest) then return 0 end
local epoch = redis.call('GET', epoch_key) or '0'
if redis.call('HGET', old_key, 'uid') ~= uid
   or redis.call('HGET', old_key, 'pwdv') ~= pwdv
   or redis.call('HGET', old_key, 'role') ~= role
   or redis.call('HGET', old_key, 'emailv') ~= emailv
   or redis.call('HGET', old_key, 'epoch') ~= epoch
   or tonumber(redis.call('HGET', old_key, 'expires_at') or '0') <= now then
  return 0
end
local ttl = redis.call('TTL', old_key)
if ttl <= 0 then return 0 end
redis.call('HSET', new_key,
  'uid', uid, 'pwdv', pwdv, 'role', role, 'emailv', emailv, 'epoch', epoch,
  'label', redis.call('HGET', old_key, 'label') or 'Navegador',
  'created_at', redis.call('HGET', old_key, 'created_at') or ARGV[7],
  'last_seen_at', ARGV[7],
  'expires_at', redis.call('HGET', old_key, 'expires_at'))
redis.call('EXPIRE', new_key, ttl)
redis.call('DEL', old_key)
redis.call('ZREM', index, old_digest)
redis.call('ZADD', index, now, new_digest)
return ttl
"""


_REVOKE_SCRIPT = """
-- Device revocation competes atomically with single-use cookie rotation.
-- A rotated credential cannot be falsely reported as revoked.
if not redis.call('ZSCORE', KEYS[2], ARGV[1]) then return 0 end
redis.call('DEL', KEYS[1])
redis.call('ZREM', KEYS[2], ARGV[1])
return 1
"""


def _redis():
    injected = current_app.extensions.get('login_otp_store')
    if injected is not None:
        return injected
    url = current_app.config.get('EMAIL_OTP_REDIS_URL') or current_app.config.get('RATELIMIT_STORAGE_URI')
    if not url or not url.startswith(('redis://', 'rediss://')):
        raise OTPStoreUnavailable('O OTP exige Redis compartilhado.')
    client = current_app.extensions.get('login_otp_redis')
    if client is None:
        client = Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=2,
            socket_timeout=2, health_check_interval=30,
        )
        current_app.extensions['login_otp_redis'] = client
    return client


def _run(action):
    try:
        return action(_redis())
    except (RedisError, OSError) as exc:
        current_app.logger.error('Shared OTP state unavailable: %s', type(exc).__name__)
        raise OTPStoreUnavailable('Serviço de verificação temporariamente indisponível.') from exc


def _signing_key():
    value = current_app.config['SECRET_KEY']
    return value if isinstance(value, bytes) else str(value).encode('utf-8')


def _code_digest(nonce, code):
    return hmac_new(_signing_key(), (nonce + ':' + code).encode('utf-8'), sha256).hexdigest()


def _token_digest(token):
    return sha256(token.encode('ascii')).hexdigest()


def _email_version(email):
    return sha256((email or '').strip().casefold().encode('utf-8')).hexdigest()


def _index_key(user_id):
    return TRUST_INDEX_PREFIX + str(user_id)


def _epoch_key(user_id):
    return TRUST_EPOCH_PREFIX + str(user_id)


def _challenge_key(nonce):
    return CHALLENGE_PREFIX + nonce


def create_challenge(user):
    """Store an OTP for five minutes and return only the nonce and email code."""
    nonce = secrets.token_urlsafe(32)
    code = f'{secrets.randbelow(1000000):06d}'
    key = _challenge_key(nonce)
    mapping = {
        'uid': str(user.id),
        'pwdv': build_password_version(user.password_hash),
        'role': str(user.permission_level),
        'emailv': _email_version(user.email),
        'epoch': str(_run(lambda redis: redis.get(_epoch_key(user.id)) or '0')),
        'digest': _code_digest(nonce, code),
        'attempts': '0',
    }

    def save(redis):
        pipe = redis.pipeline(transaction=True)
        pipe.hset(key, mapping=mapping)
        pipe.expire(key, OTP_TTL_SECONDS)
        pipe.execute()

    _run(save)
    return nonce, code


def delete_challenge(nonce):
    if nonce and re.fullmatch(r'[A-Za-z0-9_-]{30,80}', nonce):
        _run(lambda redis: redis.delete(_challenge_key(nonce)))


def challenge_matches_user(user, nonce):
    if not nonce or not re.fullmatch(r'[A-Za-z0-9_-]{30,80}', nonce):
        return False
    record = _run(lambda redis: redis.hgetall(_challenge_key(nonce)))
    return bool(
        record and record.get('uid') == str(user.id)
        and record.get('pwdv') == build_password_version(user.password_hash)
        and record.get('role') == user.permission_level
        and record.get('emailv') == _email_version(user.email)
        and record.get('epoch') == str(_run(lambda redis: redis.get(_epoch_key(user.id)) or '0'))
    )


def verify_challenge(user, nonce, code):
    """Return success/invalid/locked/expired; consume the code atomically."""
    if not nonce or not re.fullmatch(r'[A-Za-z0-9_-]{30,80}', nonce):
        return 'expired'
    entered = (code or '').strip()
    # Even malformed guesses count toward the five-attempt budget.
    digest = _code_digest(nonce, entered)
    result = _run(lambda redis: redis.eval(
        _VERIFY_SCRIPT, 2, _challenge_key(nonce), _epoch_key(user.id),
        digest, str(user.id),
        build_password_version(user.password_hash), str(user.permission_level),
        _email_version(user.email),
    ))
    return {1: 'success', 0: 'invalid', -2: 'locked'}.get(result, 'expired')


def acquire_resend_cooldown(user_id):
    return bool(_run(lambda redis: redis.set(
        RESEND_PREFIX + str(user_id), '1', ex=60, nx=True,
    )))


def validate_trusted_device(user, token):
    """A cookie is only trusted if its hashed server record still matches."""
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{32,80}', token):
        return False
    digest = _token_digest(token)
    def get_trust(redis):
        # The index is the authoritative membership set; orphaned hashes
        # from concurrent revocations cannot restore a trusted login.
        if redis.zscore(_index_key(user.id), digest) is None:
            return {}
        record = redis.hgetall(TRUST_PREFIX + digest)
        if record.get('epoch') != str(redis.get(_epoch_key(user.id)) or '0'):
            return {}
        return record

    record = _run(get_trust)
    valid = bool(
        record and record.get('uid') == str(user.id)
        and record.get('pwdv') == build_password_version(user.password_hash)
        and record.get('role') == user.permission_level
        and record.get('emailv') == _email_version(user.email)
        and int(record.get('expires_at', '0')) > int(time.time())
    )
    if valid:
        _run(lambda redis: redis.hset(TRUST_PREFIX + digest, 'last_seen_at', str(int(time.time()))))
    return valid


def rotate_trusted_device(user, raw_token):
    """Consume each trusted cookie exactly once and return its replacement.

    Atomic Redis Lua prevents concurrent logins from replaying the same
    cookie; a successful rotation preserves the original 30-day expiry.
    """
    if not raw_token or not re.fullmatch(r'[A-Za-z0-9_-]{32,80}', raw_token):
        return None
    old_digest = _token_digest(raw_token)
    new_raw = secrets.token_urlsafe(32)
    new_digest = _token_digest(new_raw)
    replaced = _run(lambda redis: redis.eval(
        _ROTATE_SCRIPT, 4,
        TRUST_PREFIX + old_digest, TRUST_PREFIX + new_digest,
        _index_key(user.id), _epoch_key(user.id),
        old_digest, new_digest, str(user.id),
        build_password_version(user.password_hash), str(user.permission_level),
        _email_version(user.email), str(int(time.time())),
    ))
    return (new_raw, int(replaced)) if int(replaced) > 0 else None


def issue_trusted_device(user, user_agent):
    """Store only SHA-256(token), with per-user index for revocation."""
    raw = secrets.token_urlsafe(32)
    digest = _token_digest(raw)
    now = int(time.time())
    key = TRUST_PREFIX + digest
    index = _index_key(user.id)
    record = {
        'uid': str(user.id),
        'pwdv': build_password_version(user.password_hash),
        'role': str(user.permission_level),
        'emailv': _email_version(user.email),
        'epoch': str(_run(lambda redis: redis.get(_epoch_key(user.id)) or '0')),
        'label': (user_agent or 'Navegador não identificado')[:180],
        'created_at': str(now),
        'last_seen_at': str(now),
        'expires_at': str(now + TRUST_SECONDS),
    }

    def save(redis):
        pipe = redis.pipeline(transaction=True)
        pipe.hset(key, mapping=record)
        pipe.expire(key, TRUST_SECONDS)
        pipe.zadd(index, {digest: now})
        pipe.expire(index, TRUST_SECONDS + 86400)
        pipe.execute()
        # Limit the number of independently valid device tokens per account.
        old = redis.zrange(index, 0, -6)
        if old:
            cleanup = redis.pipeline(transaction=True)
            for value in old:
                cleanup.delete(TRUST_PREFIX + value)
                cleanup.zrem(index, value)
            cleanup.execute()

    _run(save)
    return raw


def list_trusted_devices(user):
    index = _index_key(user.id)

    def list_records(redis):
        result = []
        for digest in redis.zrange(index, 0, -1):
            record = redis.hgetall(TRUST_PREFIX + digest)
            if (not record or record.get('pwdv') != build_password_version(user.password_hash)
                    or record.get('role') != user.permission_level
                    or record.get('emailv') != _email_version(user.email)
                    or record.get('epoch') != str(redis.get(_epoch_key(user.id)) or '0')):
                continue
            if int(record.get('expires_at', '0')) <= int(time.time()):
                continue
            result.append({
                'id': digest,
                'label': record.get('label', 'Navegador'),
                'created_at': datetime.fromtimestamp(int(record['created_at']), tz=timezone.utc),
                'last_seen_at': datetime.fromtimestamp(int(record['last_seen_at']), tz=timezone.utc),
            })
        return result

    return _run(list_records)


def revoke_trusted_device(user_id, digest):
    if not re.fullmatch(r'[0-9a-f]{64}', digest or ''):
        return False
    index = _index_key(user_id)

    def revoke(redis):
        return redis.eval(
            _REVOKE_SCRIPT, 2, TRUST_PREFIX + digest, index, digest,
        ) == 1

    return _run(revoke)


def revoke_all_trusted_devices(user_id):
    index = _index_key(user_id)

    def revoke(redis):
        digests = redis.zrange(index, 0, -1)
        pipe = redis.pipeline(transaction=True)
        # A monotonic account epoch makes old tokens non-reusable even
        # after profile/email values are later changed back.
        pipe.incr(_epoch_key(user_id))
        for digest in digests:
            pipe.delete(TRUST_PREFIX + digest)
        pipe.delete(index)
        pipe.execute()
        return len(digests)

    return _run(revoke)
