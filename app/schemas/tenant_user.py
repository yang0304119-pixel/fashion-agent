from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from decimal import Decimal


class StaffUserItem(BaseModel):
    id: int
    username: str
    role: str
    role_label: str
    is_active: bool
    created_at: datetime | None


class StaffUserListResponse(BaseModel):
    data: list[StaffUserItem]


class StaffUserResponse(BaseModel):
    data: StaffUserItem


class StaffUserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    role: str


class StaffUserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    role: str | None = None
    is_active: bool | None = None
    reason: str | None = Field(default=None, max_length=500)


class StaffPasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12, max_length=128)


class AuditEventItem(BaseModel):
    id: int
    actor_user_id: int
    actor_role: str
    action: str
    target_type: str
    target_id: str | None
    before_data: dict | None
    after_data: dict | None
    reason: str | None
    ip_address: str | None
    created_at: datetime | None


class AuditEventListResponse(BaseModel):
    data: list[AuditEventItem]
    total: int
    page: int
    page_size: int


class TenantSettingsData(BaseModel):
    tenant_id: int
    name: str
    industry: str
    contact: str | None
    refund_auto_limit: Decimal


class TenantSettingsResponse(BaseModel):
    data: TenantSettingsData


class TenantSettingsUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    contact: str | None = Field(default=None, max_length=50)
    refund_auto_limit: Decimal | None = Field(default=None, ge=0, le=100000)
