from app import create_app, db
from app.config import Config
from app.models.user import User
from app.models.config import AppConfig
from app.utils.license import get_user_counts
from app.utils.superadmin import is_superadmin
def make_app(tmp_path):
    class TestConfig(Config):
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'pronto.db'}"
        UPLOAD_ROOT = str(tmp_path / "uploads")
        LICENSE_INSTALLATION_ID_PATH = str(tmp_path / "installation.txt")
        LICENSE_PROVIDER = "bta"
        BTA_LICENSE_BASE_URL = ""
        BTA_LICENSE_CLIENT_ID = ""
        BTA_LICENSE_PRIVATE_KEY_PATH = ""
        BTA_LICENSE_KEY_ID = ""
        BTA_SNAPSHOT_PUBLIC_KEY_PATH = ""
        BTA_SNAPSHOT_CACHE_PATH = str(tmp_path / "snapshot.json")
        BTA_LICENSE_CUSTOMER_KEY = "pronto-ar-refrigeracao"
    return create_app(TestConfig)
def new_user(name, role, permission_level, job_title):
    account = User(
        name=name, email=name.lower().replace(" ", "-")+"@example.test",
        role=role, permission_level=permission_level, job_title=job_title,
        is_active=True,
    )
    account.set_password("SenhaDeTeste2026!")
    return account
def test_superadmin_works_when_bta_invalid_and_seat_exempt(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    with app.app_context():
        db.create_all()
        db.session.add(AppConfig())
        owner = new_user("Owner", "admin", "admin", "Superadmin")
        admin = new_user("Admin", "technician", "admin", "Administrador")
        technical = new_user("Tecnico", "technician", "user", "T├®cnico")
        db.session.add_all([owner, admin, technical])
        db.session.commit()
        assert is_superadmin(owner)
        assert not is_superadmin(admin)
        counts = get_user_counts()
        assert counts["staff_total"] == 2
        assert counts["admin"] == 1
    from app.utils import bta_license
    monkeypatch.setattr(bta_license, "_resolve_remote",
                        lambda: (_ for _ in ()).throw(AssertionError("BTA contacted by superadmin")))
    client = app.test_client()
    response = client.post("/auth/login", data={
        "email": owner.email, "password": "SenhaDeTeste2026!"
    }, follow_redirects=False)
    assert response.status_code == 302
    assert "/admin/dashboard" in response.location
    dashboard = client.get("/admin/dashboard", follow_redirects=False)
    assert dashboard.status_code == 200
    assert client.get("/admin/audit-logs", follow_redirects=False).status_code == 200
    assert client.get("/admin/settings", follow_redirects=False).status_code == 200
def test_fake_superadmin_title_is_not_exempt(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db.create_all()
        forged = new_user("Forged", "technician", "admin", "Superadmin")
        db.session.add(forged)
        db.session.commit()
        assert not is_superadmin(forged)
        assert get_user_counts()["admin"] == 1
    client = app.test_client()
    login = client.post("/auth/login", data={
        "email": forged.email, "password": "SenhaDeTeste2026!"
    }, follow_redirects=False)
    assert login.status_code == 302
    restricted = client.get("/admin/audit-logs", follow_redirects=False)
    assert restricted.status_code != 200

def test_superadmin_identity_cannot_be_forged_in_user_management(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db.create_all()
        owner = new_user("OwnerOnly", "admin", "admin", "Superadmin")
        db.session.add(owner)
        db.session.commit()
        owner_id = owner.id
    client = app.test_client()
    response = client.post("/auth/login", data={
        "email": "owneronly@example.test", "password": "SenhaDeTeste2026!"
    }, follow_redirects=False)
    assert response.status_code == 302
    fake = client.post("/tech/add", data={
        "name": "Falso Superadmin", "email": "fake-admin@example.test",
        "password": "FakePassword123!", "is_active": "on",
        "permission_level": "admin", "job_title": "Outros",
        "other_job_title": "Superadmin",
    }, follow_redirects=False)
    assert fake.status_code == 302
    with app.app_context():
        assert User.query.filter_by(email="fake-admin@example.test").first() is None
    locked = client.get(f"/tech/edit/{owner_id}", follow_redirects=False)
    assert locked.status_code == 302
    assert "/tech/list" in locked.location

def test_single_company_license_panel_hides_legacy_keys(tmp_path):
    app = make_app(tmp_path)
    with app.app_context():
        db.create_all()
        superadmin = new_user("Owner", "admin", "admin", "Superadmin")
        technician = new_user("Technical", "technician", "user", "Técnico")
        db.session.add_all([superadmin, technician])
        db.session.commit()
    client = app.test_client()
    response = client.post("/auth/login", data={
        "email": "owner@example.test",
        "password": "SenhaDeTeste2026!",
    }, follow_redirects=False)
    assert response.status_code == 302
    response = client.get("/admin/settings")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Licenciamento ProntoAr" in html
    assert "Superadmin isento da licença" in html
    assert "Premium · Vitalícia" in html
    assert "Ilimitados" in html
    assert "Chave salva atualmente" not in html
    assert "Ativar ou renovar licença" not in html
    assert 'id="copy-license-key"' not in html
    assert 'name="license_key"' not in html
    assert "1 <span" in html
    app.config["LICENSE_PROVIDER"] = "legacy"
    response = client.get("/admin/settings")
    assert response.status_code == 200
    legacy_html = response.get_data(as_text=True)
    assert "Integração BTA ainda não ativada." in legacy_html
    assert "Limite: 10" not in legacy_html
    assert "Ativar ou renovar licença" not in legacy_html
