"""基于本地 SQLAlchemy 数据的 Mock 外部电商系统 Adapter。"""

from app.providers.mock.sqlalchemy_inventory_provider import (
    SqlAlchemyInventoryProvider,
)
from app.providers.mock.sqlalchemy_order_provider import SqlAlchemyOrderProvider
from app.providers.mock.sqlalchemy_product_provider import (
    SqlAlchemyProductProvider,
)

__all__ = [
    "SqlAlchemyInventoryProvider",
    "SqlAlchemyOrderProvider",
    "SqlAlchemyProductProvider",
]
