"""商家员工角色与权限矩阵。权限由服务端计算，前端仅用于展示。"""

from __future__ import annotations


CUSTOMER = "customer"
CUSTOMER_SERVICE = "customer_service"
SUPERVISOR = "supervisor"
TENANT_ADMIN = "tenant_admin"
DEVELOPER = "developer"
LEGACY_ADMIN = "admin"

STAFF_ROLES = frozenset({CUSTOMER_SERVICE, SUPERVISOR, TENANT_ADMIN, DEVELOPER})
ALLOWED_ROLES = frozenset({CUSTOMER, *STAFF_ROLES, LEGACY_ADMIN})
ASSIGNABLE_STAFF_ROLES = frozenset({CUSTOMER_SERVICE, SUPERVISOR, TENANT_ADMIN, DEVELOPER})

_CUSTOMER_SERVICE_PERMISSIONS = {
    "workbench.read",
    "work_item.handle",
    "order.read",
    "ticket.read",
    "case.handle",
    "knowledge.draft",
    "knowledge.test",
}
_SUPERVISOR_PERMISSIONS = _CUSTOMER_SERVICE_PERMISSIONS | {
    "refund.review",
    "knowledge.review",
    "knowledge.publish",
    "quality.business.read",
}
_TENANT_ADMIN_PERMISSIONS = _SUPERVISOR_PERMISSIONS | {
    "user.manage",
    "role.manage",
    "tenant.settings",
    "audit.read",
    "boundary.summary.read",
}
_DEVELOPER_PERMISSIONS = {
    "knowledge.test",
    "quality.business.read",
    "agent.trace.read",
    "rag.diagnostics.read",
    "tool.diagnostics.read",
    "memory.diagnostics.read",
    "boundary.diagnostics.read",
    "system.health.read",
    "audit.read",
}

PERMISSIONS_BY_ROLE = {
    CUSTOMER: frozenset(),
    CUSTOMER_SERVICE: frozenset(_CUSTOMER_SERVICE_PERMISSIONS),
    SUPERVISOR: frozenset(_SUPERVISOR_PERMISSIONS),
    TENANT_ADMIN: frozenset(_TENANT_ADMIN_PERMISSIONS),
    DEVELOPER: frozenset(_DEVELOPER_PERMISSIONS),
    # 仅用于迁移窗口；数据库迁移会把旧admin更新成tenant_admin。
    LEGACY_ADMIN: frozenset(_TENANT_ADMIN_PERMISSIONS | _DEVELOPER_PERMISSIONS),
}

ROLE_LABELS = {
    CUSTOMER: "消费者",
    CUSTOMER_SERVICE: "客服运营",
    SUPERVISOR: "客服主管",
    TENANT_ADMIN: "租户管理员",
    DEVELOPER: "开发人员",
    LEGACY_ADMIN: "租户管理员",
}

HOME_VIEW_BY_ROLE = {
    CUSTOMER_SERVICE: "dashboard",
    SUPERVISOR: "dashboard",
    TENANT_ADMIN: "users",
    DEVELOPER: "traces",
    LEGACY_ADMIN: "users",
}


def normalize_role(role: str) -> str:
    return TENANT_ADMIN if role == LEGACY_ADMIN else role


def permissions_for_role(role: str) -> frozenset[str]:
    return PERMISSIONS_BY_ROLE.get(role, frozenset())


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


def home_view_for_role(role: str) -> str:
    return HOME_VIEW_BY_ROLE.get(role, "workbench")
