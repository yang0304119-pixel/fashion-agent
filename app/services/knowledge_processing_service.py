"""将现有批处理解析器包装为单个知识版本的领域服务。"""

import logging
from hashlib import sha256
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeRevision
from app.rag.processor import extract_processed_knowledge
from app.services.knowledge_storage import KnowledgeStorage


logger = logging.getLogger(__name__)


class KnowledgeProcessingError(RuntimeError):
    pass


class KnowledgeProcessingService:
    def __init__(
        self,
        db: Session,
        *,
        storage: KnowledgeStorage | None = None,
    ) -> None:
        self.db = db
        self.storage = storage or KnowledgeStorage()

    def parse(self, revision: KnowledgeRevision) -> KnowledgeRevision:
        revision.parse_status = "running"
        revision.parse_error_code = None
        revision.parse_error_message = None
        self.db.commit()

        raw_path = self.storage.path_for_key(revision.raw_storage_key)
        revision_root = raw_path.parent.parent
        processed_root = revision_root / "processed"
        report_path = processed_root / "quality-report.json"
        try:
            if _file_sha256(raw_path) != revision.source_sha256:
                raise RuntimeError("原始文件哈希已变化")
            report = extract_processed_knowledge(
                raw_root=raw_path.parent,
                processed_root=processed_root,
                report_path=report_path,
                force=True,
            )
            entries = report.get("documents") or []
            if len(entries) != 1:
                raise RuntimeError("单个知识版本必须只包含一个原始文件")
            entry = entries[0]
            processed_path = processed_root / entry["processed_relative_path"]
            revision.processed_storage_key = self.storage.storage_key(
                processed_path
            )
            revision.processed_sha256 = entry["processed_sha256"]
            revision.parse_status = "succeeded"
            revision.parse_error_code = None
            revision.parse_error_message = None
            revision.review_status = "pending"
            revision.reviewed_by = None
            revision.reviewed_at = None
            revision.review_reason = None
            revision.quality_status = entry["quality_status"]
            revision.quality_report = {
                "metrics": entry["quality_metrics"],
                "warnings": entry["warnings"],
                "extracted_document_count": entry[
                    "extracted_document_count"
                ],
                "report_version": report.get("version"),
            }
            self.db.commit()
            self.db.refresh(revision)
            return revision
        except Exception as error:
            logger.exception("知识版本解析失败: revision_id=%s", revision.id)
            revision.parse_status = "failed"
            revision.parse_error_code = _processing_error_code(error)
            revision.parse_error_message = _processing_error_message(error)
            revision.review_status = "pending"
            revision.reviewed_by = None
            revision.reviewed_at = None
            self.db.commit()
            raise KnowledgeProcessingError(
                revision.parse_error_message
            ) from error


def _processing_error_code(error: Exception) -> str:
    if isinstance(error, FileNotFoundError):
        return "source_or_parser_missing"
    if isinstance(error, ValueError):
        return "invalid_source"
    return "parse_failed"


def _processing_error_message(error: Exception) -> str:
    message = str(error)
    if "Docling 本地模型目录不存在" in message:
        return "本地文档解析模型尚未配置"
    if isinstance(error, FileNotFoundError):
        return "原始文件或本地解析资源不存在"
    if isinstance(error, ValueError):
        return "文件格式或内容不符合解析要求"
    return "文档解析失败，请检查文件内容后重试"


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
