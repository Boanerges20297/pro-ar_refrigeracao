import hashlib
import re
import secrets
from urllib.parse import urlparse


PASSWORD_POLICY_MESSAGE = 'A senha deve ter no mínimo 8 caracteres, incluindo letras e números.'
PASSWORD_POLICY_REGEX = re.compile(r'^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,}$')


def is_password_strong(password):
    if not password:
        return False

    return bool(PASSWORD_POLICY_REGEX.match(password))


def build_session_nonce():
    return secrets.token_urlsafe(32)


def build_user_agent_fingerprint(user_agent):
    normalized_user_agent = (user_agent or '').strip()[:512]
    return hashlib.sha256(normalized_user_agent.encode('utf-8')).hexdigest()


def build_password_version(password_hash):
    normalized_password_hash = (password_hash or '').strip()
    return hashlib.sha256(normalized_password_hash.encode('utf-8')).hexdigest()


def is_same_origin_request(origin, referer, host_url):
    expected = urlparse(host_url)
    expected_origin = (expected.scheme, expected.netloc)

    for candidate in (origin, referer):
        if not candidate:
            continue

        parsed_candidate = urlparse(candidate)
        if parsed_candidate.scheme and parsed_candidate.netloc:
            return (parsed_candidate.scheme, parsed_candidate.netloc) == expected_origin

    return False