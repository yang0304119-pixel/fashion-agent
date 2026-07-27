from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.core.permissions import role_label
from app.dependencies import get_db, require_permission
from app.models.user import User
from app.schemas.tenant_user import (
    AuditEventItem,
    AuditEventListResponse,
    StaffPasswordResetRequest,
    StaffUserCreateRequest,
    StaffUserItem,
    StaffUserListResponse,
    StaffUserResponse,
    StaffUserUpdateRequest,
    TenantSettingsData,
    TenantSettingsResponse,
    TenantSettingsUpdateRequest,
)
from app.services.admin_audit_service import AdminAuditService
from app.services.tenant_user_service import (
    TenantUserConflictError,
    TenantUserError,
    TenantUserNotFoundError,
    TenantUserService,
)
from app.models.tenant import Tenant
from app.core.config import settings


router = APIRouter(prefix="/admin", tags=["tenant-users"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _item(row: User) -> StaffUserItem:
    return StaffUserItem(
        id=row.id,
        username=row.username,
        role=row.role,
        role_label=role_label(row.role),
        is_active=bool(row.is_active),
        created_at=row.created_at,
    )


@router.get("/users", response_model=StaffUserListResponse)
def list_staff_users(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("user.manage")),
) -> StaffUserListResponse:
    return StaffUserListResponse(
        data=[_item(row) for row in TenantUserService(db).list_staff(tenant_id=actor.tenant_id)]
    )


@router.post("/users", response_model=StaffUserResponse)
def create_staff_user(
    payload: StaffUserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("user.manage")),
) -> StaffUserResponse:
    try:
        row = TenantUserService(db).create_staff(
            actor=actor,
            username=payload.username,
            password=payload.password,
            role=payload.role,
            ip_address=_ip(request),
        )
    except TenantUserConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TenantUserError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return StaffUserResponse(data=_item(row))


@router.patch("/users/{user_id}", response_model=StaffUserResponse)
def update_staff_user(
    user_id: int,
    payload: StaffUserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("user.manage")),
) -> StaffUserResponse:
    try:
        row = TenantUserService(db).update_staff(
            actor=actor,
            user_id=user_id,
            username=payload.username,
            role=payload.role,
            is_active=payload.is_active,
            reason=payload.reason,
            ip_address=_ip(request),
        )
    except TenantUserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except TenantUserConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except TenantUserError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return StaffUserResponse(data=_item(row))


@router.post("/users/{user_id}/reset-password", response_model=StaffUserResponse)
def reset_staff_password(
    user_id: int,
    payload: StaffPasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("user.manage")),
) -> StaffUserResponse:
    try:
        row = TenantUserService(db).reset_password(
            actor=actor,
            user_id=user_id,
            password=payload.password,
            ip_address=_ip(request),
        )
    except TenantUserNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return StaffUserResponse(data=_item(row))


@router.get("/audit-events", response_model=AuditEventListResponse)
def list_audit_events(
    action: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("audit.read")),
) -> AuditEventListResponse:
    rows, total = AdminAuditService(db).list_for_tenant(
        tenant_id=actor.tenant_id,
        action=action,
        page=page,
        page_size=page_size,
    )
    return AuditEventListResponse(
        data=[
            AuditEventItem(
                id=row.id,
                actor_user_id=row.actor_user_id,
                actor_role=row.actor_role,
                action=row.action,
                target_type=row.target_type,
                target_id=row.target_id,
                before_data=row.before_data,
                after_data=row.after_data,
                reason=row.reason,
                ip_address=row.ip_address,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


def _tenant_settings(tenant: Tenant) -> TenantSettingsData:
    config = dict(tenant.theme_config or {})
    return TenantSettingsData(
        tenant_id=tenant.id,
        name=tenant.name,
        industry=tenant.industry,
        contact=tenant.contact,
        refund_auto_limit=config.get("refund_auto_limit", settings.REFUND_AUTO_LIMIT),
    )


@router.get("/tenant-settings", response_model=TenantSettingsResponse)
def get_tenant_settings(
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("tenant.settings")),
) -> TenantSettingsResponse:
    tenant = db.get(Tenant, actor.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    return TenantSettingsResponse(data=_tenant_settings(tenant))


@router.patch("/tenant-settings", response_model=TenantSettingsResponse)
def update_tenant_settings(
    payload: TenantSettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    actor: User = Depends(require_permission("tenant.settings")),
) -> TenantSettingsResponse:
    tenant = db.get(Tenant, actor.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="租户不存在")
    before = _tenant_settings(tenant).model_dump(mode="json")
    if payload.name is not None:
        tenant.name = payload.name.strip()
    if payload.contact is not None:
        tenant.contact = payload.contact.strip() or None
    config = dict(tenant.theme_config or {})
    if payload.refund_auto_limit is not None:
        config["refund_auto_limit"] = str(payload.refund_auto_limit)
    tenant.theme_config = config
    after = _tenant_settings(tenant).model_dump(mode="json")
    AdminAuditService(db).record(
        actor=actor,
        action="tenant.settings_updated",
        target_type="tenant",
        target_id=tenant.id,
        before_data=before,
        after_data=after,
        ip_address=_ip(request),
    )
    db.commit()
    db.refresh(tenant)
    return TenantSettingsResponse(data=_tenant_settings(tenant))
