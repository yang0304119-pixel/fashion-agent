"""已有退款申请状态的确定性只读查询节点。"""

from app.agent.slot_extractors import collect_slots
from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.models.refund_request import RefundRequest


STATUS_LABELS = {
    "reviewing": "等待人工审核",
    "approved": "审核通过，等待退款渠道处理",
    "succeeded": "退款成功",
    "rejected": "退款申请已拒绝",
    "failed": "退款渠道处理失败",
}


def refund_status_node(state: AgentState) -> dict:
    slots = collect_slots(
        "refund_status_query",
        state.get("message", ""),
        state.get("collected_slots"),
    )
    order_id = slots.get("order_id")
    if order_id is None:
        return {
            "missing_slots": ["order_id"],
            "collected_slots": slots,
            "tool_status": "pending",
            "final_answer": "请提供需要查询退款进度的订单号。",
        }
    db = SessionLocal()
    try:
        refund = (
            db.query(RefundRequest)
            .filter(
                RefundRequest.tenant_id == state.get("tenant_id", 0),
                RefundRequest.user_id == state.get("user_id", 0),
                RefundRequest.order_id == order_id,
            )
            .order_by(RefundRequest.id.desc())
            .first()
        )
        if refund is None:
            return {
                "missing_slots": [],
                "collected_slots": slots,
                "tool_status": "error",
                "final_answer": f"没有找到订单 {order_id} 的退款申请记录。",
            }
        label = STATUS_LABELS.get(refund.status, refund.status)
        return {
            "missing_slots": [],
            "collected_slots": slots,
            "tool_status": "success",
            "tool_result": {
                "success": True,
                "data": {
                    "refund_request_id": refund.id,
                    "order_id": refund.order_id,
                    "status": refund.status,
                    "status_label": label,
                },
                "error": None,
            },
            "final_answer": (
                f"订单 {order_id} 的退款单号为 {refund.id}，当前状态：{label}。"
            ),
        }
    finally:
        db.close()
