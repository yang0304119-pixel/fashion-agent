from collections import defaultdict

from langchain_core.documents import Document

from app.rag.bm25 import BM25Result, search_bm25
from app.rag.config import (
    RAG_BM25_WEIGHT,
    RAG_DENSE_WEIGHT,
    RAG_FETCH_K,
    RAG_MIN_RELEVANCE,
    RAG_RRF_K,
    RAG_TOP_K,
)
from app.rag.embeddings import get_embeddings
from app.rag.errors import RagError
from app.rag.query_rewriter import (
    infer_knowledge_type,
    rewrite_query,
)
from app.rag.knowledge_index_resolver import resolve_vector_store


def _document_key(document: Document) -> str:
    return str(
        document.metadata.get("chunk_id")
        or document.id
        or document.metadata.get("doc_id", "")
    )


def _load_bm25_documents(
    knowledge_type: str | None,
    *,
    vector_store,
) -> list[Document]:
    where = (
        {"type": knowledge_type}
        if knowledge_type
        else None
    )
    result = vector_store.get(
        where=where,
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

    ranked_keys = sorted(
        fusion_scores,
        key=fusion_scores.get,
        reverse=True,
    )

    if not ranked_keys:
        return []

    maximum_score = fusion_scores[ranked_keys[0]]
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
            fusion_scores[key] / maximum_score
        )
        document.metadata["fusion_score"] = float(
            normalized_fusion_score
        )
        document.metadata["relevance_score"] = float(
            normalized_fusion_score
        )
        ranked_documents.append(document)

        if len(ranked_documents) >= RAG_TOP_K:
            break

    return ranked_documents


def retrieve(
    query: str,
    *,
    tenant_id: int,
    build_id: int | None = None,
) -> list[Document]:
    query = query.strip()

    if not query:
        return []

    rewritten_query = rewrite_query(query)
    knowledge_type = infer_knowledge_type(
        query,
        rewritten_query,
    )
    metadata_filter = (
        {"type": knowledge_type}
        if knowledge_type
        else None
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
                k=RAG_FETCH_K,
                filter=metadata_filter,
            )
        )
        bm25_documents = _load_bm25_documents(
            knowledge_type,
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
    bm25_results = search_bm25(
        f"{query} {rewritten_query}",
        bm25_documents,
        top_k=RAG_FETCH_K,
    )
    documents = _fuse_results(
        dense_results,
        bm25_results,
    )

    for document in documents:
        document.metadata["original_query"] = query
        document.metadata["rewritten_query"] = (
            rewritten_query
        )
        document.metadata["knowledge_type_filter"] = (
            knowledge_type or ""
        )

    return documents
