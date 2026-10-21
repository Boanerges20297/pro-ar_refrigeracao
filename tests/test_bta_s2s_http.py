"""Teste real do adaptador BTA pela rede loopback, com chaves de teste."""
import base64
import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from cryptography.hazmat.primitives import serialization as s
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from app import create_app, db
from app.config import Config
from app.utils.license import evaluate_license
def test_s2s_signed_http_and_cached_offline(tmp_path):
    client_key = Ed25519PrivateKey.generate()
    server_key = Ed25519PrivateKey.generate()
    client_file = tmp_path / "client.pem"
    public_file = tmp_path / "bta.pem"
    client_file.write_bytes(client_key.private_bytes(s.Encoding.PEM, s.PrivateFormat.PKCS8, s.NoEncryption()))
    public_file.write_bytes(server_key.public_key().public_bytes(s.Encoding.PEM, s.PublicFormat.SubjectPublicKeyInfo))
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            digest = hashlib.sha256(raw).hexdigest()
            stamp = self.headers["X-BTA-Timestamp"]
            nonce = self.headers["X-BTA-Nonce"]
            msg = "\n".join(("POST", self.path, stamp, nonce, digest)).encode()
            client_key.public_key().verify(base64.b64decode(self.headers["X-BTA-Signature"]), msg)
            assert self.headers["X-BTA-Client-Id"] == "pronto-ar-backend-prod"
            assert self.headers["X-BTA-Key-Id"] == "pronto-ar-prod-v1"
            assert digest == self.headers["X-BTA-Body-SHA256"]
            assert abs(int(stamp)-int(time.time())) < 300
            assert json.loads(raw) == {"customer_key":"pronto-ar-refrigeracao"}
            seen.append(nonce)
            now = datetime.now(timezone.utc)
            snapshot = {
                "schema_version":1, "product":"pronto-ar",
                "customer_key":"pronto-ar-refrigeracao",
                "modality":"paid", "state":"active",
                "issued_at":now.isoformat(),
                "offline_valid_until":(now+timedelta(days=7)).isoformat(),
                "expires_at":None, "grace_until":None,
                "limits":{"max_users":6,"max_admin_users":2,"max_secretary_users":2},
                "entitlements":{"reports":"enabled","audit":"enabled"},
                "unlimited_limits":["max_common_users","max_client_users"],
            }
            canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",",":")).encode()
            envelope = {"snapshot":snapshot, "signature":{
                "algorithm":"ed25519", "key_id":"pilot",
                "value":base64.b64encode(server_key.sign(canonical)).decode()
            }}
            response = json.dumps({"contract_version":1,"product":"pronto-ar","licensed":True,
                                   "snapshot":envelope}).encode()
            self.send_response(200)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        def log_message(self, *_): pass
    server = ThreadingHTTPServer(("127.0.0.1",0), Handler)
    thread = Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        class Pilot(Config):
            TESTING=True
            RATELIMIT_ENABLED=False
            WTF_CSRF_ENABLED=False
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path/'pilot.db'}"
            UPLOAD_ROOT=str(tmp_path/"uploads")
            LICENSE_INSTALLATION_ID_PATH=str(tmp_path/"installation.txt")
            LICENSE_PROVIDER="bta"
            BTA_LICENSE_BASE_URL=f"http://127.0.0.1:{server.server_port}"
            BTA_LICENSE_CLIENT_ID="pronto-ar-backend-prod"
            BTA_LICENSE_KEY_ID="pronto-ar-prod-v1"
            BTA_LICENSE_CUSTOMER_KEY="pronto-ar-refrigeracao"
            BTA_LICENSE_PRODUCT_CODE="pronto-ar"
            BTA_LICENSE_PRIVATE_KEY_PATH=str(client_file)
            BTA_SNAPSHOT_PUBLIC_KEY_PATH=str(public_file)
            BTA_SNAPSHOT_CACHE_PATH=str(tmp_path/"snapshot.json")
        app=create_app(Pilot)
        with app.app_context():
            db.create_all()
            state=evaluate_license()
            assert state["valid"] and state["license_type"]=="perpetual"
            assert state["limits"]["max_users"]==6
            assert len(seen)==1
            server.shutdown()
            assert evaluate_license()["valid"] # snapshot assinado em cache
    finally:
        server.server_close()
        thread.join(timeout=2)
