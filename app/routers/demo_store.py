"""非生产环境的 Mock 外部电商系统会话入口。"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.providers.factory import get_product_provider
from app.providers.product_provider import ProductData, ProductNotFoundError
from app.schemas.auth import AuthenticatedUser, TokenResponse


router = APIRouter(prefix="/demo-store", tags=["demo-store"])


@router.get("/products")
def list_demo_products(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """只返回当前模拟消费者所在租户的可咨询商品。"""
    products = get_product_provider(db).list_products(
        tenant_id=current_user.tenant_id,
    )
    return {"data": [_serialize_product(product) for product in products]}


@router.get("/products/{product_id}")
def get_demo_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        product = get_product_provider(db).get_product(
            tenant_id=current_user.tenant_id,
            product_id=product_id,
        )
    except ProductNotFoundError as error:
        raise HTTPException(status_code=404, detail="商品不存在") from error
    return {"data": _serialize_product(product, include_details=True)}


def _serialize_product(
    product: ProductData,
    *,
    include_details: bool = False,
) -> dict:
    data = {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "image_url": product.image_url,
        "colors": product.colors,
        "sizes": product.sizes,
        "stock": product.stock,
        "stock_status": "in_stock" if product.stock > 0 else "out_of_stock",
    }
    if include_details:
        data.update({
            "description": product.description,
            "materials": product.materials,
            "care_instructions": product.care_instructions,
        })
    return data


@router.post("/session", response_model=TokenResponse)
def create_demo_store_session(
    db: Session = Depends(get_db),
) -> TokenResponse:
    """模拟外部渠道已识别消费者，不接受浏览器提交任何身份字段。"""
    if settings.ENVIRONMENT.lower() == "production":
        raise HTTPException(status_code=404, detail="接口不存在")

    user = (
        db.query(User)
        .filter(
            User.id == settings.DEMO_STORE_USER_ID,
            User.tenant_id == settings.DEMO_STORE_TENANT_ID,
            User.role == "customer",
            User.is_active.is_(True),
        )
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mock 外部电商系统尚未初始化模拟消费者",
        )

    try:
        access_token = create_access_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
        )
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mock 外部电商系统会话配置错误",
        ) from error

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=AuthenticatedUser(
            id=user.id,
            username=user.username,
            tenant_id=user.tenant_id,
            role=user.role,
        ),
    )
