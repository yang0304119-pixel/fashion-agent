"""
售后工单查询接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.ticket import TicketListItem, TicketListResponse
from app.services.ticket_query_service import TicketQueryService

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=TicketListResponse)
def list_tickets(
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
    current_user: User = Depends(get_current_user),
) -> TicketListResponse:
    """分页返回当前登录用户在当前租户下的工单。"""
    result = TicketQueryService(db).list_for_user(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        status=status_filter,
        ticket_type=type_filter,
        page=page,
        page_size=page_size,
    )
    return TicketListResponse(
        data=[_to_ticket_list_item(ticket) for ticket in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{ticket_id}")
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只查询当前登录用户在当前租户下的售后工单。"""
    ticket = db.query(Ticket).filter(
        Ticket.id == ticket_id,
        Ticket.user_id == current_user.id,
        Ticket.tenant_id == current_user.tenant_id,
    ).first()

    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在")

    return {
        "success": True,
        "data": {
            "id": ticket.id,
            "order_id": ticket.order_id,
            "type": ticket.type,
            "reason": ticket.reason,
            "amount": float(ticket.amount),
            "risk_level": ticket.risk_level,
            "status": ticket.status,
            "human_review": ticket.human_review,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        },
    }


def _to_ticket_list_item(ticket: Ticket) -> TicketListItem:
    return TicketListItem(
        id=ticket.id,
        order_id=ticket.order_id,
        type=ticket.type,
        reason=ticket.reason,
        amount=float(ticket.amount),
        risk_level=ticket.risk_level,
        status=ticket.status,
        human_review=bool(ticket.human_review),
        created_at=ticket.created_at,
    )
