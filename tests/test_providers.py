import unittest
from datetime import datetime
from pathlib import Path

from app.agent.nodes.inventory_node import inventory_node
from app.agent.nodes.order_node import order_node
from app.providers.inventory_provider import InventoryResult
from app.providers.factory import (
    get_inventory_provider,
    get_order_provider,
    get_product_provider,
)
from app.providers.logistics_provider import LogisticsProvider, LogisticsResult
from app.providers.mock.sqlalchemy_inventory_provider import (
    SqlAlchemyInventoryProvider,
)
from app.providers.mock.sqlalchemy_order_provider import SqlAlchemyOrderProvider
from app.providers.mock.sqlalchemy_product_provider import (
    SqlAlchemyProductProvider,
)
from app.providers.order_provider import OrderNotFoundError, OrderResult
from app.providers.product_provider import ProductData, ProductNotFoundError
from app.services.chat_context_service import ChatContextService
from app.schemas.chat import ProductChatContext
from app.tools.product_search_tool import search_products
from tests.api_test_support import ApiTestCase
from tests.fakes import (
    FakeInventoryProvider,
    FakeOrderProvider,
    FakeProductProvider,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class SqlAlchemyProviderAdapterTests(ApiTestCase):
    def test_product_adapter_preserves_tenant_boundary_and_returns_dto(self):
        db = self.Session()
        provider = SqlAlchemyProductProvider(
            session_factory=self.Session,
            db=db,
        )
        try:
            product = provider.get_product(tenant_id=1, product_id=1)
            self.assertEqual(product.product_id, 1)
            self.assertEqual(product.name, "租户一羽绒服")
            self.assertIsInstance(product.colors, list)
            with self.assertRaises(ProductNotFoundError):
                provider.get_product(tenant_id=1, product_id=20)
        finally:
            db.close()

    def test_inventory_adapter_preserves_tenant_boundary(self):
        db = self.Session()
        provider = SqlAlchemyInventoryProvider(
            session_factory=self.Session,
            db=db,
        )
        try:
            inventory = provider.get_inventory(tenant_id=1, product_id=1)
            self.assertEqual(inventory.stock, 20)
            self.assertEqual(inventory.product_name, "租户一羽绒服")
        finally:
            db.close()

    def test_order_adapter_preserves_user_and_tenant_boundary(self):
        db = self.Session()
        provider = SqlAlchemyOrderProvider(
            session_factory=self.Session,
            db=db,
        )
        try:
            order = provider.get_order(
                tenant_id=1,
                user_id=1,
                order_id=10001,
            )
            self.assertEqual(order.product_name, "租户一羽绒服")
            with self.assertRaises(OrderNotFoundError):
                provider.get_order(
                    tenant_id=1,
                    user_id=1,
                    order_id=11001,
                )
        finally:
            db.close()

    def test_factory_returns_sqlalchemy_mock_adapters(self):
        db = self.Session()
        try:
            self.assertIsInstance(
                get_product_provider(db),
                SqlAlchemyProductProvider,
            )
            self.assertIsInstance(
                get_inventory_provider(db),
                SqlAlchemyInventoryProvider,
            )
            self.assertIsInstance(
                get_order_provider(db),
                SqlAlchemyOrderProvider,
            )
        finally:
            db.close()


class FakeProviderNodeTests(unittest.TestCase):
    def test_inventory_node_uses_fake_provider_without_database(self):
        provider = FakeInventoryProvider({
            9: InventoryResult(
                product_id=9,
                product_name="Fake 羽绒服",
                category="羽绒服",
                price=399.0,
                stock=8,
                colors=["黑色"],
                sizes=["M", "L"],
            )
        })
        result = inventory_node({
            "message": "这件有货吗",
            "tenant_id": 7,
            "collected_slots": {"product_id": 9},
        }, provider=provider)

        self.assertEqual(result["tool_status"], "success")
        self.assertIn("库存 8 件", result["final_answer"])
        self.assertEqual(
            provider.calls,
            [{"tenant_id": 7, "product_id": 9}],
        )

    def test_order_node_uses_fake_provider_without_database(self):
        provider = FakeOrderProvider({
            90001: OrderResult(
                order_id=90001,
                user_id=22,
                product_id=9,
                product_name="Fake 羽绒服",
                quantity=1,
                amount=399.0,
                status="shipped",
                created_at=datetime(2026, 7, 19, 12, 0, 0),
            )
        })
        result = order_node({
            "message": "这个订单发货了吗",
            "tenant_id": 7,
            "user_id": 22,
            "collected_slots": {"order_id": 90001},
        }, provider=provider)

        self.assertEqual(result["tool_status"], "success")
        self.assertIn("已发货", result["final_answer"])
        self.assertEqual(provider.get_calls, [{
            "tenant_id": 7,
            "user_id": 22,
            "order_id": 90001,
        }])

    def test_product_fake_drives_search_tool_and_chat_context(self):
        product = ProductData(
            product_id=9,
            name="Fake 羽绒服",
            category="羽绒服",
            price=399.0,
            colors=["黑色"],
            sizes=["M", "L"],
            stock=8,
            description="测试商品",
            materials="聚酯纤维",
            care_instructions="低温洗涤",
        )
        product_provider = FakeProductProvider({9: product})
        order_provider = FakeOrderProvider({})

        search_result = search_products(
            "羽绒服",
            tenant_id=7,
            provider=product_provider,
        )
        context = ChatContextService(
            product_provider=product_provider,
            order_provider=order_provider,
        ).resolve(
            tenant_id=7,
            user_id=22,
            context=ProductChatContext(type="product", product_id=9),
        )

        self.assertTrue(search_result["success"])
        self.assertEqual(
            search_result["data"]["products"][0]["product_id"],
            9,
        )
        self.assertEqual(context.collected_slots["product_id"], 9)
        self.assertEqual(context.trusted_data["stock"], 8)
        self.assertEqual(product_provider.search_calls[0]["tenant_id"], 7)
        self.assertEqual(product_provider.get_calls[0]["tenant_id"], 7)

    def test_nodes_do_not_import_database_or_orm_models(self):
        for relative_path in (
            "app/agent/nodes/inventory_node.py",
            "app/agent/nodes/order_node.py",
        ):
            source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("SessionLocal", source)
            self.assertNotIn("sqlalchemy", source.lower())
            self.assertNotIn("app.models", source)

    def test_logistics_has_contract_but_no_runtime_mock_adapter(self):
        self.assertTrue(hasattr(LogisticsProvider, "get_tracking"))
        result = LogisticsResult(
            order_id=1,
            carrier=None,
            tracking_number=None,
            status="unknown",
            latest_event=None,
            estimated_delivery=None,
        )
        self.assertEqual(result.status, "unknown")
        self.assertFalse(
            (PROJECT_ROOT / "app/providers/mock/logistics_provider.py").exists()
        )


if __name__ == "__main__":
    unittest.main()
