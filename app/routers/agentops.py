"""开发人员专用AgentOps接口，技术诊断与客服业务接口分离。"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db, require_permission
from app.models.agent_trace import AgentTrace
from app.models.agent_trace_step import AgentTraceStep
from app.models.memory import MemoryEvent, MemoryRecord
from app.models.user import User
from app.schemas.admin import (
    AdminTraceDetailResponse,
    AdminTraceListResponse,
    AdminTraceSessionResponse,
)
from app.routers.admin import _to_admin_trace, _to_admin_trace_detail
from app.services.admin_audit_service import AdminAuditService
from app.services.admin_query_service import AdminQueryService


router = APIRouter(prefix="/agentops", tags=["agentops"])


@router.get("/traces", response_model=AdminTraceListResponse)
def list_traces(
    session_id: str | None = Query(default=None, max_length=50),
    intent: str | None = Query(default=None, max_length=50),
    status_filter: str | None = Query(default=None, alias="status", max_length=20),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("agent.trace.read")),
) -> AdminTraceListResponse:
    result = AdminQueryService(db).list_traces(
        tenant_id=developer.tenant_id,
        session_id=session_id,
        intent=intent,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return AdminTraceListResponse(
        data=[_to_admin_trace(row) for row in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/traces/{trace_id}", response_model=AdminTraceDetailResponse)
def get_trace(
    trace_id: int,
    request: Request,
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("agent.trace.read")),
) -> AdminTraceDetailResponse:
    try:
        trace = AdminQueryService(db).get_trace(
            tenant_id=developer.tenant_id,
            trace_id=trace_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Trace不存在") from error
    AdminAuditService(db).record(
        actor=developer,
        action="agentops.trace_viewed",
        target_type="agent_trace",
        target_id=trace_id,
        ip_address=request.client.host if request.client else None,
        commit=True,
    )
    return AdminTraceDetailResponse(data=_to_admin_trace_detail(trace))


@router.get("/trace-sessions/{session_id}", response_model=AdminTraceSessionResponse)
def get_trace_session(
    session_id: str,
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("agent.trace.read")),
) -> AdminTraceSessionResponse:
    rows = AdminQueryService(db).list_trace_session(
        tenant_id=developer.tenant_id,
        session_id=session_id,
    )
    return AdminTraceSessionResponse(
        session_id=session_id,
        data=[_to_admin_trace(row) for row in rows],
    )


@router.get("/rag/stats")
def rag_stats(
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("rag.diagnostics.read")),
) -> dict:
    rows = db.query(AgentTrace).filter(
        AgentTrace.tenant_id == developer.tenant_id,
        AgentTrace.intent == "knowledge_query",
    ).all()
    return {"success": True, "data": {
        "requests": len(rows),
        "failed": sum(1 for row in rows if row.status == "failed"),
        "with_sources": sum(1 for row in rows if row.rag_sources),
        "source_count": sum(len(row.rag_sources or []) for row in rows),
    }}


@router.get("/tools/stats")
def tool_stats(
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("tool.diagnostics.read")),
) -> dict:
    rows = (
        db.query(
            AgentTraceStep.tool_name,
            AgentTraceStep.status,
            AgentTraceStep.error_category,
            func.count(AgentTraceStep.id),
        )
        .join(AgentTrace, AgentTrace.id == AgentTraceStep.trace_id)
        .filter(
            AgentTrace.tenant_id == developer.tenant_id,
            AgentTraceStep.tool_name.is_not(None),
        )
        .group_by(
            AgentTraceStep.tool_name,
            AgentTraceStep.status,
            AgentTraceStep.error_category,
        )
        .all()
    )
    return {"success": True, "data": [
        {
            "tool_name": row[0],
            "status": row[1],
            "error_category": row[2],
            "count": row[3],
        }
        for row in rows
    ]}


@router.get("/memories/stats")
def memory_stats(
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("memory.diagnostics.read")),
) -> dict:
    records = db.query(MemoryRecord).filter(
        MemoryRecord.tenant_id == developer.tenant_id
    ).count()
    events = db.query(MemoryEvent).filter(
        MemoryEvent.tenant_id == developer.tenant_id
    ).count()
    return {"success": True, "data": {"records": records, "events": events}}


@router.get("/boundaries/events")
def boundary_events(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("boundary.diagnostics.read")),
) -> dict:
    traces = (
        db.query(AgentTrace)
        .filter(AgentTrace.tenant_id == developer.tenant_id)
        .order_by(AgentTrace.created_at.desc(), AgentTrace.id.desc())
        .limit(limit * 3)
        .all()
    )
    data = []
    for trace in traces:
        output = trace.output or {}
        if not output.get("boundary_status"):
            continue
        data.append({
            "trace_id": trace.id,
            "session_id": trace.session_id,
            "status": output.get("boundary_status"),
            "risk_level": output.get("boundary_risk_level"),
            "reason": output.get("boundary_reason"),
            "created_at": trace.created_at,
        })
        if len(data) >= limit:
            break
    return {"success": True, "data": data}


@router.get("/health")
def system_health(
    db: Session = Depends(get_db),
    developer: User = Depends(require_permission("system.health.read")),
) -> dict:
    return {"success": True, "data": {
        "status": "ok",
        "tenant_id": developer.tenant_id,
        "trace_count": db.query(AgentTrace).filter(
            AgentTrace.tenant_id == developer.tenant_id
        ).count(),
        "memory_record_count": db.query(MemoryRecord).filter(
            MemoryRecord.tenant_id == developer.tenant_id
        ).count(),
    }}
