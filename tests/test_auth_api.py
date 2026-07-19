from tests.api_test_support import ApiTestCase


class AuthApiTests(ApiTestCase):
    def test_unauthenticated_chat_returns_401(self):
        response = self.client.post(
            "/api/chat",
            json={"session_id": "auth-test-session", "message": "你好"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_login_token_can_access_current_user(self):
        token = self.login("customer_a", "CustomerPassword123!")
        response = self.client.get(
            "/api/auth/me",
            headers=self.auth_headers(token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "customer_a")
        self.assertEqual(response.json()["tenant_id"], 1)
