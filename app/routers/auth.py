"""登录和当前用户接口。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.passwords import verify_password
from app.core.security import create_access_token
from app.core.permissions import home_view_for_role, permissions_for_role, role_label
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.auth import AuthenticatedUser, LoginRequest, TokenResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """校验账号密码并签发JWT；错误信息不区分账号或密码。"""
    username = request.username.strip()
    query = db.query(User).filter(User.username == username)
    if request.tenant_id is not None:
        query = query.filter(User.tenant_id == request.tenant_id)
    users = query.limit(2).all()
    user = users[0] if len(users) == 1 else None
    if (
        user is None
        or not user.is_active
        or not verify_password(request.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务配置错误",
        ) from error

    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=_authenticated_user(user),
    )


@router.get("/me", response_model=AuthenticatedUser)
def me(current_user: User = Depends(get_current_user)) -> AuthenticatedUser:
    return _authenticated_user(current_user)


def _authenticated_user(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        username=user.username,
        tenant_id=user.tenant_id,
        role=user.role,
        role_label=role_label(user.role),
        permissions=sorted(permissions_for_role(user.role)),
        home_view=home_view_for_role(user.role),
    )
