from datetime import datetime, timedelta, timezone
import base64
import json
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app import create_app, db
from app.config import Config
from app.utils import bta_license
from app.utils.license import evaluate_license, get_license_features
def app_and_key(tmp_path):
    private = Ed25519PrivateKey.generate()
    public_file = tmp_path / "trusted-bta-public.pem"
    public_file.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'app.db'}"
        RATELIMIT_ENABLED = False
        UPLOAD_ROOT = str(tmp_path / "uploads")
        LICENSE_INSTALLATION_ID_PATH = str(tmp_path / "installation.txt")
        LICENSE_PROVIDER = "bta"
        BTA_LICENSE_CUSTOMER_KEY = "existing-customer"
        BTA_LICENSE_PRODUCT_CODE = "pronto-ar"
        BTA_SNAPSHOT_PUBLIC_KEY_PATH = str(public_file)
        BTA_SNAPSHOT_CACHE_PATH = str(tmp_path / "bta-snapshot.json")
        BTA_LICENSE_REFRESH_SECONDS = 300
    return create_app(TestConfig), private
def signed_snapshot(private, *, expires_at=None, offline_days=5, customer="existing-customer"):
    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": 1, "product": "pronto-ar",
        "customer_key": customer, "modality": "paid", "state": "active",
        "issued_at": now.isoformat(),
        "offline_valid_until": (now + timedelta(days=offline_days)).isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "grace_until": None,
        "entitlements": {"reports": "enabled", "audit": "enabled", "email": "hidden"},
        "limits": {"max_users": 6, "max_admin_users": 2, "max_secretary_users": 2},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"snapshot": payload, "signature": {
        "algorithm": "ed25519", "key_id": "test",
        "value": base64.b64encode(private.sign(canonical)).decode()}}
def test_lifetime_paid_snapshot_and_limits(tmp_path, monkeypatch):
    app, private = app_and_key(tmp_path)
    with app.app_context():
        db.create_all()
        envelope = signed_snapshot(private)
        monkeypatch.setattr(bta_license, "_resolve_remote",
                            lambda: {"licensed": True, "snapshot": bta_license._verify_envelope(envelope)})
        state = evaluate_license()
        assert state["valid"] and not state["blocking"]
        assert state["license_type"] == "perpetual"
        assert state["limits"] == {"max_users": 6, "max_admin_users": 2, "max_secretary_users": 2}
        assert get_license_features(state) == {"reports", "audit"}
def test_offline_uses_signed_cache(tmp_path, monkeypatch):
    app, private = app_and_key(tmp_path)
    with app.app_context():
        db.create_all()
        bta_license._store_cached(signed_snapshot(private))
        monkeypatch.setattr(bta_license, "_resolve_remote",
                            lambda: (_ for _ in ()).throw(bta_license.BtaTransportError("offline")))
        app.config["BTA_LICENSE_REFRESH_SECONDS"] = 0
        assert evaluate_license()["valid"]
def test_invalid_signature_and_wrong_customer_fail_closed(tmp_path, monkeypatch):
    app, private = app_and_key(tmp_path)
    with app.app_context():
        db.create_all()
        for envelope in (signed_snapshot(Ed25519PrivateKey.generate()),
                         signed_snapshot(private, customer="other-customer")):
            monkeypatch.setattr(bta_license, "_resolve_remote",
                                lambda value=envelope: {"licensed": True, "snapshot": bta_license._verify_envelope(value)})
            assert evaluate_license()["blocking"]
def test_expired_snapshot_and_paid_grace(tmp_path, monkeypatch):
    app, private = app_and_key(tmp_path)
    with app.app_context():
        db.create_all()
        expired_envelope = signed_snapshot(private, offline_days=-1)
        monkeypatch.setattr(bta_license, "_resolve_remote",
                            lambda: {"licensed": True, "snapshot": bta_license._verify_envelope(expired_envelope)})
        assert evaluate_license()["blocking"]
        now = datetime.now(timezone.utc)
        grace_envelope = signed_snapshot(private, expires_at=now-timedelta(days=3))
        monkeypatch.setattr(bta_license, "_resolve_remote",
                            lambda: {"licensed": True, "snapshot": bta_license._verify_envelope(grace_envelope)})
        state = evaluate_license()
        assert state["valid"] and state["within_grace_period"]
