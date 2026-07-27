from app.core.config import settings
from tests.api_test_support import ApiTestCase


class DemoStoreApiTests(ApiTestCase):
    def test_demo_session_uses_server_configured_member(self):
        response = self.client.post(
            "/api/demo-store/session",
            json={"tenant_id": 2, "user_id": 4, "username": "admin_a"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["id"], settings.DEMO_STORE_USER_ID)
        self.assertEqual(
            payload["user"]["tenant_id"],
            settings.DEMO_STORE_TENANT_ID,
        )
        self.assertEqual(payload["user"]["role"], "customer")
        self.assertEqual(payload["user"]["permissions"], [])
        self.assertEqual(payload["user"]["home_view"], "workbench")
        self.assertTrue(payload["user"]["role_label"])

        orders = self.client.get(
            "/api/orders",
            headers=self.auth_headers(payload["access_token"]),
        )
        self.assertEqual(orders.status_code, 200)
        self.assertEqual(
            {item["id"] for item in orders.json()["data"]},
            {10001, 10002, 10007},
        )

    def test_demo_session_is_disabled_in_production(self):
        original_environment = settings.ENVIRONMENT
        settings.ENVIRONMENT = "production"
        try:
            response = self.client.post("/api/demo-store/session")
        finally:
            settings.ENVIRONMENT = original_environment
        self.assertEqual(response.status_code, 404)

    def test_product_picker_only_returns_current_tenant_products(self):
        session = self.client.post("/api/demo-store/session").json()
        headers = self.auth_headers(session["access_token"])

        listing = self.client.get("/api/demo-store/products", headers=headers)
        self.assertEqual(listing.status_code, 200, listing.text)
        product_ids = {item["product_id"] for item in listing.json()["data"]}
        self.assertEqual(product_ids, {1, 7})
        self.assertNotIn(20, product_ids)

        detail = self.client.get("/api/demo-store/products/1", headers=headers)
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["data"]["price"], 499.0)
        self.assertEqual(detail.json()["data"]["stock"], 20)

        cross_tenant = self.client.get(
            "/api/demo-store/products/20",
            headers=headers,
        )
        self.assertEqual(cross_tenant.status_code, 404)
