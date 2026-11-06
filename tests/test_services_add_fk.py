"""Regression coverage for integer foreign keys in POST /services/add."""
import os
import tempfile
import unittest
from unittest.mock import patch

from app import create_app, db
from app.models.client import Client
from app.models.config import AppConfig
from app.models.license import License
from app.models.push_notification import NotificationJob
from app.models.service import ServiceCatalog
from app.models.user import User
from app.models.workorder import WorkOrder
from app.utils.license import get_instance_fingerprint, issue_license_key
from app.utils.push_notifications import sync_workorder_reminders
from test_consolidated_receipt import ReceiptTestConfig


class ServiceAddFkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = self.temp.name
        class ConfigForAdd(ReceiptTestConfig):
            pass
        ConfigForAdd.UPLOAD_ROOT = os.path.join(base, "uploads")
        ConfigForAdd.LICENSE_INSTALLATION_ID_PATH = os.path.join(base, "instance", "id.txt")
        ConfigForAdd.LICENSE_PRIVATE_KEY_PATH = os.path.join(base, "keys", "private.pem")
        ConfigForAdd.LICENSE_PUBLIC_KEY_PATH = os.path.join(base, "keys", "public.pem")
        self.app = create_app(ConfigForAdd)
        self.http = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            db.session.add(AppConfig(company_name="Pronto Ar"))
            fingerprint = get_instance_fingerprint()
            payload = {
                "company_name": "Pronto Ar", "status": "active",
                "license_type": "perpetual", "issued_at": "2026-04-15T12:00:00",
                "max_users": 20, "max_admin_users": 5, "max_secretary_users": 5,
                "instance_fingerprint": fingerprint,
            }
            db.session.add(License(
                license_key=issue_license_key(payload), status="active",
                company_name="Pronto Ar", instance_fingerprint=fingerprint))
            admin = User(name="Admin", email="admin-add@test.local",
                         permission_level="admin", role="admin", job_title="Admin",
                         is_active=True, must_change_password=False)
            tech = User(name="Tecnico", email="tech-add@test.local",
                        permission_level="user", role="technician", job_title="Tecnico",
                        is_active=True, must_change_password=False)
            admin.set_password("Teste12345")
            tech.set_password("Teste12345")
            client = Client(name="Cliente Teste")
            service = ServiceCatalog(name="Servico Teste", base_price=50)
            db.session.add_all([admin, tech, client, service])
            db.session.commit()
            self.client_id, self.service_id, self.tech_id = client.id, service.id, tech.id
        login = self.http.post("/auth/login", data={
            "email": "admin-add@test.local", "password": "Teste12345"
        }, headers={"Referer": "http://localhost/auth/login"})
        self.assertEqual(login.status_code, 302)

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
        self.temp.cleanup()

    def _submit(self, tech_id, **overrides):
        data = {
            "client_id": str(self.client_id),
            "equipment_id": "",
            "service_id": str(self.service_id),
            "technician_id": tech_id,
            "scheduled_date": "2026-11-10T09:00",
            "total_value": "50",
            "description": "Teste de regressao",
        }
        data.update(overrides)
        return self.http.post("/services/add", data=data,
                              headers={"Referer": "http://localhost/services/add"})

    def test_numeric_technician_is_integer_during_real_reminder_sync(self):
        seen_types = []
        def capture_and_sync(order):
            seen_types.append(type(order.technician_id))
            sync_workorder_reminders(order)
        with patch("app.routes.services.sync_workorder_reminders", side_effect=capture_and_sync), patch("app.routes.services.sync_wo_to_finance"):
            response = self._submit(str(self.tech_id))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(seen_types, [int])
        with self.app.app_context():
            order = WorkOrder.query.one()
            self.assertEqual(order.technician_id, self.tech_id)
            self.assertGreater(NotificationJob.query.filter_by(workorder_id=order.id).count(), 0)

    def test_invalid_foreign_keys_cannot_insert_an_order(self):
        examples = [
            ("abc", {}),
            ("", {"equipment_id": "not-an-id"}),
            ("", {"client_id": "0"}),
            ("", {"service_id": "broken"}),
        ]
        for technician, overrides in examples:
            with self.subTest(technician=technician, overrides=overrides):
                with patch("app.routes.services.sync_workorder_reminders") as reminder:
                    response = self._submit(technician, **overrides)
                self.assertEqual(response.status_code, 302)
                reminder.assert_not_called()
                with self.app.app_context():
                    self.assertEqual(WorkOrder.query.count(), 0)

    def test_empty_technician_remains_optional(self):
        with patch("app.routes.services.sync_wo_to_finance"):
            response = self._submit("")
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            self.assertIsNone(WorkOrder.query.one().technician_id)


if __name__ == "__main__":
    unittest.main()
