"""
库存查询工具

根据商品 ID 查询当前库存量。

# 关键设计说明
# ─────────────────────────────
# 为什么不和 order_tool 合并：
# - 单一职责，每个工具只做一个事
# - inventory 查询频率可能远高于 order，拆开便于独立缓存
# ─────────────────────────────
"""

from app.core.database import SessionLocal
from app.models.product import Product


def query_inventory(product_id: int) -> dict:
    """查询商品库存信息。

    Args:
        product_id: 商品 ID。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {product_id, name, stock, colors, sizes} | None
        - error: str | None
    """
    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()

        if not product:
            return {
                "success": False,
                "data": None,
                "error": f"商品 {product_id} 不存在",
            }

        return {
            "success": True,
            "data": {
                "product_id": product.id,
                "name": product.name,
                "category": product.category,
                "price": float(product.price),
                "stock": product.stock,
                "colors": product.colors,
                "sizes": product.sizes,
            },
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"查询库存失败：{str(e)}",
        }

    finally:
        db.close()
