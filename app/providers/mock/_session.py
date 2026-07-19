"""SQLAlchemy Adapter 共享的短生命周期会话管理。"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session


@contextmanager
def provider_session(
    db: Session | None,
    session_factory: Callable[[], Session],
) -> Iterator[Session]:
    if db is not None:
        yield db
        return

    owned_db = session_factory()
    try:
        yield owned_db
    finally:
        owned_db.close()
