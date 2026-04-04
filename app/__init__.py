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


db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
bcrypt = Bcrypt()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()




def create_app(config_class=Config):
    app = Flask(__name__, static_folder=os.path.join(_PROJECT_ROOT, 'static'))
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    bcrypt.init_app(app)

    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect()
    csrf.init_app(app)

    # Handle JWT errors globally
    from flask import redirect, url_for, flash
    from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

    @jwt.unauthorized_loader
    def unauthorized_callback(callback):
        # When no JWT is present
        flash("Por favor, faça login para acessar esta página.", "danger")
        return redirect(url_for("auth.login"))

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        # When JWT has expired
        flash("Sua sessão expirou. Por favor, faça login novamente.", "warning")
        return redirect(url_for("auth.login"))

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        # When JWT is invalid
        flash("Sessão inválida. Por favor, faça login novamente.", "danger")
        return redirect(url_for("auth.login"))

    # Context processors for all templates
    @app.context_processor
    def inject_globals():
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        from app.models.user import User
        from flask import g

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
                g.app_config = config
            except Exception:
                g.app_config = None

        return {'app_config': g.app_config, 'current_user': g.current_user}

    # Import models here so Alembic can discover them
    from app import models

    # Register blueprints (to be created next)
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.technician import tech_bp
    from app.routes.clients import clients_bp
    from app.routes.equipment import equip_bp
    from app.routes.services import services_bp
    from app.routes.maintenance import maint_bp
    from app.routes.reports import reports_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(tech_bp, url_prefix='/tech')
    app.register_blueprint(clients_bp, url_prefix='/clients')
    app.register_blueprint(equip_bp, url_prefix='/equipment')
    app.register_blueprint(services_bp, url_prefix='/services')
    app.register_blueprint(maint_bp, url_prefix='/maintenance')
    app.register_blueprint(reports_bp, url_prefix='/reports')

    return app
