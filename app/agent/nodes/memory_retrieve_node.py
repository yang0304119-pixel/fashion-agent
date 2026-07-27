"""路由后根据意图按需检索长期记忆并重建上下文。"""

import logging

from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.services.memory_service import LongTermMemoryService, MemoryContextBuilder


logger = logging.getLogger(__name__)


def memory_retrieve_node(state: AgentState) -> dict:
    tenant_id = int(state.get("tenant_id") or 0)
    user_id = int(state.get("user_id") or 0)
    session_id = str(state.get("session_id") or "")
    if not tenant_id or not user_id or not session_id:
        return {}
    db = SessionLocal()
    try:
        targeted = LongTermMemoryService(db).retrieve(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            query=str(state.get("message") or ""),
            intent=str(state.get("intent") or "fallback"),
            exclude_ids={
                int(memory["id"])
                for memory in state.get("retrieved_memories") or []
                if memory.get("id") is not None
            },
        )
        memories = _deduplicate_memories(
            list(state.get("retrieved_memories") or []) + targeted
        )
        collected_slots = dict(state.get("collected_slots") or {})
        message = str(state.get("message") or "")
        if not any(value in message for value in ("修身", "标准", "宽松", "贴身", "休闲")):
            for memory in memories:
                if memory.get("subject_key") == "clothing.fit_preference":
                    value = (memory.get("content") or {}).get("value")
                    if value in {"修身", "标准", "宽松"}:
                        collected_slots.setdefault("style", value)
                        break
        context, budget = MemoryContextBuilder().build(
            recent_turns=list(state.get("recent_turns") or []),
            conversation_summary=state.get("conversation_summary"),
            task_checkpoint=state.get("task_checkpoint"),
            memories=memories,
            chat_context=state.get("chat_context"),
        )
        return {
            "retrieved_memories": memories,
            "memory_context": context,
            "context_token_budget": budget,
            "collected_slots": collected_slots,
        }
    except Exception:
        db.rollback()
        logger.exception("按意图检索长期记忆失败")
        return {}
    finally:
        db.close()


def _deduplicate_memories(memories: list[dict]) -> list[dict]:
    selected: dict[int | str, dict] = {}
    for memory in memories:
        key = memory.get("id") or memory.get("subject_key")
        selected[key] = memory
    return list(selected.values())
