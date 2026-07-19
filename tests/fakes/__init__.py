"""Provider 测试替身。"""

from tests.fakes.fake_inventory_provider import FakeInventoryProvider
from tests.fakes.fake_order_provider import FakeOrderProvider
from tests.fakes.fake_product_provider import FakeProductProvider

__all__ = [
    "FakeInventoryProvider",
    "FakeOrderProvider",
    "FakeProductProvider",
]
