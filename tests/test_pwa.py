import json
import os
import tempfile
import unittest

from app import create_app, db
from app.config import Config


class PwaTestConfig(Config):
    TESTING = True
    PWA_ENABLED = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RATELIMIT_ENABLED = False
    LICENSE_ALLOW_LEGACY_TOKENS = True
    SERVER_NAME = None
    TRUSTED_HOSTS = None


class PwaTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        PwaTestConfig.UPLOAD_ROOT = os.path.join(self.temp_dir.name, "uploads")
        PwaTestConfig.LICENSE_INSTALLATION_ID_PATH = os.path.join(self.temp_dir.name, "instance", "installation_id.txt")
        PwaTestConfig.LICENSE_PRIVATE_KEY_PATH = os.path.join(self.temp_dir.name, "keys", "private.pem")
        PwaTestConfig.LICENSE_PUBLIC_KEY_PATH = os.path.join(self.temp_dir.name, "keys", "public.pem")
        self.app = create_app(PwaTestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def test_manifest_exposes_installable_metadata(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/manifest+json")
        self.assertIn("no-store", response.headers["Cache-Control"])
        data = json.loads(response.data)
        self.assertEqual(data["display"], "standalone")
        self.assertEqual(data["start_url"], "/")
        self.assertEqual(data["scope"], "/")
        self.assertEqual(data["id"], "/")
        self.assertEqual({i["sizes"] for i in data["icons"]}, {"192x192", "512x512"})

    def test_service_worker_only_caches_public_offline_screen(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/javascript")
        self.assertIn("no-store", response.headers["Cache-Control"])
        script = response.get_data(as_text=True)
        self.assertIn("request.mode !== 'navigate'", script)
        self.assertIn("cache.add(new Request(OFFLINE_URL", script)
        self.assertNotIn("cache.put(", script)
        self.assertNotIn("caches.open(request", script)

    def test_icon_and_offline_assets_are_public(self):
        for path in ("/static/pwa/icon-192.png", "/static/pwa/icon-512.png", "/static/pwa/offline.html"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
        for pixels in (192, 512):
            response = self.client.get(f"/static/pwa/icon-{pixels}.png")
            self.assertEqual(response.data[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(int.from_bytes(response.data[16:20], "big"), pixels)

    def test_login_registers_pwa_only_when_enabled(self):
        enabled = self.client.get("/auth/login").get_data(as_text=True)
        self.assertIn('rel="manifest"', enabled)
        self.assertIn('pwa/register.js', enabled)
        self.assertIn('prontoar-pwa-install', enabled)
        self.app.config["PWA_ENABLED"] = False
        disabled = self.client.get("/auth/login").get_data(as_text=True)
        self.assertNotIn('rel="manifest"', disabled)
        self.assertNotIn('pwa/register.js', disabled)
        self.assertEqual(self.client.get("/manifest.webmanifest").status_code, 404)
        self.assertIn("unregister()", self.client.get("/sw.js").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
