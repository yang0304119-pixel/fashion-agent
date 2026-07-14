"""
知识库检索器

接收用户查询，从 Chroma 中语义检索相关知识 chunk。
检索结果可以直接映射到 AgentState 的 retrieved_docs / retrieved_doc_ids / retrieved_scores 字段。

# 关键设计说明
# ─────────────────────────────
# 为什么不用 query() 自带的 embedding_function 参数：
# - collection 创建时已绑定了 embedding_function，query 时默认复用
# - 但显式传入更安全：避免 collection 元数据丢失后 embedding 不匹配
# - 且 build_vector_store 和 retrieve 解耦，各自管理自己的 embedding 函数
# 为什么 scores 返回原始 L2 距离而非归一化分数：
# - Chroma 默认使用 L2 距离，越小表示越相似
# - 归一化会丢失原始距离信息，留给上层（answer_node）自行处理
# - 调用方判断：score < 1.0 通常表示高度相关，> 2.0 可能不相关
# ─────────────────────────────
"""

from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.core.config import settings


# 检索时必须使用与建库时相同的模型，否则向量空间不一致
DEFAULT_EMBED_MODEL = "BAAI/bge-small-zh-v1.5"


def retrieve(
    query: str,
    top_k: int | None = None,
    chroma_path: str | None = None,
    collection_name: str = "knowledge",
    model_name: str = DEFAULT_EMBED_MODEL,
) -> list[dict[str, Any]]:
    """从 Chroma 中检索与 query 最相关的知识 chunk。

    Args:
        query: 用户查询文本。
        top_k: 返回的 top-k 结果数，默认 settings.TOP_K（当前为 3）。
        chroma_path: Chroma 持久化目录，默认 settings.resolved_chroma_path。
        collection_name: Chroma 集合名称，默认 "knowledge"。
        model_name: embedding 模型名称，必须与建库时一致。

    Returns:
        list[dict]，按相关性降序排列，每项包含：
        - doc_id: chunk 的唯一标识
        - content: chunk 的 Markdown 正文
        - score: L2 距离（越小越相关）
        - title: chunk 标题
        - doc_title: 所属文档标题
        - type: 知识类型（如 "商品知识" / "售后规则"）
        - category: 知识分类
        - source_doc_id: 来源文档 ID

    Raises:
        FileNotFoundError: Chroma 集合不存在或目录为空。
        RuntimeError: Chroma 查询执行失败。
    """
    if not query or not query.strip():
        return []

    resolved_top_k = top_k or settings.TOP_K
    resolved_chroma_path = chroma_path or settings.resolved_chroma_path

    # ── 打开 Chroma 客户端 ──
    client = chromadb.PersistentClient(path=resolved_chroma_path)

    try:
        collection = client.get_collection(
            name=collection_name,
            embedding_function=SentenceTransformerEmbeddingFunction(
                model_name=model_name,
            ),
        )
    except ValueError:
        raise FileNotFoundError(
            f"Chroma 集合 '{collection_name}' 不存在。"
            f"请先运行 build_vector_store() 构建知识库。"
        )

    # ── 执行检索 ──
    results = collection.query(
        query_texts=[query],
        n_results=resolved_top_k,
    )

    # ── 组装结果 ──
    # Chroma query 返回结构：
    #   ids[0] / distances[0] / documents[0] / metadatas[0]
    retrieved: list[dict[str, Any]] = []
    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    for i in range(len(ids)):
        meta = metadatas[i] if metadatas else {}
        retrieved.append({
            "doc_id": ids[i],
            "content": documents[i] if documents else "",
            "score": distances[i] if distances else 0.0,
            "title": meta.get("title", ""),
            "doc_title": meta.get("doc_title", ""),
            "type": meta.get("type", ""),
            "category": meta.get("category", ""),
            "source_doc_id": meta.get("source_doc_id", ""),
        })

    return retrieved
