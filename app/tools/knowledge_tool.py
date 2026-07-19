"""ReAct 使用的只读租户知识检索工具。"""

from app.rag.errors import RagError
from app.rag.retriever import retrieve


def retrieve_knowledge(query: str, *, tenant_id: int) -> dict:
    try:
        documents = retrieve(query, tenant_id=tenant_id, top_k=3)
    except (FileNotFoundError, RagError):
        return {
            "success": False,
            "data": None,
            "error": "知识库暂时不可用",
        }
    return {
        "success": True,
        "data": {
            "documents": [
                {
                    "title": str(document.metadata.get("title", "")),
                    "content": document.page_content,
                    "chunk_id": str(document.metadata.get("chunk_id", "")),
                    "score": float(document.metadata.get("relevance_score", 0.0)),
                }
                for document in documents
            ]
        },
        "error": None,
    }
