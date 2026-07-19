"""在每轮结束时保存或清除待补槽位状态。"""

import logging

from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.services.conversation_state_service import (
    ConversationStateService,
    PENDING_INTENTS,
)


logger = logging.getLogger(__name__)


def conversation_state_node(state: AgentState) -> dict:
    tenant_id = state.get("tenant_id", 0)
    user_id = state.get("user_id", 0)
    session_id = state.get("session_id", "")
    intent = state.get("intent", "")
    missing_slots = list(state.get("missing_slots") or [])
    collected_slots = dict(state.get("collected_slots") or {})

    if not tenant_id or not user_id or not session_id:
        logger.warning("会话状态缺少可信身份或session_id，跳过持久化")
        return {}

    db = SessionLocal()
    try:
        service = ConversationStateService(db)
        if intent in PENDING_INTENTS and missing_slots:
            service.save_pending(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                pending_intent=intent,
                missing_slots=missing_slots,
                collected_slots=collected_slots,
            )
            return {
                "pending_intent": intent,
                "collected_slots": collected_slots,
            }

        service.clear(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        return {"pending_intent": None}
    except Exception:
        db.rollback()
        logger.exception("会话槽位状态持久化失败")
        return {}
    finally:
        db.close()
