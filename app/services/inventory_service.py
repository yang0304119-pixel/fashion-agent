"""库存领域服务：按租户查询商品和库存。"""

from sqlalchemy.orm import Session

from app.models.product import Product


class InventoryServiceError(Exception):
    pass


class ProductNotFoundError(InventoryServiceError):
    pass


class InventoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_product(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> Product:
        product = self.db.query(Product).filter(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
        ).first()
        if product is None:
            raise ProductNotFoundError("商品不存在")
        return product
