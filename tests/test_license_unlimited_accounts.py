"""Acesso ilimitado de clientes/comuns sem liberar equipe técnica além do plano."""
from datetime import datetime

from app import create_app, db
from app.config import Config
from app.models.config import AppConfig
from app.models.license import License
from app.models.user import User
from app.utils.license import (
    check_user_limit,
    get_user_counts,
    get_instance_fingerprint,
    issue_license_key,
)


def _app(tmp_path):
    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'app.db'}"
        UPLOAD_ROOT = str(tmp_path / "uploads")
        LICENSE_PROVIDER = "legacy"
        LICENSE_ALLOW_LEGACY_TOKENS = True
        LICENSE_PUBLIC_KEY_PATH = str(tmp_path / "missing.pem")
        LICENSE_INSTALLATION_ID_PATH = str(tmp_path / "installation.txt")
    return create_app(TestConfig)


def _user(index, permission_level):
    user = User(
        name=f"Usuário {index}",
        email=f"user-{index}@example.test",
        permission_level=permission_level,
        job_title={"admin": "Administrador", "secretary": "Atendente",
                   "user": "Técnico", "common": "Usuário comum",
                   "client": "Cliente"}[permission_level],
        is_active=True,
    )
    user.set_password("Teste12345")
    return user


def test_unlimited_client_and_common_do_not_consume_staff_seats(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        db.create_all()
        db.session.add(AppConfig(company_name="Pronto Ar Refrigeração"))
        fingerprint = get_instance_fingerprint()
        db.session.add(License(license_key=issue_license_key({
            "company_name": "Pronto Ar Refrigeração",
            "status": "active",
            "license_type": "perpetual",
            "issued_at": datetime(2026, 10, 21).isoformat(),
            "instance_fingerprint": fingerprint,
            "max_users": 6,
            "max_admin_users": 2,
            "max_secretary_users": 2,
        })))
        for i, role in enumerate(
            ["admin"] * 2 + ["secretary"] * 2 + ["user"] * 2
            + ["common"] * 20 + ["client"] * 20
        ):
            db.session.add(_user(i, role))
        db.session.commit()

        counts = get_user_counts()
        assert counts["staff_total"] == 6
        assert counts["common"] == 20
        assert counts["client"] == 20
        assert check_user_limit("common") is None
        assert check_user_limit("client") is None
        assert check_user_limit("user") is not None
        assert check_user_limit("admin") is not None
        assert check_user_limit("secretary") is not None


def test_common_account_has_no_technician_or_admin_access(tmp_path):
    app = _app(tmp_path)
    with app.app_context():
        db.create_all()
        db.session.add(AppConfig(company_name="Pronto Ar Refrigeração"))
        db.session.add(License(license_key=issue_license_key({
            "status": "active",
            "license_type": "perpetual",
            "instance_fingerprint": get_instance_fingerprint(),
            "max_users": 6,
            "max_admin_users": 2,
            "max_secretary_users": 2,
        })))
        db.session.add(_user(500, "common"))
        db.session.commit()

    client = app.test_client()
    response = client.post(
        "/auth/login",
        data={"email": "user-500@example.test", "password": "Teste12345"},
        headers={"Referer": "http://localhost/auth/login"},
    )
    assert response.status_code == 302
    assert "/common/dashboard" in response.headers["Location"]
    assert client.get("/common/dashboard").status_code == 200
    assert client.get("/tech/dashboard").status_code == 403
    assert client.get("/admin/dashboard").status_code == 403
    assert client.get("/client/dashboard").status_code == 403
