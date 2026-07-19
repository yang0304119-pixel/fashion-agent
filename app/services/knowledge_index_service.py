"""租户候选知识库构建、激活和回滚服务。"""

import logging
from datetime import UTC, datetime
from hashlib import sha256

from langchain_core.documents import Document
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeIndexBuild,
    KnowledgeRevision,
)
from app.models.unresolved_case import UnresolvedCase
from app.rag.security import sanitize_document_content
from app.rag.text_splitter import split_knowledge_documents
from app.rag.vector_store import (
    build_vector_store_collection,
    delete_vector_store_collection,
    open_vector_store_by_name,
    tenant_build_collection_name,
)
from app.services.knowledge_storage import KnowledgeStorage
from app.services.knowledge_validity import is_effective, utc_now
from app.services.query_page import QueryPage, validate_pagination


logger = logging.getLogger(__name__)
BUILD_STATUSES = frozenset({
    "building",
    "ready",
    "active",
    "failed",
    "superseded",
})


class KnowledgeIndexError(RuntimeError):
    pass


class KnowledgeIndexNotFoundError(KnowledgeIndexError):
    pass


class KnowledgeIndexStateError(KnowledgeIndexError):
    pass


class KnowledgeIndexBuildError(KnowledgeIndexError):
    pass


class KnowledgeIndexService:
    def __init__(
        self,
        db: Session,
        *,
        storage: KnowledgeStorage | None = None,
    ) -> None:
        self.db = db
        self.storage = storage or KnowledgeStorage()

    def list_for_tenant(
        self,
        *,
        tenant_id: int,
        status: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[KnowledgeIndexBuild]:
        validate_pagination(page=page, page_size=page_size)
        if status and status not in BUILD_STATUSES:
            raise KnowledgeIndexStateError("知识库构建状态筛选值无效")
        query = self.db.query(KnowledgeIndexBuild).filter(
            KnowledgeIndexBuild.tenant_id == tenant_id
        )
        if status:
            query = query.filter(KnowledgeIndexBuild.status == status)
        total = query.count()
        items = (
            query.order_by(
                KnowledgeIndexBuild.created_at.desc(),
                KnowledgeIndexBuild.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return QueryPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_for_tenant(
        self,
        *,
        tenant_id: int,
        build_id: int,
    ) -> KnowledgeIndexBuild:
        build = self.db.query(KnowledgeIndexBuild).filter(
            KnowledgeIndexBuild.id == build_id,
            KnowledgeIndexBuild.tenant_id == tenant_id,
        ).first()
        if build is None:
            raise KnowledgeIndexNotFoundError("知识库构建不存在")
        return build

    def get_active_for_tenant(
        self,
        *,
        tenant_id: int,
    ) -> KnowledgeIndexBuild:
        build = self.db.query(KnowledgeIndexBuild).filter(
            KnowledgeIndexBuild.tenant_id == tenant_id,
            KnowledgeIndexBuild.status == "active",
        ).order_by(
            KnowledgeIndexBuild.activated_at.desc(),
            KnowledgeIndexBuild.id.desc(),
        ).first()
        if build is None:
            raise KnowledgeIndexNotFoundError("当前租户尚未上线知识库")
        return build

    def resolve_read_build(
        self,
        *,
        tenant_id: int,
        build_id: int | None,
    ) -> KnowledgeIndexBuild:
        if build_id is None:
            return self.get_active_for_tenant(tenant_id=tenant_id)
        build = self.get_for_tenant(
            tenant_id=tenant_id,
            build_id=build_id,
        )
        if build.status not in {"ready", "active", "superseded"}:
            raise KnowledgeIndexStateError("该知识库版本尚不可查询")
        if not build.collection_name:
            raise KnowledgeIndexStateError("知识库版本缺少集合信息")
        return build

    def create_candidate(
        self,
        *,
        tenant_id: int,
        triggered_by: int,
    ) -> KnowledgeIndexBuild:
        existing = self.db.query(KnowledgeIndexBuild.id).filter(
            KnowledgeIndexBuild.tenant_id == tenant_id,
            KnowledgeIndexBuild.status == "building",
        ).first()
        if existing is not None:
            raise KnowledgeIndexStateError("当前租户已有知识库正在构建")

        revisions = self._latest_approved_revisions(tenant_id=tenant_id)
        if not revisions:
            raise KnowledgeIndexStateError("没有已审核通过的知识版本可构建")

        active = self.db.query(KnowledgeIndexBuild).filter(
            KnowledgeIndexBuild.tenant_id == tenant_id,
            KnowledgeIndexBuild.status == "active",
        ).order_by(KnowledgeIndexBuild.id.desc()).first()
        now = _utc_now()
        build = KnowledgeIndexBuild(
            tenant_id=tenant_id,
            status="building",
            revision_snapshot=[revision.id for revision in revisions],
            document_count=len(revisions),
            chunk_count=0,
            triggered_by=triggered_by,
            previous_active_build_id=active.id if active else None,
            started_at=now,
        )
        self.db.add(build)
        self.db.commit()
        self.db.refresh(build)
        collection_name = tenant_build_collection_name(
            tenant_id=tenant_id,
            build_id=build.id,
        )
        build.collection_name = collection_name
        self.db.commit()

        try:
            documents = [
                self._revision_document(
                    tenant_id=tenant_id,
                    revision=revision,
                    build_id=build.id,
                )
                for revision in revisions
            ]
            chunks = split_knowledge_documents(documents)
            if not chunks:
                raise ValueError("审核知识没有生成有效 chunk")
            build_vector_store_collection(
                chunks,
                collection_name=collection_name,
            )
            build.status = "ready"
            build.chunk_count = len(chunks)
            build.finished_at = _utc_now()
            build.error_code = None
            build.error_message = None
            self.db.commit()
            self.db.refresh(build)
            return build
        except Exception as error:
            logger.exception(
                "租户候选知识库构建失败: tenant_id=%s build_id=%s",
                tenant_id,
                build.id,
            )
            try:
                delete_vector_store_collection(collection_name)
            except Exception:
                logger.warning(
                    "失败候选集合清理失败: %s",
                    collection_name,
                    exc_info=True,
                )
            build.status = "failed"
            build.chunk_count = 0
            build.finished_at = _utc_now()
            build.error_code = _build_error_code(error)
            build.error_message = _build_error_message(error)
            self.db.commit()
            raise KnowledgeIndexBuildError(build.error_message) from error

    def activate(
        self,
        *,
        tenant_id: int,
        build_id: int,
    ) -> KnowledgeIndexBuild:
        build = self.get_for_tenant(
            tenant_id=tenant_id,
            build_id=build_id,
        )
        if build.status != "ready":
            raise KnowledgeIndexStateError("只有构建成功的候选版本可以上线")
        if not build.collection_name:
            raise KnowledgeIndexStateError("候选版本缺少 Chroma 集合")
        open_vector_store_by_name(build.collection_name)

        now = _utc_now()
        current = self.db.query(KnowledgeIndexBuild).filter(
            KnowledgeIndexBuild.tenant_id == tenant_id,
            KnowledgeIndexBuild.status == "active",
        ).with_for_update().first()
        build.previous_active_build_id = current.id if current else None
        if current is not None:
            current.status = "superseded"
        build.status = "active"
        build.activated_at = now
        self._close_linked_cases(build=build, now=now)
        self.db.commit()
        self.db.refresh(build)
        return build

    def rollback(
        self,
        *,
        tenant_id: int,
        target_build_id: int | None = None,
    ) -> KnowledgeIndexBuild:
        current = self.get_active_for_tenant(tenant_id=tenant_id)
        target_id = target_build_id or current.previous_active_build_id
        if target_id is None:
            raise KnowledgeIndexStateError("当前知识库没有可回滚的上一版本")
        target = self.get_for_tenant(
            tenant_id=tenant_id,
            build_id=target_id,
        )
        if target.status != "superseded":
            raise KnowledgeIndexStateError("目标版本不是可回滚的历史成功版本")
        if not target.collection_name:
            raise KnowledgeIndexStateError("历史版本缺少 Chroma 集合")
        open_vector_store_by_name(target.collection_name)

        now = _utc_now()
        current.status = "superseded"
        target.status = "active"
        target.previous_active_build_id = current.id
        target.activated_at = now
        self._close_linked_cases(build=target, now=now)
        self.db.commit()
        self.db.refresh(target)
        return target

    def _close_linked_cases(
        self,
        *,
        build: KnowledgeIndexBuild,
        now: datetime,
    ) -> None:
        revision_ids = [int(value) for value in (build.revision_snapshot or [])]
        if not revision_ids:
            return
        cases = self.db.query(UnresolvedCase).filter(
            UnresolvedCase.tenant_id == build.tenant_id,
            UnresolvedCase.knowledge_revision_id.in_(revision_ids),
            UnresolvedCase.is_resolved.is_not(True),
        ).all()
        for case in cases:
            case.is_resolved = True
            case.should_add_to_kb = False
            case.resolved_by_build_id = build.id
            case.auto_resolved_at = now
            case.updated_at = now

    def _latest_approved_revisions(
        self,
        *,
        tenant_id: int,
    ) -> list[KnowledgeRevision]:
        now = utc_now()
        latest_approved = (
            self.db.query(
                KnowledgeRevision.document_id.label("document_id"),
                func.max(KnowledgeRevision.version_no).label("version_no"),
            )
            .join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeRevision.parse_status == "succeeded",
                KnowledgeRevision.review_status == "approved",
                (
                    KnowledgeRevision.effective_at.is_(None)
                    | (KnowledgeRevision.effective_at <= now)
                ),
                (
                    KnowledgeRevision.expires_at.is_(None)
                    | (KnowledgeRevision.expires_at > now)
                ),
            )
            .group_by(KnowledgeRevision.document_id)
            .subquery()
        )
        return (
            self.db.query(KnowledgeRevision)
            .options(joinedload(KnowledgeRevision.document))
            .join(
                latest_approved,
                (KnowledgeRevision.document_id == latest_approved.c.document_id)
                & (KnowledgeRevision.version_no == latest_approved.c.version_no),
            )
            .order_by(KnowledgeRevision.document_id.asc())
            .all()
        )

    def _revision_document(
        self,
        *,
        tenant_id: int,
        revision: KnowledgeRevision,
        build_id: int,
    ) -> Document:
        if revision.document.tenant_id != tenant_id:
            raise KnowledgeIndexStateError("知识版本租户归属不一致")
        if not is_effective(
            effective_at=revision.effective_at,
            expires_at=revision.expires_at,
        ):
            raise KnowledgeIndexStateError("知识版本尚未生效或已经过期")
        if not revision.processed_storage_key:
            raise KnowledgeIndexStateError("审核知识缺少解析内容")
        path = self.storage.path_for_key(revision.processed_storage_key)
        content = path.read_text(encoding="utf-8")
        current_hash = sha256(content.encode("utf-8")).hexdigest()
        if current_hash != revision.processed_sha256:
            raise KnowledgeIndexStateError("审核后的解析内容已变化")
        sanitized = sanitize_document_content(content)
        if not sanitized.text:
            raise KnowledgeIndexStateError("审核知识清洗后为空")
        document = revision.document
        doc_id = f"t{tenant_id}_d{document.id}_r{revision.id}"
        return Document(
            id=doc_id,
            page_content=sanitized.text,
            metadata={
                "doc_id": doc_id,
                "tenant_id": tenant_id,
                "build_id": build_id,
                "document_id": document.id,
                "revision_id": revision.id,
                "version_no": revision.version_no,
                "title": document.title,
                "type": _rag_knowledge_type(document.knowledge_type),
                "knowledge_type": document.knowledge_type,
                "category": document.category,
                "relative_source": (
                    f"documents/{document.id}/revisions/{revision.id}"
                ),
                "source_sha256": revision.source_sha256,
                "processed_sha256": revision.processed_sha256 or "",
                "file_type": revision.source_file_type,
                "effective_at": (
                    revision.effective_at.isoformat()
                    if revision.effective_at else ""
                ),
                "expires_at": (
                    revision.expires_at.isoformat()
                    if revision.expires_at else ""
                ),
                "sanitized_instruction_lines": (
                    sanitized.removed_instruction_lines
                ),
                "sanitized_control_characters": (
                    sanitized.removed_control_characters
                ),
            },
        )


def _rag_knowledge_type(knowledge_type: str) -> str:
    return {
        "product_knowledge": "商品知识",
        "size_guide": "尺码知识",
        "after_sales_policy": "售后规则",
        "logistics_policy": "物流规则",
        "store_rule": "店铺规则",
        "faq": "商品知识",
    }.get(knowledge_type, "未分类")


def _build_error_code(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "knowledge_source_missing"
    if isinstance(error, ValueError):
        return "invalid_knowledge_content"
    return "index_build_failed"


def _build_error_message(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "审核知识文件或本地向量模型不存在"
    if isinstance(error, ValueError):
        return "审核知识内容无法构建索引"
    return "候选知识库构建失败，当前线上版本未受影响"


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
