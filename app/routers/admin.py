"""管理员专用查询接口；所有数据仍受当前租户边界约束。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.dependencies import get_db, require_admin
from app.models.agent_trace import AgentTrace
from app.models.order import Order
from app.models.refund_request import RefundRequest
from app.models.user import User
from app.schemas.admin import (
    AdminDashboardData,
    AdminDashboardResponse,
    AdminOrderDetailData,
    AdminOrderDetailResponse,
    AdminOrderListItem,
    AdminOrderListResponse,
    AdminOrderProductData,
    AdminOrderRefundData,
    AdminOrderTicketData,
    AdminOrderUserData,
    AdminTicketListItem,
    AdminTicketListResponse,
    AdminTicketDetailResponse,
    AdminTraceListItem,
    AdminTraceListResponse,
    AdminTraceDetailData,
    AdminTraceDetailResponse,
    AdminTraceError,
    AdminTraceSessionResponse,
    AdminTraceStepData,
    AdminUnresolvedCaseListItem,
    AdminUnresolvedCaseListResponse,
    AdminUnresolvedCaseResponse,
    AdminUnresolvedCaseStats,
    AdminUnresolvedCaseStatsResponse,
    UnresolvedCaseUpdateRequest,
    KnowledgeDraftCreateData,
    KnowledgeDraftCreateRequest,
    KnowledgeDraftCreateResponse,
)
from app.schemas.refund import (
    RefundDecisionRequest,
    RefundListResponse,
    RefundResponse,
)
from app.services.admin_query_service import (
    AdminQueryError,
    AdminQueryService,
    AdminTicketNotFoundError,
)
from app.services.refund_presenter import to_refund_data
from app.services.refund_query_service import RefundQueryService
from app.services.refund_service import (
    RefundNotFoundError,
    RefundService,
    RefundServiceError,
    RefundStateError,
)
from app.services.unresolved_case_service import (
    UnresolvedCaseNotFoundError,
    UnresolvedCaseService,
    UnresolvedCaseValidationError,
)


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard", response_model=AdminDashboardResponse)
def get_tenant_dashboard(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminDashboardResponse:
    summary = AdminQueryService(db).get_dashboard(
        tenant_id=admin.tenant_id,
    )
    return AdminDashboardResponse(
        data=AdminDashboardData(
            orders_total=summary.orders_total,
            pending_refunds=summary.pending_refunds,
            failed_refunds=summary.failed_refunds,
            pending_tickets=summary.pending_tickets,
            unresolved_cases=summary.unresolved_cases,
            today_sessions=summary.today_sessions,
            pending_knowledge_reviews=summary.pending_knowledge_reviews,
            ready_knowledge_builds=summary.ready_knowledge_builds,
            expiring_soon_knowledge=summary.expiring_soon_knowledge,
            expired_knowledge=summary.expired_knowledge,
        )
    )


@router.get("/refunds", response_model=RefundListResponse)
def list_tenant_refunds(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(reviewing|approved|succeeded|rejected|failed)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RefundListResponse:
    result = RefundQueryService(db).list_for_tenant(
        tenant_id=admin.tenant_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return RefundListResponse(
        data=[
            to_refund_data(refund, include_user=True)
            for refund in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/refunds/{refund_request_id}", response_model=RefundResponse)
def get_tenant_refund(
    refund_request_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RefundResponse:
    refund = (
        db.query(RefundRequest)
        .options(
            joinedload(RefundRequest.user),
            joinedload(RefundRequest.order).joinedload(Order.product),
        )
        .filter(
            RefundRequest.id == refund_request_id,
            RefundRequest.tenant_id == admin.tenant_id,
        )
        .first()
    )
    if refund is None:
        raise HTTPException(status_code=404, detail="退款申请不存在")
    return RefundResponse(data=to_refund_data(refund, include_user=True))


@router.post(
    "/refunds/{refund_request_id}/approve",
    response_model=RefundResponse,
)
def approve_refund(
    refund_request_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RefundResponse:
    try:
        outcome = RefundService(db).approve(
            tenant_id=admin.tenant_id,
            refund_request_id=refund_request_id,
            reviewed_by=admin.id,
        )
    except RefundNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RefundStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RefundServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return RefundResponse(
        data=to_refund_data(outcome.refund, include_user=True)
    )


@router.post(
    "/refunds/{refund_request_id}/reject",
    response_model=RefundResponse,
)
def reject_refund(
    refund_request_id: int,
    request: RefundDecisionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> RefundResponse:
    try:
        outcome = RefundService(db).reject(
            tenant_id=admin.tenant_id,
            refund_request_id=refund_request_id,
            reason=request.reason,
            reviewed_by=admin.id,
        )
    except RefundNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RefundStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RefundServiceError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return RefundResponse(
        data=to_refund_data(outcome.refund, include_user=True)
    )


@router.get("/orders", response_model=AdminOrderListResponse)
def list_tenant_orders(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(pending|shipped|delivered|refunded|cancelled)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminOrderListResponse:
    result = AdminQueryService(db).list_orders(
        tenant_id=admin.tenant_id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return AdminOrderListResponse(
        data=[
            AdminOrderListItem(
                id=item.order.id,
                user_id=item.order.user_id,
                username=item.username,
                product_name=item.product_name,
                quantity=item.order.quantity,
                total_price=float(item.order.total_price),
                status=item.order.status,
                refund_id=item.refund_id,
                refund_status=item.refund_status,
                ticket_count=item.ticket_count,
                created_at=item.order.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/orders/{order_id}", response_model=AdminOrderDetailResponse)
def get_tenant_order(
    order_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminOrderDetailResponse:
    try:
        item = AdminQueryService(db).get_order(
            tenant_id=admin.tenant_id,
            order_id=order_id,
        )
    except AdminQueryError as error:
        raise HTTPException(status_code=404, detail="订单不存在") from error
    refund = item.refund
    return AdminOrderDetailResponse(
        data=AdminOrderDetailData(
            id=item.order.id,
            user=AdminOrderUserData(
                id=item.user.id,
                username=item.user.username,
            ),
            product=AdminOrderProductData(
                id=item.product.id,
                name=item.product.name,
                category=item.product.category,
                price=float(item.product.price),
            ),
            quantity=item.order.quantity,
            total_price=float(item.order.total_price),
            status=item.order.status,
            refund=(
                AdminOrderRefundData(id=refund.id, status=refund.status)
                if refund is not None
                else None
            ),
            tickets=[
                AdminOrderTicketData(
                    id=ticket.id,
                    type=ticket.type,
                    status=ticket.status,
                )
                for ticket in item.tickets
            ],
            created_at=item.order.created_at,
        )
    )


@router.get("/tickets", response_model=AdminTicketListResponse)
def list_tenant_tickets(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(pending|approved|rejected)$",
    ),
    type_filter: str | None = Query(
        default=None,
        alias="type",
        pattern=r"^(refund|exchange)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTicketListResponse:
    result = AdminQueryService(db).list_tickets(
        tenant_id=admin.tenant_id,
        status=status_filter,
        ticket_type=type_filter,
        page=page,
        page_size=page_size,
    )
    return AdminTicketListResponse(
        data=[
            _to_admin_ticket(item)
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/tickets/{ticket_id}", response_model=AdminTicketDetailResponse)
def get_tenant_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    try:
        item = AdminQueryService(db).get_ticket(
            tenant_id=admin.tenant_id,
            ticket_id=ticket_id,
        )
    except AdminTicketNotFoundError as error:
        raise HTTPException(status_code=404, detail="工单不存在") from error
    return AdminTicketDetailResponse(data=_to_admin_ticket(item))


@router.get("/traces", response_model=AdminTraceListResponse)
def list_tenant_traces(
    session_id: str | None = Query(default=None, max_length=50),
    intent: str | None = Query(default=None, max_length=50),
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(running|succeeded|pending|failed)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTraceListResponse:
    result = AdminQueryService(db).list_traces(
        tenant_id=admin.tenant_id,
        session_id=session_id,
        intent=intent,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return AdminTraceListResponse(
        data=[
            _to_admin_trace(trace)
            for trace in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/traces/{trace_id}", response_model=AdminTraceDetailResponse)
def get_tenant_trace(
    trace_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTraceDetailResponse:
    try:
        trace = AdminQueryService(db).get_trace(
            tenant_id=admin.tenant_id,
            trace_id=trace_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Trace不存在") from error
    return AdminTraceDetailResponse(data=_to_admin_trace_detail(trace))


@router.get(
    "/trace-sessions/{session_id}",
    response_model=AdminTraceSessionResponse,
)
def get_tenant_trace_session(
    session_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminTraceSessionResponse:
    traces = AdminQueryService(db).list_trace_session(
        tenant_id=admin.tenant_id,
        session_id=session_id,
    )
    return AdminTraceSessionResponse(
        session_id=session_id,
        data=[_to_admin_trace(trace) for trace in traces],
    )


@router.get(
    "/unresolved-cases",
    response_model=AdminUnresolvedCaseListResponse,
)
def list_tenant_unresolved_cases(
    is_resolved: bool | None = Query(default=None),
    predicted_intent: str | None = Query(default=None, max_length=50),
    should_add_to_kb: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUnresolvedCaseListResponse:
    result = UnresolvedCaseService(db).list_for_tenant(
        tenant_id=admin.tenant_id,
        is_resolved=is_resolved,
        predicted_intent=predicted_intent,
        should_add_to_kb=should_add_to_kb,
        page=page,
        page_size=page_size,
    )
    return AdminUnresolvedCaseListResponse(
        data=[
            _to_admin_unresolved_case(item)
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get(
    "/unresolved-cases/stats",
    response_model=AdminUnresolvedCaseStatsResponse,
)
def get_tenant_unresolved_case_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUnresolvedCaseStatsResponse:
    stats = UnresolvedCaseService(db).stats_for_tenant(
        tenant_id=admin.tenant_id,
    )
    return AdminUnresolvedCaseStatsResponse(
        data=AdminUnresolvedCaseStats(
            pending=stats.pending,
            resolved=stats.resolved,
            knowledge_candidates=stats.knowledge_candidates,
        )
    )


@router.get(
    "/unresolved-cases/{case_id}",
    response_model=AdminUnresolvedCaseResponse,
)
def get_tenant_unresolved_case(
    case_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUnresolvedCaseResponse:
    try:
        item = UnresolvedCaseService(db).get_for_tenant(
            tenant_id=admin.tenant_id,
            case_id=case_id,
        )
    except UnresolvedCaseNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return AdminUnresolvedCaseResponse(data=_to_admin_unresolved_case(item))


@router.patch(
    "/unresolved-cases/{case_id}",
    response_model=AdminUnresolvedCaseResponse,
)
def update_tenant_unresolved_case(
    case_id: int,
    request: UnresolvedCaseUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> AdminUnresolvedCaseResponse:
    try:
        item = UnresolvedCaseService(db).update_annotation(
            tenant_id=admin.tenant_id,
            case_id=case_id,
            reviewed_by=admin.id,
            changes=request.model_dump(exclude_unset=True),
        )
    except UnresolvedCaseNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnresolvedCaseValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return AdminUnresolvedCaseResponse(data=_to_admin_unresolved_case(item))


@router.post(
    "/unresolved-cases/{case_id}/knowledge-draft",
    response_model=KnowledgeDraftCreateResponse,
    status_code=201,
)
def create_knowledge_draft_from_case(
    case_id: int,
    request: KnowledgeDraftCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> KnowledgeDraftCreateResponse:
    try:
        item, document_id, revision_id = UnresolvedCaseService(db).create_faq_draft(
            tenant_id=admin.tenant_id,
            case_id=case_id,
            created_by=admin.id,
            title=request.title,
            category=request.category,
            effective_at=request.effective_at,
            expires_at=request.expires_at,
        )
    except UnresolvedCaseNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except UnresolvedCaseValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return KnowledgeDraftCreateResponse(
        data=KnowledgeDraftCreateData(
            case=_to_admin_unresolved_case(item),
            document_id=document_id,
            revision_id=revision_id,
        )
    )


def _to_admin_ticket(item) -> AdminTicketListItem:
    ticket = item.ticket
    return AdminTicketListItem(
        id=ticket.id,
        order_id=ticket.order_id,
        user_id=ticket.user_id,
        username=item.username,
        product_name=item.product_name,
        refund_id=item.refund_id,
        refund_status=item.refund_status,
        type=ticket.type,
        reason=ticket.reason,
        amount=float(ticket.amount),
        risk_level=ticket.risk_level,
        status=ticket.status,
        human_review=bool(ticket.human_review),
        reviewed_by=ticket.reviewed_by,
        reviewer_username=item.reviewer_username,
        reviewed_at=ticket.reviewed_at,
        review_reason=ticket.review_reason,
        created_at=ticket.created_at,
    )


def _to_admin_unresolved_case(item) -> AdminUnresolvedCaseListItem:
    case = item.case
    return AdminUnresolvedCaseListItem(
        id=case.id,
        user_id=case.user_id,
        user_message=case.user_message,
        predicted_intent=case.predicted_intent,
        confidence=(
            float(case.confidence) if case.confidence is not None else None
        ),
        fallback_reason=case.fallback_reason,
        final_answer=case.final_answer,
        is_resolved=bool(case.is_resolved),
        human_label_intent=case.human_label_intent,
        human_label_answer=case.human_label_answer,
        should_add_to_kb=bool(case.should_add_to_kb),
        knowledge_document_id=case.knowledge_document_id,
        knowledge_revision_id=case.knowledge_revision_id,
        resolved_by_build_id=case.resolved_by_build_id,
        auto_resolved_at=case.auto_resolved_at,
        reviewed_by=case.reviewed_by,
        reviewer_username=item.reviewer_username,
        reviewed_at=case.reviewed_at,
        updated_at=case.updated_at,
        created_at=case.created_at,
    )


def _to_admin_trace(trace: AgentTrace) -> AdminTraceListItem:
    return AdminTraceListItem(
        id=trace.id,
        user_id=trace.user_id,
        session_id=trace.session_id,
        node_name=trace.node_name,
        message=trace.message or (trace.input or {}).get("message"),
        intent=trace.intent,
        confidence=(
            float(trace.confidence) if trace.confidence is not None else None
        ),
        workflow_name=trace.workflow_name or trace.tool_name,
        status=trace.status,
        tool_name=trace.tool_name,
        tool_status=trace.tool_status,
        human_required=bool(trace.human_required),
        missing_slots=list(trace.missing_slots or []),
        error_stage=trace.error_stage,
        final_answer=trace.final_answer,
        finished_at=trace.finished_at,
        created_at=trace.created_at,
    )


def _to_admin_trace_detail(trace: AgentTrace) -> AdminTraceDetailData:
    summary = _to_admin_trace(trace).model_dump()
    return AdminTraceDetailData(
        **summary,
        rag_sources=list(trace.rag_sources or []),
        error=_trace_error(
            trace.error_stage,
            trace.error_code,
            trace.error_type,
            trace.error_message,
        ),
        steps=[
            AdminTraceStepData(
                id=step.id,
                sequence=step.sequence,
                node_name=step.node_name,
                workflow_name=step.workflow_name,
                status=step.status,
                missing_slots=list(step.missing_slots or []),
                tool_name=step.tool_name,
                rag_sources=list(step.rag_sources or []),
                error=_trace_error(
                    step.error_stage,
                    step.error_code,
                    step.error_type,
                    step.error_message,
                ),
                started_at=step.started_at,
                finished_at=step.finished_at,
                duration_ms=step.duration_ms,
            )
            for step in trace.steps
        ],
    )


def _trace_error(stage, code, error_type, message) -> AdminTraceError | None:
    if not any((stage, code, error_type, message)):
        return None
    return AdminTraceError(
        stage=stage,
        code=code,
        type=error_type,
        message=message,
    )
