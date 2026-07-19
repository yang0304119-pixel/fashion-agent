"""请求汇总与节点步骤两层 Agent Trace 服务。"""

from collections.abc import Callable
from datetime import UTC, datetime
import logging
from time import perf_counter
from sqlalchemy import func

from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.models.agent_trace import AgentTrace
from app.models.agent_trace_step import AgentTraceStep
from app.models.unresolved_case import UnresolvedCase


logger = logging.getLogger(__name__)
WORKFLOW_BY_INTENT = {
    "knowledge_query": "rag_workflow",
    "product_query": "product_workflow",
    "order_query": "order_workflow",
    "inventory_query": "inventory_workflow",
    "size_recommend": "size_workflow",
    "composite_query": "react_readonly_workflow",
    "refund_request": "refund_workflow",
    "refund_status_query": "refund_status_workflow",
    "after_sales_request": "human_handoff_workflow",
    "human_handoff": "human_handoff_workflow",
    "fallback": "fallback_workflow",
}
ERROR_STAGE_BY_NODE = {
    "router": "router",
    "rag": "rag_retrieval",
    "react": "react_planning",
    "order": "order_query",
    "inventory": "inventory_query",
    "size": "size_recommend",
    "refund": "refund_validation",
    "refund_status": "refund_status_query",
    "handoff": "human_handoff",
    "answer": "tool_execution",
    "conversation_state": "conversation_state",
    "trace": "trace_persistence",
}
TOOL_BY_NODE = {
    "order": "order_service",
    "inventory": "inventory_service",
    "size": "size_service",
    "react": "react_readonly_tools",
    "refund": "refund_service",
    "refund_status": "refund_query_service",
    "handoff": "human_handoff",
    "rag": "rag_service",
}


def create_request_trace(
    *,
    tenant_id: int,
    user_id: int,
    session_id: str,
    message: str,
) -> int | None:
    """在Graph运行前创建请求级汇总；失败不阻断客服请求。"""
    db = SessionLocal()
    try:
        trace = AgentTrace(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            node_name="workflow",
            message=message,
            status="running",
            input={"session_id": session_id, "message": message},
        )
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace.id
    except Exception:
        db.rollback()
        logger.exception("Agent Trace请求汇总创建失败")
        return None
    finally:
        db.close()


def traced_node(node_name: str, node: Callable[[AgentState], dict]) -> Callable:
    """包装LangGraph节点，记录实际开始、结束、状态、耗时和错误。"""

    def wrapped(state: AgentState) -> dict:
        trace_id = state.get("trace_id")
        step_id = _start_step(trace_id, node_name, state)
        started = perf_counter()
        try:
            result = node(state)
        except Exception as error:
            duration_ms = max(0, round((perf_counter() - started) * 1000))
            _finish_step_exception(
                trace_id=trace_id,
                step_id=step_id,
                node_name=node_name,
                error=error,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = max(0, round((perf_counter() - started) * 1000))
        merged_state = dict(state)
        merged_state.update(result or {})
        _finish_step_result(
            trace_id=trace_id,
            step_id=step_id,
            node_name=node_name,
            state=merged_state,
            duration_ms=duration_ms,
        )
        return result

    wrapped.__name__ = f"traced_{node_name}_node"
    return wrapped


def finalize_request_trace(state: AgentState) -> int | None:
    """在Graph收尾时把最终状态更新到已存在的请求汇总。"""
    trace_id = state.get("trace_id")
    if not trace_id:
        return record_trace(state)

    db = SessionLocal()
    try:
        trace = db.query(AgentTrace).filter(AgentTrace.id == trace_id).first()
        if trace is None:
            return None
        _apply_summary(trace, state)
        db.commit()
        return trace.id
    except Exception:
        db.rollback()
        logger.exception("Agent Trace请求汇总更新失败")
        return None
    finally:
        db.close()


def finalize_request_failure(trace_id: int | None, error: Exception) -> None:
    """Graph未能进入收尾节点时标记请求失败。"""
    if not trace_id:
        return
    db = SessionLocal()
    try:
        trace = db.query(AgentTrace).filter(AgentTrace.id == trace_id).first()
        if trace is None:
            return
        trace.status = "failed"
        trace.error_stage = trace.error_stage or "tool_execution"
        trace.error_code = trace.error_code or "workflow_exception"
        trace.error_type = type(error).__name__
        trace.error_message = "工作流执行异常"
        trace.finished_at = _utc_now()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Agent Trace失败状态更新失败")
    finally:
        db.close()


def record_trace(state: AgentState) -> int | None:
    """兼容旧调用：没有预创建汇总时直接写入一条完整记录。"""
    db = SessionLocal()
    try:
        trace = AgentTrace(
            tenant_id=state.get("tenant_id", 0),
            user_id=state.get("user_id", 0),
            session_id=state.get("session_id", ""),
            node_name="workflow",
            message=state.get("message"),
            input={
                "session_id": state.get("session_id"),
                "message": state.get("message"),
            },
        )
        _apply_summary(trace, state)
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace.id
    except Exception:
        db.rollback()
        logger.exception("Agent Trace写入失败")
        return None
    finally:
        db.close()


def record_unresolved(state: AgentState) -> int | None:
    intent = state.get("intent", "")
    confidence = state.get("confidence", 0.0)
    if state.get("fallback_handled", False):
        return None
    if intent != "fallback" and confidence >= 0.5:
        return None

    db = SessionLocal()
    try:
        case = UnresolvedCase(
            tenant_id=state.get("tenant_id", 0),
            user_id=state.get("user_id", 0),
            user_message=state.get("message", ""),
            predicted_intent=intent,
            confidence=confidence,
            fallback_reason="低置信度" if confidence < 0.5 else "无法识别意图",
            final_answer=state.get("final_answer", ""),
            is_resolved=False,
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case.id
    except Exception:
        db.rollback()
        logger.exception("未解决案例写入失败")
        return None
    finally:
        db.close()


def _start_step(
    trace_id: int | None,
    node_name: str,
    state: AgentState,
) -> int | None:
    if not trace_id:
        return None
    db = SessionLocal()
    try:
        sequence = (
            db.query(func.max(AgentTraceStep.sequence))
            .filter(AgentTraceStep.trace_id == trace_id)
            .scalar()
            or 0
        ) + 1
        step = AgentTraceStep(
            trace_id=trace_id,
            sequence=sequence,
            node_name=node_name,
            workflow_name=_workflow_name(state),
            status="running",
            tool_name=TOOL_BY_NODE.get(node_name),
            started_at=_utc_now(),
        )
        db.add(step)
        db.commit()
        db.refresh(step)
        return step.id
    except Exception:
        db.rollback()
        logger.exception("Agent Trace节点开始记录失败: %s", node_name)
        return None
    finally:
        db.close()


def _finish_step_result(
    *,
    trace_id: int | None,
    step_id: int | None,
    node_name: str,
    state: AgentState,
    duration_ms: int,
) -> None:
    if not step_id:
        return
    db = SessionLocal()
    try:
        step = db.query(AgentTraceStep).filter(AgentTraceStep.id == step_id).first()
        if step is None:
            return
        status, error = _result_status(node_name, state)
        step.workflow_name = _workflow_name(state)
        step.status = status
        step.missing_slots = _safe_serialize(state.get("missing_slots") or [])
        step.rag_sources = _safe_serialize(state.get("retrieved_sources") or [])
        step.error_stage = error.get("stage")
        step.error_code = error.get("code")
        step.error_type = error.get("type")
        step.error_message = error.get("message")
        step.finished_at = _utc_now()
        step.duration_ms = duration_ms

        if trace_id:
            trace = db.query(AgentTrace).filter(AgentTrace.id == trace_id).first()
            if trace is not None:
                trace.workflow_name = _workflow_name(state)
                trace.intent = state.get("intent")
                trace.confidence = state.get("confidence")
                if status == "failed":
                    trace.error_stage = step.error_stage
                    trace.error_code = step.error_code
                    trace.error_type = step.error_type
                    trace.error_message = step.error_message
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Agent Trace节点完成记录失败: %s", node_name)
    finally:
        db.close()


def _finish_step_exception(
    *,
    trace_id: int | None,
    step_id: int | None,
    node_name: str,
    error: Exception,
    duration_ms: int,
) -> None:
    if not step_id:
        finalize_request_failure(trace_id, error)
        return
    db = SessionLocal()
    try:
        step = db.query(AgentTraceStep).filter(AgentTraceStep.id == step_id).first()
        if step is not None:
            step.status = "failed"
            step.error_stage = ERROR_STAGE_BY_NODE.get(node_name, "tool_execution")
            step.error_code = "node_exception"
            step.error_type = type(error).__name__
            step.error_message = f"{node_name}节点执行异常"
            step.finished_at = _utc_now()
            step.duration_ms = duration_ms
        trace = db.query(AgentTrace).filter(AgentTrace.id == trace_id).first()
        if trace is not None:
            trace.status = "failed"
            trace.error_stage = ERROR_STAGE_BY_NODE.get(node_name, "tool_execution")
            trace.error_code = "node_exception"
            trace.error_type = type(error).__name__
            trace.error_message = f"{node_name}节点执行异常"
            trace.finished_at = _utc_now()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Agent Trace节点异常记录失败: %s", node_name)
    finally:
        db.close()


def _apply_summary(trace: AgentTrace, state: AgentState) -> None:
    status, error = _result_status("workflow", state)
    trace.intent = state.get("intent")
    trace.confidence = state.get("confidence")
    trace.workflow_name = _workflow_name(state)
    trace.status = status
    trace.output = _trace_output(state)
    trace.retrieved_doc_ids = _safe_serialize(state.get("retrieved_doc_ids"))
    trace.retrieved_scores = _safe_serialize(state.get("retrieved_scores"))
    trace.tool_name = _workflow_name(state)
    trace.tool_status = state.get("tool_status")
    trace.human_required = bool(state.get("human_required", False))
    trace.final_answer = state.get("final_answer")
    trace.missing_slots = _safe_serialize(state.get("missing_slots") or [])
    trace.rag_sources = _safe_serialize(state.get("retrieved_sources") or [])
    trace.error_stage = trace.error_stage or error.get("stage")
    trace.error_code = trace.error_code or error.get("code")
    trace.error_type = trace.error_type or error.get("type")
    trace.error_message = trace.error_message or error.get("message")
    trace.finished_at = _utc_now()


def _trace_output(state: AgentState) -> dict:
    return {
        "intent": state.get("intent"),
        "confidence": state.get("confidence"),
        "intents": state.get("intents"),
        "router_source": state.get("router_source"),
        "router_evidence": state.get("router_evidence"),
        "requires_planning": state.get("requires_planning"),
        "missing_slots": state.get("missing_slots"),
        "pending_intent": state.get("pending_intent"),
        "collected_slots": _safe_serialize(state.get("collected_slots")),
        "tool_result": _safe_serialize(state.get("tool_result")),
        "tool_status": state.get("tool_status"),
        "risk_level": state.get("risk_level"),
        "human_required": state.get("human_required"),
        "refund_request_id": state.get("refund_request_id"),
        "refund_status": state.get("refund_status"),
        "final_answer": state.get("final_answer"),
        "retrieved_doc_ids": state.get("retrieved_doc_ids"),
        "retrieved_scores": state.get("retrieved_scores"),
        "retrieved_sources": state.get("retrieved_sources"),
        "rag_error_code": state.get("rag_error_code"),
        "rag_error_stage": state.get("rag_error_stage"),
        "rag_error_type": state.get("rag_error_type"),
    }


def _result_status(node_name: str, state: AgentState) -> tuple[str, dict[str, str | None]]:
    observes_business_result = node_name in {
        "workflow",
        "rag",
        "react",
        "order",
        "inventory",
        "size",
        "refund",
        "refund_status",
        "handoff",
    }
    if not observes_business_result:
        return "succeeded", {
            "stage": None,
            "code": None,
            "type": None,
            "message": None,
        }
    rag_stage = state.get("rag_error_stage")
    if rag_stage:
        return "failed", {
            "stage": rag_stage,
            "code": state.get("rag_error_code"),
            "type": state.get("rag_error_type"),
            "message": "RAG处理失败",
        }
    tool_status = state.get("tool_status")
    if tool_status == "error":
        tool_result = state.get("tool_result") or {}
        return "failed", {
            "stage": ERROR_STAGE_BY_NODE.get(node_name, "tool_execution"),
            "code": "business_error",
            "type": "BusinessError",
            "message": str(tool_result.get("error") or "业务处理失败"),
        }
    if tool_status == "pending" or state.get("missing_slots"):
        return "pending", {"stage": None, "code": None, "type": None, "message": None}
    return "succeeded", {"stage": None, "code": None, "type": None, "message": None}


def _workflow_name(state: AgentState) -> str | None:
    return WORKFLOW_BY_INTENT.get(state.get("intent", ""))


def _safe_serialize(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, dict):
        return {key: _safe_serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(item) for item in value]
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
