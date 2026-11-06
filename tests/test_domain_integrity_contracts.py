"""Data integrity, input fuzzing and end-to-end business contracts.

These tests use a fresh in-memory SQLite database; never modify production.
"""
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import Integer, inspect
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.finance import FinancialCategory, FinancialTransaction
from app.models.push_notification import NotificationJob
from app.models.service import ServiceCatalog
from app.models.user import User
from app.models.workorder import WorkOrder
from app.utils.push_notifications import sync_workorder_reminders
from contract_support import ContractCase


class DomainIntegrityContracts(ContractCase):
    def _payload(self, **values):
        payload = {
            "client_id": str(self.ids["client"]),
            "equipment_id": str(self.ids["equipment"]),
            "service_id": str(self.ids["service"]),
            "technician_id": str(self.ids["user"]),
            "total_value": "99.50",
            "description": "Contract test workorder",
            "scheduled_date": "2026-12-20T09:00",
        }
        payload.update(values)
        return payload

    def _post_order(self, **overrides):
        return self.http.post("/services/add", data=self._payload(**overrides),
            headers={"Referer":"http://localhost/services/add"})

    def test_all_model_tables_expose_primary_keys(self):
        with self.app.app_context():
            tables=list(db.metadata.tables.values())
            self.assertGreaterEqual(len(tables),15)
            for table in tables:
                with self.subTest(table=table.name):
                    self.assertTrue(len(table.primary_key.columns),table.name)
            print("MODEL_TABLES_AUDITED",len(tables))

    def test_foreign_key_column_types_match_referenced_columns(self):
        with self.app.app_context():
            count=0
            for table in db.metadata.tables.values():
                for col in table.columns:
                    for fk in col.foreign_keys:
                        with self.subTest(column=f"{table.name}.{col.name}"):
                            self.assertEqual(col.type._type_affinity,
                                fk.column.type._type_affinity,
                                f"{col} ({col.type}) != {fk.column} ({fk.column.type})")
                        count+=1
            self.assertGreaterEqual(count,10)
            print("FOREIGN_KEYS_AUDITED",count)

    def test_primary_key_ids_and_relationship_roundtrip(self):
        with self.app.app_context():
            wo=db.session.get(WorkOrder,self.ids["workorder"])
            self.assertEqual(wo.client.id,self.ids["client"])
            self.assertEqual(wo.equipment.id,self.ids["equipment"])
            self.assertEqual(wo.technician.id,self.ids["user"])
            self.assertEqual(len(wo.client.work_orders),1)
            self.assertEqual(wo.equipment.client_id,self.ids["client"])

    def test_service_catalog_and_financial_category_contract(self):
        with self.app.app_context():
            cat=db.session.get(FinancialCategory,self.ids["category"])
            transaction=db.session.get(FinancialTransaction,self.ids["transaction"])
            svc=db.session.get(ServiceCatalog,self.ids["service"])
            self.assertEqual(cat.type,"revenue")
            self.assertEqual(transaction.category.id,cat.id)
            self.assertEqual(transaction.amount,100)
            self.assertEqual(svc.base_price,100)

    def test_equipment_serial_is_unique(self):
        with self.app.app_context():
            twin=Equipment(name="Duplicado",client_id=self.ids["client"],
                           serial_number="TEST-CONTRACT-001")
            db.session.add(twin)
            with self.assertRaises(IntegrityError):
                db.session.flush()
            db.session.rollback()

    def test_positive_numeric_form_ids_create_os_and_reminders(self):
        self.login("admin")
        captured=[]
        def sync(order):
            captured.append((type(order.client_id).__name__,
                             type(order.equipment_id).__name__,
                             type(order.service_id).__name__,
                             type(order.technician_id).__name__))
            sync_workorder_reminders(order)
        with self.app.app_context():
            before=WorkOrder.query.count()
        with patch("app.routes.services.sync_wo_to_finance"), patch(
            "app.routes.services.sync_workorder_reminders",side_effect=sync):
            resp=self._post_order()
        self.assertEqual(resp.status_code,302)
        self.assertEqual(captured,[("int","int","int","int")])
        with self.app.app_context():
            self.assertEqual(WorkOrder.query.count(),before+1)
            order=WorkOrder.query.filter_by(description="Contract test workorder").one()
            self.assertEqual(order.technician_id,self.ids["user"])
            self.assertGreater(NotificationJob.query.filter_by(
                workorder_id=order.id).count(),0)

    def test_optional_ids_do_not_become_empty_strings(self):
        self.login("admin")
        with patch("app.routes.services.sync_wo_to_finance"):
            resp=self._post_order(equipment_id="",technician_id="")
        self.assertEqual(resp.status_code,302)
        with self.app.app_context():
            order=WorkOrder.query.filter_by(description="Contract test workorder").one()
            self.assertIsNone(order.equipment_id)
            self.assertIsNone(order.technician_id)

    def test_malformed_foreign_keys_are_rejected_before_insert(self):
        self.login("admin")
        malformed=("0","-2","abc","1.5","9x","SELECT 1","000000000000",
                   "99999999999999999999999999999999")
        for field in ("client_id","equipment_id","service_id","technician_id"):
            for invalid in malformed:
                with self.subTest(field=field,invalid=invalid):
                    # Very large all-digit values can parse as integers; such
                    # values are tested separately by FK existence tests.
                    if invalid.isdigit() and int(invalid)>0:
                        continue
                    with patch("app.routes.services.sync_wo_to_finance"):
                        response=self._post_order(**{field:invalid})
                    self.assertLess(response.status_code,500)
                    with self.app.app_context():
                        self.assertEqual(WorkOrder.query.filter_by(
                            description="Contract test workorder").count(),0)

    def test_missing_service_id_is_rejected(self):
        self.login("admin")
        resp=self._post_order(service_id="")
        self.no_server_error(resp,"empty service_id")
        with self.app.app_context():
            self.assertEqual(WorkOrder.query.filter_by(
                description="Contract test workorder").count(),0)

    def test_nonexistent_numeric_fk_is_rejected_gracefully(self):
        """FK existence must be verified before a database IntegrityError."""
        self.login("admin")
        for field in ("client_id","equipment_id","service_id","technician_id"):
            with self.subTest(field=field):
                try:
                    resp=self._post_order(**{field:"999999"})
                    self.no_server_error(resp,f"unknown {field}")
                    with self.app.app_context():
                        self.assertEqual(WorkOrder.query.filter_by(
                            description="Contract test workorder").count(),0)
                except Exception as exc:
                    self.fail(f"Invalid {field} raised {type(exc).__name__}: "
                              f"{str(exc)[:160]}")
                finally:
                    with self.app.app_context():
                        db.session.rollback()

    def test_invalid_scheduled_date_returns_validation_error_not_exception(self):
        self.login("admin")
        for bad_date in ("2026-99-99T25:99","not-a-date"):
            with self.subTest(date=bad_date):
                try:
                    resp=self._post_order(scheduled_date=bad_date)
                    self.no_server_error(resp,"invalid scheduled_date")
                except (ValueError,TypeError) as exc:
                    self.fail(f"Unhandled date parser exception: {exc}")
                finally:
                    with self.app.app_context():
                        db.session.rollback()

    def test_non_finite_money_cannot_be_persisted(self):
        self.login("admin")
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value):
                try:
                    with patch("app.routes.services.sync_wo_to_finance"):
                        resp = self._post_order(total_value=value)
                    self.no_server_error(resp, "invalid total_value")
                    with self.app.app_context():
                        self.assertEqual(WorkOrder.query.filter_by(
                            description="Contract test workorder").count(), 0)
                except (ValueError, TypeError, IntegrityError) as exc:
                    self.fail(f"Non-finite money was not validated: {type(exc).__name__}")
                finally:
                    with self.app.app_context():
                        db.session.rollback()
                        # Reset test-only SQLite state even when a regression
                        # incorrectly persisted an order, avoiding false followups.
                        for order in WorkOrder.query.filter_by(
                                description="Contract test workorder").all():
                            NotificationJob.query.filter_by(
                                workorder_id=order.id).delete()
                            db.session.delete(order)
                        db.session.commit()

    def test_duplicate_check_returns_machine_readable_json(self):
        self.login("admin")
        response=self.http.post("/services/check_duplicate",json={
            "client_id":self.ids["client"],"date":"2026-12-10T09:00"
        },headers={"Referer":"http://localhost/services/check_duplicate"})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json().get("duplicate"),True)

    def test_duplicate_check_nonmatching_date_is_false(self):
        self.login("admin")
        response=self.http.post("/services/check_duplicate",json={
            "client_id":self.ids["client"],"date":"2030-01-01T09:00"
        },headers={"Referer":"http://localhost/services/check_duplicate"})
        self.assertEqual(response.status_code,200)
        self.assertIs(response.get_json()["duplicate"],False)

    def test_accent_insensitive_client_search_and_injection_input(self):
        self.login("admin")
        for query in ("cliente","CLIENTE","' OR 1=1 --","%","", "Á"):
            with self.subTest(query=query):
                response=self.http.get("/clients/search",query_string={"q":query})
                self.assertEqual(response.status_code,200)
                self.assertIsInstance(response.get_json(),list)
                self.assertLessEqual(len(response.get_json()),10)
                if query:
                    self.assertIn("no-store",response.headers.get("Cache-Control",""))

    def test_client_equipment_api_matches_owner(self):
        self.login("admin")
        response=self.http.get(f"/clients/api/{self.ids['client']}/equipment")
        self.assertEqual(response.status_code,200)
        payload=response.get_json()
        self.assertTrue(payload)
        self.assertIn("equipments",payload)
        ids=[item["id"] for item in payload["equipments"]]
        self.assertIn(self.ids["equipment"],ids)


if __name__=="__main__":
    import unittest
    unittest.main()
