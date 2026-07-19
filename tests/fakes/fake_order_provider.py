from app.providers.order_provider import (
    OrderNotFoundError,
    OrderPage,
    OrderResult,
)


class FakeOrderProvider:
    def __init__(self, results: dict[int, OrderResult]) -> None:
        self.results = results
        self.get_calls: list[dict[str, int]] = []
        self.list_calls: list[dict] = []

    def get_order(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> OrderResult:
        self.get_calls.append({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "order_id": order_id,
        })
        result = self.results.get(order_id)
        if result is None or result.user_id != user_id:
            raise OrderNotFoundError("订单不存在或不属于当前用户")
        return result

    def list_orders(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> OrderPage:
        self.list_calls.append({
            "tenant_id": tenant_id,
            "user_id": user_id,
            "status": status,
            "page": page,
            "page_size": page_size,
        })
        return OrderPage(items=[], total=0, page=page, page_size=page_size)
