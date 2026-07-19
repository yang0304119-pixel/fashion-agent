"""商品目录只读服务。"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.product import Product


class ProductCatalogServiceError(Exception):
    pass


class InvalidProductSearchError(ProductCatalogServiceError):
    pass


class ProductCatalogService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        *,
        tenant_id: int,
        query: str,
        limit: int = 5,
    ) -> list[Product]:
        """按租户搜索商品名称、分类、描述、材质和洗护信息。"""
        keyword = query.strip()
        if not keyword:
            raise InvalidProductSearchError("请提供商品名称或搜索关键词")

        safe_limit = max(1, min(limit, 5))
        pattern = f"%{_escape_like(keyword)}%"
        return (
            self.db.query(Product)
            .filter(
                Product.tenant_id == tenant_id,
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.category.ilike(pattern, escape="\\"),
                    Product.description.ilike(pattern, escape="\\"),
                    Product.materials.ilike(pattern, escape="\\"),
                    Product.care_instructions.ilike(pattern, escape="\\"),
                ),
            )
            .order_by(Product.id.asc())
            .limit(safe_limit)
            .all()
        )


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
