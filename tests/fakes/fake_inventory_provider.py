from app.providers.inventory_provider import (
    InventoryNotFoundError,
    InventoryResult,
)


class FakeInventoryProvider:
    def __init__(self, results: dict[int, InventoryResult]) -> None:
        self.results = results
        self.calls: list[dict[str, int]] = []

    def get_inventory(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> InventoryResult:
        self.calls.append({
            "tenant_id": tenant_id,
            "product_id": product_id,
        })
        result = self.results.get(product_id)
        if result is None:
            raise InventoryNotFoundError("商品不存在")
        return result
