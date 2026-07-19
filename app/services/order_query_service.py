"""客户订单列表查询服务。"""

from dataclasses import dataclass

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.product import Product


ORDER_STATUSES = frozenset(
    {"pending", "shipped", "delivered", "refunded", "cancelled"}
)


class OrderQueryError(ValueError):
    pass


@dataclass(frozen=True)
class OrderSummary:
    id: int
    product_name: str
    quantity: int
    total_price: float
    status: str


@dataclass(frozen=True)
class OrderPage:
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int


class OrderQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> OrderPage:
        """分页查询当前租户、当前用户的订单。"""
        if page < 1:
            raise OrderQueryError("page必须大于等于1")
        if not 1 <= page_size <= 100:
            raise OrderQueryError("page_size必须在1到100之间")
        if status is not None and status not in ORDER_STATUSES:
            raise OrderQueryError("订单状态无效")

        query = (
            self.db.query(Order, Product.name.label("product_name"))
            .join(
                Product,
                and_(
                    Product.id == Order.product_id,
                    Product.tenant_id == Order.tenant_id,
                ),
            )
            .filter(
                Order.tenant_id == tenant_id,
                Order.user_id == user_id,
            )
        )
        if status is not None:
            query = query.filter(Order.status == status)

        total = query.count()
        rows = (
            query.order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return OrderPage(
            items=[
                OrderSummary(
                    id=order.id,
                    product_name=product_name,
                    quantity=order.quantity,
                    total_price=float(order.total_price),
                    status=order.status,
                )
                for order, product_name in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )
