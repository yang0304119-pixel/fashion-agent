"""
售后工单模型

记录退款/换货申请，关联风险等级和人工审核状态。
status 枚举：pending(待处理) / approved(已通过) / rejected(已拒绝)
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Ticket(Base):
    __tablename__ = "ticket"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, comment="所属租户 ID")
    order_id = Column(Integer, ForeignKey("order.id"), nullable=False, comment="关联订单 ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="用户 ID")
    type = Column(String(20), nullable=False, comment="工单类型：refund(退款) / exchange(换货)")
    reason = Column(Text, nullable=False, comment="用户申请原因")
    amount = Column(Numeric(10, 2), nullable=False, comment="退款/赔付金额")
    risk_level = Column(String(20), nullable=False, default="low", comment="风险等级：low/medium/high")
    status = Column(String(20), nullable=False, default="pending", comment="工单状态")
    human_review = Column(Boolean, default=False, comment="是否需要人工审核")
    reviewed_by = Column(
        Integer,
        ForeignKey("user.id"),
        nullable=True,
        index=True,
        comment="审核管理员 ID",
    )
    reviewed_at = Column(DateTime, nullable=True, comment="审核完成时间")
    review_reason = Column(Text, nullable=True, comment="审核意见或拒绝原因")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    # 关系
    order = relationship("Order", backref="tickets")
    user = relationship("User", foreign_keys=[user_id], backref="tickets")
    reviewed_by_user = relationship(
        "User",
        foreign_keys=[reviewed_by],
        backref="reviewed_tickets",
    )

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, type={self.type}, status={self.status})>"
