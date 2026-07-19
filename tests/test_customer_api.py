from tests.api_test_support import ApiTestCase, CUSTOMER_PASSWORD


class CustomerApiTests(ApiTestCase):
    def test_customer_a_cannot_view_customer_b_order(self):
        token = self.login("customer_a", CUSTOMER_PASSWORD)
        headers = self.auth_headers(token)

        detail = self.client.get("/api/orders/11001", headers=headers)
        self.assertEqual(detail.status_code, 404)

        listing = self.client.get("/api/orders", headers=headers)
        self.assertEqual(listing.status_code, 200)
        order_ids = {item["id"] for item in listing.json()["data"]}
        self.assertNotIn(11001, order_ids)
        self.assertEqual(order_ids, {10001, 10002, 10007})

    def test_customer_cannot_access_admin_api(self):
        token = self.login("customer_a", CUSTOMER_PASSWORD)
        response = self.client.get(
            "/api/admin/orders",
            headers=self.auth_headers(token),
        )
        self.assertEqual(response.status_code, 403)
