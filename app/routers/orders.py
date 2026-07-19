"""
订单查询接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.providers.factory import get_order_provider
from app.providers.order_provider import OrderNotFoundError
from app.schemas.order import OrderListItem, OrderListResponse

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=OrderListResponse)
def list_orders(
    status_filter: str | None = Query(
        default=None,
        alias="status",
        pattern=r"^(pending|shipped|delivered|refunded|cancelled)$",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderListResponse:
    """分页返回当前登录用户在当前租户下的订单。"""
    result = get_order_provider(db).list_orders(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )
    return OrderListResponse(
        data=[
            OrderListItem(
                id=item.order_id,
                product_name=item.product_name,
                quantity=item.quantity,
                total_price=item.amount,
                status=item.status,
            )
            for item in result.items
        ],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
    )


@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只查询当前登录用户在当前租户下的订单。"""
    try:
        order = get_order_provider(db).get_order(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            order_id=order_id,
        )
    except OrderNotFoundError as error:
        raise HTTPException(status_code=404, detail="订单不存在") from error

    return {
        "success": True,
        "data": {
            "id": order.order_id,
            "product_id": order.product_id,
            "product_name": order.product_name,
            "quantity": order.quantity,
            "total_price": order.amount,
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    }
