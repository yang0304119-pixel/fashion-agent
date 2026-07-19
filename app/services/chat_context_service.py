"""将不可信的聊天上下文 ID 解析为服务端可信业务数据。"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.providers.factory import get_order_provider, get_product_provider
from app.providers.order_provider import (
    OrderNotFoundError,
    OrderProvider,
)
from app.providers.product_provider import (
    ProductNotFoundError,
    ProductProvider,
)
from app.schemas.chat import OrderChatContext, ProductChatContext


class ChatContextError(Exception):
    pass


class ChatContextNotFoundError(ChatContextError):
    pass


@dataclass(frozen=True)
class ResolvedChatContext:
    context_type: str
    trusted_data: dict[str, Any]
    collected_slots: dict[str, Any]


class ChatContextService:
    def __init__(
        self,
        db: Session | None = None,
        *,
        product_provider: ProductProvider | None = None,
        order_provider: OrderProvider | None = None,
    ) -> None:
        self.product_provider = product_provider or get_product_provider(db)
        self.order_provider = order_provider or get_order_provider(db)

    def resolve(
        self,
        *,
        tenant_id: int,
        user_id: int,
        context: ProductChatContext | OrderChatContext,
    ) -> ResolvedChatContext:
        if isinstance(context, ProductChatContext):
            return self._resolve_product(
                tenant_id=tenant_id,
                product_id=context.product_id,
            )
        return self._resolve_order(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=context.order_id,
        )

    def _resolve_product(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> ResolvedChatContext:
        try:
            product = self.product_provider.get_product(
                tenant_id=tenant_id,
                product_id=product_id,
            )
        except ProductNotFoundError as error:
            raise ChatContextNotFoundError("商品不存在") from error

        trusted_data = {
            "context_type": "product",
            "product_id": product.product_id,
            "product_name": product.name,
            "category": product.category,
            "price": float(product.price),
            "colors": list(product.colors or []),
            "sizes": list(product.sizes or []),
            "stock": product.stock,
        }
        return ResolvedChatContext(
            context_type="product",
            trusted_data=trusted_data,
            collected_slots={
                "product_id": product.product_id,
                "product_name": product.name,
            },
        )

    def _resolve_order(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> ResolvedChatContext:
        try:
            order = self.order_provider.get_order(
                tenant_id=tenant_id,
                user_id=user_id,
                order_id=order_id,
            )
        except OrderNotFoundError as error:
            raise ChatContextNotFoundError("订单不存在") from error

        trusted_data = {
            "context_type": "order",
            "order_id": order.order_id,
            "product_id": order.product_id,
            "product_name": order.product_name,
            "quantity": order.quantity,
            "amount": order.amount,
            "status": order.status,
        }
        return ResolvedChatContext(
            context_type="order",
            trusted_data=trusted_data,
            collected_slots={
                "order_id": order.order_id,
                "product_id": order.product_id,
                "product_name": order.product_name,
            },
        )
