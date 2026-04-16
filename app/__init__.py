import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_bcrypt import Bcrypt
from app.config import Config

# Resolve the project root (two levels up from this file: app/__init__.py -> app/ -> project root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import RequestEntityTooLarge
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.utils.security import build_password_version, build_user_agent_fingerprint, is_same_origin_request


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
bcrypt = Bcrypt()
limiter = Limiter(key_func=get_remote_address, default_limits=[])


def _resolve_logo_path(config):
    fallback_logo = '/static/img/logo.jpg'
    if not config:
        return fallback_logo

    logo_path = getattr(config, 'logo_path', None)
    if not logo_path:
        return fallback_logo

    if logo_path.startswith('http://') or logo_path.startswith('https://'):
        return logo_path

    if not logo_path.startswith('/static/'):
        return fallback_logo

    static_relative = logo_path.replace('/static/', '', 1)
    candidate = os.path.join(_PROJECT_ROOT, 'static', static_relative)
    if not os.path.exists(candidate):
        return fallback_logo

    return logo_path

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()




def create_app(config_class=Config):
    app = Flask(__name__, static_folder=os.path.join(_PROJECT_ROOT, 'static'))
    app.config.from_object(config_class)

    if not os.path.isabs(app.config['UPLOAD_ROOT']):
        app.config['UPLOAD_ROOT'] = os.path.join(_PROJECT_ROOT, app.config['UPLOAD_ROOT'])

    if app.config.get('LICENSE_PRIVATE_KEY_PATH') and not os.path.isabs(app.config['LICENSE_PRIVATE_KEY_PATH']):
        app.config['LICENSE_PRIVATE_KEY_PATH'] = os.path.join(_PROJECT_ROOT, app.config['LICENSE_PRIVATE_KEY_PATH'])

    if app.config.get('LICENSE_PUBLIC_KEY_PATH') and not os.path.isabs(app.config['LICENSE_PUBLIC_KEY_PATH']):
        app.config['LICENSE_PUBLIC_KEY_PATH'] = os.path.join(_PROJECT_ROOT, app.config['LICENSE_PUBLIC_KEY_PATH'])

    if not os.path.isabs(app.config['LICENSE_INSTALLATION_ID_PATH']):
        app.config['LICENSE_INSTALLATION_ID_PATH'] = os.path.join(_PROJECT_ROOT, app.config['LICENSE_INSTALLATION_ID_PATH'])

    os.makedirs(app.config['UPLOAD_ROOT'], exist_ok=True)
    os.makedirs(os.path.dirname(app.config['LICENSE_INSTALLATION_ID_PATH']), exist_ok=True)

    if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:'):
        engine_options = app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
        connect_args = engine_options.setdefault('connect_args', {})
        connect_args.setdefault('timeout', app.config['SQLITE_BUSY_TIMEOUT_MS'] / 1000)
    elif app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgresql'):
        engine_options = app.config.setdefault('SQLALCHEMY_ENGINE_OPTIONS', {})
        engine_options.setdefault('pool_pre_ping', True)
        engine_options.setdefault('pool_recycle', app.config['DATABASE_POOL_RECYCLE_SECONDS'])

        if app.config.get('DATABASE_SSLMODE'):
            connect_args = engine_options.setdefault('connect_args', {})
            connect_args.setdefault('sslmode', app.config['DATABASE_SSLMODE'])

    app.config.setdefault('RATELIMIT_STORAGE_URI', app.config.get('RATELIMIT_STORAGE_URI', 'memory://'))

    if app.config.get('PROXY_FIX_ENABLED'):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=app.config.get('PROXY_FIX_X_FOR', 1),
            x_proto=app.config.get('PROXY_FIX_X_PROTO', 1),
            x_host=app.config.get('PROXY_FIX_X_HOST', 1),
            x_port=app.config.get('PROXY_FIX_X_PORT', 1),
            x_prefix=app.config.get('PROXY_FIX_X_PREFIX', 0),
        )

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)
    limiter.init_app(app)

    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect()
    csrf.init_app(app)
    from flask import flash, g, make_response, redirect, request, session, url_for
    from flask_jwt_extended import get_jwt, get_jwt_identity, unset_jwt_cookies, verify_jwt_in_request

    def clear_auth_and_redirect(message, category='danger', endpoint='auth.login'):
        session.pop('jwt_session_nonce', None)
        flash(message, category)
        response = make_response(redirect(url_for(endpoint)))
        unset_jwt_cookies(response)
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(error):
        flash("Arquivo muito grande. O limite do upload foi excedido.", "danger")
        return redirect(request.referrer or url_for("main.index"))

    @app.before_request
    def enforce_same_origin_for_mutations():
        if not app.config.get('SECURITY_ENFORCE_SAME_ORIGIN_MUTATIONS', False):
            return None

        endpoint = request.endpoint or ''
        if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            return None

        if endpoint == 'static' or request.path.startswith('/static/'):
            return None

        if is_same_origin_request(
            request.headers.get('Origin'),
            request.headers.get('Referer'),
            request.host_url,
        ):
            return None

        app.logger.warning('Blocked cross-origin mutable request to %s from origin=%s referer=%s', request.path, request.headers.get('Origin'), request.headers.get('Referer'))
        return clear_auth_and_redirect('Requisição bloqueada por política de segurança da aplicação.', 'danger')

    @app.before_request
    def enforce_authenticated_request_context():
        endpoint = request.endpoint or ''
        if endpoint == 'static' or request.path.startswith('/static/'):
            return None

        g.current_user = None

        try:
            verify_jwt_in_request(optional=True)
        except Exception:
            return None

        current_user_id = get_jwt_identity()
        if not current_user_id:
            return None

        from app.models.user import User

        jwt_claims = get_jwt()
        current_user = User.query.get(current_user_id)

        if not current_user or not current_user.is_active:
            return clear_auth_and_redirect('Sua sessão não é mais válida. Faça login novamente.', 'warning')

        expected_password_version = build_password_version(current_user.password_hash)
        check_session_nonce = app.config.get('SECURITY_BIND_JWT_SESSION_NONCE', False)
        check_user_agent = app.config.get('SECURITY_BIND_JWT_USER_AGENT', False)

        expected_user_agent = build_user_agent_fingerprint(request.headers.get('User-Agent')) if check_user_agent else None
        session_nonce = session.get('jwt_session_nonce') if check_session_nonce else None

        token_is_valid = all([
            str(jwt_claims.get('uid')) == str(current_user.id),
            jwt_claims.get('permission_level') == current_user.permission_level,
            jwt_claims.get('pwdv') == expected_password_version,
        ])

        if check_session_nonce:
            token_is_valid = token_is_valid and jwt_claims.get('session_nonce') == session_nonce

        if check_user_agent:
            token_is_valid = token_is_valid and jwt_claims.get('ua_hash') == expected_user_agent

        if not token_is_valid:
            app.logger.warning('Blocked request with mismatched JWT context for user_id=%s path=%s', current_user.id, request.path)
            return clear_auth_and_redirect('Sua sessão falhou na validação de segurança. Faça login novamente.', 'danger')

        g.current_user = current_user

    @app.before_request
    def enforce_license_status():
        endpoint = request.endpoint or ''
        if endpoint == 'static' or request.path.startswith('/static/'):
            return None

        from app.utils.license import evaluate_license, get_license_features, get_license_record, has_license_feature

        g.license_state = evaluate_license(get_license_record(create=True))
        current_user = getattr(g, 'current_user', None)

        if g.license_state['status'] in {'expiring', 'expired', 'invalid'}:
            last_notice_key = session.get('license_notice_key')
            if last_notice_key != g.license_state['notice_key']:
                flash(g.license_state['message'], g.license_state['flash_category'])
                session['license_notice_key'] = g.license_state['notice_key']

        if not g.license_state['blocking']:
            return None

        allowed_endpoints = {
            'auth.login',
            'auth.logout',
            'auth.forgot_password',
            'auth.reset_password',
            'main.index',
            'admin.dashboard',
            'admin.settings',
            'admin.activate_license',
            'admin.validate_license',
        }

        if endpoint in allowed_endpoints:
            return None

        if current_user and current_user.permission_level == 'admin':
            flash('A licença atual bloqueou a operação normal. Use Configurações para renovar ou revalidar a chave.', 'danger')
            return redirect(url_for('admin.settings'))

        if current_user:
            return clear_auth_and_redirect('A operação está bloqueada por licença expirada ou inválida. Contate o administrador.', 'danger')

        return None

    # Handle JWT errors globally
    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        # When no JWT is present
        flash("Por favor, faça login para acessar esta página.", "danger")
        return redirect(url_for("auth.login"))

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        # When JWT has expired
        return clear_auth_and_redirect("Sua sessão expirou. Por favor, faça login novamente.", "warning")

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        # When JWT is invalid
        return clear_auth_and_redirect("Sessão inválida. Por favor, faça login novamente.", "danger")

    # Context processors for all templates
    @app.context_processor
    def inject_globals():
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        from app.models.user import User
        from flask import g
        from app.utils.notifications import get_alerts
        from app.utils.images import get_workorder_photo_url
        from app.utils.license import evaluate_license, get_license_features, get_license_record, has_license_feature

        # Cache current user in g to avoid multiple DB lookups per request
        if 'current_user' not in g:
            g.current_user = None
            try:
                verify_jwt_in_request(optional=True)
                identity = get_jwt_identity()
                if identity:
                    g.current_user = User.query.get(identity)
            except Exception:
                pass

        # Cache config in g
        if 'app_config' not in g:
            from app.models.config import AppConfig
            try:
                config = AppConfig.query.first()
                if not config:
                    config = AppConfig()
                config.logo_path = _resolve_logo_path(config)
                g.app_config = config
            except Exception:
                g.app_config = None

        # Cache alerts in g
        if 'alerts' not in g:
            try:
                g.alerts = get_alerts(g.current_user) if g.current_user else None
            except Exception:
                g.alerts = None

        if 'license_state' not in g:
            try:
                g.license_state = evaluate_license(get_license_record(create=True))
            except Exception:
                g.license_state = None

        return {
            'app_config': g.app_config,
            'current_user': g.current_user,
            'alerts': g.alerts,
            'license_state': g.license_state,
            'license_features': get_license_features(g.license_state) if g.license_state else set(),
            'has_license_feature': lambda feature_name: has_license_feature(feature_name, g.license_state) if g.license_state else False,
            'workorder_photo_url': get_workorder_photo_url,
        }

    # Import models here so Alembic can discover them
    from app import models

    # Register audit log CLI commands
    from app.utils.audit_cli import register_commands
    register_commands(app)

    # Initialize automatic audit log cleanup on app start
    with app.app_context():
        try:
            from app.models.audit_log import AuditLog
            # Clean up old logs on startup (optional, can be done via CLI)
            # AuditLog.cleanup_old_logs(days=7)
        except Exception:
            pass

    # Register blueprints (to be created next)
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.secretary import secretary_bp
    from app.routes.technician import tech_bp
    from app.routes.clients import clients_bp
    from app.routes.equipment import equip_bp
    from app.routes.services import services_bp
    from app.routes.maintenance import maint_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(secretary_bp, url_prefix='/secretary')
    app.register_blueprint(tech_bp, url_prefix='/tech')
    app.register_blueprint(clients_bp, url_prefix='/clients')
    app.register_blueprint(equip_bp, url_prefix='/equipment')
    app.register_blueprint(services_bp, url_prefix='/services')
    app.register_blueprint(maint_bp, url_prefix='/maintenance')
    app.register_blueprint(reports_bp, url_prefix='/reports')

    return app
