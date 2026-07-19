"""退款查询与审批接口模型。"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class RefundDecisionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        reason = value.strip()
        if not reason:
            raise ValueError("拒绝原因不能为空")
        return reason


class RefundData(BaseModel):
    id: int
    order_id: int
    user_id: int | None = None
    username: str | None = None
    product_name: str | None = None
    ticket_id: int | None
    amount: float
    reason: str
    risk_level: str
    human_review: bool
    status: str
    gateway_mode: str
    provider_refund_id: str | None
    failure_reason: str | None
    created_at: datetime | None
    updated_at: datetime | None


class RefundResponse(BaseModel):
    success: bool = True
    data: RefundData


class RefundListResponse(BaseModel):
    success: bool = True
    data: list[RefundData]
    total: int
    page: int
    page_size: int
