"""
订单查询接口
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.order import Order

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    """查询订单信息（绕过 Agent，直接查数据库）。"""
    order = db.query(Order).filter(Order.id == order_id).first()

    if order is None:
        raise HTTPException(status_code=404, detail=f"订单 {order_id} 不存在")

    return {
        "success": True,
        "data": {
            "id": order.id,
            "user_id": order.user_id,
            "product_id": order.product_id,
            "quantity": order.quantity,
            "total_price": float(order.total_price),
            "status": order.status,
            "created_at": order.created_at.isoformat() if order.created_at else None,
        },
    }
