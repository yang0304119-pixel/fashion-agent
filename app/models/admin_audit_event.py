"""记录人工管理操作，与Agent执行Trace分离。"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.sql import func

from app.core.database import Base


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_event"
    __table_args__ = (
        Index("ix_admin_audit_tenant_created", "tenant_id", "created_at"),
        Index("ix_admin_audit_actor", "tenant_id", "actor_user_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    actor_role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(50), nullable=False)
    target_id = Column(String(100), nullable=True)
    before_data = Column(JSON, nullable=True)
    after_data = Column(JSON, nullable=True)
    reason = Column(String(500), nullable=True)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
