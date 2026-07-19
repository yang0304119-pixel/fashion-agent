"""管理员租户数据列表响应模型。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminDashboardData(BaseModel):
    orders_total: int
    pending_refunds: int
    failed_refunds: int
    pending_tickets: int
    unresolved_cases: int
    today_sessions: int


class AdminDashboardResponse(BaseModel):
    success: bool = True
    data: AdminDashboardData


class AdminOrderListItem(BaseModel):
    id: int
    user_id: int
    username: str
    product_name: str
    quantity: int
    total_price: float
    status: str
    refund_id: int | None
    refund_status: str | None
    ticket_count: int
    created_at: datetime | None


class AdminOrderListResponse(BaseModel):
    data: list[AdminOrderListItem]
    total: int
    page: int
    page_size: int


class AdminOrderUserData(BaseModel):
    id: int
    username: str


class AdminOrderProductData(BaseModel):
    id: int
    name: str
    category: str
    price: float


class AdminOrderRefundData(BaseModel):
    id: int
    status: str


class AdminOrderTicketData(BaseModel):
    id: int
    type: str
    status: str


class AdminOrderDetailData(BaseModel):
    id: int
    user: AdminOrderUserData
    product: AdminOrderProductData
    quantity: int
    total_price: float
    status: str
    refund: AdminOrderRefundData | None
    tickets: list[AdminOrderTicketData]
    created_at: datetime | None


class AdminOrderDetailResponse(BaseModel):
    success: bool = True
    data: AdminOrderDetailData


class AdminTicketListItem(BaseModel):
    id: int
    order_id: int
    user_id: int
    username: str
    product_name: str
    refund_id: int | None
    refund_status: str | None
    type: str
    reason: str
    amount: float
    risk_level: str
    status: str
    human_review: bool
    reviewed_by: int | None
    reviewer_username: str | None
    reviewed_at: datetime | None
    review_reason: str | None
    created_at: datetime | None


class AdminTicketListResponse(BaseModel):
    data: list[AdminTicketListItem]
    total: int
    page: int
    page_size: int


class AdminTicketDetailResponse(BaseModel):
    success: bool = True
    data: AdminTicketListItem


class AdminTraceListItem(BaseModel):
    id: int
    user_id: int
    session_id: str
    node_name: str
    message: str | None
    intent: str | None
    confidence: float | None
    workflow_name: str | None
    status: str | None
    tool_name: str | None
    tool_status: str | None
    human_required: bool
    missing_slots: list[str]
    error_stage: str | None
    final_answer: str | None
    finished_at: datetime | None
    created_at: datetime | None


class AdminTraceListResponse(BaseModel):
    data: list[AdminTraceListItem]
    total: int
    page: int
    page_size: int


class AdminTraceError(BaseModel):
    stage: str | None
    code: str | None
    type: str | None
    message: str | None


class AdminTraceStepData(BaseModel):
    id: int
    sequence: int
    node_name: str
    workflow_name: str | None
    status: str
    missing_slots: list[str]
    tool_name: str | None
    rag_sources: list[dict]
    error: AdminTraceError | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None


class AdminTraceDetailData(AdminTraceListItem):
    rag_sources: list[dict]
    error: AdminTraceError | None
    steps: list[AdminTraceStepData]


class AdminTraceDetailResponse(BaseModel):
    success: bool = True
    data: AdminTraceDetailData


class AdminTraceSessionResponse(BaseModel):
    success: bool = True
    session_id: str
    data: list[AdminTraceListItem]


class AdminUnresolvedCaseListItem(BaseModel):
    id: int
    user_id: int
    user_message: str
    predicted_intent: str | None
    confidence: float | None
    fallback_reason: str | None
    final_answer: str | None
    is_resolved: bool
    human_label_intent: str | None
    human_label_answer: str | None
    should_add_to_kb: bool
    reviewed_by: int | None
    reviewer_username: str | None
    reviewed_at: datetime | None
    updated_at: datetime | None
    created_at: datetime | None


class AdminUnresolvedCaseListResponse(BaseModel):
    data: list[AdminUnresolvedCaseListItem]
    total: int
    page: int
    page_size: int


class AdminUnresolvedCaseResponse(BaseModel):
    success: bool = True
    data: AdminUnresolvedCaseListItem


class AdminUnresolvedCaseStats(BaseModel):
    pending: int
    resolved: int
    knowledge_candidates: int


class AdminUnresolvedCaseStatsResponse(BaseModel):
    success: bool = True
    data: AdminUnresolvedCaseStats


class UnresolvedCaseUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_resolved: bool | None = None
    human_label_intent: str | None = Field(default=None, max_length=50)
    human_label_answer: str | None = Field(default=None, max_length=4000)
    should_add_to_kb: bool | None = None

    @field_validator("human_label_intent", "human_label_answer")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
