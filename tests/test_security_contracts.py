"""Authentication, authorization, privacy and security regression contracts."""
from app import db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.utils.security import (
    build_password_version, build_session_nonce,
    build_user_agent_fingerprint, is_password_strong,
    is_same_origin_request,
)
from contract_support import ContractCase


class SecurityContracts(ContractCase):
    def test_password_strength_rules(self):
        self.assertTrue(is_password_strong("Admin1234"))
        self.assertTrue(is_password_strong("lowercase123"))
        for weak in ("", "short1A", "NoNumbersHere", "12345678"):
            with self.subTest(password_type=weak[:3]):
                self.assertFalse(is_password_strong(weak))

    def test_password_hash_verifies_and_does_not_store_plaintext(self):
        with self.app.app_context():
            u=db.session.get(User,self.ids["admin"])
            self.assertTrue(u.check_password("Teste12345"))
            self.assertFalse(u.check_password("not-the-password"))
            self.assertNotIn("Teste12345",u.password_hash)
            self.assertNotEqual(build_password_version(u.password_hash),
                                build_password_version("other-hash"))

    def test_session_nonces_are_unpredictable(self):
        a,b=build_session_nonce(),build_session_nonce()
        self.assertNotEqual(a,b)
        self.assertGreaterEqual(len(a),32)
        self.assertGreaterEqual(len(b),32)

    def test_user_agent_fingerprint_is_stable_and_sensitive(self):
        self.assertEqual(build_user_agent_fingerprint("BrowserX"),
                         build_user_agent_fingerprint(" BrowserX "))
        self.assertNotEqual(build_user_agent_fingerprint("BrowserX"),
                            build_user_agent_fingerprint("BrowserY"))

    def test_origin_enforcement_contract(self):
        host="https://app.example.test/"
        cases=[
            ("https://app.example.test",None,True),
            (None,"https://app.example.test/clients/add",True),
            ("https://attacker.example",None,False),
            (None,"https://attacker.example/clients/add",False),
            (None,None,False),
        ]
        for origin,referer,expected in cases:
            with self.subTest(origin=origin,referer=referer):
                self.assertEqual(is_same_origin_request(origin,referer,host),
                                 expected)

    def test_login_success_creates_httponly_auth_cookie(self):
        response=self.login("admin").get("/admin/dashboard")
        self.assertEqual(response.status_code,200)
        client=self.app.test_client()
        login=client.post("/auth/login",
            data={"email":"admin@contract.local","password":"Teste12345"},
            headers={"Referer":"http://localhost/auth/login"})
        self.assertEqual(login.status_code,302)
        cookies=login.headers.getlist("Set-Cookie")
        self.assertTrue(any("HttpOnly" in cookie for cookie in cookies))
        self.assertFalse(any("Teste12345" in cookie for cookie in cookies))

    def test_wrong_password_does_not_authenticate(self):
        response=self.http.post("/auth/login",data={
            "email":"admin@contract.local","password":"wrong-password"},
            headers={"Referer":"http://localhost/auth/login"})
        self.no_server_error(response,"login invalid password")
        self.assertNotEqual(self.http.get("/admin/dashboard").status_code,200)

    def test_failed_login_is_recorded_in_audit(self):
        """Invalid login attempts must leave an audit record for investigation."""
        self.http.post("/auth/login",data={
            "email":"admin@contract.local","password":"wrong-password"},
            headers={"Referer":"http://localhost/auth/login"})
        with self.app.app_context():
            db.session.rollback()
            failed=AuditLog.query.filter_by(action="LOGIN",status="error").count()
            self.assertGreaterEqual(failed,1,
                "Failed login cannot be audited (possible null user_id bug)")

    def test_unknown_email_login_is_auditable_without_database_error(self):
        response=self.http.post("/auth/login",data={
            "email":"nonexistent@contract.local","password":"invalid"},
            headers={"Referer":"http://localhost/auth/login"})
        self.no_server_error(response,"unknown email login")
        with self.app.app_context():
            db.session.rollback()
            failed=AuditLog.query.filter_by(action="LOGIN",status="error").count()
            self.assertGreaterEqual(failed,1,
                "Unknown-user login must be auditable without NULL user_id violation")

    def test_inactive_user_does_not_receive_authorization(self):
        with self.app.app_context():
            u=db.session.get(User,self.ids["admin"])
            u.is_active=False
            db.session.commit()
        login=self.http.post("/auth/login",data={
            "email":"admin@contract.local","password":"Teste12345"},
            headers={"Referer":"http://localhost/auth/login"})
        self.no_server_error(login,"inactive login")
        self.assertNotEqual(self.http.get("/admin/dashboard").status_code,200)

    def test_invalid_password_reset_token_does_not_crash(self):
        for method in ("GET","POST"):
            with self.subTest(method=method):
                response=self.http.open("/auth/reset-password/invalid-token",
                                         method=method)
                self.no_server_error(response,"invalid reset token")

    def test_invalid_password_reset_request_does_not_send_email(self):
        response=self.http.post("/auth/forgot-password",data={
            "email":"unknown@contract.local"
        },headers={"Referer":"http://localhost/auth/forgot-password"})
        self.no_server_error(response,"password reset unknown email")

    def test_same_origin_mutation_policy_blocks_cross_site_post(self):
        self.app.config["SECURITY_ENFORCE_SAME_ORIGIN_MUTATIONS"]=True
        rejected=self.http.post("/auth/login",data={
            "email":"admin@contract.local","password":"Teste12345"},
            headers={"Origin":"https://attacker.example.test"})
        self.assertNotEqual(rejected.status_code,200)
        self.assertNotEqual(self.http.get("/admin/dashboard").status_code,200)
        allowed=self.http.post("/auth/login",data={
            "email":"admin@contract.local","password":"Teste12345"},
            headers={"Referer":"http://localhost/auth/login"})
        self.assertEqual(allowed.status_code,302)
        self.assertEqual(self.http.get("/admin/dashboard").status_code,200)

    def test_logout_revokes_access_for_this_client(self):
        self.login("admin")
        self.assertEqual(self.http.get("/admin/dashboard").status_code,200)
        result=self.http.post("/auth/logout",
            headers={"Referer":"http://localhost/auth/logout"})
        self.no_server_error(result,"logout")
        self.assertNotEqual(self.http.get("/admin/dashboard").status_code,200)

    def test_non_admin_cannot_mutate_administrator_license(self):
        self.login("user")
        for path in ("/admin/license","/admin/license/revalidate"):
            with self.subTest(path=path):
                response=self.http.post(path,data={},
                    headers={"Referer":f"http://localhost{path}"})
                self.no_server_error(response,path)
                self.assertNotEqual(response.status_code,200)


if __name__=="__main__":
    import unittest
    unittest.main()
