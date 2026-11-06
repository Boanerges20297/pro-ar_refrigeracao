"""Isolated in-memory fixtures for application-wide contract tests.

Never loads production .env, external services, or persistent databases.
"""
import os
import tempfile
import unittest
from datetime import datetime

from app import create_app, db
from app.models.client import Client
from app.models.config import AppConfig
from app.models.equipment import Equipment
from app.models.finance import FinancialCategory, FinancialTransaction
from app.models.license import License
from app.models.service import ServiceCatalog
from app.models.user import User
from app.models.workorder import WorkOrder
from app.utils.license import get_instance_fingerprint, issue_license_key
from test_consolidated_receipt import ReceiptTestConfig


class ContractConfig(ReceiptTestConfig):
    TESTING = True
    PWA_ENABLED = True
    SECURITY_ENFORCE_SAME_ORIGIN_MUTATIONS = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RATELIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False
    SERVER_NAME = None
    TRUSTED_HOSTS = None


class ContractCase(unittest.TestCase):
    """Each test gets a new SQLite schema, signing keys and local Flask client."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        base = self.tempdir.name
        # Class-specific paths: never write to the project or production instance.
        cfg = type("ConfigForContract", (ContractConfig,), {
            "UPLOAD_ROOT": os.path.join(base, "uploads"),
            "LICENSE_INSTALLATION_ID_PATH": os.path.join(base, "instance", "id.txt"),
            "LICENSE_PRIVATE_KEY_PATH": os.path.join(base, "keys", "private.pem"),
            "LICENSE_PUBLIC_KEY_PATH": os.path.join(base, "keys", "public.pem"),
        })
        self.app = create_app(cfg)
        self.http = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            db.session.add(AppConfig(company_name="Pronto Ar - Teste"))
            fingerprint = get_instance_fingerprint()
            payload = {
                "company_name": "Pronto Ar - Teste", "status": "active",
                "license_type": "perpetual", "issued_at": "2026-04-15T12:00:00",
                "max_users": 100, "max_admin_users": 50,
                "max_secretary_users": 50,
                "instance_fingerprint": fingerprint,
            }
            db.session.add(License(
                license_key=issue_license_key(payload),
                company_name="Pronto Ar - Teste", status="active",
                instance_fingerprint=fingerprint,
            ))
            self.users = {}
            for level in ("admin", "secretary", "user", "client", "common"):
                u = User(
                    name=f"Teste {level}", email=f"{level}@contract.local",
                    permission_level=level,
                    role="technician" if level == "user" else level,
                    job_title=level, is_active=True,
                    must_change_password=False,
                )
                if not hasattr(ContractCase, "_test_password_hash"):
                    u.set_password("Teste12345")
                    ContractCase._test_password_hash = u.password_hash
                else:
                    u.password_hash = ContractCase._test_password_hash
                db.session.add(u)
                self.users[level] = u
            primary = Client(name="Cliente Teste A")
            other = Client(name="Cliente Teste B")
            service = ServiceCatalog(name="Refrigeracao Teste", base_price=100)
            db.session.add_all((primary, other, service))
            db.session.flush()
            equipment = Equipment(name="Split Teste", client_id=primary.id,
                                  serial_number="TEST-CONTRACT-001")
            db.session.add(equipment)
            db.session.flush()
            order = WorkOrder(client_id=primary.id, equipment_id=equipment.id,
                              service_id=service.id, technician_id=self.users["user"].id,
                              status="Pending", scheduled_date=datetime(2026, 12, 10, 9),
                              total_value=100)
            category = FinancialCategory(name="Servico", type="revenue")
            db.session.add_all((order, category))
            db.session.flush()
            transaction = FinancialTransaction(type="revenue",
                category_id=category.id, description="Teste Financeiro", amount=100)
            db.session.add(transaction)
            db.session.commit()
            self.ids = {
                "client": primary.id, "client_other": other.id,
                "equipment": equipment.id, "service": service.id,
                "workorder": order.id, "category": category.id,
                "transaction": transaction.id,
                "admin": self.users["admin"].id, "secretary": self.users["secretary"].id,
                "user": self.users["user"].id,
            }

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.tempdir.cleanup()

    def login(self, level="admin"):
        self.http = self.app.test_client()
        response = self.http.post("/auth/login",
            data={"email": f"{level}@contract.local",
                  "password": "Teste12345"},
            headers={"Referer": "http://localhost/auth/login"})
        self.assertEqual(response.status_code, 302,
                         f"Login failed for profile {level}")
        return self.http

    def no_server_error(self, response, label):
        self.assertLess(response.status_code, 500,
                        f"{label}: returned HTTP {response.status_code}")
