"""
订单模型

订单 ID 从 10001 开始递增，模拟真实电商订单号格式。
status 字段枚举：pending(待发货) / shipped(已发货) / delivered(已签收) / refunded(已退款)
"""

from decimal import Decimal

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Order(Base):
    __tablename__ = "order"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, comment="所属租户 ID")
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, comment="用户 ID")
    product_id = Column(Integer, ForeignKey("product.id"), nullable=False, comment="商品 ID")
    quantity = Column(Integer, nullable=False, default=1, comment="数量")
    total_price = Column(Numeric(10, 2), nullable=False, comment="总价")
    status = Column(String(20), nullable=False, default="pending", comment="订单状态")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="下单时间")

    # 关系
    user = relationship("User", backref="orders")
    product = relationship("Product", backref="orders")

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, status={self.status}, total={self.total_price})>"
