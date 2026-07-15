"""
退款风控工具

包含风险判断和工单创建两个工具函数。

# 关键设计说明
# ─────────────────────────────
# 为什么 risk_check 和 create_ticket 放一个文件：
# - 两个函数在退款流程中总是成对出现，放一起好找
# - risk_check 的输出（risk_level）直接决定 create_ticket 的调用
# 为什么阶段只做金额阈值判断：
# - 频率检测（用户退款次数/累计金额）需要历史数据支撑
# - MVP 阶段先跑通流程，上线前再加用户维度的防护
# ─────────────────────────────
"""

from decimal import Decimal

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.order import Order
from app.models.ticket import Ticket


def risk_check(order_id: int, reason: str, user_id: int | None = None) -> dict:
    """判断退款请求的风险等级。

    Args:
        order_id: 订单号。
        reason: 用户填写的退款原因。
        user_id: 用户 ID（预留，后续频率检测用）。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {risk_level, human_required, reason} | None
        - error: str | None
    """
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()

        # ── 订单不存在 ──
        if not order:
            return {
                "success": False,
                "data": None,
                "error": f"订单 {order_id} 不存在",
            }

        # ── 已退款订单不重复处理 ──
        if order.status == "refunded":
            return {
                "success": False,
                "data": None,
                "error": f"订单 {order_id} 已完成退款，无需重复处理",
            }

        # ── 金额判断 ──
        limit = settings.REFUND_AUTO_LIMIT  # 默认 100.00
        amount = Decimal(str(order.total_price))

        if amount > limit:
            return {
                "success": True,
                "data": {
                    "risk_level": "high",
                    "human_required": True,
                    "reason": f"退款金额 {amount} 元超过自动审批限额 {limit} 元，需人工审核",
                },
                "error": None,
            }

        # 金额 ≤ 100：规则明确则自动通过
        return {
            "success": True,
            "data": {
                "risk_level": "low",
                "human_required": False,
                "reason": f"退款金额 {amount} 元在自动审批范围内，已自动处理",
            },
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"风险判断失败：{str(e)}",
        }

    finally:
        db.close()


def create_ticket(order_id: int, user_id: int, reason: str,
                  amount: Decimal, risk_level: str) -> dict:
    """创建售后工单（退款/换货）。

    Args:
        order_id: 关联订单号。
        user_id: 用户 ID。
        reason: 退款原因。
        amount: 退款金额。
        risk_level: 风险等级（low/medium/high）。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {ticket_id, status} | None
        - error: str | None
    """
    db = SessionLocal()
    try:
        ticket = Ticket(
            tenant_id=1,
            order_id=order_id,
            user_id=user_id,
            type="refund",
            reason=reason,
            amount=amount,
            risk_level=risk_level,
            status="pending",
            human_review=(risk_level != "low"),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        return {
            "success": True,
            "data": {
                "ticket_id": ticket.id,
                "status": ticket.status,
            },
            "error": None,
        }

    except Exception as e:
        db.rollback()
        return {
            "success": False,
            "data": None,
            "error": f"创建工单失败：{str(e)}",
        }

    finally:
        db.close()
