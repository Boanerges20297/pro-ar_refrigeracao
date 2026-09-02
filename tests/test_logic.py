import os
from datetime import datetime, timedelta

import pytest

from app import create_app, db
from app.config import Config
from app.models.config import AppConfig
from app.models.license import License
from app.models.user import User
from app.utils.license import get_instance_fingerprint, issue_license_key
from app.utils.security import is_password_strong


def test_password_strength_rules():
    assert is_password_strong('Admin1234') is True
    assert is_password_strong('short1A') is False
    assert is_password_strong('alllowercase123') is False
    assert is_password_strong('ALLUPPERCASE123') is False
    assert is_password_strong('NoNumbersHere') is False


def test_admin_forced_to_change_password_on_first_login(tmp_path):
    database_path = tmp_path / 'app.db'
    upload_root = tmp_path / 'uploads'
    installation_id_path = tmp_path / 'instance' / 'installation_id.txt'
    public_key_path = tmp_path / 'keys' / 'ed25519_public.pem'

    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database_path.as_posix()}"
        RATELIMIT_ENABLED = False
        LICENSE_ALLOW_LEGACY_TOKENS = True
        UPLOAD_ROOT = str(upload_root)
        LICENSE_INSTALLATION_ID_PATH = str(installation_id_path)
        LICENSE_PUBLIC_KEY_PATH = str(public_key_path)

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        app_config = AppConfig(company_name='Pronto Ar Refrigeração')
        db.session.add(app_config)

        installation_id = get_instance_fingerprint()
        license_payload = {
            'company_name': 'Pronto Ar Refrigeração',
            'status': 'active',
            'license_type': 'perpetual',
            'issued_at': datetime(2026, 4, 15, 12, 0, 0).isoformat(),
            'expires_at': None,
            'max_users': 10,
            'max_admin_users': 2,
            'max_secretary_users': 2,
            'instance_fingerprint': installation_id,
        }
        license_record = License(
            license_key=issue_license_key(license_payload),
            status='active',
            company_name='Pronto Ar Refrigeração',
            instance_fingerprint=installation_id,
            max_users=10,
            max_admin_users=2,
            max_secretary_users=2,
        )
        db.session.add(license_record)

        admin = User(
            name='Administrador',
            email='admin@prontoar.com',
            role='admin',
            permission_level='admin',
            job_title='Administrador',
            is_active=True,
            must_change_password=True,
        )
        admin.set_password('Admin1234')
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()
    login_response = client.post(
        '/auth/login',
        data={'email': 'admin@prontoar.com', 'password': 'Admin1234'},
        headers={'Referer': 'http://localhost/auth/login'},
        follow_redirects=False,
    )

    assert login_response.status_code == 302
    assert '/auth/change-password' in login_response.headers['Location']


def test_admin_can_edit_own_email_and_login_with_new_email(tmp_path):
    database_path = tmp_path / 'app.db'
    upload_root = tmp_path / 'uploads'
    installation_id_path = tmp_path / 'instance' / 'installation_id.txt'
    public_key_path = tmp_path / 'keys' / 'ed25519_public.pem'

    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database_path.as_posix()}"
        RATELIMIT_ENABLED = False
        LICENSE_ALLOW_LEGACY_TOKENS = True
        UPLOAD_ROOT = str(upload_root)
        LICENSE_INSTALLATION_ID_PATH = str(installation_id_path)
        LICENSE_PUBLIC_KEY_PATH = str(public_key_path)

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        app_config = AppConfig(company_name='Pronto Ar Refrigeração')
        db.session.add(app_config)

        installation_id = get_instance_fingerprint()
        license_payload = {
            'company_name': 'Pronto Ar Refrigeração',
            'status': 'active',
            'license_type': 'perpetual',
            'issued_at': datetime(2026, 4, 15, 12, 0, 0).isoformat(),
            'expires_at': None,
            'max_users': 10,
            'max_admin_users': 2,
            'max_secretary_users': 2,
            'instance_fingerprint': installation_id,
        }
        license_record = License(
            license_key=issue_license_key(license_payload),
            status='active',
            company_name='Pronto Ar Refrigeração',
            instance_fingerprint=installation_id,
            max_users=10,
            max_admin_users=2,
            max_secretary_users=2,
        )
        db.session.add(license_record)

        admin = User(
            name='Administrador',
            email='admin@prontoar.com',
            role='admin',
            permission_level='admin',
            job_title='Administrador',
            is_active=True,
        )
        admin.set_password('Admin1234')
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    client = app.test_client()

    login_response = client.post(
        '/auth/login',
        data={'email': 'admin@prontoar.com', 'password': 'Admin1234'},
        headers={'Referer': 'http://localhost/auth/login'},
        follow_redirects=False,
    )

    assert login_response.status_code == 302

    edit_response = client.post(
        f'/tech/edit/{admin_id}',
        data={
            'name': 'Administrador',
            'email': 'novo.admin@prontoar.com',
            'password': '',
            'permission_level': 'admin',
            'job_title': 'Administrador',
            'specialty': '',
            'is_active': 'on',
        },
        headers={'Referer': f'http://localhost/tech/edit/{admin_id}'},
        follow_redirects=True,
    )

    assert 'Usuário atualizado com sucesso!' in edit_response.get_data(as_text=True)

    with app.app_context():
        updated_admin = db.session.get(User, admin_id)
        assert updated_admin.email == 'novo.admin@prontoar.com'

    client.post(
        '/auth/logout',
        headers={'Referer': 'http://localhost/'},
        follow_redirects=False,
    )

    old_login_response = client.post(
        '/auth/login',
        data={'email': 'admin@prontoar.com', 'password': 'Admin1234'},
        headers={'Referer': 'http://localhost/auth/login'},
        follow_redirects=True,
    )

    assert 'Email ou senha inválidos.' in old_login_response.get_data(as_text=True)

    new_login_response = client.post(
        '/auth/login',
        data={'email': 'novo.admin@prontoar.com', 'password': 'Admin1234'},
        headers={'Referer': 'http://localhost/auth/login'},
        follow_redirects=False,
    )

    assert new_login_response.status_code == 302

    staff_list_response = client.get('/tech/list')
    assert staff_list_response.status_code == 200
    assert 'novo.admin@prontoar.com' in staff_list_response.get_data(as_text=True)


def test_license_key_persists_when_public_key_is_missing(monkeypatch, tmp_path):
    database_path = tmp_path / 'app.db'

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{database_path.as_posix()}"
        LICENSE_PUBLIC_KEY_PATH = str(tmp_path / 'missing_public.pem')
        LICENSE_ALLOW_LEGACY_TOKENS = False
        LICENSE_INSTALLATION_ID_PATH = str(tmp_path / 'instance' / 'installation_id.txt')

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        db.session.add(AppConfig(company_name='Pronto Ar Refrigeração'))
        db.session.commit()

        monkeypatch.setattr('app.utils.license.verify_license_key', lambda *_args, **_kwargs: (False, None, 'Chave pública indisponível'))

        license_record = License(
            license_key='legacy-license-key',
            status='active',
            company_name='Pronto Ar Refrigeração',
            instance_fingerprint=get_instance_fingerprint(),
        )
        db.session.add(license_record)
        db.session.commit()

        assert license_record.license_key == 'legacy-license-key'
