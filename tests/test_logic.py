import pytest
import base64
import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
import os
import io
from PIL import Image
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app import create_app
from app import db
from app.config import Config
from app.models.config import AppConfig
from app.models.license import License
from app.models.user import User
from app.utils.images import save_and_resize_image
from app.utils.license import activate_license_key, decode_license_key, get_instance_fingerprint, get_license_record, issue_license_key

class MockFile:
    def __init__(self, filename, content):
        self.filename = filename
        self.content = content
        self.stream = io.BytesIO(content)
        self.closed = False
    
    def save(self, path):
        with open(path, 'wb') as f:
            f.write(self.content)
    
    def read(self, *args, **kwargs):
        return self.stream.read(*args, **kwargs)

    def seek(self, *args, **kwargs):
        return self.stream.seek(*args, **kwargs)

def test_maintenance_date_calculation():
    now = datetime(2026, 1, 1)
    interval = 6
    next_date = now + relativedelta(months=interval)
    assert next_date == datetime(2026, 7, 1)

def test_image_resizing_utility(tmp_path, monkeypatch):
    # Mocking dummy large image
    img = Image.new('RGB', (2000, 1500), color='red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='JPEG')
    img_content = img_byte_arr.getvalue()
    
    mock_file = MockFile("test.jpg", img_content)
    
    # Mock current_app
    static_folder = tmp_path / "static"
    static_folder.mkdir()
    
    class MockApp:
        pass
    
    mock_app = MockApp()
    mock_app.static_folder = str(static_folder)
    monkeypatch.setattr("app.utils.images.current_app", mock_app)
    
    # Run the save_and_resize utility
    saved_url = save_and_resize_image(mock_file, "uploads")
    expected_file = static_folder / saved_url
    
    # Validating
    assert expected_file.exists()
    
    saved_img = Image.open(expected_file)
    assert saved_img.width == 1024
    assert saved_img.height == 768
    assert os.path.getsize(expected_file) > 0


def test_license_key_roundtrip():
    original_legacy_setting = Config.LICENSE_ALLOW_LEGACY_TOKENS
    Config.LICENSE_ALLOW_LEGACY_TOKENS = True
    app = create_app()

    with app.app_context():
        payload = {
            'company_name': 'Pronto Ar Refrigeração',
            'status': 'active',
            'issued_at': datetime(2026, 4, 8, 10, 0, 0).isoformat(),
            'expires_at': datetime(2027, 4, 8, 10, 0, 0).isoformat(),
            'max_users': 10,
            'max_admin_users': 2,
            'max_secretary_users': 2,
            'instance_fingerprint': get_instance_fingerprint(),
        }

        token = issue_license_key(payload)
        decoded = decode_license_key(token)

        assert decoded['company_name'] == payload['company_name']
        assert decoded['expires_at'] == payload['expires_at']
        assert decoded['instance_fingerprint'] == payload['instance_fingerprint']

    Config.LICENSE_ALLOW_LEGACY_TOKENS = original_legacy_setting


def test_public_key_perpetual_license_validation(monkeypatch, tmp_path):
    public_key = tmp_path / 'ed25519_public.pem'
    installation_id_path = tmp_path / 'installation_id.txt'

    monkeypatch.setattr(Config, 'LICENSE_PUBLIC_KEY_PATH', str(public_key), raising=False)
    monkeypatch.setattr(Config, 'LICENSE_INSTALLATION_ID_PATH', str(installation_id_path), raising=False)
    monkeypatch.setattr(Config, 'LICENSE_ALLOW_LEGACY_TOKENS', False, raising=False)

    private_key = Ed25519PrivateKey.generate()
    public_key.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    app = create_app()

    with app.app_context():
        installation_id = get_instance_fingerprint()
        payload = {
            'license_id': 'lic_public_demo',
            'company_name': 'Pronto Ar Refrigeração',
            'instance_fingerprint': installation_id,
            'license_type': 'perpetual',
            'status': 'active',
            'issued_at': datetime(2026, 4, 8, 10, 0, 0).isoformat(),
            'expires_at': None,
            'max_users': 10,
            'max_admin_users': 2,
            'max_secretary_users': 2,
            'features': ['reports'],
            'metadata': {},
        }

        message = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
        signature = private_key.sign(message)
        token = (
            base64.urlsafe_b64encode(message).rstrip(b'=').decode('ascii')
            + '.' +
            base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')
        )
        decoded = decode_license_key(token)

        assert decoded['license_type'] == 'perpetual'
        assert decoded['instance_fingerprint'] == installation_id


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

    assert 'Funcionário atualizado com sucesso!' in edit_response.get_data(as_text=True)

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

        license_payload = {
            'company_name': 'Pronto Ar Refrigeração',
            'status': 'active',
            'license_type': 'perpetual',
            'issued_at': datetime(2026, 4, 15, 12, 0, 0).isoformat(),
            'expires_at': None,
            'max_users': 10,
            'max_admin_users': 2,
            'max_secretary_users': 2,
            'instance_fingerprint': get_instance_fingerprint(),
        }
        token = issue_license_key(license_payload)

        state = activate_license_key(token, explicit_user_id=admin.id)
        license_record = get_license_record(create=False)

        assert state['valid'] is False
        assert state['validation_error_code'] == 'public_key_not_configured'
        assert license_record is not None
        assert license_record.license_key == token


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
        db.session.add(AppConfig(company_name='Pronto Ar Refrigeração'))

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
        admin.set_password('prontoar123')
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    client = app.test_client()

    login_response = client.post(
        '/auth/login',
        data={'email': 'admin@prontoar.com', 'password': 'prontoar123'},
        headers={'Referer': 'http://localhost/auth/login'},
        follow_redirects=False,
    )

    assert login_response.status_code == 302
    assert '/auth/reset-password/' in login_response.headers['Location']

    token = login_response.headers['Location'].rsplit('/', 1)[-1]

    reset_response = client.post(
        f'/auth/reset-password/{token}',
        data={'password': 'NovaSenha123', 'confirm_password': 'NovaSenha123'},
        headers={'Referer': f'http://localhost/auth/reset-password/{token}'},
        follow_redirects=False,
    )

    assert reset_response.status_code == 302
    assert '/admin/dashboard' in reset_response.headers['Location']

    with app.app_context():
        updated_admin = db.session.get(User, admin_id)
        assert updated_admin.must_change_password is False
        assert updated_admin.check_password('NovaSenha123')