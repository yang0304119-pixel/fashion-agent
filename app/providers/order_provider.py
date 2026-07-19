"""订单系统只读 Provider 契约。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


class OrderProviderError(Exception):
    pass


class OrderNotFoundError(OrderProviderError):
    pass


class OrderQueryError(OrderProviderError):
    pass


@dataclass(frozen=True)
class OrderResult:
    order_id: int
    user_id: int
    product_id: int
    product_name: str
    quantity: int
    amount: float
    status: str
    created_at: datetime | None


@dataclass(frozen=True)
class OrderSummary:
    order_id: int
    product_name: str
    quantity: int
    amount: float
    status: str


@dataclass(frozen=True)
class OrderPage:
    items: list[OrderSummary]
    total: int
    page: int
    page_size: int


class OrderProvider(Protocol):
    def get_order(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> OrderResult: ...

    def list_orders(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> OrderPage: ...
