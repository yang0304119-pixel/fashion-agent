"""列表查询共享分页结构与校验。"""

from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


class PaginationError(ValueError):
    pass


@dataclass(frozen=True)
class QueryPage(Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def validate_pagination(*, page: int, page_size: int) -> None:
    if page < 1:
        raise PaginationError("page必须大于等于1")
    if not 1 <= page_size <= 100:
        raise PaginationError("page_size必须在1到100之间")

