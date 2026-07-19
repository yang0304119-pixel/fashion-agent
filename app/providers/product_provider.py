"""商品系统只读 Provider 契约。"""

from dataclasses import dataclass
from typing import Protocol


class ProductProviderError(Exception):
    pass


class ProductNotFoundError(ProductProviderError):
    pass


class InvalidProductSearchError(ProductProviderError):
    pass


@dataclass(frozen=True)
class ProductData:
    product_id: int
    name: str
    category: str
    price: float
    colors: list[str]
    sizes: list[str]
    stock: int
    description: str
    materials: str
    care_instructions: str
    image_url: str | None = None


class ProductProvider(Protocol):
    def list_products(
        self,
        *,
        tenant_id: int,
        limit: int = 50,
    ) -> list[ProductData]: ...

    def get_product(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> ProductData: ...

    def search_products(
        self,
        *,
        tenant_id: int,
        query: str,
        limit: int = 5,
    ) -> list[ProductData]: ...
