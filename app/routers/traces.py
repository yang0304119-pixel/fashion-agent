"""
Agent 执行轨迹查询接口
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.agent_trace import AgentTrace

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("/{session_id}")
def get_traces(session_id: str, db: Session = Depends(get_db)):
    """查询指定会话的 Agent 执行轨迹。"""
    traces = (
        db.query(AgentTrace)
        .filter(AgentTrace.session_id == session_id)
        .order_by(AgentTrace.created_at)
        .all()
    )

    return {
        "success": True,
        "data": [
            {
                "id": t.id,
                "node_name": t.node_name,
                "intent": t.intent,
                "confidence": float(t.confidence) if t.confidence else None,
                "tool_status": t.tool_status,
                "human_required": t.human_required,
                "final_answer": t.final_answer,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in traces
        ],
    }
