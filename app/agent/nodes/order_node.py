"""确定性订单查询节点。"""

import logging

from app.agent.state import AgentState
from app.agent.slot_extractors import collect_slots
from app.providers.factory import get_order_provider
from app.providers.order_provider import OrderNotFoundError, OrderProvider


logger = logging.getLogger(__name__)
ORDER_STATUS_LABELS = {
    "pending": "待发货",
    "shipped": "已发货",
    "delivered": "已签收",
    "refunded": "已退款",
    "cancelled": "已取消",
}


def order_node(
    state: AgentState,
    provider: OrderProvider | None = None,
) -> dict:
    collected_slots = collect_slots(
        "order_query",
        state.get("message", ""),
        state.get("collected_slots"),
    )
    order_id = collected_slots.get("order_id")
    if order_id is None:
        return {
            "missing_slots": ["order_id"],
            "collected_slots": collected_slots,
            "tool_status": "pending",
            "tool_result": {
                "success": False,
                "data": None,
                "error": "缺少订单号",
            },
            "final_answer": "请提供需要查询的订单号，例如：查询订单 10001。",
        }

    try:
        order = (provider or get_order_provider()).get_order(
            tenant_id=state.get("tenant_id", 0),
            user_id=state.get("user_id", 0),
            order_id=order_id,
        )
        status_label = ORDER_STATUS_LABELS.get(order.status, order.status)
        data = {
            "order_id": order.order_id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "total_price": order.amount,
            "status": order.status,
            "status_label": status_label,
            "created_at": (
                order.created_at.isoformat() if order.created_at else None
            ),
        }
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "success",
            "tool_result": {"success": True, "data": data, "error": None},
            "final_answer": (
                f"订单 {order.order_id} 当前状态为“{status_label}”，"
                f"共 {order.quantity} 件，订单金额 "
                f"{order.amount:.2f} 元。"
            ),
        }
    except OrderNotFoundError:
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "error",
            "tool_result": {
                "success": False,
                "data": None,
                "error": "订单不存在或不属于当前用户",
            },
            "final_answer": "没有找到该订单，请确认订单号是否正确。",
        }
    except Exception:
        logger.exception("确定性订单节点执行失败")
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "error",
            "tool_result": {
                "success": False,
                "data": None,
                "error": "订单查询暂时失败",
            },
            "final_answer": "订单查询暂时失败，请稍后重试。",
        }
