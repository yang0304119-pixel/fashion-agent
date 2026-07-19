import unittest
from decimal import Decimal
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.integrations.refund_gateway import MockRefundGateway
    from app.integrations.refund_gateway import get_refund_gateway
    from app.agent.nodes.refund_node import refund_node
    from app.models import Order, Product, Tenant, Ticket, User
    from app.services.refund_service import RefundService
except ModuleNotFoundError as error:
    if error.name in {"sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class MockRefundDemoTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        db = self.Session()
        db.add(Tenant(id=1, name="演示店铺", industry="服装"))
        db.flush()
        db.add_all([
            User(
                id=1,
                tenant_id=1,
                username="张三",
                password_hash="test",
                role="customer",
                is_active=True,
            ),
            User(
                id=4,
                tenant_id=1,
                username="admin",
                password_hash="test",
                role="admin",
                is_active=True,
            ),
        ])
        db.add_all([
            Product(
                id=1,
                tenant_id=1,
                name="极寒系列加厚羽绒服",
                category="羽绒服",
                price=Decimal("499.00"),
                colors=["黑色"],
                sizes=["M"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=10,
            ),
            Product(
                id=2,
                tenant_id=1,
                name="轻薄都市羽绒服",
                category="羽绒服",
                price=Decimal("299.00"),
                colors=["灰色"],
                sizes=["L"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=10,
            ),
            Product(
                id=7,
                tenant_id=1,
                name="纯色羊毛围巾",
                category="配饰",
                price=Decimal("89.00"),
                colors=["驼色"],
                sizes=["均码"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=10,
            ),
        ])
        db.flush()
        db.add_all([
            Order(
                id=10001,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("499.00"),
                status="shipped",
            ),
            Order(
                id=10002,
                tenant_id=1,
                user_id=1,
                product_id=2,
                quantity=2,
                total_price=Decimal("598.00"),
                status="delivered",
            ),
            Order(
                id=10007,
                tenant_id=1,
                user_id=1,
                product_id=7,
                quantity=1,
                total_price=Decimal("89.00"),
                status="pending",
            ),
        ])
        db.commit()
        db.close()

    def _service(self, db):
        return RefundService(
            db,
            MockRefundGateway(
                result="succeeded",
                failed_order_ids=frozenset({10002}),
            ),
        )

    def test_small_refund_succeeds_and_updates_order(self):
        db = self.Session()
        outcome = self._service(db).submit(
            tenant_id=1,
            user_id=1,
            order_id=10007,
            reason="不需要了",
            idempotency_key="demo-small-success",
        )
        self.assertEqual(outcome.refund.status, "succeeded")
        self.assertEqual(outcome.refund.gateway_mode, "mock")
        self.assertTrue(outcome.refund.provider_refund_id.startswith("mock_10007_"))
        self.assertEqual(db.get(Order, 10007).status, "refunded")
        db.close()

    def test_large_refund_waits_for_admin_then_succeeds(self):
        db = self.Session()
        service = self._service(db)
        submitted = service.submit(
            tenant_id=1,
            user_id=1,
            order_id=10001,
            reason="质量问题",
            idempotency_key="demo-review-success",
        )
        self.assertEqual(submitted.refund.status, "reviewing")
        self.assertIsNotNone(submitted.refund.ticket_id)
        self.assertEqual(db.get(Order, 10001).status, "shipped")

        approved = service.approve(
            tenant_id=1,
            refund_request_id=submitted.refund.id,
            reviewed_by=4,
        )
        self.assertEqual(approved.refund.status, "succeeded")
        self.assertEqual(db.get(Order, 10001).status, "refunded")
        ticket = db.get(Ticket, submitted.refund.ticket_id)
        self.assertEqual(ticket.status, "approved")
        self.assertEqual(ticket.reviewed_by, 4)
        db.close()

    def test_failed_order_returns_channel_failure_after_approval(self):
        db = self.Session()
        service = self._service(db)
        submitted = service.submit(
            tenant_id=1,
            user_id=1,
            order_id=10002,
            reason="质量问题",
            idempotency_key="demo-channel-failure",
        )
        self.assertEqual(submitted.refund.status, "reviewing")
        approved = service.approve(
            tenant_id=1,
            refund_request_id=submitted.refund.id,
            reviewed_by=4,
        )
        self.assertEqual(approved.refund.status, "failed")
        self.assertEqual(
            approved.refund.failure_reason,
            "Mock渠道按演示场景返回失败",
        )
        self.assertEqual(db.get(Order, 10002).status, "delivered")
        db.close()

    def test_mock_gateway_supports_all_configured_results(self):
        pending = MockRefundGateway(result="pending").execute(
            refund_request_id=1,
            order_id=1,
            amount=Decimal("1.00"),
            idempotency_key="pending-key",
        )
        failed = MockRefundGateway(result="failed").execute(
            refund_request_id=2,
            order_id=2,
            amount=Decimal("1.00"),
            idempotency_key="failed-key",
        )
        self.assertEqual(pending.status, "pending")
        self.assertEqual(failed.status, "failed")

    def test_refund_node_completes_small_demo_refund_with_warning(self):
        with patch("app.agent.nodes.refund_node.SessionLocal", self.Session):
            result = refund_node(
                {
                    "tenant_id": 1,
                    "user_id": 1,
                    "session_id": "demo-small-node",
                    "message": "订单10007申请退款，原因是不需要了",
                    "collected_slots": {},
                }
            )
        self.assertEqual(result["refund_status"], "succeeded")
        self.assertEqual(result["tool_result"]["data"]["gateway_mode"], "mock")
        self.assertIn("模拟退款", result["final_answer"])
        self.assertIn("不涉及真实资金", result["final_answer"])
        db = self.Session()
        self.assertEqual(db.get(Order, 10007).status, "refunded")
        db.close()

    def test_production_environment_rejects_mock_gateway(self):
        with (
            patch("app.integrations.refund_gateway.settings.ENVIRONMENT", "production"),
            patch("app.integrations.refund_gateway.settings.REFUND_GATEWAY_MODE", "mock"),
        ):
            with self.assertRaisesRegex(RuntimeError, "生产环境禁止使用 mock"):
                get_refund_gateway()


if __name__ == "__main__":
    unittest.main()
