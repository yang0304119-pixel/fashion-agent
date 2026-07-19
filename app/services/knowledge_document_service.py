"""租户知识文档上传、内容编辑与人工审核服务。"""

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.knowledge_document import KnowledgeDocument, KnowledgeRevision
from app.rag.processor import analyze_processed_text, approve_processed_knowledge
from app.services.knowledge_processing_service import KnowledgeProcessingService
from app.services.knowledge_storage import KnowledgeStorage, KnowledgeStorageError
from app.services.query_page import QueryPage, validate_pagination


KNOWLEDGE_TYPES = frozenset({
    "product_knowledge",
    "size_guide",
    "after_sales_policy",
    "logistics_policy",
    "store_rule",
    "faq",
})
PARSE_STATUSES = frozenset({"pending", "running", "succeeded", "failed"})
REVIEW_STATUSES = frozenset({"pending", "approved", "rejected"})
MAX_PROCESSED_CONTENT_CHARACTERS = 2_000_000


class KnowledgeDocumentError(ValueError):
    pass


class KnowledgeDocumentNotFoundError(KnowledgeDocumentError):
    pass


class KnowledgeDocumentValidationError(KnowledgeDocumentError):
    pass


class KnowledgeDocumentStateError(KnowledgeDocumentError):
    pass


class KnowledgeDocumentService:
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
        parse_status: str | None,
        review_status: str | None,
        knowledge_type: str | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> QueryPage[KnowledgeDocument]:
        validate_pagination(page=page, page_size=page_size)
        _validate_optional_status(parse_status, PARSE_STATUSES, "解析状态")
        _validate_optional_status(review_status, REVIEW_STATUSES, "审核状态")
        if knowledge_type and knowledge_type not in KNOWLEDGE_TYPES:
            raise KnowledgeDocumentValidationError("知识类型筛选值无效")

        query = self.db.query(KnowledgeDocument).filter(
            KnowledgeDocument.tenant_id == tenant_id
        )
        if knowledge_type:
            query = query.filter(
                KnowledgeDocument.knowledge_type == knowledge_type
            )
        normalized_search = _normalized_text(search)
        if normalized_search:
            escaped = (
                normalized_search.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            query = query.filter(
                or_(
                    KnowledgeDocument.title.ilike(
                        f"%{escaped}%",
                        escape="\\",
                    ),
                    KnowledgeDocument.category.ilike(
                        f"%{escaped}%",
                        escape="\\",
                    ),
                )
            )
        if parse_status or review_status:
            latest = (
                self.db.query(
                    KnowledgeRevision.document_id.label("document_id"),
                    func.max(KnowledgeRevision.version_no).label("version_no"),
                )
                .group_by(KnowledgeRevision.document_id)
                .subquery()
            )
            query = (
                query.join(
                    latest,
                    latest.c.document_id == KnowledgeDocument.id,
                )
                .join(
                    KnowledgeRevision,
                    (KnowledgeRevision.document_id == latest.c.document_id)
                    & (KnowledgeRevision.version_no == latest.c.version_no),
                )
            )
            if parse_status:
                query = query.filter(
                    KnowledgeRevision.parse_status == parse_status
                )
            if review_status:
                query = query.filter(
                    KnowledgeRevision.review_status == review_status
                )

        total = query.count()
        items = (
            query.options(selectinload(KnowledgeDocument.revisions))
            .order_by(
                KnowledgeDocument.updated_at.desc(),
                KnowledgeDocument.id.desc(),
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
        document_id: int,
    ) -> KnowledgeDocument:
        document = (
            self.db.query(KnowledgeDocument)
            .options(selectinload(KnowledgeDocument.revisions))
            .filter(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.tenant_id == tenant_id,
            )
            .first()
        )
        if document is None:
            raise KnowledgeDocumentNotFoundError("知识文档不存在")
        return document

    def create_document(
        self,
        *,
        tenant_id: int,
        created_by: int,
        title: str,
        knowledge_type: str,
        category: str,
        original_filename: str,
        stream: BinaryIO,
    ) -> KnowledgeDocument:
        normalized_title, normalized_type, normalized_category = (
            _validate_document_metadata(title, knowledge_type, category)
        )
        document = KnowledgeDocument(
            tenant_id=tenant_id,
            title=normalized_title,
            knowledge_type=normalized_type,
            category=normalized_category,
            created_by=created_by,
        )
        self.db.add(document)
        self.db.flush()
        revision = KnowledgeRevision(
            document_id=document.id,
            version_no=1,
            original_filename=str(original_filename or ""),
            source_file_type="pending",
            raw_storage_key="pending",
            source_sha256="0" * 64,
            parse_status="pending",
            review_status="pending",
            created_by=created_by,
        )
        self.db.add(revision)
        self.db.flush()
        try:
            stored = self.storage.save_upload(
                tenant_id=tenant_id,
                document_id=document.id,
                revision_id=revision.id,
                original_filename=original_filename,
                stream=stream,
            )
            revision.original_filename = Path(original_filename).name
            revision.source_file_type = stored.file_type
            revision.raw_storage_key = stored.storage_key
            revision.source_sha256 = stored.source_sha256
            self.db.commit()
        except (KnowledgeStorageError, OSError) as error:
            self.db.rollback()
            self.storage.remove_revision(
                tenant_id=tenant_id,
                document_id=document.id,
                revision_id=revision.id,
            )
            raise KnowledgeDocumentValidationError(str(error)) from error
        return self.get_for_tenant(
            tenant_id=tenant_id,
            document_id=document.id,
        )

    def create_revision(
        self,
        *,
        tenant_id: int,
        document_id: int,
        created_by: int,
        original_filename: str,
        stream: BinaryIO,
    ) -> KnowledgeDocument:
        document = self.get_for_tenant(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        next_version = max(
            (revision.version_no for revision in document.revisions),
            default=0,
        ) + 1
        revision = KnowledgeRevision(
            document_id=document.id,
            version_no=next_version,
            original_filename=str(original_filename or ""),
            source_file_type="pending",
            raw_storage_key="pending",
            source_sha256="0" * 64,
            parse_status="pending",
            review_status="pending",
            created_by=created_by,
        )
        self.db.add(revision)
        self.db.flush()
        try:
            stored = self.storage.save_upload(
                tenant_id=tenant_id,
                document_id=document.id,
                revision_id=revision.id,
                original_filename=original_filename,
                stream=stream,
            )
            revision.original_filename = Path(original_filename).name
            revision.source_file_type = stored.file_type
            revision.raw_storage_key = stored.storage_key
            revision.source_sha256 = stored.source_sha256
            document.updated_at = _utc_now()
            self.db.commit()
        except (KnowledgeStorageError, OSError) as error:
            self.db.rollback()
            self.storage.remove_revision(
                tenant_id=tenant_id,
                document_id=document.id,
                revision_id=revision.id,
            )
            raise KnowledgeDocumentValidationError(str(error)) from error
        return self.get_for_tenant(
            tenant_id=tenant_id,
            document_id=document.id,
        )

    def parse_revision(
        self,
        *,
        tenant_id: int,
        revision_id: int,
    ) -> KnowledgeRevision:
        revision = self.get_revision_for_tenant(
            tenant_id=tenant_id,
            revision_id=revision_id,
        )
        if revision.parse_status == "running":
            raise KnowledgeDocumentStateError("知识版本正在解析，请稍后刷新")
        return KnowledgeProcessingService(
            self.db,
            storage=self.storage,
        ).parse(revision)

    def get_revision_for_tenant(
        self,
        *,
        tenant_id: int,
        revision_id: int,
    ) -> KnowledgeRevision:
        revision = (
            self.db.query(KnowledgeRevision)
            .join(KnowledgeDocument)
            .filter(
                KnowledgeRevision.id == revision_id,
                KnowledgeDocument.tenant_id == tenant_id,
            )
            .first()
        )
        if revision is None:
            raise KnowledgeDocumentNotFoundError("知识版本不存在")
        return revision

    def read_processed_content(
        self,
        *,
        tenant_id: int,
        revision_id: int,
    ) -> tuple[KnowledgeRevision, str]:
        revision = self.get_revision_for_tenant(
            tenant_id=tenant_id,
            revision_id=revision_id,
        )
        processed_path = self._require_processed_path(revision)
        try:
            content = processed_path.read_text(encoding="utf-8")
        except OSError as error:
            raise KnowledgeDocumentStateError("解析内容文件不存在") from error
        return revision, content

    def update_processed_content(
        self,
        *,
        tenant_id: int,
        revision_id: int,
        content: str,
    ) -> KnowledgeRevision:
        normalized = str(content).strip()
        if not normalized:
            raise KnowledgeDocumentValidationError("解析内容不能为空")
        if len(normalized) > MAX_PROCESSED_CONTENT_CHARACTERS:
            raise KnowledgeDocumentValidationError("解析内容超过允许长度")
        revision = self.get_revision_for_tenant(
            tenant_id=tenant_id,
            revision_id=revision_id,
        )
        processed_path = self._require_processed_path(revision)
        stored_content = normalized + "\n"
        self.storage.write_text(processed_path, stored_content)
        metrics, warnings = analyze_processed_text(stored_content)
        revision.processed_sha256 = sha256(
            stored_content.encode("utf-8")
        ).hexdigest()
        revision.quality_status = "warning" if warnings else "passed"
        revision.quality_report = {
            "metrics": metrics,
            "warnings": warnings,
            "extracted_document_count": (
                (revision.quality_report or {}).get(
                    "extracted_document_count",
                    1,
                )
            ),
            "report_version": (
                (revision.quality_report or {}).get("report_version", "1.0")
            ),
        }
        revision.review_status = "pending"
        revision.reviewed_by = None
        revision.reviewed_at = None
        revision.review_reason = None
        revision.updated_at = _utc_now()
        revision.document.updated_at = revision.updated_at
        self.db.commit()
        self.db.refresh(revision)
        return revision

    def approve_revision(
        self,
        *,
        tenant_id: int,
        revision_id: int,
        reviewed_by: int,
    ) -> KnowledgeRevision:
        revision = self.get_revision_for_tenant(
            tenant_id=tenant_id,
            revision_id=revision_id,
        )
        if revision.parse_status != "succeeded":
            raise KnowledgeDocumentStateError("只有解析成功的版本可以审核")
        processed_path = self._require_processed_path(revision)
        raw_path = self.storage.path_for_key(revision.raw_storage_key)
        if _file_sha256(raw_path) != revision.source_sha256:
            raise KnowledgeDocumentStateError("原始文件已变化，请重新上传版本")
        report_path = processed_path.parent / "quality-report.json"
        try:
            report = approve_processed_knowledge(
                approve_all=True,
                raw_root=raw_path.parent,
                processed_root=processed_path.parent,
                report_path=report_path,
            )
        except Exception as error:
            raise KnowledgeDocumentStateError(
                "知识内容校验失败，请重新解析后审核"
            ) from error
        entry = report["documents"][0]
        revision.processed_sha256 = entry["processed_sha256"]
        revision.quality_status = entry["quality_status"]
        revision.quality_report = {
            "metrics": entry["quality_metrics"],
            "warnings": entry["warnings"],
            "extracted_document_count": entry[
                "extracted_document_count"
            ],
            "report_version": report.get("version"),
        }
        revision.review_status = "approved"
        revision.reviewed_by = reviewed_by
        revision.reviewed_at = _utc_now()
        revision.review_reason = None
        revision.updated_at = revision.reviewed_at
        revision.document.updated_at = revision.reviewed_at
        self.db.commit()
        self.db.refresh(revision)
        return revision

    def reject_revision(
        self,
        *,
        tenant_id: int,
        revision_id: int,
        reviewed_by: int,
        reason: str,
    ) -> KnowledgeRevision:
        normalized_reason = _normalized_text(reason)
        if not normalized_reason:
            raise KnowledgeDocumentValidationError("拒绝时必须填写原因")
        if len(normalized_reason) > 500:
            raise KnowledgeDocumentValidationError("拒绝原因不能超过 500 字")
        revision = self.get_revision_for_tenant(
            tenant_id=tenant_id,
            revision_id=revision_id,
        )
        if revision.parse_status != "succeeded":
            raise KnowledgeDocumentStateError("只有解析成功的版本可以审核")
        revision.review_status = "rejected"
        revision.reviewed_by = reviewed_by
        revision.reviewed_at = _utc_now()
        revision.review_reason = normalized_reason
        revision.updated_at = revision.reviewed_at
        revision.document.updated_at = revision.reviewed_at
        self.db.commit()
        self.db.refresh(revision)
        return revision

    def _require_processed_path(self, revision: KnowledgeRevision) -> Path:
        if (
            revision.parse_status != "succeeded"
            or not revision.processed_storage_key
        ):
            raise KnowledgeDocumentStateError("知识版本尚未成功解析")
        processed_path = self.storage.path_for_key(
            revision.processed_storage_key
        )
        if not processed_path.is_file():
            raise KnowledgeDocumentStateError("解析内容文件不存在")
        return processed_path


def latest_revision(document: KnowledgeDocument) -> KnowledgeRevision:
    if not document.revisions:
        raise KnowledgeDocumentStateError("知识文档缺少版本")
    return max(document.revisions, key=lambda item: item.version_no)


def _validate_document_metadata(
    title: str,
    knowledge_type: str,
    category: str,
) -> tuple[str, str, str]:
    normalized_title = _normalized_text(title)
    normalized_type = _normalized_text(knowledge_type)
    normalized_category = _normalized_text(category) or "通用"
    if not normalized_title or len(normalized_title) > 200:
        raise KnowledgeDocumentValidationError("文档标题长度必须为 1-200 字")
    if normalized_type not in KNOWLEDGE_TYPES:
        raise KnowledgeDocumentValidationError("知识类型无效")
    if len(normalized_category) > 100:
        raise KnowledgeDocumentValidationError("知识分类不能超过 100 字")
    return normalized_title, normalized_type, normalized_category


def _validate_optional_status(
    value: str | None,
    allowed: frozenset[str],
    label: str,
) -> None:
    if value and value not in allowed:
        raise KnowledgeDocumentValidationError(f"{label}筛选值无效")


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
