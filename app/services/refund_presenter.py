"""将退款ORM对象转换为稳定的API响应模型。"""

from app.models.refund_request import RefundRequest
from app.schemas.refund import RefundData


def to_refund_data(
    refund: RefundRequest,
    *,
    include_user: bool,
) -> RefundData:
    return RefundData(
        id=refund.id,
        order_id=refund.order_id,
        user_id=refund.user_id if include_user else None,
        username=refund.user.username if include_user else None,
        product_name=refund.order.product.name if include_user else None,
        ticket_id=refund.ticket_id,
        amount=float(refund.amount),
        reason=refund.reason,
        risk_level=refund.risk_level,
        human_review=refund.human_review,
        status=refund.status,
        gateway_mode=refund.gateway_mode,
        provider_refund_id=refund.provider_refund_id,
        failure_reason=refund.failure_reason,
        created_at=refund.created_at,
        updated_at=refund.updated_at,
    )
