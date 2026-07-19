"""
Agent 执行追踪模型

记录每次Agent请求的汇总结果，具体节点执行过程保存在
agent_trace_step表中，用于排查问题、审计和复盘。

# 关键设计说明
# ─────────────────────────────
# 为什么采用请求汇总表加步骤表：
# - 汇总表适合按session、意图、状态分页查询
# - 步骤表保留实际节点顺序、耗时、槽位、来源和错误阶段
# 为什么 input/output 用 JSON：
# - 不同节点的输入输出结构完全不同（路由有 intent，RAG 有 docs，工单有 risk_level）
# - JSON 可以灵活记录异构数据，不需要为每种节点建一张表
# ─────────────────────────────
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTrace(Base):
    __tablename__ = "agent_trace"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    session_id = Column(String(50), nullable=False, index=True, comment="会话 ID")
    node_name = Column(String(50), nullable=False, comment="当前节点名称")
    message = Column(Text, nullable=True, comment="用户消息")
    workflow_name = Column(String(50), nullable=True, index=True, comment="实际工作流")
    status = Column(String(20), nullable=True, index=True, comment="请求执行状态")
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
    missing_slots = Column(JSON, nullable=True, comment="最终缺失槽位")
    rag_sources = Column(JSON, nullable=True, comment="RAG来源摘要")
    error_stage = Column(String(50), nullable=True, comment="失败阶段")
    error_code = Column(String(100), nullable=True, comment="错误代码")
    error_type = Column(String(100), nullable=True, comment="错误类型")
    error_message = Column(Text, nullable=True, comment="安全错误信息")
    finished_at = Column(DateTime, nullable=True, comment="请求完成时间")
    created_at = Column(DateTime, nullable=False, server_default=func.now(), comment="记录时间")

    steps = relationship(
        "AgentTraceStep",
        back_populates="trace",
        cascade="all, delete-orphan",
        order_by="AgentTraceStep.sequence",
    )

    def __repr__(self) -> str:
        return f"<AgentTrace(id={self.id}, node={self.node_name}, session={self.session_id})>"
