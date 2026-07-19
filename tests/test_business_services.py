import unittest
from decimal import Decimal

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.models import Order, Product, Tenant, User
    from app.services.inventory_service import (
        InventoryService,
        ProductNotFoundError,
    )
    from app.services.order_service import OrderNotFoundError, OrderService
    from app.services.order_query_service import OrderQueryService
    from app.services.product_catalog_service import ProductCatalogService
    from app.providers.mock.sqlalchemy_inventory_provider import (
        SqlAlchemyInventoryProvider,
    )
    from app.providers.mock.sqlalchemy_order_provider import (
        SqlAlchemyOrderProvider,
    )
    from app.providers.mock.sqlalchemy_product_provider import (
        SqlAlchemyProductProvider,
    )
    from app.tools.product_search_tool import search_products
    from app.agent.nodes.inventory_node import inventory_node
    from app.agent.nodes.order_node import order_node
except ModuleNotFoundError as error:
    if error.name in {"sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class BusinessServiceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add_all([
            Tenant(id=1, name="租户一", industry="服装"),
            Tenant(id=2, name="租户二", industry="服装"),
        ])
        self.db.flush()
        self.db.add_all([
            User(
                id=1,
                tenant_id=1,
                username="用户一",
                password_hash="test",
                role="customer",
                is_active=True,
            ),
            User(
                id=2,
                tenant_id=2,
                username="用户二",
                password_hash="test",
                role="customer",
                is_active=True,
            ),
            User(
                id=3,
                tenant_id=1,
                username="同租户其他用户",
                password_hash="test",
                role="customer",
                is_active=True,
            ),
        ])
        self.db.add_all([
            Product(
                id=1,
                tenant_id=1,
                name="商品一",
                category="服装",
                price=Decimal("99.00"),
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
                name="商品二",
                category="服装",
                price=Decimal("199.00"),
                colors=["白色"],
                sizes=["L"],
                description="测试",
                materials="测试",
                care_instructions="测试",
                stock=20,
            ),
        ])
        self.db.flush()
        self.db.add_all([
            Order(
                id=10001,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=1,
                total_price=Decimal("99.00"),
                status="pending",
            ),
            Order(
                id=10002,
                tenant_id=1,
                user_id=1,
                product_id=1,
                quantity=2,
                total_price=Decimal("198.00"),
                status="shipped",
            ),
            Order(
                id=20001,
                tenant_id=2,
                user_id=2,
                product_id=2,
                quantity=1,
                total_price=Decimal("199.00"),
                status="pending",
            ),
            Order(
                id=10003,
                tenant_id=1,
                user_id=3,
                product_id=1,
                quantity=1,
                total_price=Decimal("99.00"),
                status="pending",
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_order_service_enforces_user_and_tenant(self):
        service = OrderService(self.db)
        self.assertEqual(
            service.get_for_user(
                tenant_id=1,
                user_id=1,
                order_id=10001,
            ).id,
            10001,
        )
        with self.assertRaises(OrderNotFoundError):
            service.get_for_user(
                tenant_id=1,
                user_id=1,
                order_id=20001,
            )

    def test_order_query_service_filters_owner_status_and_paginates(self):
        service = OrderQueryService(self.db)
        first_page = service.list_for_user(
            tenant_id=1,
            user_id=1,
            status=None,
            page=1,
            page_size=1,
        )
        self.assertEqual(first_page.total, 2)
        self.assertEqual([item.id for item in first_page.items], [10002])
        self.assertEqual(first_page.items[0].product_name, "商品一")

        second_page = service.list_for_user(
            tenant_id=1,
            user_id=1,
            status=None,
            page=2,
            page_size=1,
        )
        self.assertEqual(second_page.total, 2)
        self.assertEqual([item.id for item in second_page.items], [10001])

        shipped = service.list_for_user(
            tenant_id=1,
            user_id=1,
            status="shipped",
            page=1,
            page_size=20,
        )
        self.assertEqual(shipped.total, 1)
        self.assertEqual([item.id for item in shipped.items], [10002])

        other_tenant = service.list_for_user(
            tenant_id=2,
            user_id=2,
            status=None,
            page=1,
            page_size=20,
        )
        self.assertEqual([item.id for item in other_tenant.items], [20001])

    def test_inventory_service_enforces_tenant(self):
        service = InventoryService(self.db)
        self.assertEqual(
            service.get_product(tenant_id=1, product_id=1).stock,
            10,
        )
        with self.assertRaises(ProductNotFoundError):
            service.get_product(tenant_id=1, product_id=2)

    def test_product_catalog_search_enforces_tenant(self):
        service = ProductCatalogService(self.db)
        tenant_one = service.search(tenant_id=1, query="商品")
        self.assertEqual([product.id for product in tenant_one], [1])

        result = search_products(
            "商品",
            tenant_id=1,
            provider=SqlAlchemyProductProvider(
                session_factory=lambda: self.db,
                db=self.db,
            ),
        )
        self.assertTrue(result["success"])
        self.assertEqual(
            [product["product_id"] for product in result["data"]["products"]],
            [1],
        )

    def test_order_node_uses_service_and_fixed_template(self):
        state = {
            "message": "查询订单 10001",
            "tenant_id": 1,
            "user_id": 1,
        }
        result = order_node(
            state,
            provider=SqlAlchemyOrderProvider(
                session_factory=lambda: self.db,
                db=self.db,
            ),
        )
        self.assertEqual(result["tool_status"], "success")
        self.assertIn("待发货", result["final_answer"])

    def test_inventory_node_uses_service_and_fixed_template(self):
        state = {
            "message": "商品 1 还有库存吗",
            "tenant_id": 1,
            "user_id": 1,
        }
        result = inventory_node(
            state,
            provider=SqlAlchemyInventoryProvider(
                session_factory=lambda: self.db,
                db=self.db,
            ),
        )
        self.assertEqual(result["tool_status"], "success")
        self.assertIn("库存 10 件", result["final_answer"])


if __name__ == "__main__":
    unittest.main()
