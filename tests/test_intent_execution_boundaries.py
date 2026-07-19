from decimal import Decimal
from unittest.mock import patch

from app.agent.nodes.router_node import _recent_messages
from app.models import AgentTrace, Order, RefundRequest
from tests.api_test_support import ApiTestCase, CUSTOMER_PASSWORD


class IntentExecutionBoundaryTests(ApiTestCase):
    def customer_headers(self, username: str = "customer_a"):
        token = self.login(username, CUSTOMER_PASSWORD)
        return self.auth_headers(token)

    def test_cancel_order_routes_to_human_without_mutating_order(self):
        response = self.client.post(
            "/api/chat",
            headers=self.customer_headers(),
            json={
                "session_id": "cancel-handoff-session",
                "message": "帮我取消订单10001",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["intent"], "after_sales_request")
        self.assertIn("人工", response.json()["answer"])
        db = self.Session()
        self.assertEqual(db.get(Order, 10001).status, "shipped")
        db.close()

    def test_refund_status_query_is_readonly_and_owner_scoped(self):
        db = self.Session()
        db.add(
            RefundRequest(
                tenant_id=1,
                order_id=10001,
                user_id=1,
                reason="质量问题",
                amount=Decimal("499.00"),
                risk_level="high",
                human_review=True,
                status="reviewing",
                idempotency_key="status-query-test",
                gateway_mode="manual",
            )
        )
        db.commit()
        db.close()

        owner = self.client.post(
            "/api/chat",
            headers=self.customer_headers("customer_a"),
            json={
                "session_id": "refund-status-owner",
                "message": "我的订单10001退款到哪了",
            },
        )
        other_user = self.client.post(
            "/api/chat",
            headers=self.customer_headers("customer_b"),
            json={
                "session_id": "refund-status-other",
                "message": "我的订单10001退款到哪了",
            },
        )

        self.assertEqual(owner.status_code, 200, owner.text)
        self.assertEqual(owner.json()["intent"], "refund_status_query")
        self.assertIn("等待人工审核", owner.json()["answer"])
        self.assertEqual(other_user.status_code, 200, other_user.text)
        self.assertNotIn("等待人工审核", other_user.json()["answer"])
        db = self.Session()
        self.assertEqual(db.query(RefundRequest).count(), 1)
        self.assertEqual(db.get(Order, 10001).status, "shipped")
        db.close()

    def test_recent_history_is_scoped_by_tenant_user_and_session(self):
        db = self.Session()
        db.add_all(
            [
                AgentTrace(
                    tenant_id=1,
                    user_id=1,
                    session_id="history-scope-session",
                    node_name="workflow",
                    message="本用户上一轮",
                ),
                AgentTrace(
                    tenant_id=1,
                    user_id=2,
                    session_id="history-scope-session",
                    node_name="workflow",
                    message="同租户其他用户秘密",
                ),
                AgentTrace(
                    tenant_id=2,
                    user_id=4,
                    session_id="history-scope-session",
                    node_name="workflow",
                    message="其他租户秘密",
                ),
            ]
        )
        db.commit()
        db.close()

        with patch("app.agent.nodes.router_node.SessionLocal", self.Session):
            messages = _recent_messages(
                {
                    "tenant_id": 1,
                    "user_id": 1,
                    "session_id": "history-scope-session",
                    "message": "当前消息",
                }
            )

        self.assertEqual(messages, ["本用户上一轮"])

