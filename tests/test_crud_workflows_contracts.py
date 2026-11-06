"""Cross-module CRUD and state-transition tests with isolated test data."""
import os
from datetime import datetime
from unittest.mock import patch

from app import db
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.finance import FinancialTransaction
from app.models.maintenance import MaintenanceSchedule
from app.models.workorder import WorkOrder
from app.models.workorder_expense import WorkOrderExpense
from app.utils.finance import sync_wo_to_finance
from contract_support import ContractCase


class CrudWorkflowContracts(ContractCase):
    def test_edit_order_completion_syncs_finance(self):
        self.login("admin")
        order_id=self.ids["workorder"]
        response=self.http.post(f"/services/edit/{order_id}",data={
            "status":"Completed","description":"Concluido em teste",
            "total_value":"235.75","is_paid":"on",
            "scheduled_date":"2026-12-10T09:00",
        },headers={"Referer":f"http://localhost/services/edit/{order_id}"})
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            order=db.session.get(WorkOrder,order_id)
            self.assertEqual(order.status,"Completed")
            self.assertIsNotNone(order.completed_date)
            self.assertTrue(order.is_paid)
            self.assertEqual(order.total_value,235.75)
            revenue=FinancialTransaction.query.filter_by(
                work_order_id=order_id,is_automated=True,
                work_order_expense_id=None).one()
            self.assertEqual(revenue.amount,235.75)
            self.assertEqual(revenue.status,"paid")

    def test_completed_order_cannot_be_edited_by_technician(self):
        with self.app.app_context():
            order=db.session.get(WorkOrder,self.ids["workorder"])
            order.status="Completed"
            order.description="Protegido"
            db.session.commit()
        self.login("user")
        resp=self.http.post(f"/services/edit/{self.ids['workorder']}",data={
            "status":"Pending","description":"Alteracao nao permitida",
            "total_value":"0"},
            headers={"Referer":f"http://localhost/services/edit/{self.ids['workorder']}"})
        self.no_server_error(resp,"technician edits completed order")
        with self.app.app_context():
            order=db.session.get(WorkOrder,self.ids["workorder"])
            self.assertEqual(order.status,"Completed")
            self.assertEqual(order.description,"Protegido")

    def test_client_cannot_edit_order(self):
        self.login("client")
        with self.app.app_context():
            before=WorkOrder.query.get(self.ids["workorder"]).description
        response=self.http.post(f"/services/edit/{self.ids['workorder']}",
            data={"status":"Completed","description":"Abuso"},
            headers={"Referer":f"http://localhost/services/edit/{self.ids['workorder']}"})
        self.no_server_error(response,"client mutation")
        with self.app.app_context():
            self.assertEqual(db.session.get(WorkOrder,self.ids["workorder"]).description,before)

    def test_workorder_expense_create_and_delete_syncs_finance(self):
        self.login("admin")
        oid=self.ids["workorder"]
        post=self.http.post(f"/services/edit/{oid}/expenses/add",json={
            "description":"Material teste","category":"Peca",
            "quantity":2,"unit_price":19.50},
            headers={"Referer":f"http://localhost/services/edit/{oid}"})
        self.assertEqual(post.status_code,201)
        data=post.get_json()
        self.assertTrue(data["ok"])
        expense_id=data["expense"]["id"]
        self.assertEqual(data["expense"]["total"],39)
        with self.app.app_context():
            self.assertEqual(FinancialTransaction.query.filter_by(
                work_order_expense_id=expense_id,is_automated=True).count(),1)
        out=self.http.post(f"/services/edit/{oid}/expenses/{expense_id}/delete",
            headers={"Referer":f"http://localhost/services/edit/{oid}"})
        self.assertEqual(out.status_code,200)
        with self.app.app_context():
            self.assertIsNone(db.session.get(WorkOrderExpense,expense_id))
            self.assertEqual(FinancialTransaction.query.filter_by(
                work_order_expense_id=expense_id).count(),0)

    def test_admin_deletes_workorder_and_linked_revenue(self):
        with self.app.app_context():
            order=db.session.get(WorkOrder,self.ids["workorder"])
            sync_wo_to_finance(order)
        self.login("admin")
        response=self.http.post(f"/services/delete/{self.ids['workorder']}",
            headers={"Referer":f"http://localhost/services/"})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.get_json()["ok"])
        with self.app.app_context():
            self.assertIsNone(db.session.get(WorkOrder,self.ids["workorder"]))
            self.assertEqual(FinancialTransaction.query.filter_by(
                work_order_id=self.ids["workorder"],is_automated=True).count(),0)

    def test_related_client_deletion_does_not_orphan_equipment(self):
        self.login("admin")
        response=self.http.post(f"/clients/delete/{self.ids['client']}",
            headers={"Referer":"http://localhost/clients/"})
        self.no_server_error(response,"delete client with FKs")
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Client,self.ids["client"]))
            self.assertIsNotNone(db.session.get(Equipment,self.ids["equipment"]))

    def test_equipment_delete_preserves_orders_via_nullable_fk(self):
        self.login("admin")
        response=self.http.post(f"/equipment/delete/{self.ids['equipment']}",
            headers={"Referer":"http://localhost/equipment/"})
        self.no_server_error(response,"equipment deletion with work orders")
        with self.app.app_context():
            order=db.session.get(WorkOrder,self.ids["workorder"])
            self.assertIsNotNone(order)
            self.assertIsNone(db.session.get(Equipment,self.ids["equipment"]))
            self.assertIsNone(order.equipment_id)

    def test_regenerate_qr_image_through_both_endpoints(self):
        self.app.static_folder=self.tempdir.name
        self.login("admin")
        equip_id=self.ids["equipment"]
        first=self.http.post(f"/equipment/regenerate-qr/{equip_id}",
            headers={"Referer":"http://localhost/equipment/"})
        self.assertEqual(first.status_code,302)
        second=self.http.post(f"/equipment/generate-qr-ajax/{equip_id}",
            headers={"Referer":"http://localhost/equipment/"})
        self.assertEqual(second.status_code,200)
        self.assertTrue(second.get_json()["success"])
        self.assertTrue(os.path.isfile(os.path.join(
            self.tempdir.name,"img","qrcodes",f"equip_{equip_id}.png")))

    def test_automated_finance_entry_cannot_be_deleted_directly(self):
        with self.app.app_context():
            wo=db.session.get(WorkOrder,self.ids["workorder"])
            sync_wo_to_finance(wo)
            entry=FinancialTransaction.query.filter_by(
                work_order_id=wo.id,is_automated=True).one()
            entry_id=entry.id
        self.login("admin")
        result=self.http.post(f"/admin/finance/transaction/delete/{entry_id}",
            headers={"Referer":"http://localhost/admin/finance/transactions"})
        self.assertEqual(result.status_code,302)
        with self.app.app_context():
            self.assertIsNotNone(db.session.get(FinancialTransaction,entry_id))

    def test_maintenance_schedule_can_create_workorder(self):
        self.login("admin")
        add=self.http.post("/maintenance/add",data={
            "equipment_id":str(self.ids["equipment"]),
            "next_maintenance_date":"2026-12-25",
            "description":"Manutencao em teste"},
            headers={"Referer":"http://localhost/maintenance/add"})
        self.no_server_error(add,"maintenance add")
        with self.app.app_context():
            schedule=MaintenanceSchedule.query.filter_by(
                description="Manutencao em teste").one()
            schedule_id=schedule.id
        open_result=self.http.get(f"/maintenance/{schedule_id}/workorder")
        self.no_server_error(open_result,"maintenance to work order")
        with self.app.app_context():
            schedule=db.session.get(MaintenanceSchedule,schedule_id)
            self.assertIsNotNone(schedule.workorder_id)
            self.assertEqual(schedule.work_order.client_id,self.ids["client"])

    def test_secretary_schedule_requires_valid_service_reference(self):
        """A dedicated schedule form must never insert an incomplete WorkOrder."""
        self.login("secretary")
        before=self._workorder_count()
        response=self.http.post("/secretary/workorder/schedule",data={
            "client_id":str(self.ids["client"]),
            "equipment_id":str(self.ids["equipment"]),
            "technician_id":str(self.ids["user"]),
            "description":"Agendamento pela secretaria",
            "scheduled_date":"2026-12-26T10:00"},
            headers={"Referer":"http://localhost/secretary/workorder/schedule"})
        self.no_server_error(response,"secretary schedule workorder")
        self.assertEqual(self._workorder_count(),before+1,
            "Secretary booking route did not persist a valid OS")

    def _workorder_count(self):
        with self.app.app_context():
            return WorkOrder.query.count()


if __name__=="__main__":
    import unittest
    unittest.main()
