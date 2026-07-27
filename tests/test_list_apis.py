import unittest
from decimal import Decimal

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.database import Base
    from app.dependencies import get_current_user, get_db
    from app.models import (
        AgentTrace,
        AgentTraceStep,
        Order,
        Product,
        RefundRequest,
        Tenant,
        Ticket,
        UnresolvedCase,
        User,
    )
    from app.routers import admin, agentops, orders, refunds, tickets
except ModuleNotFoundError as error:
    if error.name in {"fastapi", "httpx", "sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class ListApiTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
        self._seed()

        api = FastAPI()
        api.include_router(orders.router, prefix="/api")
        api.include_router(tickets.router, prefix="/api")
        api.include_router(refunds.router, prefix="/api")
        api.include_router(admin.router, prefix="/api")
        api.include_router(agentops.router, prefix="/api")

        def override_db():
            yield self.session

        def override_current_user():
            return self.current_user

        api.dependency_overrides[get_db] = override_db
        api.dependency_overrides[get_current_user] = override_current_user
        self.current_user = self.customer
        self.client = TestClient(api)

    def tearDown(self):
        self.client.close()
        self.session.close()

    def _seed(self):
        self.session.add_all([
            Tenant(id=1, name="租户一", industry="服装"),
            Tenant(id=2, name="租户二", industry="服装"),
        ])
        self.session.flush()
        self.customer = User(
            id=1,
            tenant_id=1,
            username="客户一",
            password_hash="test",
            role="customer",
            is_active=True,
        )
        self.other_customer = User(
            id=2,
            tenant_id=1,
            username="客户二",
            password_hash="test",
            role="customer",
            is_active=True,
        )
        self.admin = User(
            id=3,
            tenant_id=1,
            username="管理员",
            password_hash="test",
            role="admin",
            is_active=True,
        )
        tenant_two_user = User(
            id=4,
            tenant_id=2,
            username="租户二客户",
            password_hash="test",
            role="customer",
            is_active=True,
        )
        self.session.add_all([
            self.customer,
            self.other_customer,
            self.admin,
            tenant_two_user,
        ])
        self.session.add_all([
            Product(
                id=1,
                tenant_id=1,
                name="租户一商品",
                category="服装",
                price=Decimal("100.00"),
                colors=["黑色"],
                sizes=["M"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=10,
            ),
            Product(
                id=2,
                tenant_id=2,
                name="租户二商品",
                category="服装",
                price=Decimal("200.00"),
                colors=["白色"],
                sizes=["L"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=10,
            ),
        ])
        self.session.flush()
        self.session.add_all([
            Order(
                id=10001,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("100.00"),
                status="pending",
            ),
            Order(
                id=10002,
                tenant_id=1,
                user_id=2,
                product_id=1,
                quantity=1,
                total_price=Decimal("100.00"),
                status="shipped",
            ),
            Order(
                id=20001,
                tenant_id=2,
                user_id=4,
                product_id=2,
                quantity=1,
                total_price=Decimal("200.00"),
                status="pending",
            ),
        ])
        self.session.flush()
        self.session.add_all([
            Ticket(
                id=1,
                tenant_id=1,
                order_id=10001,
                user_id=1,
                type="refund",
                reason="客户一退款",
                amount=Decimal("100.00"),
                risk_level="low",
                status="pending",
                human_review=False,
            ),
            Ticket(
                id=2,
                tenant_id=1,
                order_id=10002,
                user_id=2,
                type="exchange",
                reason="客户二换货",
                amount=Decimal("100.00"),
                risk_level="low",
                status="approved",
                human_review=False,
            ),
            Ticket(
                id=3,
                tenant_id=2,
                order_id=20001,
                user_id=4,
                type="refund",
                reason="租户二退款",
                amount=Decimal("200.00"),
                risk_level="high",
                status="pending",
                human_review=True,
            ),
        ])
        self.session.flush()
        self.session.add_all([
            RefundRequest(
                id=1,
                tenant_id=1,
                order_id=10001,
                user_id=1,
                ticket_id=1,
                reason="客户一退款",
                amount=Decimal("100.00"),
                risk_level="low",
                human_review=False,
                status="reviewing",
                idempotency_key="refund-1",
                gateway_mode="manual",
            ),
            RefundRequest(
                id=2,
                tenant_id=1,
                order_id=10002,
                user_id=2,
                ticket_id=None,
                reason="客户二退款",
                amount=Decimal("100.00"),
                risk_level="low",
                human_review=False,
                status="failed",
                idempotency_key="refund-2",
                gateway_mode="manual",
            ),
            RefundRequest(
                id=3,
                tenant_id=2,
                order_id=20001,
                user_id=4,
                ticket_id=3,
                reason="租户二退款",
                amount=Decimal("200.00"),
                risk_level="high",
                human_review=True,
                status="reviewing",
                idempotency_key="refund-3",
                gateway_mode="manual",
            ),
        ])
        self.session.add_all([
            AgentTrace(
                id=1,
                tenant_id=1,
                user_id=1,
                session_id="tenant-one",
                node_name="router",
            ),
            AgentTrace(
                id=2,
                tenant_id=2,
                user_id=4,
                session_id="tenant-two",
                node_name="router",
            ),
            UnresolvedCase(
                id=1,
                tenant_id=1,
                user_id=1,
                user_message="租户一问题",
                predicted_intent="fallback",
                confidence=Decimal("0.3100"),
                final_answer="抱歉，我没有理解您的问题。",
                is_resolved=False,
            ),
            UnresolvedCase(
                id=2,
                tenant_id=2,
                user_id=4,
                user_message="租户二问题",
                predicted_intent="fallback",
                confidence=Decimal("0.2500"),
                final_answer="抱歉，我没有理解您的问题。",
                is_resolved=False,
            ),
        ])
        self.session.flush()
        self.session.add(
            AgentTraceStep(
                id=1,
                trace_id=1,
                sequence=1,
                node_name="router",
                workflow_name="order_workflow",
                status="succeeded",
                missing_slots=[],
                rag_sources=[],
                duration_ms=12,
            )
        )
        self.session.commit()

    def test_customer_lists_only_return_owned_data(self):
        orders_response = self.client.get("/api/orders")
        tickets_response = self.client.get("/api/tickets")
        refunds_response = self.client.get("/api/refunds")

        self.assertEqual(orders_response.status_code, 200)
        self.assertEqual(
            [item["id"] for item in orders_response.json()["data"]],
            [10001],
        )
        self.assertEqual(
            [item["id"] for item in tickets_response.json()["data"]],
            [1],
        )
        self.assertEqual(
            [item["id"] for item in refunds_response.json()["data"]],
            [1],
        )
        order_detail = self.client.get("/api/orders/10001")
        self.assertEqual(order_detail.status_code, 200)
        self.assertEqual(order_detail.json()["data"]["product_name"], "租户一商品")

    def test_ticket_filters_and_pagination(self):
        response = self.client.get(
            "/api/tickets",
            params={"status": "pending", "type": "refund", "page_size": 1},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["page_size"], 1)
        self.assertEqual(response.json()["data"][0]["id"], 1)
        self.assertEqual(
            self.client.get("/api/tickets", params={"page_size": 101}).status_code,
            422,
        )

    def test_customer_cannot_access_any_admin_list(self):
        for path in (
            "/api/admin/orders",
            "/api/admin/tickets",
            "/api/agentops/traces",
            "/api/admin/unresolved-cases",
            "/api/admin/refunds",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)

    def test_admin_lists_only_return_current_tenant_and_paginate(self):
        self.current_user = self.admin
        expected_ids = {
            "/api/admin/orders": {10001, 10002},
            "/api/admin/tickets": {1, 2},
            "/api/agentops/traces": {1},
            "/api/admin/unresolved-cases": {1},
            "/api/admin/refunds": {1, 2},
        }
        for path, ids in expected_ids.items():
            with self.subTest(path=path):
                response = self.client.get(path, params={"page": 1, "page_size": 1})
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["total"], len(ids))
                self.assertEqual(payload["page"], 1)
                self.assertEqual(payload["page_size"], 1)
                self.assertEqual(len(payload["data"]), 1)
                self.assertIn(payload["data"][0]["id"], ids)
                self.assertEqual(
                    self.client.get(path, params={"page_size": 101}).status_code,
                    422,
                )

        refund_response = self.client.get("/api/admin/refunds/1")
        self.assertEqual(refund_response.status_code, 200)
        refund = refund_response.json()["data"]
        self.assertEqual(refund["username"], "客户一")
        self.assertEqual(refund["product_name"], "租户一商品")
        self.assertEqual(self.client.get("/api/admin/refunds/3").status_code, 404)

    def test_admin_refund_reject_requires_non_blank_reason(self):
        self.current_user = self.admin
        response = self.client.post(
            "/api/admin/refunds/1/reject",
            json={"reason": "   "},
        )
        self.assertEqual(response.status_code, 422)

    def test_admin_can_approve_reviewing_refund(self):
        self.current_user = self.admin
        response = self.client.post("/api/admin/refunds/1/approve")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "succeeded")
        self.assertTrue(
            response.json()["data"]["provider_refund_id"].startswith(
                "mock_10001_"
            )
        )
        self.assertEqual(response.json()["data"]["username"], "客户一")
        self.assertEqual(response.json()["data"]["product_name"], "租户一商品")
        self.assertEqual(self.session.get(Order, 10001).status, "refunded")
        ticket = self.client.get("/api/admin/tickets/1").json()["data"]
        self.assertEqual(ticket["status"], "approved")
        self.assertEqual(ticket["reviewed_by"], self.admin.id)
        self.assertEqual(ticket["reviewer_username"], "管理员")
        self.assertIsNotNone(ticket["reviewed_at"])
        self.assertEqual(ticket["review_reason"], "管理员批准退款申请")

    def test_admin_can_reject_with_reason(self):
        self.current_user = self.admin
        response = self.client.post(
            "/api/admin/refunds/1/reject",
            json={"reason": " 已超过退款期限 "},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["status"], "rejected")
        self.assertEqual(
            response.json()["data"]["failure_reason"],
            "已超过退款期限",
        )
        ticket = self.client.get("/api/admin/tickets/1").json()["data"]
        self.assertEqual(ticket["status"], "rejected")
        self.assertEqual(ticket["reviewer_username"], "管理员")
        self.assertEqual(ticket["review_reason"], "已超过退款期限")

    def test_admin_ticket_list_and_detail_include_business_links(self):
        self.current_user = self.admin
        response = self.client.get(
            "/api/admin/tickets",
            params={"status": "pending", "type": "refund"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        ticket = response.json()["data"][0]
        self.assertEqual(ticket["username"], "客户一")
        self.assertEqual(ticket["product_name"], "租户一商品")
        self.assertEqual(ticket["refund_id"], 1)
        self.assertEqual(ticket["refund_status"], "reviewing")

        detail = self.client.get("/api/admin/tickets/1")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"]["order_id"], 10001)
        order = self.client.get("/api/admin/orders/10001")
        self.assertEqual(order.status_code, 200)
        self.assertEqual(order.json()["data"]["product"]["name"], "租户一商品")
        self.assertEqual(self.client.get("/api/admin/tickets/3").status_code, 404)

    def test_admin_order_list_and_detail_include_business_links_without_duplicates(self):
        self.current_user = self.admin
        self.session.add(Ticket(
            id=4,
            tenant_id=1,
            order_id=10001,
            user_id=1,
            type="exchange",
            reason="同一订单的第二张工单",
            amount=Decimal("100.00"),
            risk_level="low",
            status="pending",
            human_review=False,
        ))
        self.session.commit()

        response = self.client.get(
            "/api/admin/orders",
            params={"status": "pending", "page": 1, "page_size": 20},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(payload["data"]), 1)
        order = payload["data"][0]
        self.assertEqual(order["id"], 10001)
        self.assertEqual(order["username"], "客户一")
        self.assertEqual(order["refund_id"], 1)
        self.assertEqual(order["refund_status"], "reviewing")
        self.assertEqual(order["ticket_count"], 2)

        detail_response = self.client.get("/api/admin/orders/10001")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()["data"]
        self.assertEqual(detail["user"], {"id": 1, "username": "客户一"})
        self.assertEqual(detail["product"]["name"], "租户一商品")
        self.assertEqual(detail["refund"], {"id": 1, "status": "reviewing"})
        self.assertEqual({item["id"] for item in detail["tickets"]}, {1, 4})

        self.assertEqual(
            self.client.get("/api/admin/orders/20001").status_code,
            404,
        )

    def test_admin_trace_detail_session_and_tenant_boundary(self):
        self.current_user = self.admin
        trace = self.session.get(AgentTrace, 1)
        trace.message = "查询订单10001"
        trace.intent = "order_query"
        trace.workflow_name = "order_workflow"
        trace.status = "succeeded"
        trace.missing_slots = []
        trace.rag_sources = []
        trace.final_answer = "订单已发货"
        tenant_two_trace = self.session.get(AgentTrace, 2)
        tenant_two_trace.status = "failed"
        self.session.commit()

        response = self.client.get(
            "/api/agentops/traces",
            params={
                "session_id": "tenant-one",
                "intent": "order_query",
                "status": "succeeded",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.assertEqual(response.json()["data"][0]["workflow_name"], "order_workflow")

        detail = self.client.get("/api/agentops/traces/1")
        self.assertEqual(detail.status_code, 200)
        payload = detail.json()["data"]
        self.assertEqual(payload["message"], "查询订单10001")
        self.assertEqual(payload["steps"][0]["node_name"], "router")
        self.assertEqual(payload["steps"][0]["duration_ms"], 12)

        session = self.client.get("/api/agentops/trace-sessions/tenant-one")
        self.assertEqual(session.status_code, 200)
        self.assertEqual([item["id"] for item in session.json()["data"]], [1])
        cross_tenant = self.client.get("/api/agentops/traces/2")
        self.assertEqual(cross_tenant.status_code, 404)
        hidden_session = self.client.get("/api/agentops/trace-sessions/tenant-two")
        self.assertEqual(hidden_session.status_code, 200)
        self.assertEqual(hidden_session.json()["data"], [])

    def test_admin_unresolved_case_stats_filters_and_annotation(self):
        self.current_user = self.admin
        stats = self.client.get("/api/admin/unresolved-cases/stats")
        self.assertEqual(stats.status_code, 200)
        self.assertEqual(
            stats.json()["data"],
            {"pending": 1, "resolved": 0, "knowledge_candidates": 0},
        )

        filtered = self.client.get(
            "/api/admin/unresolved-cases",
            params={
                "is_resolved": "false",
                "predicted_intent": "fallback",
                "should_add_to_kb": "false",
            },
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual([item["id"] for item in filtered.json()["data"]], [1])

        updated = self.client.patch(
            "/api/admin/unresolved-cases/1",
            json={
                "is_resolved": True,
                "human_label_intent": " knowledge_query ",
                "human_label_answer": " 建议使用中性洗涤剂低温手洗。 ",
                "should_add_to_kb": True,
            },
        )
        self.assertEqual(updated.status_code, 200)
        case = updated.json()["data"]
        self.assertTrue(case["is_resolved"])
        self.assertEqual(case["human_label_intent"], "knowledge_query")
        self.assertEqual(case["human_label_answer"], "建议使用中性洗涤剂低温手洗。")
        self.assertTrue(case["should_add_to_kb"])
        self.assertEqual(case["reviewed_by"], self.admin.id)
        self.assertEqual(case["reviewer_username"], "管理员")
        self.assertIsNotNone(case["reviewed_at"])
        self.assertIsNotNone(case["updated_at"])

        updated_stats = self.client.get("/api/admin/unresolved-cases/stats")
        self.assertEqual(
            updated_stats.json()["data"],
            {"pending": 0, "resolved": 1, "knowledge_candidates": 1},
        )

    def test_unresolved_case_annotation_validation_and_boundaries(self):
        self.current_user = self.admin
        for payload in (
            {"is_resolved": True, "human_label_answer": ""},
            {"should_add_to_kb": True, "human_label_answer": "   "},
            {"human_label_intent": "unsupported_intent"},
            {"tenant_id": 2, "human_label_answer": "越权"},
            {"user_id": 4, "human_label_answer": "越权"},
        ):
            with self.subTest(payload=payload):
                response = self.client.patch(
                    "/api/admin/unresolved-cases/1",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

        cross_tenant = self.client.patch(
            "/api/admin/unresolved-cases/2",
            json={"human_label_answer": "不可见"},
        )
        self.assertEqual(cross_tenant.status_code, 404)

        self.current_user = self.customer
        forbidden = self.client.patch(
            "/api/admin/unresolved-cases/1",
            json={"human_label_answer": "普通用户不可操作"},
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_customer_cannot_approve_or_reject_refund(self):
        for action in ("approve", "reject"):
            with self.subTest(action=action):
                response = self.client.post(
                    f"/api/admin/refunds/1/{action}",
                    json={"reason": "不符合条件"} if action == "reject" else None,
                )
                self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
