"""管理员租户级业务总览和列表查询。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import and_, distinct, func
from sqlalchemy.orm import Session, aliased

from app.models.agent_trace import AgentTrace
from app.models.order import Order
from app.models.product import Product
from app.models.refund_request import RefundRequest
from app.models.ticket import Ticket
from app.models.unresolved_case import UnresolvedCase
from app.models.user import User
from app.services.order_query_service import ORDER_STATUSES
from app.services.query_page import QueryPage, validate_pagination
from app.services.ticket_query_service import TICKET_STATUSES, TICKET_TYPES


class AdminQueryError(ValueError):
    pass


class AdminTicketNotFoundError(AdminQueryError):
    pass


@dataclass(frozen=True)
class AdminDashboardSummary:
    orders_total: int
    pending_refunds: int
    failed_refunds: int
    pending_tickets: int
    unresolved_cases: int
    today_sessions: int


@dataclass(frozen=True)
class AdminOrderSummary:
    order: Order
    username: str
    product_name: str
    refund_id: int | None
    refund_status: str | None
    ticket_count: int


@dataclass(frozen=True)
class AdminOrderDetail:
    order: Order
    user: User
    product: Product
    refund: RefundRequest | None
    tickets: list[Ticket]


@dataclass(frozen=True)
class AdminTicketSummary:
    ticket: Ticket
    username: str
    product_name: str
    refund_id: int | None
    refund_status: str | None
    reviewer_username: str | None


class AdminQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_dashboard(
        self,
        *,
        tenant_id: int,
        now: datetime | None = None,
    ) -> AdminDashboardSummary:
        day_start, day_end = _shanghai_day_utc_bounds(now)
        return AdminDashboardSummary(
            orders_total=self._count(Order, tenant_id=tenant_id),
            pending_refunds=self._count(
                RefundRequest,
                tenant_id=tenant_id,
                status="reviewing",
            ),
            failed_refunds=self._count(
                RefundRequest,
                tenant_id=tenant_id,
                status="failed",
            ),
            pending_tickets=self._count(
                Ticket,
                tenant_id=tenant_id,
                status="pending",
            ),
            unresolved_cases=(
                self.db.query(func.count(UnresolvedCase.id))
                .filter(
                    UnresolvedCase.tenant_id == tenant_id,
                    UnresolvedCase.is_resolved.is_(False),
                )
                .scalar()
                or 0
            ),
            today_sessions=(
                self.db.query(func.count(distinct(AgentTrace.session_id)))
                .filter(
                    AgentTrace.tenant_id == tenant_id,
                    AgentTrace.created_at >= day_start,
                    AgentTrace.created_at < day_end,
                )
                .scalar()
                or 0
            ),
        )

    def _count(
        self,
        model,
        *,
        tenant_id: int,
        status: str | None = None,
    ) -> int:
        query = self.db.query(func.count(model.id)).filter(
            model.tenant_id == tenant_id,
        )
        if status is not None:
            query = query.filter(model.status == status)
        return query.scalar() or 0

    def list_orders(
        self,
        *,
        tenant_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[AdminOrderSummary]:
        validate_pagination(page=page, page_size=page_size)
        if status is not None and status not in ORDER_STATUSES:
            raise AdminQueryError("订单状态无效")

        ticket_counts = (
            self.db.query(
                Ticket.tenant_id.label("tenant_id"),
                Ticket.order_id.label("order_id"),
                func.count(Ticket.id).label("ticket_count"),
            )
            .group_by(Ticket.tenant_id, Ticket.order_id)
            .subquery()
        )
        query = (
            self.db.query(
                Order,
                User.username.label("username"),
                Product.name.label("product_name"),
                RefundRequest.id.label("refund_id"),
                RefundRequest.status.label("refund_status"),
                func.coalesce(ticket_counts.c.ticket_count, 0).label(
                    "ticket_count"
                ),
            )
            .join(
                User,
                and_(
                    User.id == Order.user_id,
                    User.tenant_id == Order.tenant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.id == Order.product_id,
                    Product.tenant_id == Order.tenant_id,
                ),
            )
            .outerjoin(
                RefundRequest,
                and_(
                    RefundRequest.order_id == Order.id,
                    RefundRequest.tenant_id == Order.tenant_id,
                ),
            )
            .outerjoin(
                ticket_counts,
                and_(
                    ticket_counts.c.order_id == Order.id,
                    ticket_counts.c.tenant_id == Order.tenant_id,
                ),
            )
            .filter(Order.tenant_id == tenant_id)
        )
        if status is not None:
            query = query.filter(Order.status == status)

        total = query.count()
        rows = (
            query.order_by(Order.created_at.desc(), Order.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=[
                AdminOrderSummary(
                    order=row[0],
                    username=row[1],
                    product_name=row[2],
                    refund_id=row[3],
                    refund_status=row[4],
                    ticket_count=int(row[5]),
                )
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_order(
        self,
        *,
        tenant_id: int,
        order_id: int,
    ) -> AdminOrderDetail:
        row = (
            self.db.query(Order, User, Product, RefundRequest)
            .join(
                User,
                and_(
                    User.id == Order.user_id,
                    User.tenant_id == Order.tenant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.id == Order.product_id,
                    Product.tenant_id == Order.tenant_id,
                ),
            )
            .outerjoin(
                RefundRequest,
                and_(
                    RefundRequest.order_id == Order.id,
                    RefundRequest.tenant_id == Order.tenant_id,
                ),
            )
            .filter(
                Order.id == order_id,
                Order.tenant_id == tenant_id,
            )
            .first()
        )
        if row is None:
            raise AdminQueryError("订单不存在")
        tickets = (
            self.db.query(Ticket)
            .filter(
                Ticket.order_id == order_id,
                Ticket.tenant_id == tenant_id,
            )
            .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .all()
        )
        return AdminOrderDetail(
            order=row[0],
            user=row[1],
            product=row[2],
            refund=row[3],
            tickets=tickets,
        )

    def list_traces(
        self,
        *,
        tenant_id: int,
        session_id: str | None,
        intent: str | None,
        status: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[AgentTrace]:
        validate_pagination(page=page, page_size=page_size)
        query = self.db.query(AgentTrace).filter(
            AgentTrace.tenant_id == tenant_id,
        )
        if session_id:
            query = query.filter(AgentTrace.session_id == session_id)
        if intent:
            query = query.filter(AgentTrace.intent == intent)
        if status:
            query = query.filter(AgentTrace.status == status)

        total = query.count()
        traces = (
            query.order_by(AgentTrace.created_at.desc(), AgentTrace.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=traces,
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_trace(
        self,
        *,
        tenant_id: int,
        trace_id: int,
    ) -> AgentTrace:
        trace = self.db.query(AgentTrace).filter(
            AgentTrace.id == trace_id,
            AgentTrace.tenant_id == tenant_id,
        ).first()
        if trace is None:
            raise AdminQueryError("Trace不存在")
        return trace

    def list_trace_session(
        self,
        *,
        tenant_id: int,
        session_id: str,
    ) -> list[AgentTrace]:
        return (
            self.db.query(AgentTrace)
            .filter(
                AgentTrace.tenant_id == tenant_id,
                AgentTrace.session_id == session_id,
            )
            .order_by(AgentTrace.created_at, AgentTrace.id)
            .all()
        )

    def list_tickets(
        self,
        *,
        tenant_id: int,
        status: str | None,
        ticket_type: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[AdminTicketSummary]:
        validate_pagination(page=page, page_size=page_size)
        if status is not None and status not in TICKET_STATUSES:
            raise AdminQueryError("工单状态无效")
        if ticket_type is not None and ticket_type not in TICKET_TYPES:
            raise AdminQueryError("工单类型无效")

        query = self._ticket_query().filter(Ticket.tenant_id == tenant_id)
        if status is not None:
            query = query.filter(Ticket.status == status)
        if ticket_type is not None:
            query = query.filter(Ticket.type == ticket_type)

        total = query.count()
        rows = (
            query.order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=[self._ticket_summary(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_ticket(
        self,
        *,
        tenant_id: int,
        ticket_id: int,
    ) -> AdminTicketSummary:
        row = self._ticket_query().filter(
            Ticket.id == ticket_id,
            Ticket.tenant_id == tenant_id,
        ).first()
        if row is None:
            raise AdminTicketNotFoundError("工单不存在")
        return self._ticket_summary(row)

    def list_unresolved_cases(
        self,
        *,
        tenant_id: int,
        is_resolved: bool | None,
        page: int,
        page_size: int,
    ) -> QueryPage[UnresolvedCase]:
        validate_pagination(page=page, page_size=page_size)
        query = self.db.query(UnresolvedCase).filter(
            UnresolvedCase.tenant_id == tenant_id,
        )
        if is_resolved is not None:
            query = query.filter(UnresolvedCase.is_resolved.is_(is_resolved))

        total = query.count()
        cases = (
            query.order_by(UnresolvedCase.created_at.desc(), UnresolvedCase.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=cases,
            total=total,
            page=page,
            page_size=page_size,
        )

    def _ticket_query(self):
        reviewer = aliased(User)
        return (
            self.db.query(
                Ticket,
                User.username.label("username"),
                Product.name.label("product_name"),
                RefundRequest.id.label("refund_id"),
                RefundRequest.status.label("refund_status"),
                reviewer.username.label("reviewer_username"),
            )
            .join(
                User,
                and_(
                    User.id == Ticket.user_id,
                    User.tenant_id == Ticket.tenant_id,
                ),
            )
            .join(
                Order,
                and_(
                    Order.id == Ticket.order_id,
                    Order.tenant_id == Ticket.tenant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.id == Order.product_id,
                    Product.tenant_id == Ticket.tenant_id,
                ),
            )
            .outerjoin(
                RefundRequest,
                and_(
                    RefundRequest.ticket_id == Ticket.id,
                    RefundRequest.tenant_id == Ticket.tenant_id,
                ),
            )
            .outerjoin(
                reviewer,
                and_(
                    reviewer.id == Ticket.reviewed_by,
                    reviewer.tenant_id == Ticket.tenant_id,
                ),
            )
        )

    @staticmethod
    def _ticket_summary(row) -> AdminTicketSummary:
        return AdminTicketSummary(
            ticket=row[0],
            username=row[1],
            product_name=row[2],
            refund_id=row[3],
            refund_status=row[4],
            reviewer_username=row[5],
        )


def _shanghai_day_utc_bounds(
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    shanghai_timezone = timezone(timedelta(hours=8))
    current = now or datetime.now(shanghai_timezone)
    if current.tzinfo is None:
        current = current.replace(tzinfo=shanghai_timezone)
    else:
        current = current.astimezone(shanghai_timezone)
    local_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        local_end.astimezone(UTC).replace(tzinfo=None),
    )
