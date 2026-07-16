"""
售后工单查询接口
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.ticket import Ticket

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("/{ticket_id}")
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """查询售后工单信息。"""
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()

    if ticket is None:
        raise HTTPException(status_code=404, detail=f"工单 {ticket_id} 不存在")

    return {
        "success": True,
        "data": {
            "id": ticket.id,
            "order_id": ticket.order_id,
            "user_id": ticket.user_id,
            "type": ticket.type,
            "reason": ticket.reason,
            "amount": float(ticket.amount),
            "risk_level": ticket.risk_level,
            "status": ticket.status,
            "human_review": ticket.human_review,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        },
    }
