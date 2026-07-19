from app.providers.product_provider import (
    InvalidProductSearchError,
    ProductData,
    ProductNotFoundError,
)


class FakeProductProvider:
    def __init__(self, results: dict[int, ProductData]) -> None:
        self.results = results
        self.get_calls: list[dict[str, int]] = []
        self.list_calls: list[dict[str, int]] = []
        self.search_calls: list[dict] = []

    def list_products(
        self,
        *,
        tenant_id: int,
        limit: int = 50,
    ) -> list[ProductData]:
        self.list_calls.append({"tenant_id": tenant_id, "limit": limit})
        return list(self.results.values())[:limit]

    def get_product(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> ProductData:
        self.get_calls.append({
            "tenant_id": tenant_id,
            "product_id": product_id,
        })
        result = self.results.get(product_id)
        if result is None:
            raise ProductNotFoundError("商品不存在")
        return result

    def search_products(
        self,
        *,
        tenant_id: int,
        query: str,
        limit: int = 5,
    ) -> list[ProductData]:
        self.search_calls.append({
            "tenant_id": tenant_id,
            "query": query,
            "limit": limit,
        })
        keyword = query.strip()
        if not keyword:
            raise InvalidProductSearchError("请提供商品名称或搜索关键词")
        return [
            product
            for product in self.results.values()
            if keyword in product.name or keyword in product.category
        ][:limit]
