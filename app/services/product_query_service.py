"""Demo 客服会话使用的只读商品查询服务。"""

from sqlalchemy.orm import Session

from app.models.product import Product


class ProductQueryError(Exception):
    pass


class ProductNotFoundError(ProductQueryError):
    pass


class ProductQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_tenant(
        self,
        *,
        tenant_id: int,
        limit: int = 50,
    ) -> list[Product]:
        safe_limit = max(1, min(limit, 50))
        return (
            self.db.query(Product)
            .filter(Product.tenant_id == tenant_id)
            .order_by(Product.id.asc())
            .limit(safe_limit)
            .all()
        )

    def get_for_tenant(
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


def product_image_url(product_id: int) -> str:
    """返回由前端本地样式渲染的稳定商品视觉标识。"""
    return "/assets/products/product-card.svg"

