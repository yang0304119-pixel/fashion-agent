"""
未解决问题记录模型

当 Agent 无法处理用户问题（fallback 或低置信度）时，记录到此表。
后续由人工标注意图和答案，反向优化路由和 RAG。

# 关键设计说明
# ─────────────────────────────
# 为什么需要这张表：
# - 冷启动阶段没有真实标注数据，需要积累 bad case
# - 记录了"系统判断的意图"与"人工标注意图"的差异，用于定位路由问题
# - should_add_to_kb 标记是否需要补充知识库，直接指导 RAG 优化方向
# ─────────────────────────────
"""

from decimal import Decimal

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class UnresolvedCase(Base):
    __tablename__ = "unresolved_case"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_message = Column(Text, nullable=False, comment="用户原始输入")
    predicted_intent = Column(String(50), nullable=True, comment="系统预测意图")
    confidence = Column(Numeric(5, 4), nullable=True, comment="路由置信度")
    fallback_reason = Column(String(200), nullable=True, comment="fallback 原因")
    final_answer = Column(Text, nullable=True, comment="系统回复内容")
    is_resolved = Column(Boolean, default=False, comment="用户问题是否解决")
    human_label_intent = Column(String(50), nullable=True, comment="人工标注的正确意图")
    human_label_answer = Column(Text, nullable=True, comment="人工修正的答案")
    should_add_to_kb = Column(Boolean, default=False, comment="是否需要补充知识库")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="记录时间")

    def __repr__(self) -> str:
        return f"<UnresolvedCase(id={self.id}, predicted={self.predicted_intent})>"
