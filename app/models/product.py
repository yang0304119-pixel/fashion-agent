"""
商品模型

面向男装羽绒服品类，覆盖 199-499 元价位、6 款商品。
sizes 使用 JSON 字段存储可用尺码列表，比关联表更轻量。

# 关键设计说明
# ─────────────────────────────
# 为什么用 JSON 存尺码而非关联表：
# - 尺码是固定枚举值（S~3XL），不会单独查询或扩展属性
# - JSON 字段减少一次表关联查询，代码更简洁
# - 如果后续尺码需要独立属性（如各尺码库存），再拆为关联表
# ─────────────────────────────
"""

from decimal import Decimal

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class Product(Base):
    __tablename__ = "product"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="商品名称")
    category = Column(String(50), nullable=False, comment="商品分类")
    price = Column(Numeric(10, 2), nullable=False, comment="单价")
    colors = Column(JSON, nullable=False, comment="可选颜色列表")
    sizes = Column(JSON, nullable=False, comment="可选尺码列表")
    description = Column(Text, nullable=False, comment="商品描述")
    materials = Column(Text, nullable=False, comment="材质说明")
    care_instructions = Column(Text, nullable=False, comment="洗护说明")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name}, price={self.price})>"
