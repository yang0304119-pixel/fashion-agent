"""未解决案例人工标注与知识库候选队列服务。"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session, aliased

from app.models.unresolved_case import UnresolvedCase
from app.models.user import User
from app.services.query_page import QueryPage, validate_pagination


SUPPORTED_INTENTS = frozenset(
    {
        "knowledge_query",
        "order_query",
        "inventory_query",
        "size_recommend",
        "refund_request",
        "composite_query",
        "fallback",
    }
)


class UnresolvedCaseError(ValueError):
    pass


class UnresolvedCaseNotFoundError(UnresolvedCaseError):
    pass


class UnresolvedCaseValidationError(UnresolvedCaseError):
    pass


@dataclass(frozen=True)
class UnresolvedCaseSummary:
    case: UnresolvedCase
    reviewer_username: str | None


@dataclass(frozen=True)
class UnresolvedCaseStats:
    pending: int
    resolved: int
    knowledge_candidates: int


class UnresolvedCaseService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_tenant(
        self,
        *,
        tenant_id: int,
        is_resolved: bool | None,
        predicted_intent: str | None,
        should_add_to_kb: bool | None,
        page: int,
        page_size: int,
    ) -> QueryPage[UnresolvedCaseSummary]:
        validate_pagination(page=page, page_size=page_size)
        if predicted_intent and predicted_intent not in SUPPORTED_INTENTS:
            raise UnresolvedCaseValidationError("预测意图筛选值无效")

        query = self._query().filter(UnresolvedCase.tenant_id == tenant_id)
        if is_resolved is not None:
            if is_resolved:
                query = query.filter(UnresolvedCase.is_resolved.is_(True))
            else:
                query = query.filter(
                    UnresolvedCase.is_resolved.is_not(True)
                )
        if predicted_intent:
            query = query.filter(UnresolvedCase.predicted_intent == predicted_intent)
        if should_add_to_kb is not None:
            if should_add_to_kb:
                query = query.filter(
                    UnresolvedCase.should_add_to_kb.is_(True)
                )
            else:
                query = query.filter(
                    UnresolvedCase.should_add_to_kb.is_not(True)
                )

        total = query.count()
        rows = (
            query.order_by(
                UnresolvedCase.created_at.desc(),
                UnresolvedCase.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=[self._summary(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_for_tenant(
        self,
        *,
        tenant_id: int,
        case_id: int,
    ) -> UnresolvedCaseSummary:
        row = self._query().filter(
            UnresolvedCase.id == case_id,
            UnresolvedCase.tenant_id == tenant_id,
        ).first()
        if row is None:
            raise UnresolvedCaseNotFoundError("未解决案例不存在")
        return self._summary(row)

    def stats_for_tenant(self, *, tenant_id: int) -> UnresolvedCaseStats:
        pending, resolved, knowledge_candidates = self.db.query(
            func.sum(
                case((UnresolvedCase.is_resolved.is_not(True), 1), else_=0)
            ),
            func.sum(
                case((UnresolvedCase.is_resolved.is_(True), 1), else_=0)
            ),
            func.sum(
                case(
                    (UnresolvedCase.should_add_to_kb.is_(True), 1),
                    else_=0,
                )
            ),
        ).filter(UnresolvedCase.tenant_id == tenant_id).one()
        return UnresolvedCaseStats(
            pending=int(pending or 0),
            resolved=int(resolved or 0),
            knowledge_candidates=int(knowledge_candidates or 0),
        )

    def update_annotation(
        self,
        *,
        tenant_id: int,
        case_id: int,
        reviewed_by: int,
        changes: dict,
    ) -> UnresolvedCaseSummary:
        case = self.db.query(UnresolvedCase).filter(
            UnresolvedCase.id == case_id,
            UnresolvedCase.tenant_id == tenant_id,
        ).first()
        if case is None:
            raise UnresolvedCaseNotFoundError("未解决案例不存在")

        intent = _normalized_text(
            changes.get("human_label_intent", case.human_label_intent)
        )
        answer = _normalized_text(
            changes.get("human_label_answer", case.human_label_answer)
        )
        is_resolved = changes.get("is_resolved", bool(case.is_resolved))
        should_add = changes.get(
            "should_add_to_kb",
            bool(case.should_add_to_kb),
        )

        if intent is not None and intent not in SUPPORTED_INTENTS:
            raise UnresolvedCaseValidationError("人工意图标注无效")
        if is_resolved and not answer:
            raise UnresolvedCaseValidationError("标记已处理时必须填写人工答案")
        if should_add and not answer:
            raise UnresolvedCaseValidationError("加入知识库候选时必须填写人工答案")

        case.human_label_intent = intent
        case.human_label_answer = answer
        case.is_resolved = bool(is_resolved)
        case.should_add_to_kb = bool(should_add)
        case.reviewed_by = reviewed_by
        case.reviewed_at = _utc_now()
        case.updated_at = case.reviewed_at
        self.db.commit()
        return self.get_for_tenant(tenant_id=tenant_id, case_id=case_id)

    def _query(self):
        reviewer = aliased(User)
        return (
            self.db.query(
                UnresolvedCase,
                reviewer.username.label("reviewer_username"),
            )
            .outerjoin(
                reviewer,
                and_(
                    reviewer.id == UnresolvedCase.reviewed_by,
                    reviewer.tenant_id == UnresolvedCase.tenant_id,
                ),
            )
        )

    @staticmethod
    def _summary(row) -> UnresolvedCaseSummary:
        return UnresolvedCaseSummary(
            case=row[0],
            reviewer_username=row[1],
        )


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
