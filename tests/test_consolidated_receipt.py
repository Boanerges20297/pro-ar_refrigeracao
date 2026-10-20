"""Integration tests for the explicitly selected, same-client consolidated receipt."""
import os
import tempfile
import unittest
from datetime import datetime

from app import create_app, db
from app.config import Config
from app.models.client import Client
from app.models.config import AppConfig
from app.models.license import License
from app.models.service import ServiceCatalog
from app.models.user import User
from app.models.workorder import WorkOrder
from app.utils.license import get_instance_fingerprint, issue_license_key


class ReceiptTestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    LICENSE_ALLOW_LEGACY_TOKENS = True
    SECURITY_ENFORCE_SAME_ORIGIN_MUTATIONS = False
    SECURITY_BIND_JWT_SESSION_NONCE = False
    SECURITY_BIND_JWT_USER_AGENT = False
    JWT_COOKIE_SECURE = False
    SERVER_NAME = None
    TRUSTED_HOSTS = None
    PWA_ENABLED = False


class ConsolidatedReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = self.temp.name
        ReceiptTestConfig.UPLOAD_ROOT = os.path.join(base, "uploads")
        ReceiptTestConfig.LICENSE_INSTALLATION_ID_PATH = os.path.join(base, "instance", "id.txt")
        ReceiptTestConfig.LICENSE_PRIVATE_KEY_PATH = os.path.join(base, "keys", "private.pem")
        ReceiptTestConfig.LICENSE_PUBLIC_KEY_PATH = os.path.join(base, "keys", "public.pem")
        self.app = create_app(ReceiptTestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            db.session.add(AppConfig(company_name="Pronto Ar Refrigeração"))
            fingerprint = get_instance_fingerprint()
            payload = {
                "company_name": "Pronto Ar Refrigeração", "status": "active",
                "license_type": "perpetual", "issued_at": "2026-04-15T12:00:00",
                "max_users": 20, "max_admin_users": 5, "max_secretary_users": 5,
                "instance_fingerprint": fingerprint,
            }
            db.session.add(License(
                license_key=issue_license_key(payload), status="active",
                company_name="Pronto Ar Refrigeração",
                instance_fingerprint=fingerprint,
            ))
            self.admin = self._user("Administrador", "admin@test.local", "admin")
            self.tech = self._user("Técnico Um", "tech@test.local", "user")
            self.other_tech = self._user("Técnico Dois", "tech2@test.local", "user")
            primary = Client(name="Cliente A")
            other = Client(name="Cliente B")
            service = ServiceCatalog(name="Manutenção", base_price=100)
            db.session.add_all([primary, other, service])
            db.session.flush()
            self.client_a = primary.id
            self.client_b = other.id
            self.first = self._order(primary.id, service.id, self.tech.id, 150, True)
            self.second = self._order(primary.id, service.id, self.tech.id, 250, False)
            self.foreign = self._order(other.id, service.id, self.tech.id, 400, True)
            self.unassigned = self._order(primary.id, service.id, self.other_tech.id, 500, True)
            self.pending = self._order(primary.id, service.id, self.tech.id, 600, True, "Pending")
            db.session.commit()

    def _user(self, name, email, level):
        user = User(name=name, email=email, permission_level=level,
                    role="technician" if level == "user" else "admin",
                    job_title="Técnico" if level == "user" else "Administrador",
                    is_active=True, must_change_password=False)
        user.set_password("Teste12345")
        db.session.add(user)
        db.session.flush()
        return user

    def _order(self, client_id, service_id, tech_id, amount, paid, status="Completed"):
        order = WorkOrder(client_id=client_id, service_id=service_id,
                          technician_id=tech_id, status=status,
                          total_value=amount, is_paid=paid,
                          completed_date=datetime(2026, 10, 20) if status == "Completed" else None)
        db.session.add(order)
        db.session.flush()
        return order.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp.cleanup()

    def _login(self, email):
        response = self.client.post("/auth/login", data={"email": email, "password": "Teste12345"},
                                    headers={"Referer": "http://localhost/auth/login"})
        self.assertEqual(response.status_code, 302)

    def _receipt(self, *ids):
        return self.client.get(f"/services/receipt/consolidated/{self.client_a}",
                               query_string=[("os", str(value)) for value in ids])

    def test_selection_lists_completed_orders_from_same_client(self):
        self._login("admin@test.local")
        response = self.client.get(f"/services/receipt/select/{self.client_a}")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Gerar recibo único", html)
        self.assertIn(f'value="{self.first}"', html)
        self.assertIn(f'value="{self.second}"', html)
        self.assertNotIn(f'value="{self.foreign}"', html)
        self.assertNotIn(f'value="{self.pending}"', html)

    def test_two_services_generate_one_receipt_with_correct_total(self):
        self._login("admin@test.local")
        response = self._receipt(self.first, self.second)
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Recibo consolidado de serviços", html)
        self.assertIn("400.00", html)  # total 150 + 250
        self.assertIn("150.00", html)
        self.assertIn("250.00", html)
        self.assertIn("Há valores pendentes", html)
        self.assertEqual(html.count('<main class="sheet">'), 1)
        self.assertEqual(self.client.get(f"/services/receipt/{self.first}").status_code, 200)

    def test_foreign_duplicate_pending_missing_and_invalid_ids_rejected(self):
        self._login("admin@test.local")
        for ids in [
            (self.first, self.foreign),
            (self.first, self.first),
            (self.first, self.pending),
            (self.first, 999999),
            (self.first,),
            (),
            (self.first, "abc"),
            tuple([self.first] + list(range(1000, 1050))),
        ]:
            with self.subTest(ids=ids):
                self.assertEqual(self._receipt(*ids).status_code, 400)

    def test_technician_can_only_select_own_orders(self):
        self._login("tech@test.local")
        page = self.client.get(f"/services/receipt/select/{self.client_a}")
        html = page.get_data(as_text=True)
        self.assertEqual(page.status_code, 200)
        self.assertIn(f'value="{self.first}"', html)
        self.assertNotIn(f'value="{self.unassigned}"', html)
        self.assertEqual(self._receipt(self.first, self.second).status_code, 200)
        self.assertEqual(self._receipt(self.first, self.unassigned).status_code, 403)

    def test_requires_authentication_and_does_not_modify_orders(self):
        self.assertEqual(self._receipt(self.first, self.second).status_code, 302)
        self._login("admin@test.local")
        self.assertEqual(self._receipt(self.first, self.second).status_code, 200)
        with self.app.app_context():
            first = db.session.get(WorkOrder, self.first)
            second = db.session.get(WorkOrder, self.second)
            self.assertEqual(first.total_value, 150)
            self.assertEqual(second.total_value, 250)
            self.assertTrue(first.is_paid)
            self.assertFalse(second.is_paid)


if __name__ == "__main__":
    unittest.main()
