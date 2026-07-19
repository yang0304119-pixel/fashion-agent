"""工单列表接口响应模型。"""

from datetime import datetime

from pydantic import BaseModel


class TicketListItem(BaseModel):
    id: int
    order_id: int
    type: str
    reason: str
    amount: float
    risk_level: str
    status: str
    human_review: bool
    created_at: datetime | None


class TicketListResponse(BaseModel):
    data: list[TicketListItem]
    total: int
    page: int
    page_size: int

