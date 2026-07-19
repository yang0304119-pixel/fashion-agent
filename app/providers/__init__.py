"""外部业务系统 Provider 契约与运行时 Adapter。"""

from app.providers.inventory_provider import (
    InventoryNotFoundError,
    InventoryProvider,
    InventoryResult,
)
from app.providers.logistics_provider import LogisticsProvider, LogisticsResult
from app.providers.order_provider import (
    OrderNotFoundError,
    OrderPage,
    OrderProvider,
    OrderResult,
    OrderSummary,
)
from app.providers.product_provider import (
    InvalidProductSearchError,
    ProductData,
    ProductNotFoundError,
    ProductProvider,
)

__all__ = [
    "InventoryNotFoundError",
    "InventoryProvider",
    "InventoryResult",
    "InvalidProductSearchError",
    "LogisticsProvider",
    "LogisticsResult",
    "OrderNotFoundError",
    "OrderPage",
    "OrderProvider",
    "OrderResult",
    "OrderSummary",
    "ProductData",
    "ProductNotFoundError",
    "ProductProvider",
]
