import logging

from app.rag.embeddings import get_embeddings
from app.rag.loader import load_knowledge
from app.rag.text_splitter import split_knowledge_documents
from app.rag.vector_store import (
    rebuild_vector_store,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_index() -> int:
    logger.info("开始扫描知识库")

    documents = load_knowledge()

    if not documents:
        raise RuntimeError("知识库目录中没有可用文件")

    logger.info(
        "文档加载完成，共 %d 个 Document",
        len(documents),
    )

    chunks = split_knowledge_documents(documents)

    if not chunks:
        raise RuntimeError("没有生成有效 chunk")

    logger.info(
        "文档切分完成，共 %d 个 chunk",
        len(chunks),
    )

    # 删除旧集合前先验证模型能够正常运行
    embeddings = get_embeddings()
    embeddings.embed_query("模型可用性测试")

    rebuild_vector_store(chunks)

    logger.info("Chroma 知识库构建完成")

    return len(chunks)


if __name__ == "__main__":
    count = build_index()
    print(f"构建完成，共写入 {count} 个 chunk")
