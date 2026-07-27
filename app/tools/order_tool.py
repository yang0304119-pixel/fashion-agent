"""
订单查询工具

根据订单号查询订单状态、物流信息等数据。

# 关键设计说明
# ─────────────────────────────
# 为什么输入输出用结构化 dict：
# - 统一接口，ReAct执行层不需要理解ORM对象
# - 返回结构包含 error 字段，调用方统一判断 success/error
# 为什么不直接返回 ORM 对象：
# - ORM 对象含 SQLAlchemy 内部状态，序列化后传给 LLM 不安全
# - dict 是纯数据，可控、可序列化、可记录到 Agent Trace
# ─────────────────────────────
"""

import logging

from app.providers.factory import get_order_provider
from app.providers.order_provider import OrderNotFoundError, OrderProvider
from app.tools.executor import ToolErrorCategory, ToolErrorDetail, failure_result


logger = logging.getLogger(__name__)


def query_order(
    order_id: int,
    *,
    user_id: int,
    tenant_id: int,
    provider: OrderProvider | None = None,
) -> dict:
    """查询订单状态信息。

    Args:
        order_id: 订单号（如 10001）。
        user_id: 服务端认证得到的用户 ID。
        tenant_id: 服务端认证得到的租户 ID。
        provider: 可选的订单系统 Provider，测试时可注入 Fake。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {order_id, status, product_name, quantity, total_price, created_at} | None
        - error: str | None
    """
    try:
        order = (provider or get_order_provider()).get_order(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
        )

        return {
            "success": True,
            "data": {
                "order_id": order.order_id,
                "status": order.status,
                "product_id": order.product_id,
                "product_name": order.product_name,
                "quantity": order.quantity,
                "total_price": order.amount,
                "created_at": str(order.created_at) if order.created_at else None,
            },
            "error": None,
        }

    except OrderNotFoundError as error:
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.BUSINESS,
            code="order_not_found",
            message=str(error),
            correction_hint="请核对订单号；不要重复查询同一个无效订单号",
        ))
    except Exception:
        logger.exception("订单工具调用Provider失败")
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.TRANSIENT,
            code="order_provider_unavailable",
            message="订单查询暂时失败，请稍后重试",
            retryable=True,
        ))
