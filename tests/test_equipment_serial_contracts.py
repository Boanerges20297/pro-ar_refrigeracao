"""Regression coverage for unique equipment serials and modal feedback."""
from types import SimpleNamespace
from unittest.mock import patch

from app import db
from app.models.equipment import Equipment
from app.models.maintenance import MaintenanceSchedule
from contract_support import ContractCase


class EquipmentSerialContracts(ContractCase):
    def payload(self, serial):
        return {
            "name": "Split de teste", "brand": "Fabricante",
            "model": "Modelo A", "serial_number": serial,
            "location": "Laboratorio", "client_id": str(self.ids["client"]),
            "maintenance_interval": "8",
        }

    def post_equipment(self, serial):
        return self.http.post(
            "/equipment/add", data=self.payload(serial),
            headers={"Referer": "http://localhost/equipment/add"},
        )

    def test_duplicate_serial_shows_modal_preserves_fields_and_writes_nothing(self):
        self.login("admin")
        with self.app.app_context():
            original_count = Equipment.query.count()
        response = self.post_equipment("  TEST-CONTRACT-001  ")
        self.assertEqual(response.status_code, 409)
        content = response.get_data(as_text=True)
        self.assertIn("Este n", content)
        self.assertIn("modal-error", content)
        self.assertIn("Swal.fire", content)
        self.assertIn('name="brand" id="brand" value="Fabricante"', content)
        self.assertIn('name="serial_number" id="serial_number" value="  TEST-CONTRACT-001  "', content)
        self.assertIn(f'name="client_id" id="client_id" value="{self.ids["client"]}"', content)
        self.assertIn("Cliente Teste A", content)
        self.assertIn('value="8" selected', content)
        with self.app.app_context():
            self.assertEqual(Equipment.query.count(), original_count)

    def test_blank_serial_allows_distinct_bank_generated_ids(self):
        self.app.static_folder = self.tempdir.name
        self.login("admin")
        first = self.post_equipment("")
        second = self.post_equipment("   ")
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        with self.app.app_context():
            objects = Equipment.query.filter_by(serial_number=None).order_by(Equipment.id).all()
            self.assertEqual(len(objects), 2)
            self.assertNotEqual(objects[0].id, objects[1].id)
            self.assertTrue(all(isinstance(obj.id, int) for obj in objects))
            for obj in objects:
                self.assertEqual(
                    MaintenanceSchedule.query.filter_by(equipment_id=obj.id).count(), 1
                )

    def test_unique_constraint_race_returns_modal_instead_of_500(self):
        self.login("admin")
        serial = "TEST-CONTRACT-001"

        class RaceQuery:
            first_check = True

            def filter_by(self, **kwargs):
                if kwargs.get("serial_number") == serial and self.first_check:
                    self.first_check = False
                    return SimpleNamespace(first=lambda: None)
                return db.session.query(Equipment).filter_by(**kwargs)

        # Faz a verificacao inicial nao enxergar o registro; o INSERT real
        # ainda colide com a restricao UNIQUE do SQLite, como no PostgreSQL.
        with self.app.app_context():
            with patch.object(Equipment, "query", RaceQuery()):
                response = self.post_equipment(serial)
        self.assertEqual(response.status_code, 409)
        self.assertIn("modal-error", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(Equipment.query.filter_by(serial_number=serial).count(), 1)
            # Garante que rollback deixou a sessao reutilizavel.
            self.assertIsNotNone(db.session.get(Equipment, self.ids["equipment"]))

    def test_duplicate_message_escapes_rendered_form_data(self):
        self.login("admin")
        payload = self.payload("TEST-CONTRACT-001")
        payload["name"] = "<script>alert(1)</script>"
        response = self.http.post(
            "/equipment/add", data=payload,
            headers={"Referer": "http://localhost/equipment/add"},
        )
        self.assertEqual(response.status_code, 409)
        rendered = response.get_data(as_text=True)
        self.assertNotIn('value="<script>alert(1)</script>"', rendered)
        self.assertIn("&lt;script&gt;", rendered)
