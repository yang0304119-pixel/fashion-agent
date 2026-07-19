"""多轮会话槽位状态的持久化与过期控制。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.conversation_state import ConversationState


PENDING_INTENTS = frozenset(
    {
        "order_query",
        "inventory_query",
        "size_recommend",
        "refund_request",
    }
)


@dataclass(frozen=True)
class PendingConversation:
    pending_intent: str
    missing_slots: list[str]
    collected_slots: dict[str, Any]


class ConversationStateService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def load_active(
        self,
        *,
        tenant_id: int,
        user_id: int,
        session_id: str,
    ) -> PendingConversation | None:
        record = self._find(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if record is None:
            return None

        if record.expires_at <= _utcnow():
            self.db.delete(record)
            self.db.commit()
            return None

        return PendingConversation(
            pending_intent=record.pending_intent,
            missing_slots=list(record.missing_slots or []),
            collected_slots=dict(record.collected_slots or {}),
        )

    def save_pending(
        self,
        *,
        tenant_id: int,
        user_id: int,
        session_id: str,
        pending_intent: str,
        missing_slots: list[str],
        collected_slots: dict[str, Any],
    ) -> None:
        if pending_intent not in PENDING_INTENTS:
            raise ValueError(f"不支持保存待补槽位的意图: {pending_intent}")
        if not missing_slots:
            self.clear(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
            return

        now = _utcnow()
        expires_at = now + timedelta(
            minutes=settings.CONVERSATION_STATE_TTL_MINUTES
        )
        record = self._find(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if record is None:
            record = ConversationState(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                pending_intent=pending_intent,
                missing_slots=list(missing_slots),
                collected_slots=dict(collected_slots),
                updated_at=now,
                expires_at=expires_at,
            )
            self.db.add(record)
        else:
            record.pending_intent = pending_intent
            record.missing_slots = list(missing_slots)
            record.collected_slots = dict(collected_slots)
            record.updated_at = now
            record.expires_at = expires_at
        self.db.commit()

    def clear(
        self,
        *,
        tenant_id: int,
        user_id: int,
        session_id: str,
    ) -> None:
        record = self._find(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if record is not None:
            self.db.delete(record)
            self.db.commit()

    def _find(
        self,
        *,
        tenant_id: int,
        user_id: int,
        session_id: str,
    ) -> ConversationState | None:
        return self.db.query(ConversationState).filter(
            ConversationState.tenant_id == tenant_id,
            ConversationState.user_id == user_id,
            ConversationState.session_id == session_id,
        ).first()


def _utcnow() -> datetime:
    """SQLite使用无时区UTC时间，避免本地时区参与过期判断。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
