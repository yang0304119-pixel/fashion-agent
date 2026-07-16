"""
FastAPI 依赖注入

集中管理跨路由的共享依赖，当前提供数据库会话注入。
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from app.core.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """提供数据库会话，请求结束后自动关闭。

    替代在每个路由函数中手动 `SessionLocal()` + try/finally 的模式。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
