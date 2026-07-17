"""
Trace 服务 — 请求级可观测性

将每次 Agent 请求的完整状态写入 agent_trace 表，
用于排查问题、审计复盘和效果分析。

# 关键设计说明
# ─────────────────────────────
# 为什么是请求级写入而非节点级：
# - MVP 阶段先打通"每次请求可追溯"的能力
# - 节点级追踪（每步都写一条）后续再补充
# - 一个请求一条记录，查询时按 session_id 定位即可
# ─────────────────────────────
"""

import json
import logging

from app.core.database import SessionLocal
from app.models.agent_trace import AgentTrace
from app.models.unresolved_case import UnresolvedCase
from app.agent.state import AgentState


logger = logging.getLogger(__name__)


def record_trace(state: AgentState) -> int | None:
    """将当前 AgentState 记录到 agent_trace 表。

    捕捉一个请求的完整执行链路，写入一条记录。
    后续需要节点级追踪时，可在此函数基础上加 node_name 参数。

    Args:
        state: 工作流结束后的完整 AgentState。

    Returns:
        trace_id: agent_trace 表记录 ID，写入失败时返回 None。
    """
    db = None

    try:
        # 构造用于 JSON 序列化的 input/output
        trace_input = {
            "session_id": state.get("session_id"),
            "user_id": state.get("user_id"),
            "message": state.get("message"),
        }
        trace_output = {
            "intent": state.get("intent"),
            "confidence": state.get("confidence"),
            "missing_slots": state.get("missing_slots"),
            "tool_result": _safe_serialize(state.get("tool_result")),
            "tool_status": state.get("tool_status"),
            "risk_level": state.get("risk_level"),
            "human_required": state.get("human_required"),
            "final_answer": state.get("final_answer"),
            "retrieved_doc_ids": state.get("retrieved_doc_ids"),
            "retrieved_scores": state.get("retrieved_scores"),
            "retrieved_sources": state.get(
                "retrieved_sources"
            ),
            "rag_error_code": state.get(
                "rag_error_code"
            ),
            "rag_error_stage": state.get(
                "rag_error_stage"
            ),
            "rag_error_type": state.get(
                "rag_error_type"
            ),
        }

        trace = AgentTrace(
            session_id=state.get("session_id", ""),
            node_name="workflow",  # 请求级记录，节点名固定为 workflow
            intent=state.get("intent"),
            confidence=state.get("confidence"),
            input=trace_input,
            output=trace_output,
            retrieved_doc_ids=state.get("retrieved_doc_ids"),
            retrieved_scores=state.get("retrieved_scores"),
            tool_name=_detect_tool_name(state.get("intent", "")),
            tool_status=state.get("tool_status"),
            human_required=state.get("human_required", False),
            final_answer=state.get("final_answer"),
        )

        db = SessionLocal()
        db.add(trace)
        db.commit()
        db.refresh(trace)
        return trace.id

    except Exception:
        logger.exception("Agent Trace 写入失败")
        return None

    finally:
        if db is not None:
            db.close()


def record_unresolved(state: AgentState) -> int | None:
    """将 fallback 或低置信度请求记录到 unresolved_case 表。

    Args:
        state: 工作流结束后的 AgentState。

    Returns:
        case_id: unresolved_case 记录 ID，写入失败时返回 None。
    """
    intent: str = state.get("intent", "")
    confidence: float = state.get("confidence", 0.0)

    # 只记录 fallback 或低置信度
    if intent != "fallback" and confidence >= 0.5:
        return None

    db = None

    try:
        case = UnresolvedCase(
            user_message=state.get("message", ""),
            predicted_intent=intent,
            confidence=confidence,
            fallback_reason="低置信度" if confidence < 0.5 else "无法识别意图",
            final_answer=state.get("final_answer", ""),
            is_resolved=False,
        )

        db = SessionLocal()
        db.add(case)
        db.commit()
        db.refresh(case)
        return case.id

    except Exception:
        logger.exception("未解决案例写入失败")
        return None

    finally:
        if db is not None:
            db.close()


def _safe_serialize(value: object) -> object:
    """确保值可 JSON 序列化，Decimal 等类型转 float。"""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _safe_serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _detect_tool_name(intent: str) -> str | None:
    """根据 intent 推断调用的工具名称。"""
    mapping = {
        "order_query": "query_order",
        "size_recommend": "size_recommend",
        "refund_request": "refund_flow",
    }
    return mapping.get(intent)
