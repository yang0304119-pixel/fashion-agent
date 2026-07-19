"""确定性退款工作流节点。

LLM只负责上游意图识别；订单归属、金额、风险、幂等和状态均由
RefundService基于可信身份和数据库数据决定。

当前有意保持普通确定性Workflow，而不是LangGraph子图。只有出现跨时暂停、
人工审核后自动恢复、渠道重试或节点级可视化需求时才升级编排层。
"""

from hashlib import sha256

from app.agent.state import AgentState
from app.agent.slot_extractors import collect_slots
from app.core.database import SessionLocal
from app.models.refund_request import RefundRequest
from app.services.refund_service import (
    RefundNotFoundError,
    RefundService,
    RefundServiceError,
    RefundStateError,
)


class RefundWorkflow:
    """把聊天状态转换成一次确定性的退款服务调用。"""

    def run(self, state: AgentState) -> dict:
        return _run_refund_workflow(state)


def refund_node(state: AgentState) -> dict:
    """LangGraph节点适配器。"""
    return RefundWorkflow().run(state)


def _run_refund_workflow(state: AgentState) -> dict:
    """提交退款申请并直接生成确定性回复，不经过ReAct或LLM。"""
    message = state.get("message", "").strip()
    tenant_id = state.get("tenant_id", 0)
    user_id = state.get("user_id", 0)
    session_id = state.get("session_id", "")
    collected_slots = collect_slots(
        "refund_request",
        message,
        state.get("collected_slots"),
    )
    order_id = collected_slots.get("order_id")

    if order_id is None:
        return {
            "missing_slots": ["order_id"],
            "collected_slots": collected_slots,
            "tool_result": {
                "success": False,
                "error": "缺少订单号",
            },
            "tool_status": "pending",
            "risk_level": "medium",
            "human_required": False,
            "final_answer": "请提供需要退款的订单号，例如：订单 10001 申请退款。",
        }

    reason = collected_slots.get("reason", "用户未明确说明原因")
    idempotency_key = _build_idempotency_key(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        order_id=order_id,
    )

    db = SessionLocal()
    try:
        outcome = RefundService(db).submit(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        refund = outcome.refund
        result = _success_state(refund, reused=outcome.reused)
        result["collected_slots"] = collected_slots
        return result
    except (RefundNotFoundError, RefundStateError) as error:
        result = _error_state(str(error))
        result["collected_slots"] = collected_slots
        return result
    except RefundServiceError:
        result = _error_state("退款申请暂时无法处理，请稍后重试。")
        result["collected_slots"] = collected_slots
        return result
    finally:
        db.close()


def _success_state(refund: RefundRequest, *, reused: bool) -> dict:
    prefix = "检测到该订单已有退款申请。" if reused else "退款申请已创建。"
    amount = f"{float(refund.amount):.2f}"
    demo_notice = (
        "当前为演示环境，本次为模拟退款，不涉及真实资金。"
        if refund.gateway_mode == "mock"
        else ""
    )

    if refund.status == "reviewing":
        answer = (
            f"{prefix}退款单号 {refund.id}，金额 {amount} 元。"
            "该申请需要人工审核，审核结果会更新到退款记录中。"
            f"{demo_notice}"
        )
        tool_status = "pending"
    elif refund.status == "approved":
        answer = (
            f"{prefix}退款单号 {refund.id}，金额 {amount} 元，"
            "已通过自动审批，正在等待退款渠道处理；当前尚不能视为到账完成。"
            f"{demo_notice}"
        )
        tool_status = "pending"
    elif refund.status == "succeeded":
        answer = (
            f"退款单号 {refund.id} 已处理成功，退款金额 {amount} 元。"
            f"{demo_notice or '具体到账时间以支付渠道为准。'}"
        )
        tool_status = "success"
    elif refund.status == "rejected":
        answer = (
            f"退款单号 {refund.id} 未通过审核。"
            f"原因：{refund.failure_reason or '请联系人工客服了解详情'}。"
            f"{demo_notice}"
        )
        tool_status = "error"
    else:
        answer = (
            f"退款单号 {refund.id} 的渠道处理失败，申请记录已保留，"
            "请联系人工客服继续处理。"
            f"{demo_notice}"
        )
        tool_status = "error"

    data = {
        "refund_request_id": refund.id,
        "order_id": refund.order_id,
        "amount": float(refund.amount),
        "status": refund.status,
        "risk_level": refund.risk_level,
        "human_required": refund.human_review,
        "ticket_id": refund.ticket_id,
        "gateway_mode": refund.gateway_mode,
        "provider_refund_id": refund.provider_refund_id,
        "failure_reason": refund.failure_reason,
        "reused": reused,
    }
    return {
        "missing_slots": [],
        "tool_result": {"success": True, "data": data, "error": None},
        "tool_status": tool_status,
        "risk_level": refund.risk_level,
        "human_required": refund.human_review,
        "refund_request_id": refund.id,
        "refund_status": refund.status,
        "final_answer": answer,
    }


def _error_state(message: str) -> dict:
    return {
        "missing_slots": [],
        "tool_result": {"success": False, "data": None, "error": message},
        "tool_status": "error",
        "risk_level": "medium",
        "human_required": False,
        "final_answer": message,
    }


def _build_idempotency_key(
    *,
    tenant_id: int,
    user_id: int,
    session_id: str,
    order_id: int,
) -> str:
    raw = f"refund:{tenant_id}:{user_id}:{session_id}:{order_id}"
    return sha256(raw.encode("utf-8")).hexdigest()
