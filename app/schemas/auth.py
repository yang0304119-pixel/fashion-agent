"""身份认证接口模型。"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    tenant_id: int | None = Field(default=None, gt=0)
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128)


class AuthenticatedUser(BaseModel):
    id: int
    username: str
    tenant_id: int
    role: str
    role_label: str
    permissions: list[str]
    home_view: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthenticatedUser
