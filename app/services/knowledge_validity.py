"""知识版本有效期判断，供构建、检索和运营指标统一复用。"""

from datetime import UTC, datetime, timedelta


EXPIRING_SOON_DAYS = 7


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def lifecycle_status(
    *,
    effective_at: datetime | None,
    expires_at: datetime | None,
    now: datetime | None = None,
) -> str:
    current = now or utc_now()
    if effective_at is not None and effective_at > current:
        return "scheduled"
    if expires_at is not None and expires_at <= current:
        return "expired"
    if (
        expires_at is not None
        and expires_at <= current + timedelta(days=EXPIRING_SOON_DAYS)
    ):
        return "expiring_soon"
    return "active"


def is_effective(
    *,
    effective_at: datetime | None,
    expires_at: datetime | None,
    now: datetime | None = None,
) -> bool:
    return lifecycle_status(
        effective_at=effective_at,
        expires_at=expires_at,
        now=now,
    ) in {"active", "expiring_soon"}
