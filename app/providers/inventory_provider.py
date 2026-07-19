"""库存系统只读 Provider 契约。"""

from dataclasses import dataclass
from typing import Protocol


class InventoryProviderError(Exception):
    pass


class InventoryNotFoundError(InventoryProviderError):
    pass


@dataclass(frozen=True)
class InventoryResult:
    product_id: int
    product_name: str
    category: str
    price: float
    stock: int
    colors: list[str]
    sizes: list[str]


class InventoryProvider(Protocol):
    def get_inventory(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> InventoryResult: ...
