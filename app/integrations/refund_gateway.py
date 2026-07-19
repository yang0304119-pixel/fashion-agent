"""退款渠道抽象。

manual 模式不会声称资金已退回；mock 模式只允许在非生产环境使用。
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.core.config import settings


@dataclass(frozen=True)
class GatewayRefundResult:
    status: str  # pending / succeeded / failed
    provider_refund_id: str | None = None
    error: str | None = None


class RefundGateway(Protocol):
    mode: str

    def execute(
        self,
        *,
        refund_request_id: int,
        order_id: int,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayRefundResult: ...


class ManualRefundGateway:
    mode = "manual"

    def execute(
        self,
        *,
        refund_request_id: int,
        order_id: int,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayRefundResult:
        return GatewayRefundResult(status="pending")


class MockRefundGateway:
    mode = "mock"

    def __init__(
        self,
        *,
        result: str,
        failed_order_ids: frozenset[int] = frozenset(),
    ) -> None:
        if result not in {"succeeded", "pending", "failed"}:
            raise ValueError("Mock退款结果无效")
        self.result = result
        self.failed_order_ids = failed_order_ids

    def execute(
        self,
        *,
        refund_request_id: int,
        order_id: int,
        amount: Decimal,
        idempotency_key: str,
    ) -> GatewayRefundResult:
        result = "failed" if order_id in self.failed_order_ids else self.result
        if result == "pending":
            return GatewayRefundResult(status="pending")
        if result == "failed":
            return GatewayRefundResult(
                status="failed",
                error="Mock渠道按演示场景返回失败",
            )
        return GatewayRefundResult(
            status="succeeded",
            provider_refund_id=(
                f"mock_{order_id}_{refund_request_id}_{idempotency_key[:8]}"
            ),
        )


def get_refund_gateway() -> RefundGateway:
    if settings.REFUND_GATEWAY_MODE == "mock":
        if settings.ENVIRONMENT.lower() == "production":
            raise RuntimeError("生产环境禁止使用 mock 退款渠道")
        return MockRefundGateway(
            result=settings.MOCK_REFUND_RESULT,
            failed_order_ids=settings.mock_refund_failed_order_ids,
        )
    return ManualRefundGateway()
