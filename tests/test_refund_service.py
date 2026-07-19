import unittest
from decimal import Decimal

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.integrations.refund_gateway import GatewayRefundResult
    from app.models import Order, Product, Tenant, Ticket, User
    from app.services.refund_service import RefundService
except ModuleNotFoundError as error:
    if error.name in {"sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class PendingGateway:
    mode = "manual"

    def execute(self, **kwargs):
        return GatewayRefundResult(status="pending")


class SuccessGateway:
    mode = "test"

    def execute(self, **kwargs):
        return GatewayRefundResult(
            status="succeeded",
            provider_refund_id=f"provider-{kwargs['refund_request_id']}",
        )


class RefundServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        db = self.Session()
        tenant = Tenant(id=1, name="测试店铺", industry="服装")
        user = User(
            id=1,
            tenant_id=1,
            username="测试用户",
            password_hash="test",
            role="customer",
            is_active=True,
        )
        admin = User(
            id=2,
            tenant_id=1,
            username="审核管理员",
            password_hash="test",
            role="admin",
            is_active=True,
        )
        product = Product(
            id=1,
            tenant_id=1,
            name="测试商品",
            category="服装",
            price=Decimal("89.00"),
            colors=["黑色"],
            sizes=["M"],
            description="测试",
            materials="测试",
            care_instructions="测试",
            stock=1,
        )
        db.add_all([tenant, user, admin, product])
        db.flush()
        db.add_all([
            Order(
                id=10001,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("89.00"),
                status="pending",
            ),
            Order(
                id=10002,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("499.00"),
                status="delivered",
            ),
        ])
        db.commit()
        db.close()

    def test_manual_low_risk_is_approved_but_not_marked_refunded(self):
        db = self.Session()
        outcome = RefundService(db, PendingGateway()).submit(
            tenant_id=1,
            user_id=1,
            order_id=10001,
            reason="不想要了",
            idempotency_key="idem-low",
        )
        order = db.get(Order, 10001)
        self.assertEqual(outcome.refund.status, "approved")
        self.assertEqual(order.status, "pending")
        db.close()

    def test_successful_gateway_updates_refund_and_order(self):
        db = self.Session()
        outcome = RefundService(db, SuccessGateway()).submit(
            tenant_id=1,
            user_id=1,
            order_id=10001,
            reason="不想要了",
            idempotency_key="idem-success",
        )
        order = db.get(Order, 10001)
        self.assertEqual(outcome.refund.status, "succeeded")
        self.assertEqual(order.status, "refunded")
        db.close()

    def test_high_risk_requires_admin_approval(self):
        db = self.Session()
        service = RefundService(db, SuccessGateway())
        submitted = service.submit(
            tenant_id=1,
            user_id=1,
            order_id=10002,
            reason="质量问题",
            idempotency_key="idem-high",
        )
        self.assertEqual(submitted.refund.status, "reviewing")
        self.assertIsNotNone(submitted.refund.ticket_id)

        approved = service.approve(
            tenant_id=1,
            refund_request_id=submitted.refund.id,
            reviewed_by=2,
        )
        order = db.get(Order, 10002)
        self.assertEqual(approved.refund.status, "succeeded")
        self.assertEqual(order.status, "refunded")
        self.assertEqual(approved.refund.ticket.status, "approved")
        self.assertEqual(approved.refund.ticket.reviewed_by, 2)
        self.assertIsNotNone(approved.refund.ticket.reviewed_at)
        self.assertEqual(
            approved.refund.ticket.review_reason,
            "管理员批准退款申请",
        )
        db.close()


if __name__ == "__main__":
    unittest.main()
