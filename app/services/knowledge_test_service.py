"""管理员知识库上线前问答测试与安全来源诊断。"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeIndexBuild
from app.rag.retriever import retrieve
from app.rag.knowledge_index_resolver import current_revision_validity
from app.rag.security import safe_relative_source
from app.rag.service import answer_from_documents
from app.services.knowledge_index_service import (
    KnowledgeIndexService,
)


MAX_PREVIEW_CHARACTERS = 1200


@dataclass(frozen=True)
class KnowledgeTestResult:
    build: KnowledgeIndexBuild
    answer: str
    original_query: str
    rewritten_query: str
    knowledge_type_filter: str | None
    hits: list[dict]


class KnowledgeTestService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.index_service = KnowledgeIndexService(db)

    def test_question(
        self,
        *,
        tenant_id: int,
        question: str,
        build_id: int | None,
        top_k: int,
    ) -> KnowledgeTestResult:
        build = self.index_service.resolve_read_build(
            tenant_id=tenant_id,
            build_id=build_id,
        )
        documents = retrieve(
            question,
            tenant_id=tenant_id,
            build_id=build.id,
            top_k=top_k,
        )
        answer_result = answer_from_documents(
            question,
            documents=documents,
        )
        first_metadata = documents[0].metadata if documents else {}
        validity = current_revision_validity(
            tenant_id=tenant_id,
            revision_ids={
                int(document.metadata["revision_id"])
                for document in documents
                if document.metadata.get("revision_id") is not None
            },
        )
        return KnowledgeTestResult(
            build=build,
            answer=answer_result["answer"],
            original_query=str(
                first_metadata.get("original_query", question)
            ),
            rewritten_query=str(
                first_metadata.get("rewritten_query", question)
            ),
            knowledge_type_filter=(
                str(first_metadata.get("knowledge_type_filter")) or None
            ),
            hits=[
                _safe_hit(document, rank, validity=validity)
                for rank, document in enumerate(documents, start=1)
            ],
        )


def _safe_hit(document, rank: int, *, validity: dict) -> dict:
    metadata = document.metadata
    content = str(document.page_content).strip()
    preview = content[:MAX_PREVIEW_CHARACTERS]
    if len(content) > MAX_PREVIEW_CHARACTERS:
        preview = f"{preview}…"
    revision_id = _positive_int(metadata.get("revision_id"))
    effective_at, expires_at = validity.get(revision_id, (None, None))
    return {
        "rank": rank,
        "source_id": f"S{rank}",
        "title": str(metadata.get("title", "")),
        "knowledge_type": str(metadata.get("knowledge_type", "")),
        "category": str(metadata.get("category", "")),
        "document_id": _positive_int(metadata.get("document_id")),
        "revision_id": revision_id,
        "version_no": _positive_int(metadata.get("version_no")),
        "chunk_id": str(
            metadata.get("chunk_id")
            or document.id
            or metadata.get("doc_id", "")
        ),
        "relative_source": safe_relative_source(
            metadata.get("relative_source")
        ),
        "preview": preview,
        "dense_score": _score(metadata.get("dense_score")),
        "dense_rank": _positive_int(metadata.get("dense_rank"), zero=True),
        "bm25_score": _score(metadata.get("bm25_score")),
        "bm25_rank": _positive_int(metadata.get("bm25_rank"), zero=True),
        "fusion_score": _score(metadata.get("fusion_score")),
        "fusion_rank": _positive_int(metadata.get("fusion_rank"), zero=True),
        "effective_at": effective_at,
        "expires_at": expires_at,
    }


def _score(value: object) -> float:
    try:
        return round(float(value or 0.0), 6)
    except (TypeError, ValueError):
        return 0.0


def _positive_int(value: object, *, zero: bool = False) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0 if zero else None
    if parsed > 0:
        return parsed
    return 0 if zero else None
