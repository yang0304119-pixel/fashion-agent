from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models import AgentTrace, RefundRequest, Ticket, UnresolvedCase
from tests.api_test_support import (
    ADMIN_PASSWORD,
    CUSTOMER_PASSWORD,
    ApiTestCase,
)


class AdminApiTests(ApiTestCase):
    def test_dashboard_uses_tenant_scoped_business_counts(self):
        now = datetime.now(UTC).replace(tzinfo=None)
        db = self.Session()
        db.add_all([
            RefundRequest(
                id=1,
                tenant_id=1,
                order_id=10001,
                user_id=1,
                reason="尺码不合适",
                amount=Decimal("499.00"),
                risk_level="high",
                human_review=True,
                status="reviewing",
                idempotency_key="tenant-one-reviewing",
                gateway_mode="mock",
            ),
            RefundRequest(
                id=2,
                tenant_id=1,
                order_id=10002,
                user_id=1,
                reason="模拟渠道失败",
                amount=Decimal("598.00"),
                risk_level="high",
                human_review=True,
                status="failed",
                idempotency_key="tenant-one-failed",
                gateway_mode="mock",
            ),
            RefundRequest(
                id=3,
                tenant_id=2,
                order_id=20001,
                user_id=4,
                reason="跨租户数据",
                amount=Decimal("299.00"),
                risk_level="high",
                human_review=True,
                status="reviewing",
                idempotency_key="tenant-two-reviewing",
                gateway_mode="mock",
            ),
            Ticket(
                id=1,
                tenant_id=1,
                order_id=10001,
                user_id=1,
                type="refund",
                reason="等待处理",
                amount=Decimal("499.00"),
                risk_level="high",
                status="pending",
                human_review=True,
            ),
            Ticket(
                id=2,
                tenant_id=2,
                order_id=20001,
                user_id=4,
                type="refund",
                reason="跨租户工单",
                amount=Decimal("299.00"),
                risk_level="high",
                status="pending",
                human_review=True,
            ),
            UnresolvedCase(
                id=1,
                tenant_id=1,
                user_id=1,
                user_message="怎么保养",
                is_resolved=False,
            ),
            UnresolvedCase(
                id=2,
                tenant_id=2,
                user_id=4,
                user_message="跨租户案例",
                is_resolved=False,
            ),
            AgentTrace(
                id=1,
                tenant_id=1,
                user_id=1,
                session_id="today-session",
                node_name="workflow",
                created_at=now,
            ),
            AgentTrace(
                id=2,
                tenant_id=1,
                user_id=1,
                session_id="today-session",
                node_name="workflow",
                created_at=now,
            ),
            AgentTrace(
                id=3,
                tenant_id=1,
                user_id=1,
                session_id="old-session",
                node_name="workflow",
                created_at=now - timedelta(days=2),
            ),
            AgentTrace(
                id=4,
                tenant_id=2,
                user_id=4,
                session_id="other-tenant-session",
                node_name="workflow",
                created_at=now,
            ),
        ])
        db.commit()
        db.close()

        token = self.login("admin_a", ADMIN_PASSWORD)
        response = self.client.get(
            "/api/admin/dashboard",
            headers=self.auth_headers(token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {
            "orders_total": 4,
            "pending_refunds": 1,
            "failed_refunds": 1,
            "pending_tickets": 1,
            "unresolved_cases": 1,
            "today_sessions": 1,
        })

    def test_dashboard_requires_admin_role(self):
        customer_token = self.login("customer_a", CUSTOMER_PASSWORD)
        response = self.client.get(
            "/api/admin/dashboard",
            headers=self.auth_headers(customer_token),
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_only_sees_current_tenant_data(self):
        token = self.login("admin_a", ADMIN_PASSWORD)
        headers = self.auth_headers(token)

        orders = self.client.get("/api/admin/orders", headers=headers)
        self.assertEqual(orders.status_code, 200)
        order_ids = {item["id"] for item in orders.json()["data"]}
        self.assertEqual(order_ids, {10001, 10002, 10007, 11001})
        self.assertNotIn(20001, order_ids)

        cross_tenant_detail = self.client.get(
            "/api/admin/orders/20001",
            headers=headers,
        )
        self.assertEqual(cross_tenant_detail.status_code, 404)
