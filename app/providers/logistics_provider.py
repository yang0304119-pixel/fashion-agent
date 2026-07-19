"""物流系统只读 Provider 契约；当前不提供运行时实现。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class LogisticsResult:
    order_id: int
    carrier: str | None
    tracking_number: str | None
    status: str
    latest_event: str | None
    estimated_delivery: datetime | None


class LogisticsProvider(Protocol):
    def get_tracking(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> LogisticsResult: ...
