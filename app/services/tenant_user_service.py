"""租户员工账号管理，所有操作均限制在操作者所属租户。"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.passwords import hash_password
from app.core.permissions import ASSIGNABLE_STAFF_ROLES, TENANT_ADMIN
from app.models.user import User
from app.services.admin_audit_service import AdminAuditService


class TenantUserError(ValueError):
    pass


class TenantUserNotFoundError(TenantUserError):
    pass


class TenantUserConflictError(TenantUserError):
    pass


class TenantUserService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_staff(self, *, tenant_id: int) -> list[User]:
        return (
            self.db.query(User)
            .filter(User.tenant_id == tenant_id, User.role.in_(ASSIGNABLE_STAFF_ROLES))
            .order_by(User.is_active.desc(), User.created_at, User.id)
            .all()
        )

    def create_staff(
        self,
        *,
        actor: User,
        username: str,
        password: str,
        role: str,
        ip_address: str | None,
    ) -> User:
        self._validate_role(role)
        normalized = username.strip()
        if not normalized:
            raise TenantUserError("用户名不能为空")
        row = User(
            tenant_id=actor.tenant_id,
            username=normalized,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        self.db.add(row)
        try:
            self.db.flush()
            AdminAuditService(self.db).record(
                actor=actor,
                action="staff_user.created",
                target_type="user",
                target_id=row.id,
                after_data=self._snapshot(row),
                ip_address=ip_address,
            )
            self.db.commit()
            self.db.refresh(row)
            return row
        except IntegrityError as error:
            self.db.rollback()
            raise TenantUserConflictError("当前租户已存在该用户名") from error

    def update_staff(
        self,
        *,
        actor: User,
        user_id: int,
        username: str | None,
        role: str | None,
        is_active: bool | None,
        reason: str | None,
        ip_address: str | None,
    ) -> User:
        row = self._get(actor.tenant_id, user_id)
        before = self._snapshot(row)
        if row.id == actor.id and (
            (role is not None and role != row.role)
            or is_active is False
        ):
            raise TenantUserError("不能修改自己的角色或停用自己的账号")
        target_role = role or row.role
        self._validate_role(target_role)
        target_active = row.is_active if is_active is None else is_active
        if row.role == TENANT_ADMIN and (
            target_role != TENANT_ADMIN or not target_active
        ):
            self._ensure_another_admin(actor.tenant_id, row.id)
        if username is not None:
            normalized = username.strip()
            if not normalized:
                raise TenantUserError("用户名不能为空")
            row.username = normalized
        row.role = target_role
        row.is_active = target_active
        try:
            self.db.flush()
            AdminAuditService(self.db).record(
                actor=actor,
                action="staff_user.updated",
                target_type="user",
                target_id=row.id,
                before_data=before,
                after_data=self._snapshot(row),
                reason=reason,
                ip_address=ip_address,
            )
            self.db.commit()
            self.db.refresh(row)
            return row
        except IntegrityError as error:
            self.db.rollback()
            raise TenantUserConflictError("当前租户已存在该用户名") from error

    def reset_password(
        self,
        *,
        actor: User,
        user_id: int,
        password: str,
        ip_address: str | None,
    ) -> User:
        row = self._get(actor.tenant_id, user_id)
        row.password_hash = hash_password(password)
        AdminAuditService(self.db).record(
            actor=actor,
            action="staff_user.password_reset",
            target_type="user",
            target_id=row.id,
            ip_address=ip_address,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _get(self, tenant_id: int, user_id: int) -> User:
        row = self.db.query(User).filter(
            User.id == user_id,
            User.tenant_id == tenant_id,
            User.role.in_(ASSIGNABLE_STAFF_ROLES),
        ).first()
        if row is None:
            raise TenantUserNotFoundError("员工账号不存在")
        return row

    def _ensure_another_admin(self, tenant_id: int, excluded_user_id: int) -> None:
        exists = self.db.query(User.id).filter(
            User.tenant_id == tenant_id,
            User.role == TENANT_ADMIN,
            User.is_active.is_(True),
            User.id != excluded_user_id,
        ).first()
        if exists is None:
            raise TenantUserError("不能停用或降级当前租户最后一个管理员")

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in ASSIGNABLE_STAFF_ROLES:
            raise TenantUserError("员工角色无效")

    @staticmethod
    def _snapshot(row: User) -> dict:
        return {
            "id": row.id,
            "username": row.username,
            "role": row.role,
            "is_active": bool(row.is_active),
        }
