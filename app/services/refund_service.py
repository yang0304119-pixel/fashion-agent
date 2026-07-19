"""确定性的退款领域服务。

服务负责订单归属、风险等级、幂等、工单、审批状态和退款渠道执行。
LLM不得参与这些判断。
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.refund_gateway import RefundGateway, get_refund_gateway
from app.models.order import Order
from app.models.refund_request import RefundRequest
from app.models.ticket import Ticket
from app.services.order_service import OrderNotFoundError, OrderService


logger = logging.getLogger(__name__)
REFUNDABLE_ORDER_STATUSES = ("pending", "shipped", "delivered")


class RefundServiceError(Exception):
    """退款服务可安全展示给调用方的业务错误。"""


class RefundNotFoundError(RefundServiceError):
    pass


class RefundStateError(RefundServiceError):
    pass


@dataclass(frozen=True)
class RefundOutcome:
    refund: RefundRequest
    reused: bool = False


class RefundService:
    def __init__(
        self,
        db: Session,
        gateway: RefundGateway | None = None,
    ) -> None:
        self.db = db
        self.gateway = gateway

    def submit(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
        reason: str,
        idempotency_key: str,
    ) -> RefundOutcome:
        """创建退款申请；重复请求返回原记录，不重复建单或执行。"""
        existing = self._find_by_idempotency(tenant_id, idempotency_key)
        if existing is not None:
            return RefundOutcome(existing, reused=True)

        try:
            order = OrderService(self.db).get_for_user(
                tenant_id=tenant_id,
                user_id=user_id,
                order_id=order_id,
            )
        except OrderNotFoundError as error:
            raise RefundNotFoundError(
                "订单不存在或不属于当前用户"
            ) from error

        existing_for_order = (
            self.db.query(RefundRequest)
            .filter(
                RefundRequest.tenant_id == tenant_id,
                RefundRequest.user_id == user_id,
                RefundRequest.order_id == order_id,
            )
            .order_by(RefundRequest.created_at.desc())
            .first()
        )
        if existing_for_order is not None:
            return RefundOutcome(existing_for_order, reused=True)

        if order.status == "refunded":
            raise RefundStateError("该订单已经退款，无需重复申请")
        if order.status not in REFUNDABLE_ORDER_STATUSES:
            raise RefundStateError("当前订单状态不支持退款")

        amount = Decimal(str(order.total_price))
        high_risk = amount > settings.REFUND_AUTO_LIMIT
        try:
            gateway = self._get_gateway()
        except RuntimeError as error:
            raise RefundServiceError("退款渠道配置错误") from error
        refund = RefundRequest(
            tenant_id=tenant_id,
            user_id=user_id,
            order_id=order_id,
            reason=reason.strip() or "用户未明确说明原因",
            amount=amount,
            risk_level="high" if high_risk else "low",
            human_review=high_risk,
            status="reviewing" if high_risk else "approved",
            idempotency_key=idempotency_key,
            gateway_mode=gateway.mode,
        )

        try:
            self.db.add(refund)
            self.db.flush()

            if high_risk:
                ticket = Ticket(
                    tenant_id=tenant_id,
                    order_id=order_id,
                    user_id=user_id,
                    type="refund",
                    reason=refund.reason,
                    amount=amount,
                    risk_level="high",
                    status="pending",
                    human_review=True,
                )
                self.db.add(ticket)
                self.db.flush()
                refund.ticket_id = ticket.id
            else:
                self._execute_approved_refund(refund, order)

            self.db.commit()
            self.db.refresh(refund)
            return RefundOutcome(refund)
        except IntegrityError:
            self.db.rollback()
            existing = self._find_by_idempotency(tenant_id, idempotency_key)
            if existing is None:
                existing = self.db.query(RefundRequest).filter(
                    RefundRequest.tenant_id == tenant_id,
                    RefundRequest.order_id == order_id,
                ).first()
            if existing is not None:
                return RefundOutcome(existing, reused=True)
            raise RefundServiceError("退款申请重复提交，请查询已有退款记录")
        except RefundServiceError:
            self.db.rollback()
            raise
        except Exception as error:
            self.db.rollback()
            raise RefundServiceError("退款申请暂时无法处理，请稍后重试") from error

    def approve(
        self,
        *,
        tenant_id: int,
        refund_request_id: int,
        reviewed_by: int | None = None,
    ) -> RefundOutcome:
        """管理员批准高风险退款，并交给配置的退款渠道执行。"""
        refund = self._get_for_tenant(tenant_id, refund_request_id)
        if refund.status in {"approved", "succeeded"}:
            return RefundOutcome(refund, reused=True)
        if refund.status != "reviewing":
            raise RefundStateError(f"退款状态 {refund.status} 不允许批准")

        try:
            order = OrderService(self.db).get_for_tenant(
                tenant_id=tenant_id,
                order_id=refund.order_id,
            )
        except OrderNotFoundError as error:
            raise RefundNotFoundError("关联订单不存在") from error

        try:
            refund.status = "approved"
            if refund.ticket_id:
                ticket = self.db.query(Ticket).filter(
                    Ticket.id == refund.ticket_id,
                    Ticket.tenant_id == tenant_id,
                ).first()
                if ticket is not None:
                    ticket.status = "approved"
                    ticket.reviewed_by = reviewed_by
                    ticket.reviewed_at = _utc_now()
                    ticket.review_reason = "管理员批准退款申请"
            self._execute_approved_refund(refund, order)
            self.db.commit()
            self.db.refresh(refund)
            return RefundOutcome(refund)
        except Exception as error:
            self.db.rollback()
            if isinstance(error, RefundServiceError):
                raise
            raise RefundServiceError("退款批准暂时无法处理，请稍后重试") from error

    def reject(
        self,
        *,
        tenant_id: int,
        refund_request_id: int,
        reason: str,
        reviewed_by: int | None = None,
    ) -> RefundOutcome:
        """管理员拒绝仍处于人工审核中的退款。"""
        refund = self._get_for_tenant(tenant_id, refund_request_id)
        if refund.status == "rejected":
            return RefundOutcome(refund, reused=True)
        if refund.status != "reviewing":
            raise RefundStateError(f"退款状态 {refund.status} 不允许拒绝")

        try:
            refund.status = "rejected"
            refund.failure_reason = reason.strip() or "管理员拒绝退款申请"
            if refund.ticket_id:
                ticket = self.db.query(Ticket).filter(
                    Ticket.id == refund.ticket_id,
                    Ticket.tenant_id == tenant_id,
                ).first()
                if ticket is not None:
                    ticket.status = "rejected"
                    ticket.reviewed_by = reviewed_by
                    ticket.reviewed_at = _utc_now()
                    ticket.review_reason = refund.failure_reason
            self.db.commit()
            self.db.refresh(refund)
            return RefundOutcome(refund)
        except Exception as error:
            self.db.rollback()
            raise RefundServiceError("退款拒绝操作暂时失败，请稍后重试") from error

    def get_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        refund_request_id: int,
    ) -> RefundRequest:
        refund = self.db.query(RefundRequest).filter(
            RefundRequest.id == refund_request_id,
            RefundRequest.tenant_id == tenant_id,
            RefundRequest.user_id == user_id,
        ).first()
        if refund is None:
            raise RefundNotFoundError("退款申请不存在")
        return refund

    def get_by_order_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        order_id: int,
    ) -> RefundRequest:
        refund = (
            self.db.query(RefundRequest)
            .filter(
                RefundRequest.tenant_id == tenant_id,
                RefundRequest.user_id == user_id,
                RefundRequest.order_id == order_id,
            )
            .order_by(RefundRequest.created_at.desc())
            .first()
        )
        if refund is None:
            raise RefundNotFoundError("该订单没有退款申请")
        return refund

    def _execute_approved_refund(
        self,
        refund: RefundRequest,
        order: Order,
    ) -> None:
        """只有渠道明确返回 succeeded 时才把订单标为已退款。"""
        try:
            result = self._get_gateway().execute(
                refund_request_id=refund.id,
                order_id=order.id,
                amount=Decimal(str(refund.amount)),
                idempotency_key=refund.idempotency_key,
            )
        except Exception:
            logger.exception(
                "退款渠道执行异常: refund_request_id=%s",
                refund.id,
            )
            refund.status = "failed"
            refund.failure_reason = "退款渠道调用异常"
            return

        if result.status == "succeeded":
            refund.status = "succeeded"
            refund.provider_refund_id = result.provider_refund_id
            refund.failure_reason = None
            order.status = "refunded"
        elif result.status == "pending":
            refund.status = "approved"
            refund.failure_reason = None
        else:
            refund.status = "failed"
            refund.failure_reason = result.error or "退款渠道处理失败"

    def _find_by_idempotency(
        self,
        tenant_id: int,
        idempotency_key: str,
    ) -> RefundRequest | None:
        return self.db.query(RefundRequest).filter(
            RefundRequest.tenant_id == tenant_id,
            RefundRequest.idempotency_key == idempotency_key,
        ).first()

    def _get_gateway(self) -> RefundGateway:
        if self.gateway is None:
            self.gateway = get_refund_gateway()
        return self.gateway

    def _get_for_tenant(
        self,
        tenant_id: int,
        refund_request_id: int,
    ) -> RefundRequest:
        refund = self.db.query(RefundRequest).filter(
            RefundRequest.id == refund_request_id,
            RefundRequest.tenant_id == tenant_id,
        ).first()
        if refund is None:
            raise RefundNotFoundError("退款申请不存在")
        return refund


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
