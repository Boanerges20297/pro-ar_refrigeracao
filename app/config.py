import os

class Config:
    # Use environment variables for secrets, fallback to secure random string for dev
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///pronto_ar.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or os.urandom(32).hex()
    JWT_ACCESS_TOKEN_EXPIRES = 1800 # 30 minutos
    JWT_TOKEN_LOCATION = ['cookies']
    JWT_COOKIE_SECURE = False # Set to True in production with HTTPS

    # Disable JWT's built-in CSRF to prevent conflict with Flask-WTF
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_CHECK_FORM = True 
