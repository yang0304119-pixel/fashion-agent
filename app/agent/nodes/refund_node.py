"""
退款编排节点

处理退款请求的多步流程：查订单 → 风险判断 → 自动处理/创建工单。

# 关键设计说明
# ─────────────────────────────
# 为什么 refund_node 不从 tool_node 走：
# - 退款不是"调一个工具就完事"，需要多步编排和条件分支
# - tool_node 的设计是"一个 intent 对应一个工具"，不适用于多步流程
# - refund_node 内部串联 query_order → risk_check → create_ticket
# ─────────────────────────────
"""

import re

from app.agent.state import AgentState
from app.tools.order_tool import query_order
from app.tools.refund_tool import risk_check, create_ticket
from app.core.config import settings


def refund_node(state: AgentState) -> dict:
    """退款编排节点：查订单 → 风险判断 → 自动处理／创建工单。

    Args:
        state: 当前 AgentState，至少包含 message 和 user_id。

    Returns:
        更新 state 的字典，包含 tool_result / risk_level / human_required。
    """
    message: str = state.get("message", "")
    user_id: int = state.get("user_id", 0)

    # ── 提取订单号和退款原因 ──
    order_id = _extract_order_id(message)
    reason = _extract_reason(message)

    if not order_id:
        return {
            "tool_result": {"success": False, "error": "未找到订单号，请提供订单号"},
            "tool_status": "error",
            "risk_level": "medium",
            "human_required": False,
        }

    # ── 第 1 步：查订单 ──
    order_result = query_order(order_id)

    if not order_result.get("success"):
        return {
            "tool_result": order_result,
            "tool_status": "error",
            "risk_level": "medium",
            "human_required": False,
        }

    # ── 第 2 步：风险判断 ──
    risk_result = risk_check(
        order_id=order_id,
        reason=reason,
        user_id=user_id,
    )

    if not risk_result.get("success"):
        return {
            "tool_result": risk_result,
            "tool_status": "error",
            "risk_level": "medium",
            "human_required": False,
        }

    risk_data = risk_result["data"]
    risk_level = risk_data["risk_level"]
    human_required = risk_data["human_required"]

    # ── 第 3 步：高风险 → 创建工单 ──
    if human_required:
        amount = order_result["data"]["total_price"]

        ticket_result = create_ticket(
            order_id=order_id,
            user_id=user_id,
            reason=reason or "用户未填写原因",
            amount=amount,
            risk_level=risk_level,
        )

        return {
            "tool_result": ticket_result,
            "tool_status": "success" if ticket_result.get("success") else "error",
            "risk_level": risk_level,
            "human_required": True,
        }

    # 低风险 → 自动通过（不创建工单）
    return {
        "tool_result": {
            "success": True,
            "data": {"auto_approved": True, "message": "退款已自动处理"},
        },
        "tool_status": "success",
        "risk_level": "low",
        "human_required": False,
    }


def _extract_order_id(message: str) -> int | None:
    """从消息中提取订单号。"""
    patterns = [
        r"订单[号#\s]*(\d{5,})",
        r"(\d{5,})[号#]",
        r"订单[\s:：]*(\d{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return None


def _extract_reason(message: str) -> str:
    """从消息中提取退款原因关键词。"""
    reasons = {
        "质量问题": ["质量问题", "破了", "坏了", "破损", "脱线", "起球", "褪色", "掉色"],
        "发错货": ["发错", "发的不对", "不是我买的", "错发"],
        "不想要了": ["不想要了", "不喜欢", "买错了", "后悔了"],
        "尺寸不合适": ["太大", "太小", "不合身", "穿不了", "太紧", "太松"],
    }

    for category, keywords in reasons.items():
        for keyword in keywords:
            if keyword in message:
                return category

    return "用户未明确说明原因"
