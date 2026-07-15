"""
租户模型

SaaS 多租户核心实体。每个个体户商家对应一个租户。
数据隔离以 tenant_id 为维度，查询时强制过滤。

# 关键设计说明
# ─────────────────────────────
# 为什么 tenant 表设计得这么简洁：
# - 起步阶段只做服装垂直，不需要复杂的商户属性
# - industry 字段为后续扩展预留（食品/玩具等行业）
# - theme_config 用 JSON 字段存放店铺风格配置，避免频繁加列
# ─────────────────────────────
"""

from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenant"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="商户名称")
    industry = Column(String(50), nullable=False, default="服装", comment="行业类型")
    contact = Column(String(50), nullable=True, comment="联系人")
    # 店铺风格 / 品牌色 / Logo 等，起步阶段用 JSON 兜底，后续可拆成独立配置表
    theme_config = Column(JSON, nullable=True, comment="店铺风格配置（预留）")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name={self.name}, industry={self.industry})>"
