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

import logging

from app.providers.factory import get_inventory_provider
from app.providers.inventory_provider import InventoryNotFoundError, InventoryProvider
from app.tools.executor import ToolErrorCategory, ToolErrorDetail, failure_result


logger = logging.getLogger(__name__)


def query_inventory(
    product_id: int,
    *,
    tenant_id: int,
    provider: InventoryProvider | None = None,
) -> dict:
    """查询商品库存信息。

    Args:
        product_id: 商品 ID。
        tenant_id: 服务端认证得到的租户 ID。
        provider: 可选的库存系统 Provider，测试时可注入 Fake。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {product_id, name, stock, colors, sizes} | None
        - error: str | None
    """
    try:
        inventory = (provider or get_inventory_provider()).get_inventory(
            tenant_id=tenant_id,
            product_id=product_id,
        )

        return {
            "success": True,
            "data": {
                "product_id": inventory.product_id,
                "name": inventory.product_name,
                "category": inventory.category,
                "price": inventory.price,
                "stock": inventory.stock,
                "colors": inventory.colors,
                "sizes": inventory.sizes,
            },
            "error": None,
        }

    except InventoryNotFoundError as error:
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.BUSINESS,
            code="inventory_not_found",
            message=str(error),
            correction_hint="先使用 search_products 获取当前租户内的有效商品ID",
        ))
    except Exception:
        logger.exception("库存工具调用Provider失败")
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.TRANSIENT,
            code="inventory_provider_unavailable",
            message="库存查询暂时失败，请稍后重试",
            retryable=True,
        ))
