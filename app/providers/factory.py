"""Provider 工厂；当前选择 SQLAlchemy Mock 外部电商系统 Adapter。"""

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.providers.inventory_provider import InventoryProvider
from app.providers.mock.sqlalchemy_inventory_provider import (
    SqlAlchemyInventoryProvider,
)
from app.providers.mock.sqlalchemy_order_provider import SqlAlchemyOrderProvider
from app.providers.mock.sqlalchemy_product_provider import (
    SqlAlchemyProductProvider,
)
from app.providers.order_provider import OrderProvider
from app.providers.product_provider import ProductProvider


def get_product_provider(db: Session | None = None) -> ProductProvider:
    return SqlAlchemyProductProvider(session_factory=SessionLocal, db=db)


def get_inventory_provider(db: Session | None = None) -> InventoryProvider:
    return SqlAlchemyInventoryProvider(session_factory=SessionLocal, db=db)


def get_order_provider(db: Session | None = None) -> OrderProvider:
    return SqlAlchemyOrderProvider(session_factory=SessionLocal, db=db)
