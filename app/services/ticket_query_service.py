"""客户和管理员工单列表查询服务。"""

from sqlalchemy.orm import Session

from app.models.ticket import Ticket
from app.services.query_page import QueryPage, validate_pagination


TICKET_STATUSES = frozenset({"pending", "approved", "rejected"})
TICKET_TYPES = frozenset({"refund", "exchange"})


class TicketQueryError(ValueError):
    pass


class TicketQueryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_user(
        self,
        *,
        tenant_id: int,
        user_id: int,
        status: str | None,
        ticket_type: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[Ticket]:
        return self._list(
            tenant_id=tenant_id,
            user_id=user_id,
            status=status,
            ticket_type=ticket_type,
            page=page,
            page_size=page_size,
        )

    def list_for_tenant(
        self,
        *,
        tenant_id: int,
        status: str | None,
        ticket_type: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[Ticket]:
        return self._list(
            tenant_id=tenant_id,
            user_id=None,
            status=status,
            ticket_type=ticket_type,
            page=page,
            page_size=page_size,
        )

    def _list(
        self,
        *,
        tenant_id: int,
        user_id: int | None,
        status: str | None,
        ticket_type: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[Ticket]:
        validate_pagination(page=page, page_size=page_size)
        if status is not None and status not in TICKET_STATUSES:
            raise TicketQueryError("工单状态无效")
        if ticket_type is not None and ticket_type not in TICKET_TYPES:
            raise TicketQueryError("工单类型无效")

        query = self.db.query(Ticket).filter(Ticket.tenant_id == tenant_id)
        if user_id is not None:
            query = query.filter(Ticket.user_id == user_id)
        if status is not None:
            query = query.filter(Ticket.status == status)
        if ticket_type is not None:
            query = query.filter(Ticket.type == ticket_type)

        total = query.count()
        tickets = (
            query.order_by(Ticket.created_at.desc(), Ticket.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=tickets,
            total=total,
            page=page,
            page_size=page_size,
        )

