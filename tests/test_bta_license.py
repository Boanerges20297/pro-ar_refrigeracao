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
        BTA_LICENSE_PUSH_ONLY = False
    return create_app(TestConfig), private
def signed_snapshot(private, *, expires_at=None, offline_days=5, customer="existing-customer", state="active", modality="paid"):
    now = datetime.now(timezone.utc)
    payload = {
        "schema_version": 1, "product": "pronto-ar", "license_id": "test-license-id",
        "customer_key": customer, "modality": modality, "state": state,
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


def test_perpetual_license_never_polls_after_first_signed_activation(tmp_path, monkeypatch):
    app, private = app_and_key(tmp_path)
    with app.app_context():
        db.create_all()
        bta_license._store_cached(signed_snapshot(private, offline_days=-100))
        monkeypatch.setattr(
            bta_license, "_resolve_remote",
            lambda: (_ for _ in ()).throw(AssertionError("perpetual license polled")),
        )
        state = evaluate_license()
        assert state["valid"] and not state["blocking"]
        assert state["license_type"] == "perpetual"


def test_signed_revocation_is_applied_without_csrf_and_stops_access(tmp_path, monkeypatch):
    app, private = app_and_key(tmp_path)
    app.config["SECURITY_ENFORCE_SAME_ORIGIN_MUTATIONS"] = True
    with app.app_context():
        db.create_all()
        active = signed_snapshot(private)
        bta_license._store_cached(active)
        monkeypatch.setattr(
            bta_license, "_resolve_remote",
            lambda: (_ for _ in ()).throw(AssertionError("unexpected BTA poll")),
        )

    revoked = signed_snapshot(private, state="revoked")
    response = app.test_client().post(
        "/api/internal/bta-license/events",
        json={"snapshot": revoked},
    )
    assert response.status_code == 200
    assert response.json["result"] == "updated"
    with app.app_context():
        assert evaluate_license()["blocking"]
        assert bta_license._load_cached(allow_expired_offline=True)["state"] == "revoked"

    duplicate = app.test_client().post(
        "/api/internal/bta-license/events", json={"snapshot": revoked}
    )
    assert duplicate.status_code == 200
    assert duplicate.json["result"] == "duplicate"
    stale = app.test_client().post(
        "/api/internal/bta-license/events", json={"snapshot": active}
    )
    assert stale.status_code == 200
    assert stale.json["result"] == "stale"
    with app.app_context():
        assert evaluate_license()["blocking"]


def test_webhook_rejects_forgery_and_wrong_customer(tmp_path):
    app, private = app_and_key(tmp_path)
    with app.app_context():
        db.create_all()
    client = app.test_client()
    for bad in (
        signed_snapshot(Ed25519PrivateKey.generate(), state="revoked"),
        signed_snapshot(private, customer="different", state="revoked"),
    ):
        response = client.post("/api/internal/bta-license/events", json={"snapshot": bad})
        assert response.status_code == 403
    with app.app_context():
        assert bta_license._load_cached(allow_expired_offline=True) is None


def test_push_only_does_not_query_bta_without_initial_event(tmp_path, monkeypatch):
    app, _ = app_and_key(tmp_path)
    app.config["BTA_LICENSE_PUSH_ONLY"] = True
    with app.app_context():
        db.create_all()
        monkeypatch.setattr(
            bta_license, "_resolve_remote",
            lambda: (_ for _ in ()).throw(AssertionError("outbound verification forbidden")),
        )
        state = evaluate_license()
        assert state["blocking"]
        assert state["validation_error_code"] == "awaiting_bta_event"
