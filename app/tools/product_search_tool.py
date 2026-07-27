"""ReAct 使用的商品目录只读搜索工具。"""

import logging

from app.providers.factory import get_product_provider
from app.providers.product_provider import InvalidProductSearchError, ProductProvider
from app.tools.executor import ToolErrorCategory, ToolErrorDetail, failure_result


logger = logging.getLogger(__name__)


def search_products(
    query: str,
    *,
    tenant_id: int,
    provider: ProductProvider | None = None,
) -> dict:
    """在服务端可信租户边界内搜索最多5件商品。"""
    try:
        products = (provider or get_product_provider()).search_products(
            tenant_id=tenant_id,
            query=query,
        )
    except InvalidProductSearchError as error:
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.VALIDATION,
            code="invalid_product_search",
            message=str(error),
            retryable=True,
            correction_hint="提供非空、具体的商品名称或关键词",
        ))
    except Exception:
        logger.exception("商品搜索工具调用Provider失败")
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.TRANSIENT,
            code="product_provider_unavailable",
            message="商品搜索暂时失败，请稍后重试",
            retryable=True,
        ))

    return {
        "success": True,
        "data": {
            "products": [
                {
                    "product_id": product.product_id,
                    "name": product.name,
                    "category": product.category,
                    "price": product.price,
                    "colors": product.colors,
                    "sizes": product.sizes,
                    "description": product.description,
                    "materials": product.materials,
                    "care_instructions": product.care_instructions,
                }
                for product in products
            ]
        },
        "error": None,
    }
