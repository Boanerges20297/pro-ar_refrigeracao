"""Restrict persisted Web Push destinations to browser push providers.

Browsers generate opaque subscription URLs. Do not accept arbitrary URLs
from authenticated clients: dispatchers make outbound HTTPS requests later.
"""
from urllib.parse import urlsplit


TRUSTED_PUSH_HOSTS = (
    'fcm.googleapis.com',
    'updates.push.services.mozilla.com',
    'updates-push.services.mozaws.net',
    '*.push.apple.com',
    '*.notify.windows.com',
)


def is_trusted_push_endpoint(endpoint):
    if not isinstance(endpoint, str) or not endpoint or len(endpoint) > 4096:
        return False
    if endpoint != endpoint.strip() or any(ord(char) < 32 for char in endpoint):
        return False
    try:
        parsed = urlsplit(endpoint)
        host = parsed.hostname
        if (parsed.scheme != 'https' or not host or parsed.username is not None
                or parsed.password is not None or parsed.port not in (None, 443)
                or not parsed.path or parsed.fragment):
            return False
    except ValueError:
        return False

    host = host.lower()
    return any(
        (host == pattern if not pattern.startswith('*.')
         else host.endswith(pattern[1:]) and host != pattern[2:])
        for pattern in TRUSTED_PUSH_HOSTS
    )
