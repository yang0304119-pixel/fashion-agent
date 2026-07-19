"""库存 Provider 的 SQLAlchemy Mock Adapter。"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.providers.inventory_provider import (
    InventoryNotFoundError,
    InventoryResult,
)
from app.providers.mock._session import provider_session
from app.services.inventory_service import (
    InventoryService,
    ProductNotFoundError as ServiceProductNotFoundError,
)


class SqlAlchemyInventoryProvider:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        db: Session | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.db = db

    def get_inventory(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> InventoryResult:
        with provider_session(self.db, self.session_factory) as db:
            try:
                product = InventoryService(db).get_product(
                    tenant_id=tenant_id,
                    product_id=product_id,
                )
            except ServiceProductNotFoundError as error:
                raise InventoryNotFoundError("商品不存在") from error
            return InventoryResult(
                product_id=product.id,
                product_name=product.name,
                category=product.category,
                price=float(product.price),
                stock=product.stock,
                colors=list(product.colors or []),
                sizes=list(product.sizes or []),
            )
