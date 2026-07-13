"""
Agent 执行追踪模型

记录 LangGraph 工作流每一步的输入、输出、决策过程和结果。
这是系统的核心可观测性表，用于排查问题、审计和复盘。

# 关键设计说明
# ─────────────────────────────
# 为什么设计为单表而非按节点分表：
# - 单表可以按 session_id 和时间排序还原完整执行链路
# - 查询时一次 JOIN 都不需要，性能开销最小
# - 后续如果需要按节点类型分析，用 node_name 字段过滤即可
# 为什么 input/output 用 JSON：
# - 不同节点的输入输出结构完全不同（路由有 intent，RAG 有 docs，工单有 risk_level）
# - JSON 可以灵活记录异构数据，不需要为每种节点建一张表
# ─────────────────────────────
"""

from decimal import Decimal

from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, JSON, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTrace(Base):
    __tablename__ = "agent_trace"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), nullable=False, index=True, comment="会话 ID")
    node_name = Column(String(50), nullable=False, comment="当前节点名称")
    intent = Column(String(50), nullable=True, comment="预测意图")
    confidence = Column(Numeric(5, 4), nullable=True, comment="路由置信度")
    input = Column(JSON, nullable=True, comment="节点输入数据")
    output = Column(JSON, nullable=True, comment="节点输出数据")
    retrieved_doc_ids = Column(JSON, nullable=True, comment="RAG 召回文档 ID 列表")
    retrieved_scores = Column(JSON, nullable=True, comment="RAG 召回分数列表")
    tool_name = Column(String(50), nullable=True, comment="工具名称")
    tool_status = Column(String(20), nullable=True, comment="工具调用状态")
    human_required = Column(Boolean, default=False, comment="是否需要人工审核")
    final_answer = Column(Text, nullable=True, comment="最终回复内容")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="记录时间")

    def __repr__(self) -> str:
        return f"<AgentTrace(id={self.id}, node={self.node_name}, session={self.session_id})>"
