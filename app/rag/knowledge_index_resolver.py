"""将可信租户和可选候选构建解析为 Chroma 集合。"""

from app.core.database import SessionLocal
from app.rag.vector_store import open_vector_store_by_name
from app.services.knowledge_index_service import (
    KnowledgeIndexNotFoundError,
    KnowledgeIndexService,
)


def resolve_vector_store(
    *,
    tenant_id: int,
    build_id: int | None = None,
):
    if tenant_id <= 0:
        raise ValueError("RAG 查询缺少可信租户身份")
    db = SessionLocal()
    try:
        try:
            build = KnowledgeIndexService(db).resolve_read_build(
                tenant_id=tenant_id,
                build_id=build_id,
            )
        except KnowledgeIndexNotFoundError as error:
            if build_id is None:
                raise FileNotFoundError(
                    "当前租户尚未上线知识库"
                ) from error
            raise
        if not build.collection_name:
            raise FileNotFoundError("知识库版本缺少 Chroma 集合")
        return open_vector_store_by_name(build.collection_name)
    finally:
        db.close()
