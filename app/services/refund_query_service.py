"""客户和管理员退款列表查询服务。"""

from sqlalchemy.orm import Session, joinedload

from app.models.order import Order
from app.models.refund_request import RefundRequest
from app.services.query_page import QueryPage, validate_pagination


REFUND_STATUSES = frozenset(
    {"reviewing", "approved", "succeeded", "rejected", "failed"}
)


class RefundQueryError(ValueError):
    pass


class RefundQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        page: int,
        page_size: int,
    ) -> QueryPage[RefundRequest]:
        return self._list(
            tenant_id=tenant_id,
            user_id=user_id,
            status=None,
            page=page,
            page_size=page_size,
        )

    def list_for_tenant(
        self,
        *,
        tenant_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[RefundRequest]:
        return self._list(
            tenant_id=tenant_id,
            user_id=None,
            status=status,
            page=page,
            page_size=page_size,
        )

    def _list(
        self,
        *,
        tenant_id: int,
        user_id: int | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[RefundRequest]:
        validate_pagination(page=page, page_size=page_size)
        if status is not None and status not in REFUND_STATUSES:
            raise RefundQueryError("退款状态无效")

        query = self.db.query(RefundRequest)
        if user_id is None:
            query = query.options(
                joinedload(RefundRequest.user),
                joinedload(RefundRequest.order).joinedload(Order.product),
            )
        query = query.filter(RefundRequest.tenant_id == tenant_id)
        if user_id is not None:
            query = query.filter(RefundRequest.user_id == user_id)
        if status is not None:
            query = query.filter(RefundRequest.status == status)

        total = query.count()
        refunds = (
            query.order_by(RefundRequest.created_at.desc(), RefundRequest.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=refunds,
            total=total,
            page=page,
            page_size=page_size,
        )
