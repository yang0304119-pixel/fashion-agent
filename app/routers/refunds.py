"""当前用户的退款状态查询接口。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.refund_request import RefundRequest
from app.models.user import User
from app.schemas.refund import RefundListResponse, RefundResponse
from app.services.refund_presenter import to_refund_data
from app.services.refund_query_service import RefundQueryService
from app.services.refund_service import RefundNotFoundError, RefundService


router = APIRouter(prefix="/refunds", tags=["refunds"])


@router.get("", response_model=RefundListResponse)
def list_refunds(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RefundListResponse:
    result = RefundQueryService(db).list_for_user(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    return RefundListResponse(
        data=[
            to_refund_data(refund, include_user=False)
            for refund in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/order/{order_id}", response_model=RefundResponse)
def get_refund_by_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RefundResponse:
    try:
        refund = RefundService(db).get_by_order_for_user(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            order_id=order_id,
        )
    except RefundNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return RefundResponse(data=to_refund_data(refund, include_user=False))


@router.get("/{refund_request_id}", response_model=RefundResponse)
def get_refund(
    refund_request_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RefundResponse:
    try:
        refund = RefundService(db).get_for_user(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            refund_request_id=refund_request_id,
        )
    except RefundNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return RefundResponse(data=to_refund_data(refund, include_user=False))
