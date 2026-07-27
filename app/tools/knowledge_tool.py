"""ReAct 使用的只读租户知识检索工具。"""

import logging

from app.rag.errors import RagError
from app.rag.retriever import retrieve
from app.rag.security import safe_relative_source
from app.tools.executor import ToolErrorCategory, ToolErrorDetail, failure_result


logger = logging.getLogger(__name__)


def retrieve_knowledge(query: str, *, tenant_id: int) -> dict:
    try:
        documents = retrieve(query, tenant_id=tenant_id, top_k=3)
    except (FileNotFoundError, RagError):
        logger.exception("知识检索工具暂时不可用")
        return failure_result(ToolErrorDetail(
            category=ToolErrorCategory.TRANSIENT,
            code="knowledge_retrieval_unavailable",
            message="知识库暂时不可用",
            retryable=True,
        ))
    return {
        "success": True,
        "data": {
            "documents": [
                {
                    "title": str(document.metadata.get("title", "")),
                    "content": document.page_content,
                    "chunk_id": str(document.metadata.get("chunk_id", "")),
                    "score": float(document.metadata.get("relevance_score", 0.0)),
                    "source": {
                        "title": str(document.metadata.get("title", "")),
                        "type": str(document.metadata.get("type", "")),
                        "category": str(document.metadata.get("category", "")),
                        "relative_source": str(safe_relative_source(
                            document.metadata.get("relative_source", "")
                        )),
                        "source_sha256": str(document.metadata.get("source_sha256", "")),
                    },
                }
                for document in documents
            ]
        },
        "error": None,
    }
