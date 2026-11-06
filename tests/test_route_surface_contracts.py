"""Inventory-driven contracts for every registered Flask route.

All HTTP calls use an isolated Flask test client and SQLite database.
Mutation endpoints are exercised only in their unauthenticated state.
"""
import re
from collections import Counter

from flask import url_for
from sqlalchemy import select, func

from app import db
from app.models.client import Client
from app.models.equipment import Equipment
from app.models.finance import FinancialTransaction
from app.models.user import User
from app.models.workorder import WorkOrder
from contract_support import ContractCase


def concrete_path(rule, ids):
    """Replace Flask path parameters without contacting real data."""
    blueprint = rule.endpoint.split(".", 1)[0]
    def value(match):
        typ, name = match.group(1), match.group(2)
        if typ == "path":
            return "missing-file.txt"
        if typ == "uuid":
            return "00000000-0000-0000-0000-000000000001"
        if typ == "float":
            return "1.0"
        if typ == "int":
            if name == "client_id": return str(ids["client"])
            if name == "equip_id": return str(ids["equipment"])
            if name == "service_id": return str(ids["service"])
            if name in ("wo_id", "workorder_id"): return str(ids["workorder"])
            if name == "expense_id": return "999999"
            if name == "schedule_id": return "999999"
            if name == "user_id": return str(ids["user"])
            if name == "id":
                return str({
                    "clients": ids["client"], "equipment": ids["equipment"],
                    "finance": ids["transaction"], "services": ids["workorder"],
                    "technician": ids["user"]
                }.get(blueprint, 999999))
            return "999999"
        return "invalid-token" if name == "token" else "not-found"
    return re.sub(r"<(?:(int|float|path|uuid|string):)?([^>]+)>",
                  value, rule.rule)


class RouteSurfaceContracts(ContractCase):
    """Exercise the entire request map; failures remain visible, never silenced."""

    def all_rules(self):
        return sorted((r for r in self.app.url_map.iter_rules()
                       if r.endpoint != "static"),
                      key=lambda r: r.rule)

    def test_every_registered_route_is_in_the_inventory(self):
        rules = self.all_rules()
        names = Counter(r.endpoint.split(".", 1)[0] for r in rules)
        self.assertGreaterEqual(len(rules), 90, names)
        required = {
            "auth", "admin", "clients", "client_portal", "common_portal",
            "equipment", "finance", "main", "maintenance", "push",
            "reports", "secretary", "services", "tech",
        }
        self.assertFalse(required - names.keys(), required - names.keys())
        self.assertTrue(all(r.methods for r in rules))
        print("ROUTE_INVENTORY", len(rules), dict(sorted(names.items())))

    def test_every_get_route_anonymous_returns_without_server_failure(self):
        scanned = 0
        for rule in self.all_rules():
            if "GET" not in rule.methods:
                continue
            path = concrete_path(rule, self.ids)
            with self.subTest(route=rule.endpoint, path=path):
                response = self.http.get(path)
                self.no_server_error(response, path)
            scanned += 1
        print("ANONYMOUS_GET_ROUTES_SCANNED", scanned)

    def test_every_post_route_anonymous_returns_without_server_failure(self):
        count = 0
        initial = self._counts()
        for rule in self.all_rules():
            if "POST" not in rule.methods:
                continue
            path = concrete_path(rule, self.ids)
            with self.subTest(route=rule.endpoint, path=path):
                response = self.http.post(path, data={},
                    headers={"Referer": f"http://localhost{path}"})
                self.no_server_error(response, f"POST {path}")
            count += 1
        self.assertEqual(initial, self._counts(),
                         "Anonymous HTTP requests changed business data")
        print("ANONYMOUS_POST_ROUTES_SCANNED", count)

    def _counts(self):
        with self.app.app_context():
            return (db.session.query(Client).count(),
                    db.session.query(Equipment).count(),
                    db.session.query(WorkOrder).count(),
                    db.session.query(FinancialTransaction).count(),
                    db.session.query(User).count())

    def test_public_login_rejects_wrong_credentials(self):
        response = self.http.post("/auth/login",
            data={"email":"admin@contract.local","password":"wrong"},
            headers={"Referer":"http://localhost/auth/login"})
        self.assertIn(response.status_code,(200,302))
        dashboard = self.http.get("/admin/dashboard")
        self.assertNotEqual(dashboard.status_code,200)

    def test_anonymous_sensitive_dashboard_access_is_denied(self):
        cases = [
            "/admin/dashboard", "/admin/settings", "/admin/audit-logs",
            "/clients/", "/equipment/", "/services/", "/services/add",
            "/admin/finance/", "/admin/finance/transactions", "/reports/",
            "/secretary/dashboard", "/tech/dashboard",
            "/client/dashboard", "/maintenance/", "/push/preferences",
        ]
        for path in cases:
            with self.subTest(path=path):
                result = self.http.get(path)
                self.no_server_error(result,path)
                self.assertNotEqual(result.status_code,200,
                    f"Anonymous access to protected page: {path}")

    def test_authenticated_administrator_page_matrix(self):
        self.login("admin")
        # Non-mutating GET pages. No fixture IDs for user-specific side effects.
        paths = [
            "/admin/dashboard", "/admin/settings", "/admin/audit-logs",
            "/clients/", "/clients/add", "/clients/search",
            "/equipment/", "/equipment/add", "/services/", "/services/add",
            "/services/catalog", "/services/history", "/services/routes",
            "/admin/finance/", "/admin/finance/transactions",
            "/admin/finance/transaction/add", "/admin/finance/categories",
            "/maintenance/", "/maintenance/add", "/reports/",
            "/reports/finance", "/reports/clients", "/reports/services",
            "/secretary/dashboard", "/secretary/workorders/pending",
            "/push/preferences", "/notifications/today",
        ]
        tested = 0
        for path in paths:
            with self.subTest(path=path):
                response = self.http.get(path)
                self.no_server_error(response, f"admin GET {path}")
            tested += 1
        print("ADMIN_GET_PAGES_SCANNED", tested)

    def test_non_admin_roles_cannot_open_administration(self):
        protected = ["/admin/dashboard", "/admin/settings", "/admin/audit-logs"]
        for role in ("secretary","user","client","common"):
            self.login(role)
            for path in protected:
                with self.subTest(role=role,path=path):
                    resp=self.http.get(path)
                    self.no_server_error(resp, path)
                    self.assertNotEqual(resp.status_code,200,
                        f"{role} received administration content")

    def test_roles_landing_pages_do_not_crash(self):
        for role in ("secretary","user","client","common"):
            self.login(role)
            path = {"secretary":"/secretary/dashboard",
                    "user":"/tech/dashboard",
                    "client":"/client/dashboard",
                    "common":"/common/dashboard"}[role]
            with self.subTest(role=role):
                resp=self.http.get(path)
                self.no_server_error(resp,path)

    def test_invalid_numeric_route_parameters_are_handled(self):
        for path in (
            "/clients/edit/999999", "/equipment/edit/999999",
            "/services/view/999999", "/services/edit/999999",
            "/admin/finance/transaction/edit/999999", "/tech/edit/999999",
            "/services/catalog/999999", "/client/service/999999",
        ):
            self.login("admin")
            with self.subTest(path=path):
                response=self.http.get(path)
                self.no_server_error(response,path)

    def test_mutating_endpoints_deny_unauthenticated_requests(self):
        self.assertEqual(self.http.get("/services/check_duplicate").status_code,302)
        paths = [
            "/services/add", "/clients/add", "/equipment/add",
            "/admin/finance/transaction/add", "/admin/finance/categories",
            "/maintenance/add", "/tech/add", "/secretary/workorder/schedule",
        ]
        initial=self._counts()
        for path in paths:
            with self.subTest(path=path):
                response=self.http.post(path,data={},
                    headers={"Referer":f"http://localhost{path}"})
                self.no_server_error(response,path)
                self.assertNotEqual(response.status_code,200)
        self.assertEqual(initial,self._counts())

    def test_duplicate_check_frontend_and_backend_agree_on_http_method(self):
        """The form GET check must return an existing open OS as JSON."""
        self.login("admin")
        path=(f"/services/check_duplicate?client_id={self.ids['client']}"
              f"&equipment_id={self.ids['equipment']}"
              f"&service_id={self.ids['service']}")
        response=self.http.get(path)
        self.assertEqual(response.status_code,200)
        self.assertIs(response.get_json()["exists"], True)
        self.assertIs(response.get_json()["duplicate"], True)

    def test_authenticated_admin_all_safe_get_routes_no_5xx(self):
        """Broad authenticated coverage without mutating the seed database."""
        # An absent VAPID key legitimately returns 503; supply a fake local key
        # when asserting all configured GET routes respond without a 5xx.
        self.app.config["VAPID_PUBLIC_KEY"] = "test-only-vapid-key"
        self.login("admin")
        before=self._counts()
        scanned=0
        excluded={"/maintenance/<int:schedule_id>/workorder",
                  "/admin/client-preview/exit"}
        for rule in self.all_rules():
            if "GET" not in rule.methods or rule.rule in excluded:
                continue
            path=concrete_path(rule,self.ids)
            with self.subTest(route=rule.endpoint,path=path):
                response=self.http.get(path)
                self.no_server_error(response,f"admin GET {path}")
            scanned+=1
        self.assertEqual(before,self._counts(),
                         "An authenticated GET unexpectedly changed business data")
        print("AUTHENTICATED_GET_ROUTES_SCANNED",scanned)

    def test_push_vapid_contract_handles_unconfigured_and_configured(self):
        self.login('admin')
        self.app.config['VAPID_PUBLIC_KEY'] = ''
        missing = self.http.get('/notifications/vapid-public-key')
        self.assertEqual(missing.status_code, 503)
        self.assertEqual(missing.get_json(), {'enabled': False})
        self.app.config['VAPID_PUBLIC_KEY'] = 'test-only-vapid-key'
        configured = self.http.get('/notifications/vapid-public-key')
        self.assertEqual(configured.status_code, 200)
        self.assertEqual(configured.get_json()['publicKey'], 'test-only-vapid-key')

    def test_unknown_route_returns_404(self):
        self.assertEqual(self.http.get("/definitely-not-an-endpoint").status_code,404)

    def test_critical_routes_have_expected_methods(self):
        routes = {r.rule:r.methods for r in self.all_rules()}
        for path in ("/services/add", "/auth/login", "/clients/add",
                     "/equipment/add", "/admin/finance/transaction/add",
                     "/secretary/workorder/schedule"):
            self.assertTrue({"GET","POST"}.issubset(routes[path]),path)
        for path in ("/services/delete/<int:id>", "/auth/logout"):
            self.assertIn("POST",routes[path])
            self.assertNotIn("GET",routes[path])


if __name__ == "__main__":
    import unittest
    unittest.main()
