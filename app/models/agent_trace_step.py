"""Agent 请求中的实际节点执行步骤。"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class AgentTraceStep(Base):
    __tablename__ = "agent_trace_step"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(
        Integer,
        ForeignKey("agent_trace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence = Column(Integer, nullable=False)
    node_name = Column(String(50), nullable=False)
    workflow_name = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="running")
    missing_slots = Column(JSON, nullable=True)
    tool_name = Column(String(50), nullable=True)
    rag_sources = Column(JSON, nullable=True)
    error_stage = Column(String(50), nullable=True)
    error_code = Column(String(100), nullable=True)
    error_type = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, server_default=func.now())
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    trace = relationship("AgentTrace", back_populates="steps")

    def __repr__(self) -> str:
        return (
            f"<AgentTraceStep(trace={self.trace_id}, "
            f"sequence={self.sequence}, node={self.node_name})>"
        )
