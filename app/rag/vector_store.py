"""
向量存储构建器

将 splitter 切分的 chunk 通过本地 embedding 模型向量化后存入 Chroma。
使用 Chroma 的 PersistentClient 持久化到本地磁盘。

# 关键设计说明
# ─────────────────────────────
# 为什么用 SentenceTransformer（本地模型）而非 OpenAI API：
# - 开发环境网络可能无法直连 OpenAI API（已踩坑）
# - 本地模型无需 API Key、无调用费用、无网络延迟
# - 44 个 chunk 的规模下，本地模型与 API 模型效果差异可以忽略
# 为什么每次 build 删除重建集合：
# - 开发阶段知识库内容会频繁调整，追加逻辑复杂（去重、更新）
# - 知识库规模小（几十个 chunk），重建成本极低
# - 生产环境可改为 upsert 方式追加
# ─────────────────────────────
"""

from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from app.core.config import settings


# Chroma 集合名称
COLLECTION_NAME = "knowledge"

# 默认 embedding 模型（阿里出品，中文效果优秀，轻量级）
DEFAULT_EMBED_MODEL = "BAAI/bge-small-zh-v1.5"


def build_vector_store(
    chunks: list[dict[str, Any]],
    chroma_path: str | None = None,
    collection_name: str = COLLECTION_NAME,
    model_name: str = DEFAULT_EMBED_MODEL,
) -> int:
    """将 chunk 列表向量化并存入 Chroma。

    每次调用会删除已存在的同名集合后重建（幂等）。
    每个 chunk 的 metadata 保留 type/category 等信息，供后续检索过滤。

    Args:
        chunks: split_docs() 输出的 chunk 列表。
        chroma_path: Chroma 持久化目录，默认使用 settings.resolved_chroma_path。
        collection_name: Chroma 集合名称，默认 "knowledge"。
        model_name: 本地 embedding 模型名称，默认 "BAAI/bge-small-zh-v1.5"。

    Returns:
        写入的 chunk 数量。

    Raises:
        chromadb.errors.ChromaError: Chroma 操作失败。
        ValueError: chunks 为空列表时抛出。
    """
    if not chunks:
        return 0

    resolved_chroma_path = chroma_path or settings.resolved_chroma_path

    # ── 初始化 Chroma 客户端 ──
    client = chromadb.PersistentClient(path=resolved_chroma_path)

    # 删除已有集合（幂等：不存在时忽略）
    try:
        client.delete_collection(collection_name)
    except (ValueError, chromadb.errors.NotFoundError):
        pass  # 不同 Chroma 版本抛不同类型的异常，统一忽略

    # ── 创建 embedding 函数 ──
    embedding_func = SentenceTransformerEmbeddingFunction(
        model_name=model_name,
    )

    # ── 创建新集合 ──
    collection = client.create_collection(
        name=collection_name,
        embedding_function=embedding_func,
        metadata={"description": "FashionAgent 知识库"},
    )

    # ── 准备数据 ──
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []

    for chunk in chunks:
        chunk_id: str = chunk.get("id", "")
        content: str = chunk.get("content", "")

        if not chunk_id or not content.strip():
            continue

        ids.append(chunk_id)
        documents.append(content)

        # metadata 只保留业务需要的字段，排除 content 避免冗余
        metadatas.append({
            "title": chunk.get("title", ""),
            "doc_title": chunk.get("doc_title", ""),
            "type": chunk.get("type", ""),
            "category": chunk.get("category", ""),
            "source_doc_id": chunk.get("source_doc_id", ""),
            "chunk_index": chunk.get("chunk_index", 0),
        })

    # ── 批量写入 ──
    collection.add(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
    )

    return len(ids)
