"""路由前加载会话窗口、摘要、任务检查点和少量稳定偏好。"""

import logging

from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.services.memory_service import (
    ConversationMemoryService,
    LongTermMemoryService,
    MemoryContextBuilder,
    TaskCheckpointService,
)


logger = logging.getLogger(__name__)


def memory_load_node(state: AgentState) -> dict:
    tenant_id = int(state.get("tenant_id") or 0)
    user_id = int(state.get("user_id") or 0)
    session_id = str(state.get("session_id") or "")
    message = str(state.get("message") or "").strip()
    if not tenant_id or not user_id or not session_id or not message:
        return {
            "recent_turns": [],
            "conversation_summary": None,
            "task_checkpoint": None,
            "retrieved_memories": [],
            "memory_context": {},
            "context_token_budget": {},
        }

    db = SessionLocal()
    try:
        conversations = ConversationMemoryService(db)
        conversations.append_turn(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=message,
            context_summary=state.get("chat_context"),
        )
        recent_turns = conversations.load_window(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        summary = conversations.load_summary(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        checkpoint = TaskCheckpointService(db).load_active(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        preferences = LongTermMemoryService(db).retrieve_stage_one(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        collected_slots = dict(state.get("collected_slots") or {})
        if checkpoint:
            for key, value in (checkpoint.get("collected_slots") or {}).items():
                collected_slots.setdefault(key, value)
        context, budget = MemoryContextBuilder().build(
            recent_turns=recent_turns,
            conversation_summary=summary,
            task_checkpoint=checkpoint,
            memories=preferences,
            chat_context=state.get("chat_context"),
        )
        return {
            "recent_turns": recent_turns,
            "conversation_summary": summary,
            "task_checkpoint": checkpoint,
            "retrieved_memories": preferences,
            "memory_context": context,
            "context_token_budget": budget,
            "collected_slots": collected_slots,
        }
    except Exception:
        db.rollback()
        logger.exception("加载分层记忆失败")
        return {
            "recent_turns": [],
            "conversation_summary": None,
            "task_checkpoint": None,
            "retrieved_memories": [],
            "memory_context": {},
            "context_token_budget": {},
        }
    finally:
        db.close()
