from collections import defaultdict
from datetime import datetime
from typing import Any

from langchain_core.documents import Document

from app.rag.bm25 import BM25Result, search_bm25
from app.rag.config import (
    RAG_BM25_WEIGHT,
    RAG_DENSE_WEIGHT,
    RAG_FETCH_K,
    RAG_KNOWLEDGE_TYPE_BOOST,
    RAG_MIN_RELEVANCE,
    RAG_RRF_K,
    RAG_TOP_K,
)
from app.rag.embeddings import get_embeddings
from app.rag.errors import RagError
from app.rag.query_rewriter import (
    infer_knowledge_type_scores,
    rewrite_query,
)
from app.rag.knowledge_index_resolver import (
    current_revision_validity,
    resolve_vector_store,
)
from app.services.knowledge_validity import is_effective, utc_now


def _document_key(document: Document) -> str:
    return str(
        document.metadata.get("chunk_id")
        or document.id
        or document.metadata.get("doc_id", "")
    )


def _metadata_datetime(value: object) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _document_is_effective(document: Document, *, now: datetime) -> bool:
    metadata = document.metadata
    return is_effective(
        effective_at=_metadata_datetime(metadata.get("effective_at")),
        expires_at=_metadata_datetime(metadata.get("expires_at")),
        now=now,
    )


def _current_effective_documents(
    documents: list[Document],
    *,
    tenant_id: int,
    now: datetime,
) -> list[Document]:
    revision_ids = {
        int(document.metadata["revision_id"])
        for document in documents
        if document.metadata.get("revision_id") is not None
    }
    current_validity = current_revision_validity(
        tenant_id=tenant_id,
        revision_ids=revision_ids,
    )
    return [
        document
        for document in documents
        if (
            document.metadata.get("revision_id") is None
            or (
                int(document.metadata["revision_id"]) in current_validity
                and is_effective(
                    effective_at=current_validity[int(document.metadata["revision_id"])][0],
                    expires_at=current_validity[int(document.metadata["revision_id"])][1],
                    now=now,
                )
            )
        )
    ]


def _load_bm25_documents(
    *,
    vector_store,
) -> list[Document]:
    result = vector_store.get(
        include=["documents", "metadatas"],
    )
    ids = result.get("ids") or []
    contents = result.get("documents") or []
    metadatas = result.get("metadatas") or []

    return [
        Document(
            id=document_id,
            page_content=content,
            metadata=metadata or {},
        )
        for document_id, content, metadata in zip(
            ids,
            contents,
            metadatas,
            strict=True,
        )
    ]


def _fuse_results(
    dense_results: list[tuple[Document, float]],
    bm25_results: list[BM25Result],
    *,
    top_k: int,
    knowledge_type_scores: dict[str, float] | None = None,
) -> list[Document]:
    documents: dict[str, Document] = {}
    fusion_scores: defaultdict[str, float] = (
        defaultdict(float)
    )

    for rank, (document, relevance) in enumerate(
        dense_results,
        start=1,
    ):
        key = _document_key(document)
        documents[key] = document
        fusion_scores[key] += (
            RAG_DENSE_WEIGHT
            / (RAG_RRF_K + rank)
        )
        document.metadata["dense_score"] = float(
            relevance
        )
        document.metadata["dense_rank"] = rank

    for rank, result in enumerate(
        bm25_results,
        start=1,
    ):
        key = _document_key(result.document)
        document = documents.setdefault(
            key,
            result.document,
        )
        fusion_scores[key] += (
            RAG_BM25_WEIGHT
            / (RAG_RRF_K + rank)
        )
        document.metadata["bm25_score"] = float(
            result.score
        )
        document.metadata["bm25_rank"] = rank

    type_scores = knowledge_type_scores or {}
    adjusted_scores = {
        key: fusion_scores[key]
        * (
            1
            + RAG_KNOWLEDGE_TYPE_BOOST
            * type_scores.get(
                str(documents[key].metadata.get("type", "")),
                0.0,
            )
        )
        for key in fusion_scores
    }
    ranked_keys = sorted(
        fusion_scores,
        key=adjusted_scores.get,
        reverse=True,
    )

    if not ranked_keys:
        return []

    maximum_score = adjusted_scores[ranked_keys[0]]
    ranked_documents: list[Document] = []

    for key in ranked_keys:
        document = documents[key]
        dense_score = float(
            document.metadata.get("dense_score", 0.0)
        )
        bm25_score = float(
            document.metadata.get("bm25_score", 0.0)
        )

        if (
            dense_score < RAG_MIN_RELEVANCE
            and bm25_score <= 0
        ):
            continue

        normalized_fusion_score = (
            adjusted_scores[key] / maximum_score
        )
        type_weight = type_scores.get(
            str(document.metadata.get("type", "")),
            0.0,
        )
        document.metadata.setdefault("dense_score", 0.0)
        document.metadata.setdefault("dense_rank", 0)
        document.metadata.setdefault("bm25_score", 0.0)
        document.metadata.setdefault("bm25_rank", 0)
        document.metadata["fusion_raw_score"] = float(
            fusion_scores[key]
        )
        document.metadata["knowledge_type_weight"] = float(type_weight)
        document.metadata["knowledge_type_boost"] = float(
            RAG_KNOWLEDGE_TYPE_BOOST * type_weight
        )
        document.metadata["fusion_score"] = float(
            normalized_fusion_score
        )
        document.metadata["fusion_rank"] = len(ranked_documents) + 1
        document.metadata["relevance_score"] = float(
            normalized_fusion_score
        )
        ranked_documents.append(document)

        if len(ranked_documents) >= top_k:
            break

    return ranked_documents


def _source_key(document: Document) -> str:
    return str(
        document.metadata.get("revision_id")
        or document.metadata.get("document_id")
        or document.metadata.get("relative_source")
        or document.metadata.get("doc_id")
        or _document_key(document)
    )


def _select_diverse_documents(
    documents: list[Document],
    *,
    top_k: int,
) -> list[Document]:
    """Prefer one chunk per source, then fill remaining result slots."""
    selected: list[Document] = []
    selected_keys: set[str] = set()
    seen_sources: set[str] = set()

    for document in documents:
        source = _source_key(document)
        if source in seen_sources:
            continue
        selected.append(document)
        selected_keys.add(_document_key(document))
        seen_sources.add(source)
        if len(selected) >= top_k:
            break

    if len(selected) < top_k:
        for document in documents:
            key = _document_key(document)
            if key in selected_keys:
                continue
            selected.append(document)
            selected_keys.add(key)
            if len(selected) >= top_k:
                break

    for rank, document in enumerate(selected, start=1):
        document.metadata["pre_diversity_rank"] = int(
            document.metadata.get("fusion_rank", rank)
        )
        document.metadata["fusion_rank"] = rank
    return selected


def retrieve(
    query: str,
    *,
    tenant_id: int,
    build_id: int | None = None,
    top_k: int = RAG_TOP_K,
    recent_turns: list[dict[str, Any]] | None = None,
    conversation_summary: dict[str, Any] | None = None,
) -> list[Document]:
    query = query.strip()

    if not query:
        return []
    if top_k <= 0:
        return []

    fetch_k = max(RAG_FETCH_K, top_k)

    rewrite_context: dict[str, Any] = {}
    if recent_turns:
        rewrite_context["recent_turns"] = recent_turns
    if conversation_summary:
        rewrite_context["conversation_summary"] = conversation_summary
    rewritten_query = rewrite_query(query, **rewrite_context)
    knowledge_type_scores = infer_knowledge_type_scores(
        query,
        rewritten_query,
    )

    try:
        vector_store = resolve_vector_store(
            tenant_id=tenant_id,
            build_id=build_id,
        )
    except FileNotFoundError:
        raise
    except Exception as error:
        raise RagError(
            code="retrieval_failed",
            stage="retrieval",
            cause=error,
        ) from error

    try:
        query_embedding = get_embeddings().embed_query(
            rewritten_query
        )
    except Exception as error:
        raise RagError(
            code="embedding_failed",
            stage="embedding",
            cause=error,
        ) from error

    try:
        dense_results = (
            vector_store
            .similarity_search_by_vector_with_relevance_scores(
                embedding=query_embedding,
                k=fetch_k,
            )
        )
        bm25_documents = _load_bm25_documents(
            vector_store=vector_store,
        )
    except FileNotFoundError:
        raise
    except Exception as error:
        raise RagError(
            code="retrieval_failed",
            stage="retrieval",
            cause=error,
        ) from error
    now = utc_now()
    dense_results = [
        (document, score)
        for document, score in dense_results
        if _document_is_effective(document, now=now)
    ]
    bm25_documents = [
        document
        for document in bm25_documents
        if _document_is_effective(document, now=now)
    ]
    dense_documents = _current_effective_documents(
        [document for document, _ in dense_results],
        tenant_id=tenant_id,
        now=now,
    )
    allowed_dense_keys = {
        _document_key(document)
        for document in dense_documents
    }
    dense_results = [
        (document, score)
        for document, score in dense_results
        if _document_key(document) in allowed_dense_keys
    ]
    bm25_documents = _current_effective_documents(
        bm25_documents,
        tenant_id=tenant_id,
        now=now,
    )
    bm25_results = search_bm25(
        f"{query} {rewritten_query}",
        bm25_documents,
        top_k=fetch_k,
    )
    documents = _fuse_results(
        dense_results,
        bm25_results,
        top_k=fetch_k,
        knowledge_type_scores=knowledge_type_scores,
    )
    documents = _select_diverse_documents(
        documents,
        top_k=top_k,
    )

    for document in documents:
        document.metadata["original_query"] = query
        document.metadata["rewritten_query"] = (
            rewritten_query
        )
        document.metadata["knowledge_type_filter"] = (
            ",".join(knowledge_type_scores)
        )
        document.metadata["knowledge_type_candidates"] = list(
            knowledge_type_scores
        )

    return documents
