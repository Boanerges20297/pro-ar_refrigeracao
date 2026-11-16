"""Regression tests for CSRF session loss in the production login form.

Uses the isolated ContractCase database; never calls production.
"""
import re

from contract_support import ContractCase


class LoginCsrfRecoveryContracts(ContractCase):
    def setUp(self):
        super().setUp()
        self.app.config['WTF_CSRF_ENABLED'] = True

    def _csrf_token(self, response):
        match = re.search(rb'name="csrf_token"\s+value="([^"]+)"', response.data)
        self.assertIsNotNone(match, 'Login must render a CSRF token')
        return match.group(1).decode('ascii')

    def test_missing_session_recovers_without_authentication(self):
        old_client = self.app.test_client()
        stale_token = self._csrf_token(old_client.get('/auth/login'))
        client = self.app.test_client()

        rejected = client.post('/auth/login', data={
            'email': 'admin@contract.local',
            'password': 'Teste12345',
            'csrf_token': stale_token,
        })
        self.assertEqual(rejected.status_code, 303)
        self.assertEqual(rejected.headers['Location'], '/auth/login')
        self.assertIn('no-store', rejected.headers['Cache-Control'])
        self.assertFalse(any('access_token_cookie=' in cookie
                             for cookie in rejected.headers.getlist('Set-Cookie')))
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)

        refreshed = client.get('/auth/login')
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn(b'formul\xc3\xa1rio expirou', refreshed.data)
        self.assertIn('no-store', refreshed.headers['Cache-Control'])
        token = self._csrf_token(refreshed)

        valid = client.post('/auth/login', data={
            'email': 'admin@contract.local',
            'password': 'Teste12345',
            'csrf_token': token,
        })
        self.assertEqual(valid.status_code, 302)
        self.assertIn('/admin/dashboard', valid.headers['Location'])
        self.assertEqual(client.get('/admin/dashboard').status_code, 200)

    def test_mismatched_browser_session_recovers(self):
        old_client = self.app.test_client()
        old_token = self._csrf_token(old_client.get('/auth/login'))
        client = self.app.test_client()
        self._csrf_token(client.get('/auth/login'))
        result = client.post('/auth/login', data={
            'email': 'admin@contract.local',
            'password': 'Teste12345',
            'csrf_token': old_token,
        })
        self.assertEqual(result.status_code, 303)
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)

    def test_missing_and_forged_csrf_remain_blocked(self):
        client = self.app.test_client()
        for path in ('/auth/login', '/auth/forgot-password'):
            with self.subTest(path=path):
                rejected = client.post(path, data={
                    'email': 'admin@contract.local',
                    'password': 'Teste12345',
                })
                self.assertEqual(rejected.status_code, 400)
        client.get('/auth/login')  # Establish a session before submitting a forged token.
        forged = client.post('/auth/login', data={
            'email': 'admin@contract.local',
            'password': 'Teste12345',
            'csrf_token': 'forged-token',
        })
        self.assertEqual(forged.status_code, 400)
        self.assertNotEqual(client.get('/admin/dashboard').status_code, 200)
