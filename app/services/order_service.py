"""订单领域服务：集中处理用户、租户与订单归属查询。"""

from sqlalchemy.orm import Session

from app.models.order import Order


class OrderServiceError(Exception):
    pass


class OrderNotFoundError(OrderServiceError):
    pass


class OrderService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> Order:
        """只返回当前租户中属于当前用户的订单。"""
        order = self.db.query(Order).filter(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
            Order.user_id == user_id,
        ).first()
        if order is None:
            raise OrderNotFoundError("订单不存在或不属于当前用户")
        return order

    def get_for_tenant(
        self,
        *,
        tenant_id: int,
        order_id: int,
    ) -> Order:
        """管理员或内部工作流按租户边界查询订单。"""
        order = self.db.query(Order).filter(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        ).first()
        if order is None:
            raise OrderNotFoundError("订单不存在")
        return order
