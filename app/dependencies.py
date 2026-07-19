"""
FastAPI 依赖注入

集中管理跨路由的共享依赖，当前提供数据库会话注入。
"""

from collections.abc import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import TokenError, decode_access_token
from app.models.user import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_db() -> Generator[Session, None, None]:
    """提供数据库会话，请求结束后自动关闭。

    替代在每个路由函数中手动 `SessionLocal()` + try/finally 的模式。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从Bearer令牌恢复可信用户，不接受客户端提交的 user_id。"""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="登录状态无效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        claims = decode_access_token(token)
    except (TokenError, RuntimeError):
        raise unauthorized

    user = db.query(User).filter(
        User.id == claims.user_id,
        User.tenant_id == claims.tenant_id,
        User.is_active.is_(True),
    ).first()
    if user is None or user.role != claims.role:
        raise unauthorized
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """限制接口只能由当前租户的管理员访问。"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user
