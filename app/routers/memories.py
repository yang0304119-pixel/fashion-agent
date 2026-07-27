"""用户记忆管理和租户级记忆运营API。"""

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db, require_permission
from app.models.user import User
from app.schemas.memory import (
    AdminMemoryCreateRequest,
    AdminMemoryStatsResponse,
    MemoryCreateRequest,
    MemoryDeleteResponse,
    MemoryListResponse,
    MemoryResponse,
    MemoryUpdateRequest,
    SessionMemoryData,
    SessionMemoryDeleteResponse,
    SessionMemoryResponse,
)
from app.services.memory_service import (
    ConversationMemoryService,
    LongTermMemoryService,
    MemoryCandidate,
    TaskCheckpointService,
    _searchable_content,
)


router = APIRouter(prefix="/memories", tags=["memories"])
admin_router = APIRouter(prefix="/admin/memories", tags=["admin-memory"])


@router.get("", response_model=MemoryListResponse)
def list_memories(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryListResponse:
    rows = LongTermMemoryService(db).list_user_memories(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        include_inactive=include_inactive,
    )
    return MemoryListResponse(data=rows)


@router.post("", response_model=MemoryResponse)
def create_memory(
    request: MemoryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryResponse:
    searchable = _searchable_content(request.content)
    candidate = MemoryCandidate(
        memory_type=request.memory_type,
        subject_key=request.subject_key,
        content=request.content,
        searchable_text=searchable,
        source_type="explicit_user",
        confidence=1.0,
        importance=0.8,
        stability=0.8,
        scope_id=str(current_user.id),
        expires_at=request.expires_at,
    )
    results = LongTermMemoryService(db).write_candidates(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        session_id="memory-api",
        candidates=[candidate],
    )
    result = results[0]
    if "memory" not in result:
        raise HTTPException(status_code=400, detail=result.get("reason", "记忆未保存"))
    return MemoryResponse(data=result["memory"])


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: int,
    request: MemoryUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryResponse:
    try:
        row = LongTermMemoryService(db).update_user_memory(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            memory_id=memory_id,
            content=request.content,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return MemoryResponse(data=row)


@router.delete("/{memory_id}", response_model=MemoryDeleteResponse)
def delete_memory(
    memory_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryDeleteResponse:
    try:
        LongTermMemoryService(db).delete_user_memory(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            memory_id=memory_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return MemoryDeleteResponse()


@router.get("/sessions/{session_id}", response_model=SessionMemoryResponse)
def session_memory(
    session_id: str = Path(min_length=8, max_length=50, pattern=r"^[A-Za-z0-9_-]+$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionMemoryResponse:
    conversations = ConversationMemoryService(db)
    return SessionMemoryResponse(data=SessionMemoryData(
        session_id=session_id,
        recent_turns=conversations.load_window(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            session_id=session_id,
        ),
        conversation_summary=conversations.load_summary(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            session_id=session_id,
        ),
        task_checkpoint=TaskCheckpointService(db).load_active(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            session_id=session_id,
        ),
    ))


@router.delete("/sessions/{session_id}", response_model=SessionMemoryDeleteResponse)
def delete_session_memory(
    session_id: str = Path(min_length=8, max_length=50, pattern=r"^[A-Za-z0-9_-]+$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SessionMemoryDeleteResponse:
    result = ConversationMemoryService(db).delete_session(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        session_id=session_id,
    )
    return SessionMemoryDeleteResponse(data=result)


@admin_router.get("/stats", response_model=AdminMemoryStatsResponse)
def memory_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.diagnostics.read")),
) -> AdminMemoryStatsResponse:
    return AdminMemoryStatsResponse(
        data=LongTermMemoryService(db).stats(tenant_id=current_user.tenant_id)
    )


@admin_router.post("", response_model=MemoryResponse)
def create_shared_memory(
    request: AdminMemoryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tenant.settings")),
) -> MemoryResponse:
    candidate = MemoryCandidate(
        memory_type=request.memory_type,
        subject_key=request.subject_key,
        content=request.content,
        searchable_text=_searchable_content(request.content),
        source_type="admin_rule",
        confidence=1.0,
        importance=request.importance,
        stability=request.stability,
        scope_type=request.scope_type,
        scope_id=(str(current_user.tenant_id) if request.scope_type == "tenant" else request.scope_id),
        expires_at=request.expires_at,
    )
    result = LongTermMemoryService(db).write_candidates(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        session_id="admin-memory-api",
        candidates=[candidate],
    )[0]
    if "memory" not in result:
        raise HTTPException(status_code=400, detail=result.get("reason", "记忆未保存"))
    return MemoryResponse(data=result["memory"])
