"""商品 Provider 的 SQLAlchemy Mock Adapter。"""

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.providers.mock._session import provider_session
from app.providers.product_provider import (
    InvalidProductSearchError,
    ProductData,
    ProductNotFoundError,
)
from app.services.product_catalog_service import (
    InvalidProductSearchError as ServiceInvalidProductSearchError,
    ProductCatalogService,
)
from app.services.product_query_service import (
    ProductNotFoundError as ServiceProductNotFoundError,
    ProductQueryService,
    product_image_url,
)


class SqlAlchemyProductProvider:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Session],
        db: Session | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.db = db

    def list_products(
        self,
        *,
        tenant_id: int,
        limit: int = 50,
    ) -> list[ProductData]:
        with provider_session(self.db, self.session_factory) as db:
            products = ProductQueryService(db).list_for_tenant(
                tenant_id=tenant_id,
                limit=limit,
            )
            return [_to_product_data(product) for product in products]

    def get_product(
        self,
        *,
        tenant_id: int,
        product_id: int,
    ) -> ProductData:
        with provider_session(self.db, self.session_factory) as db:
            try:
                product = ProductQueryService(db).get_for_tenant(
                    tenant_id=tenant_id,
                    product_id=product_id,
                )
            except ServiceProductNotFoundError as error:
                raise ProductNotFoundError("商品不存在") from error
            return _to_product_data(product)

    def search_products(
        self,
        *,
        tenant_id: int,
        query: str,
        limit: int = 5,
    ) -> list[ProductData]:
        with provider_session(self.db, self.session_factory) as db:
            try:
                products = ProductCatalogService(db).search(
                    tenant_id=tenant_id,
                    query=query,
                    limit=limit,
                )
            except ServiceInvalidProductSearchError as error:
                raise InvalidProductSearchError(str(error)) from error
            return [_to_product_data(product) for product in products]


def _to_product_data(product) -> ProductData:
    return ProductData(
        product_id=product.id,
        name=product.name,
        category=product.category,
        price=float(product.price),
        colors=list(product.colors or []),
        sizes=list(product.sizes or []),
        stock=product.stock,
        description=product.description,
        materials=product.materials,
        care_instructions=product.care_instructions,
        image_url=product_image_url(product.id),
    )
