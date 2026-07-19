"""退款申请模型：记录从申请、审核到渠道执行的完整状态。"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class RefundRequest(Base):
    __tablename__ = "refund_request"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_refund_tenant_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "order_id",
            name="uq_refund_tenant_order",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'high')",
            name="ck_refund_risk_level",
        ),
        CheckConstraint(
            "status IN ('reviewing', 'approved', 'succeeded', "
            "'rejected', 'failed')",
            name="ck_refund_status",
        ),
        Index(
            "ix_refund_order_status",
            "tenant_id",
            "order_id",
            "status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenant.id"),
        nullable=False,
        index=True,
    )
    order_id = Column(
        Integer,
        ForeignKey("order.id"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=False,
        index=True,
    )
    ticket_id = Column(
        Integer,
        ForeignKey("ticket.id"),
        nullable=True,
        unique=True,
    )
    reason = Column(Text, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    risk_level = Column(String(20), nullable=False)
    human_review = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False)
    idempotency_key = Column(String(64), nullable=False)
    gateway_mode = Column(String(20), nullable=False, default="manual")
    provider_refund_id = Column(String(100), nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    order = relationship("Order", backref="refund_requests")
    user = relationship("User", backref="refund_requests")
    ticket = relationship("Ticket", backref="refund_request", uselist=False)

    def __repr__(self) -> str:
        return (
            f"<RefundRequest(id={self.id}, order={self.order_id}, "
            f"status={self.status})>"
        )
