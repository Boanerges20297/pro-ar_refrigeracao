import os
import tempfile
import unittest

from app import create_app, db
from app.config import Config


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    RATELIMIT_ENABLED = False
    SECURITY_ENFORCE_SAME_ORIGIN_MUTATIONS = False
    SECURITY_BIND_JWT_SESSION_NONCE = False
    SECURITY_BIND_JWT_USER_AGENT = False
    LICENSE_ALLOW_LEGACY_TOKENS = True
    SERVER_NAME = None
    TRUSTED_HOSTS = None


class ApplicationSmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        TestConfig.UPLOAD_ROOT = os.path.join(self.temp_dir.name, "uploads")
        TestConfig.LICENSE_INSTALLATION_ID_PATH = os.path.join(
            self.temp_dir.name, "instance", "installation_id.txt"
        )
        TestConfig.LICENSE_PRIVATE_KEY_PATH = os.path.join(
            self.temp_dir.name, "keys", "private.pem"
        )
        TestConfig.LICENSE_PUBLIC_KEY_PATH = os.path.join(
            self.temp_dir.name, "keys", "public.pem"
        )

        self.app = create_app(TestConfig)
        self.client = self.app.test_client()

        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp_dir.cleanup()

    def test_application_factory_starts(self):
        self.assertTrue(self.app.testing)
        self.assertIn("auth", self.app.blueprints)
        self.assertIn("admin", self.app.blueprints)
        self.assertIn("services", self.app.blueprints)
        self.assertIn("client_portal", self.app.blueprints)

    def test_root_responds_without_server_error(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertLess(response.status_code, 500)

    def test_login_page_responds(self):
        response = self.client.get("/auth/login", follow_redirects=False)
        self.assertEqual(response.status_code, 200)

    def test_protected_admin_route_does_not_return_server_error(self):
        response = self.client.get("/admin/", follow_redirects=False)
        self.assertLess(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()
