"""Integration tests of real business functions, isolated from external services."""
import io
import os
from datetime import datetime, timedelta

from PIL import Image
from werkzeug.datastructures import FileStorage

from app import db
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.finance import FinancialCategory, FinancialTransaction
from app.models.maintenance import MaintenanceSchedule
from app.models.workorder import WorkOrder
from app.models.workorder_expense import WorkOrderExpense
from app.utils.finance import (
    get_or_create_category, sync_wo_to_finance, sync_expense_to_finance,
    delete_finance_sync, run_retroactive_sync,
)
from app.utils.images import save_and_resize_image, get_workorder_photo_url
from app.utils.maintenance import (
    get_or_create_maintenance_service, sync_schedule_with_workorder,
)
from app.utils.notifications import get_alerts
from contract_support import ContractCase


class BusinessWorkflowContracts(ContractCase):
    def test_financial_category_get_or_create_is_idempotent(self):
        with self.app.app_context():
            a=get_or_create_category("Manutencao Teste","revenue")
            b=get_or_create_category("Manutencao Teste","revenue")
            self.assertEqual(a.id,b.id)
            self.assertEqual(FinancialCategory.query.filter_by(
                name="Manutencao Teste").count(),1)

    def test_workorder_revenue_sync_create_update_and_no_duplicates(self):
        with self.app.app_context():
            wo=db.session.get(WorkOrder,self.ids["workorder"])
            sync_wo_to_finance(wo)
            q=FinancialTransaction.query.filter_by(work_order_id=wo.id,
                is_automated=True,work_order_expense_id=None)
            self.assertEqual(q.count(),1)
            entry=q.one()
            self.assertEqual(entry.amount,100)
            self.assertEqual(entry.status,"pending")
            wo.total_value=245.5
            wo.is_paid=True
            sync_wo_to_finance(wo)
            self.assertEqual(q.count(),1)
            self.assertEqual(q.one().amount,245.5)
            self.assertEqual(q.one().status,"paid")

    def test_workorder_expense_finance_sync_create_update(self):
        with self.app.app_context():
            expense=WorkOrderExpense(work_order_id=self.ids["workorder"],
                description="Gas teste",quantity=2,unit_price=35)
            db.session.add(expense);db.session.commit()
            sync_expense_to_finance(expense)
            query=FinancialTransaction.query.filter_by(
                work_order_expense_id=expense.id,is_automated=True)
            self.assertEqual(query.count(),1)
            self.assertEqual(query.one().amount,70)
            expense.quantity=3
            sync_expense_to_finance(expense)
            self.assertEqual(query.count(),1)
            self.assertEqual(query.one().amount,105)

    def test_financial_sync_deletion_preserves_manual_transactions(self):
        with self.app.app_context():
            wo=db.session.get(WorkOrder,self.ids["workorder"])
            manual=db.session.get(FinancialTransaction,self.ids["transaction"])
            manual.work_order_id=wo.id
            db.session.commit()
            sync_wo_to_finance(wo)
            self.assertEqual(FinancialTransaction.query.filter_by(
                work_order_id=wo.id).count(),2)
            delete_finance_sync(work_order_id=wo.id)
            self.assertEqual(FinancialTransaction.query.filter_by(
                work_order_id=wo.id,is_automated=True).count(),0)
            self.assertIsNotNone(db.session.get(FinancialTransaction,manual.id))

    def test_retroactive_financial_sync_is_idempotent(self):
        with self.app.app_context():
            expense=WorkOrderExpense(work_order_id=self.ids["workorder"],
                description="Peca teste",quantity=2,unit_price=7)
            db.session.add(expense);db.session.commit()
            self.assertEqual(run_retroactive_sync(),(1,1))
            first=FinancialTransaction.query.filter_by(is_automated=True).count()
            self.assertEqual(first,2)
            self.assertEqual(run_retroactive_sync(),(1,1))
            self.assertEqual(FinancialTransaction.query.filter_by(
                is_automated=True).count(),first)

    def test_workorder_expense_total_calculation(self):
        expense=WorkOrderExpense(quantity=3,unit_price=12.5,
                                 description="Teste",work_order_id=self.ids["workorder"])
        self.assertEqual(expense.total,37.5)

    def test_zero_quantity_has_zero_cost(self):
        expense=WorkOrderExpense(quantity=0,unit_price=15,
                                 description="Teste",work_order_id=self.ids["workorder"])
        self.assertEqual(expense.total,0,
                         "Zero units cannot generate a nonzero expense")

    def test_preventive_maintenance_catalog_is_reused(self):
        with self.app.app_context():
            a=get_or_create_maintenance_service()
            b=get_or_create_maintenance_service()
            self.assertEqual(a.id,b.id)
            self.assertGreater(a.id,0)

    def test_schedule_transitions_complete_and_reopen(self):
        with self.app.app_context():
            wo=db.session.get(WorkOrder,self.ids["workorder"])
            schedule=MaintenanceSchedule(
                equipment_id=self.ids["equipment"],workorder_id=wo.id,
                next_maintenance_date=datetime(2026,12,20,9),is_active=True)
            db.session.add(schedule);db.session.commit()
            wo.status="Completed"
            wo.completed_date=datetime(2026,12,20,11)
            sync_schedule_with_workorder(wo,previous_status="Pending")
            self.assertFalse(schedule.is_active)
            self.assertEqual(schedule.last_maintenance_date,wo.completed_date)
            wo.status="Pending"
            sync_schedule_with_workorder(wo,previous_status="Completed")
            self.assertTrue(schedule.is_active)
            self.assertIsNone(schedule.last_maintenance_date)
            self.assertIsNone(wo.completed_date)

    def test_role_specific_notifications_do_not_leak_unassigned_orders(self):
        with self.app.app_context():
            old=WorkOrder(client_id=self.ids["client"],
                equipment_id=self.ids["equipment"],
                service_id=self.ids["service"],technician_id=self.ids["user"],
                scheduled_date=datetime.utcnow()-timedelta(days=5),status="Pending")
            db.session.add(old);db.session.commit()
            admin=get_alerts()
            technician=get_alerts(db.session.get(
                __import__("app.models.user",fromlist=["User"]).User,self.ids["user"]))
            self.assertGreaterEqual(admin["total_count"],1)
            self.assertTrue(any(w.id==old.id for w in technician["overdue_services"]))

    def test_client_create_update_via_http(self):
        self.login("admin")
        add=self.http.post("/clients/add",data={
            "name":"Cliente Inserido Contract","email":"insert@contract.local",
            "phone":"85999999999","address":"Endereco Teste"},
            headers={"Referer":"http://localhost/clients/add"})
        self.assertEqual(add.status_code,302)
        with self.app.app_context():
            client=Client.query.filter_by(name="Cliente Inserido Contract").one()
            client_id=client.id
        edit=self.http.post(f"/clients/edit/{client_id}",data={
            "name":"Cliente Atualizado Contract",
            "email":"update@contract.local","phone":"8588888888",
            "address":"Endereco Atualizado"},
            headers={"Referer":f"http://localhost/clients/edit/{client_id}"})
        self.assertEqual(edit.status_code,302)
        with self.app.app_context():
            client=db.session.get(Client,client_id)
            self.assertEqual(client.name,"Cliente Atualizado Contract")

    def test_finance_manual_transaction_create_edit_delete(self):
        self.login("admin")
        resp=self.http.post("/admin/finance/transaction/add",data={
            "type":"expense","category_id":"",
            "description":"Manual Contract","amount":"34.25",
            "date":"2026-11-06","status":"paid"},
            headers={"Referer":"http://localhost/admin/finance/transaction/add"})
        self.assertEqual(resp.status_code,302)
        with self.app.app_context():
            entry=FinancialTransaction.query.filter_by(
                description="Manual Contract").one()
            manual_id=entry.id
            self.assertEqual(entry.amount,34.25)
        update=self.http.post(f"/admin/finance/transaction/edit/{manual_id}",data={
            "type":"expense","category_id":"","description":"Manual Editado",
            "amount":"45.50","date":"2026-11-07","status":"pending"},
            headers={"Referer":"http://localhost/admin/finance/transactions"})
        self.assertEqual(update.status_code,302)
        with self.app.app_context():
            self.assertEqual(db.session.get(FinancialTransaction,manual_id).amount,45.50)
        remove=self.http.post(f"/admin/finance/transaction/delete/{manual_id}",
            headers={"Referer":"http://localhost/admin/finance/transactions"})
        self.assertEqual(remove.status_code,302)
        with self.app.app_context():
            self.assertIsNone(db.session.get(FinancialTransaction,manual_id))

    def test_finance_rejects_non_numeric_amount_without_server_error(self):
        self.login("admin")
        try:
            resp=self.http.post("/admin/finance/transaction/add",data={
                "type":"expense","category_id":"",
                "description":"Invalid Amount Contract","amount":"not-a-number",
                "date":"2026-11-06","status":"paid"},
                headers={"Referer":"http://localhost/admin/finance/transaction/add"})
            self.no_server_error(resp,"finance invalid amount")
        except ValueError as exc:
            self.fail(f"Unhandled amount conversion: {exc}")

    def test_equipment_create_generates_schedule_and_qr_in_temp_folder(self):
        self.app.static_folder=self.tempdir.name
        self.login("admin")
        response=self.http.post("/equipment/add",data={
            "name":"Split Criado Contract","brand":"Marca Teste",
            "model":"M-01","serial_number":"TEST-CONTRACT-NEW",
            "location":"Teste","client_id":str(self.ids["client"]),
            "maintenance_interval":"6"},
            headers={"Referer":"http://localhost/equipment/add"})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            equipment=Equipment.query.filter_by(
                serial_number="TEST-CONTRACT-NEW").one()
            schedule=MaintenanceSchedule.query.filter_by(
                equipment_id=equipment.id).one()
            self.assertTrue(schedule.is_active)
            self.assertTrue(os.path.isfile(os.path.join(
                self.tempdir.name,"img","qrcodes",f"equip_{equipment.id}.png")))

    def test_equipment_rejects_invalid_maintenance_interval(self):
        self.app.static_folder=self.tempdir.name
        self.login("admin")
        try:
            response=self.http.post("/equipment/add",data={
                "name":"Split Invalid Contract",
                "client_id":str(self.ids["client"]),
                "serial_number":"CONTRACT-INVALID",
                "maintenance_interval":"six"},
                headers={"Referer":"http://localhost/equipment/add"})
            self.no_server_error(response,"equipment invalid interval")
        except ValueError as exc:
            self.fail(f"Unhandled maintenance_interval parsing: {exc}")

    def test_upload_image_resize_restriction_and_invalid_bytes(self):
        with self.app.app_context():
            self.assertIsNone(save_and_resize_image(None,"work_orders"))
            img=Image.new("RGBA",(1600,800),(230,40,40,200))
            buf=io.BytesIO();img.save(buf,format="PNG");buf.seek(0)
            uploaded=FileStorage(stream=buf,filename="Imagem.png")
            stored=save_and_resize_image(uploaded,"work_orders",target_width=800)
            path=os.path.join(self.app.config["UPLOAD_ROOT"],*stored.split("/"))
            self.assertTrue(os.path.isfile(path))
            with Image.open(path) as saved:
                self.assertEqual(saved.format,"JPEG")
                self.assertEqual(saved.size,(800,400))
            with self.assertRaises(ValueError):
                save_and_resize_image(FileStorage(stream=io.BytesIO(b"no"),
                    filename="evil.exe"),"work_orders")
            with self.assertRaises(ValueError):
                save_and_resize_image(FileStorage(stream=io.BytesIO(b"not png"),
                    filename="bad.png"),"work_orders")

    def test_photo_url_preserves_absolute_and_builds_internal_route(self):
        with self.app.test_request_context():
            self.assertIsNone(get_workorder_photo_url(None))
            self.assertEqual(get_workorder_photo_url("/static/a.jpg"),"/static/a.jpg")
            self.assertEqual(get_workorder_photo_url("https://cdn.test/a.jpg"),
                             "https://cdn.test/a.jpg")
            self.assertIn("/services/uploads/work-orders/",
                          get_workorder_photo_url("work_orders/a.jpg"))


if __name__=="__main__":
    import unittest
    unittest.main()
