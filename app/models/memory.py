"""分层记忆模型：会话Turn、摘要、任务检查点、长期记忆和审计事件。"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.core.database import Base


class ConversationTurn(Base):
    __tablename__ = "conversation_turn"
    __table_args__ = (
        Index(
            "ix_conversation_turn_owner_session_created",
            "tenant_id",
            "user_id",
            "session_id",
            "created_at",
        ),
        Index("ix_conversation_turn_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    session_id = Column(String(50), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    message_type = Column(String(30), nullable=False, default="text")
    tool_name = Column(String(50), nullable=True)
    tool_result_summary = Column(JSON, nullable=True)
    context_summary = Column(JSON, nullable=True)
    token_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)


class ConversationSummary(Base):
    __tablename__ = "conversation_summary"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "session_id",
            name="uq_conversation_summary_owner_session",
        ),
        Index("ix_conversation_summary_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    session_id = Column(String(50), nullable=False)
    summary = Column(JSON, nullable=False, default=dict)
    source_turn_ids = Column(JSON, nullable=False, default=list)
    last_turn_id = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=False)


class TaskCheckpoint(Base):
    __tablename__ = "task_checkpoint"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "session_id",
            name="uq_task_checkpoint_owner_session",
        ),
        Index("ix_task_checkpoint_status", "tenant_id", "status"),
        Index("ix_task_checkpoint_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    session_id = Column(String(50), nullable=False)
    task_id = Column(String(100), nullable=False, unique=True)
    intent = Column(String(50), nullable=False)
    status = Column(String(30), nullable=False)
    goal = Column(Text, nullable=False)
    completed_steps = Column(JSON, nullable=False, default=list)
    current_step = Column(String(200), nullable=True)
    missing_slots = Column(JSON, nullable=False, default=list)
    collected_slots = Column(JSON, nullable=False, default=dict)
    tool_conclusions = Column(JSON, nullable=False, default=list)
    open_issues = Column(JSON, nullable=False, default=list)
    next_action = Column(String(500), nullable=True)
    final_result_summary = Column(JSON, nullable=True)
    business_critical = Column(Boolean, nullable=False, default=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class MemoryRecord(Base):
    __tablename__ = "memory_record"
    __table_args__ = (
        Index(
            "ix_memory_record_owner_status_type",
            "tenant_id",
            "user_id",
            "status",
            "memory_type",
        ),
        Index("ix_memory_record_scope", "tenant_id", "scope_type", "scope_id"),
        Index("ix_memory_record_subject", "tenant_id", "user_id", "subject_key"),
        Index("ix_memory_record_expires_at", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    scope_type = Column(String(30), nullable=False, default="user")
    scope_id = Column(String(100), nullable=False)
    memory_type = Column(String(50), nullable=False)
    subject_key = Column(String(150), nullable=False)
    content = Column(JSON, nullable=False)
    searchable_text = Column(Text, nullable=False)
    source_type = Column(String(50), nullable=False)
    source_id = Column(String(150), nullable=True)
    confidence = Column(Float, nullable=False, default=1.0)
    importance = Column(Float, nullable=False, default=0.5)
    stability = Column(Float, nullable=False, default=0.5)
    sensitivity = Column(String(30), nullable=False, default="low")
    status = Column(String(30), nullable=False, default="active")
    embedding = Column(JSON, nullable=True)
    valid_from = Column(DateTime, nullable=False, server_default=func.now())
    expires_at = Column(DateTime, nullable=True)
    supersedes_id = Column(Integer, ForeignKey("memory_record.id"), nullable=True)
    access_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now())


class MemoryEvent(Base):
    __tablename__ = "memory_event"
    __table_args__ = (
        Index("ix_memory_event_owner_created", "tenant_id", "user_id", "created_at"),
        Index("ix_memory_event_type", "tenant_id", "event_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    session_id = Column(String(50), nullable=True)
    memory_id = Column(Integer, ForeignKey("memory_record.id"), nullable=True)
    event_type = Column(String(30), nullable=False)
    reason = Column(String(300), nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
