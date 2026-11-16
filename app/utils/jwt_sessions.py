"""Redis-backed JWT session allowlist: logout invalidates bearer tokens server-side.

The JWT remains reusable for authenticated requests during its 30-minute
session. Missing registry entries and Redis outages fail closed when enabled.
"""
import time
from math import ceil

from flask import current_app
from flask_jwt_extended import decode_token
from redis import Redis
from redis.exceptions import RedisError
from app.utils.login_otp import TRUST_EPOCH_PREFIX


PREFIX = 'prontoar:jwt:session:'


class JWTSessionStoreUnavailable(RuntimeError):
    pass


def _redis():
    injected = current_app.extensions.get('jwt_session_store')
    if injected is not None:
        return injected
    url = (current_app.config.get('EMAIL_OTP_REDIS_URL')
           or current_app.config.get('RATELIMIT_STORAGE_URI'))
    if not isinstance(url, str) or not url.startswith(('redis://', 'rediss://')):
        raise JWTSessionStoreUnavailable('JWT exige Redis compartilhado.')
    client = current_app.extensions.get('jwt_session_redis')
    if client is None:
        client = Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=2,
            socket_timeout=2, health_check_interval=30,
        )
        current_app.extensions['jwt_session_redis'] = client
    return client


def _run(action):
    try:
        return action(_redis())
    except (RedisError, OSError) as exc:
        current_app.logger.error('JWT state backend unavailable: %s', type(exc).__name__)
        raise JWTSessionStoreUnavailable('Verificação de sessão indisponível.') from exc


def register_jwt(token, user_id):
    claims = decode_token(token)
    jti = claims['jti']
    identity = str(claims['sub'])
    if identity != str(user_id):
        raise ValueError('JWT identity mismatch.')
    ttl = max(1, ceil(claims['exp'] - time.time()))
    def register(redis):
        epoch = str(redis.get(TRUST_EPOCH_PREFIX + identity) or '0')
        redis.set(PREFIX + jti, identity + ':' + epoch, ex=ttl)

    _run(register)


def is_jwt_revoked(claims):
    jti = claims.get('jti')
    identity = str(claims.get('sub', ''))
    if not jti or not identity:
        return True
    def revoked(redis):
        epoch = str(redis.get(TRUST_EPOCH_PREFIX + identity) or '0')
        return redis.get(PREFIX + jti) != identity + ':' + epoch

    return _run(revoked)


def revoke_jwt(claims):
    jti = claims.get('jti')
    if jti:
        _run(lambda redis: redis.delete(PREFIX + jti))
