"""人工管理操作审计。"""

from typing import Any

from sqlalchemy.orm import Session

from app.models.admin_audit_event import AdminAuditEvent
from app.models.user import User


class AdminAuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        actor: User,
        action: str,
        target_type: str,
        target_id: str | int | None = None,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
        reason: str | None = None,
        ip_address: str | None = None,
        commit: bool = False,
    ) -> AdminAuditEvent:
        event = AdminAuditEvent(
            tenant_id=actor.tenant_id,
            actor_user_id=actor.id,
            actor_role=actor.role,
            action=action[:100],
            target_type=target_type[:50],
            target_id=str(target_id)[:100] if target_id is not None else None,
            before_data=before_data,
            after_data=after_data,
            reason=(reason or "")[:500] or None,
            ip_address=(ip_address or "")[:64] or None,
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    def list_for_tenant(
        self,
        *,
        tenant_id: int,
        action: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[AdminAuditEvent], int]:
        query = self.db.query(AdminAuditEvent).filter(
            AdminAuditEvent.tenant_id == tenant_id
        )
        if action:
            query = query.filter(AdminAuditEvent.action == action)
        total = query.count()
        rows = (
            query.order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return rows, total
