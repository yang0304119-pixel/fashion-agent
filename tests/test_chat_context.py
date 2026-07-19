from unittest.mock import patch

from tests.api_test_support import ApiTestCase, CUSTOMER_PASSWORD


class ChatContextApiTests(ApiTestCase):
    def customer_headers(self):
        token = self.login("customer_a", CUSTOMER_PASSWORD)
        return self.auth_headers(token)

    def test_product_context_is_reloaded_and_injected_as_trusted_slots(self):
        headers = self.customer_headers()

        def echo_state(state):
            return {
                **state,
                "intent": "inventory_query",
                "confidence": 0.95,
                "final_answer": "测试完成",
                "retrieved_sources": [],
            }

        with patch("app.routers.chat.agent_app.invoke", side_effect=echo_state) as invoke:
            response = self.client.post(
                "/api/chat",
                headers=headers,
                json={
                    "session_id": "product-context-session",
                    "message": "这件有货吗",
                    "context": {"type": "product", "product_id": 1},
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        state = invoke.call_args.args[0]
        self.assertEqual(state["collected_slots"]["product_id"], 1)
        self.assertEqual(state["chat_context"]["product_name"], "租户一羽绒服")
        self.assertEqual(state["chat_context"]["price"], 499.0)
        self.assertEqual(state["chat_context"]["stock"], 20)
        self.assertNotIn("user_id", response.request.content.decode("utf-8"))

    def test_client_cannot_override_product_or_identity_fields(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "forged-product-session",
                "message": "这件有货吗",
                "user_id": 2,
                "tenant_id": 2,
                "context": {
                    "type": "product",
                    "product_id": 1,
                    "price": 0,
                    "stock": 999999,
                },
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_order_context_rejects_another_users_order(self):
        with patch("app.routers.chat.agent_app.invoke") as invoke:
            response = self.client.post(
                "/api/chat",
                headers=self.customer_headers(),
                json={
                    "session_id": "forged-order-session",
                    "message": "这个订单发货了吗",
                    "context": {"type": "order", "order_id": 11001},
                },
            )
        self.assertEqual(response.status_code, 404)
        invoke.assert_not_called()

    def test_order_context_injects_only_current_users_order(self):
        headers = self.customer_headers()

        def echo_state(state):
            return {
                **state,
                "intent": "order_query",
                "confidence": 0.95,
                "final_answer": "测试完成",
                "retrieved_sources": [],
            }

        with patch("app.routers.chat.agent_app.invoke", side_effect=echo_state) as invoke:
            response = self.client.post(
                "/api/chat",
                headers=headers,
                json={
                    "session_id": "owned-order-session",
                    "message": "这个订单发货了吗",
                    "context": {"type": "order", "order_id": 10001},
                },
            )
        self.assertEqual(response.status_code, 200, response.text)
        state = invoke.call_args.args[0]
        self.assertEqual(state["collected_slots"]["order_id"], 10001)
        self.assertEqual(state["chat_context"]["status"], "shipped")
        self.assertEqual(state["chat_context"]["amount"], 499.0)

    def test_product_context_reaches_inventory_node_without_name_extraction(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "product-full-path-session",
                "message": "这件商品现在有货吗",
                "context": {"type": "product", "product_id": 1},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["intent"], "inventory_query")
        self.assertIn("租户一羽绒服", response.json()["answer"])
        self.assertIn("库存 20 件", response.json()["answer"])

    def test_order_context_reaches_order_node_without_order_number_in_text(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "order-full-path-session",
                "message": "这个订单发货了吗",
                "context": {"type": "order", "order_id": 10001},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["intent"], "order_query")
        self.assertIn("订单 10001", response.json()["answer"])
        self.assertIn("已发货", response.json()["answer"])

    def test_product_price_comes_from_database_not_browser_context(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "product-price-session",
                "message": "这件多少钱",
                "context": {"type": "product", "product_id": 1},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["intent"], "product_query")
        self.assertIn("499.00 元", response.json()["answer"])

    def test_product_card_supplies_context_for_size_recommendation(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "product-size-session",
                "message": "我175cm、70kg，喜欢正常合身",
                "context": {"type": "product", "product_id": 1},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["intent"], "size_recommend")
        self.assertIn("L 码", response.json()["answer"])

    def test_order_card_supplies_context_for_refund_workflow(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "order-refund-session",
                "message": "我不想要了，申请退款",
                "context": {"type": "order", "order_id": 10007},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["intent"], "refund_request")
        self.assertEqual(payload["message_type"], "refund_status")
        self.assertEqual(payload["payload"]["order_id"], 10007)
        self.assertEqual(payload["payload"]["status"], "succeeded")
