import os


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default

    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def normalize_database_url(url):
    if not url:
        return url

    if url.startswith('postgres://'):
        return f"postgresql+psycopg://{url[len('postgres://') :]}"

    if url.startswith('postgresql://') and '+psycopg' not in url:
        return f"postgresql+psycopg://{url[len('postgresql://') :]}"

    return url


class Config:
    # Use environment variables for secrets, fallback to secure random string for dev
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.environ.get('DATABASE_URL') or 'sqlite:///pronto_ar.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLITE_BUSY_TIMEOUT_MS = int(os.environ.get('SQLITE_BUSY_TIMEOUT_MS', '30000'))
    DATABASE_SSLMODE = os.environ.get('DATABASE_SSLMODE') or None
    DATABASE_POOL_RECYCLE_SECONDS = int(os.environ.get('DATABASE_POOL_RECYCLE_SECONDS', '1800'))
    UPLOAD_ROOT = os.environ.get('UPLOAD_ROOT', 'uploads')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', str(8 * 1024 * 1024)))
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'http')
    SERVER_NAME = os.environ.get('SERVER_NAME') or None
    TRUSTED_HOSTS = [host.strip() for host in os.environ.get('TRUSTED_HOSTS', '').split(',') if host.strip()] or None

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or os.urandom(32).hex()
    LICENSE_SIGNING_SECRET = os.environ.get('LICENSE_SIGNING_SECRET') or SECRET_KEY
    LICENSE_PUBLIC_KEY_PATH = os.environ.get('LICENSE_PUBLIC_KEY_PATH', os.path.join('license_api', 'keys', 'ed25519_public.pem'))
    LICENSE_PUBLIC_KEY_PEM = os.environ.get('LICENSE_PUBLIC_KEY_PEM') or None
    LICENSE_WARNING_DAYS = int(os.environ.get('LICENSE_WARNING_DAYS', '15'))
    LICENSE_GRACE_DAYS = int(os.environ.get('LICENSE_GRACE_DAYS', '7'))
    LICENSE_INSTANCE_ID = os.environ.get('LICENSE_INSTANCE_ID') or None
    LICENSE_INSTALLATION_ID_PATH = os.environ.get('LICENSE_INSTALLATION_ID_PATH', os.path.join('instance', 'installation_id.txt'))
    LICENSE_ALLOW_LEGACY_TOKENS = env_bool('LICENSE_ALLOW_LEGACY_TOKENS', False)
    JWT_ACCESS_TOKEN_EXPIRES = 1800 # 30 minutos
    JWT_TOKEN_LOCATION = ['cookies']
    JWT_COOKIE_SECURE = env_bool('JWT_COOKIE_SECURE', False)
    JWT_COOKIE_SAMESITE = os.environ.get('JWT_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', False)
    SESSION_COOKIE_HTTPONLY = env_bool('SESSION_COOKIE_HTTPONLY', True)
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    WTF_CSRF_SSL_STRICT = env_bool('WTF_CSRF_SSL_STRICT', False)
    PROXY_FIX_ENABLED = env_bool('PROXY_FIX_ENABLED', False)
    PROXY_FIX_X_FOR = int(os.environ.get('PROXY_FIX_X_FOR', '1'))
    PROXY_FIX_X_PROTO = int(os.environ.get('PROXY_FIX_X_PROTO', '1'))
    PROXY_FIX_X_HOST = int(os.environ.get('PROXY_FIX_X_HOST', '1'))
    PROXY_FIX_X_PORT = int(os.environ.get('PROXY_FIX_X_PORT', '1'))
    PROXY_FIX_X_PREFIX = int(os.environ.get('PROXY_FIX_X_PREFIX', '0'))

    # Disable JWT's built-in CSRF to prevent conflict with Flask-WTF
    JWT_COOKIE_CSRF_PROTECT = False
    JWT_CSRF_CHECK_FORM = False 
