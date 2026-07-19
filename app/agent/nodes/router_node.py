"""分层漏斗意图路由节点。"""

import logging

from app.agent.intent_rules import (
    READONLY_INTENTS,
    classify_by_rules,
    detect_all_intents,
    is_after_sales_write_action,
    is_explicit_refund_action,
)
from app.agent.planner import plan_intents
from app.agent.semantic_router import (
    SEMANTIC_DIRECT_THRESHOLD,
    SEMANTIC_PLANNER_THRESHOLD,
    semantic_router,
)
from app.agent.slot_extractors import collect_slots, missing_slots_for_intent
from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.models.agent_trace import AgentTrace
from app.services.conversation_state_service import ConversationStateService


logger = logging.getLogger(__name__)


def router_node(state: AgentState) -> dict:
    message = state.get("message", "").strip()
    if not message:
        return _decision("fallback", 1.0, "rule", ["空消息"])

    pending = _resume_pending_conversation(state, message)
    if pending is not None:
        return pending

    rule_intent = classify_by_rules(message)
    if rule_intent is not None:
        matched_intents = [
            intent
            for intent in detect_all_intents(message)
            if intent in READONLY_INTENTS
        ]
        if rule_intent != "composite_query":
            matched_intents = [rule_intent]
        return _decision(
            rule_intent,
            0.99,
            "deterministic_rule",
            [f"高精度规则:{rule_intent}"],
            intents=matched_intents,
            requires_planning=(rule_intent == "composite_query"),
        )

    semantic = semantic_router.route(
        message=message,
        pending_intent=state.get("pending_intent"),
        chat_context=state.get("chat_context"),
        collected_slots=state.get("collected_slots"),
        recent_messages=_recent_messages(state),
    )
    if (
        semantic is not None
        and not semantic.requires_planning
        and semantic.confidence >= SEMANTIC_DIRECT_THRESHOLD
        and len(semantic.intents) == 1
    ):
        intent = semantic.intents[0]
        if intent == "refund_request" and not is_explicit_refund_action(message):
            intent = "knowledge_query"
        if intent == "after_sales_request" and not is_after_sales_write_action(message):
            intent = "fallback"
        return _decision(
            intent,
            semantic.confidence,
            semantic.source,
            semantic.evidence,
        )

    semantic_intents = semantic.intents if semantic else []
    planner = plan_intents(
        message=message,
        semantic_intents=semantic_intents,
        context_summary=_context_summary(state),
    )
    if planner is not None:
        if planner.requires_clarification:
            return {
                **_decision(
                    "fallback",
                    planner.confidence,
                    "llm_planner",
                    planner.evidence,
                ),
                "clarification_question": planner.clarification_question,
                "final_answer": planner.clarification_question
                or "请再说明一下您希望查询还是办理业务。",
                "fallback_handled": True,
            }
        intents = _guard_planner_intents(message, planner.intents)
        route_intent = _route_intents(intents)
        return _decision(
            route_intent,
            planner.confidence,
            "llm_planner",
            planner.evidence,
            intents=intents,
            requires_planning=(route_intent == "composite_query"),
        )

    if semantic is not None and semantic.confidence >= SEMANTIC_PLANNER_THRESHOLD:
        intents = _guard_planner_intents(message, semantic.intents)
        route_intent = _route_intents(intents)
        if route_intent != "fallback":
            return _decision(
                route_intent,
                semantic.confidence,
                semantic.source,
                semantic.evidence,
                intents=intents,
                requires_planning=(route_intent == "composite_query"),
            )

    return _decision(
        "fallback",
        semantic.confidence if semantic else 0.0,
        "safe_fallback",
        (semantic.evidence if semantic else []) + ["低置信度，未执行写操作"],
    )


def _decision(
    intent: str,
    confidence: float,
    source: str,
    evidence: list[str],
    *,
    intents: list[str] | None = None,
    requires_planning: bool = False,
) -> dict:
    return {
        "intent": intent,
        "intents": intents or [intent],
        "confidence": round(float(confidence), 4),
        "router_source": source,
        "router_evidence": evidence,
        "requires_planning": requires_planning,
        "missing_slots": [],
    }


def _route_intents(intents: list[str]) -> str:
    unique = list(dict.fromkeys(intents))
    protected = [
        intent
        for intent in unique
        if intent in {"human_handoff", "after_sales_request", "refund_request"}
    ]
    if protected:
        return protected[0]
    readonly = [intent for intent in unique if intent in READONLY_INTENTS]
    if len(readonly) > 1:
        return "composite_query"
    if readonly:
        return readonly[0]
    return "fallback"


def _guard_planner_intents(message: str, intents: list[str]) -> list[str]:
    guarded: list[str] = []
    for intent in intents:
        if intent == "refund_request" and not is_explicit_refund_action(message):
            guarded.append("knowledge_query")
        elif intent == "after_sales_request" and not is_after_sales_write_action(message):
            guarded.append("fallback")
        else:
            guarded.append(intent)
    return list(dict.fromkeys(guarded))


def _resume_pending_conversation(state: AgentState, message: str) -> dict | None:
    tenant_id = state.get("tenant_id", 0)
    user_id = state.get("user_id", 0)
    session_id = state.get("session_id", "")
    if not tenant_id or not user_id or not session_id:
        return None
    db = SessionLocal()
    try:
        pending = ConversationStateService(db).load_active(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        db.rollback()
        logger.exception("读取待补槽位会话失败")
        return None
    finally:
        db.close()
    if pending is None:
        return None
    context_type = (state.get("chat_context") or {}).get("context_type")
    if _context_conflicts_with_pending(context_type, pending.pending_intent):
        return None
    current_rule_intent = classify_by_rules(message)
    existing = dict(pending.collected_slots)
    existing.update(state.get("collected_slots") or {})
    slots = collect_slots(pending.pending_intent, message, existing)
    compatible = current_rule_intent in {None, pending.pending_intent}
    if (
        pending.pending_intent in {"refund_request", "refund_status_query"}
        and current_rule_intent == "order_query"
        and slots.get("order_id") is not None
        and not any(word in message for word in ("查询", "发货", "物流", "快递", "状态"))
    ):
        compatible = True
    if not compatible:
        return None
    return {
        **_decision(
            pending.pending_intent,
            1.0,
            "conversation_state",
            ["恢复待补参数意图"],
        ),
        "pending_intent": pending.pending_intent,
        "missing_slots": missing_slots_for_intent(pending.pending_intent, slots),
        "collected_slots": slots,
    }


def _context_conflicts_with_pending(context_type: str | None, pending: str) -> bool:
    if context_type == "product":
        return pending in {"order_query", "refund_request", "refund_status_query"}
    if context_type == "order":
        return pending in {"inventory_query", "product_query", "size_recommend"}
    return False


def _context_summary(state: AgentState) -> str:
    context = state.get("chat_context") or {}
    slots = state.get("collected_slots") or {}
    return f"context={context}; collected_slots={slots}; pending={state.get('pending_intent')}"


def _recent_messages(state: AgentState) -> list[str]:
    tenant_id = state.get("tenant_id", 0)
    user_id = state.get("user_id", 0)
    session_id = state.get("session_id", "")
    if not tenant_id or not user_id or not session_id:
        return []
    db = SessionLocal()
    try:
        rows = (
            db.query(AgentTrace.message)
            .filter(
                AgentTrace.tenant_id == tenant_id,
                AgentTrace.user_id == user_id,
                AgentTrace.session_id == session_id,
                AgentTrace.message.is_not(None),
            )
            .order_by(AgentTrace.id.desc())
            .limit(4)
            .all()
        )
        messages = [str(row[0]) for row in reversed(rows) if row[0]]
        current = state.get("message", "").strip()
        if messages and messages[-1] == current:
            messages.pop()
        return messages[-3:]
    except Exception:
        return []
    finally:
        db.close()


def _classify_by_llm(message: str) -> tuple[str, float]:
    """向后兼容旧测试和调用；新运行时使用结构化 Planner。"""
    decision = plan_intents(
        message=message,
        semantic_intents=[],
        context_summary="",
    )
    if decision is None:
        return "fallback", 0.0
    return _route_intents(decision.intents), decision.confidence
