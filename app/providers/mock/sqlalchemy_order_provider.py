"""订单 Provider 的 SQLAlchemy Mock Adapter。"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.providers.mock._session import provider_session
from app.providers.order_provider import (
    OrderNotFoundError,
    OrderPage,
    OrderQueryError,
    OrderResult,
    OrderSummary,
)
from app.services.order_query_service import (
    OrderQueryError as ServiceOrderQueryError,
    OrderQueryService,
)
from app.services.order_service import (
    OrderNotFoundError as ServiceOrderNotFoundError,
    OrderService,
)


class SqlAlchemyOrderProvider:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        db: Session | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.db = db

    def get_order(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> OrderResult:
        with provider_session(self.db, self.session_factory) as db:
            try:
                order = OrderService(db).get_for_user(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    order_id=order_id,
                )
            except ServiceOrderNotFoundError as error:
                raise OrderNotFoundError(
                    "订单不存在或不属于当前用户"
                ) from error
            return OrderResult(
                order_id=order.id,
                user_id=order.user_id,
                product_id=order.product_id,
                product_name=order.product.name,
                quantity=order.quantity,
                amount=float(order.total_price),
                status=order.status,
                created_at=order.created_at,
            )

    def list_orders(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> OrderPage:
        with provider_session(self.db, self.session_factory) as db:
            try:
                result = OrderQueryService(db).list_for_user(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    status=status,
                    page=page,
                    page_size=page_size,
                )
            except ServiceOrderQueryError as error:
                raise OrderQueryError(str(error)) from error
            return OrderPage(
                items=[
                    OrderSummary(
                        order_id=item.id,
                        product_name=item.product_name,
                        quantity=item.quantity,
                        amount=item.total_price,
                        status=item.status,
                    )
                    for item in result.items
                ],
                total=result.total,
                page=result.page,
                page_size=result.page_size,
            )
