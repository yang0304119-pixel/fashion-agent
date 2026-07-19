"""确定性业务节点的多轮槽位会话状态。"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from app.core.database import Base


class ConversationState(Base):
    __tablename__ = "conversation_state"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "session_id",
            name="uq_conversation_state_owner_session",
        ),
        Index(
            "ix_conversation_state_expires_at",
            "expires_at",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenant.id"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    session_id = Column(String(50), nullable=False)
    pending_intent = Column(String(50), nullable=False)
    missing_slots = Column(JSON, nullable=False, default=list)
    collected_slots = Column(JSON, nullable=False, default=dict)
    updated_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<ConversationState(session={self.session_id}, "
            f"intent={self.pending_intent})>"
        )
