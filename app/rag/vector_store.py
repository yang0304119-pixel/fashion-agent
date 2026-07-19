import logging
import os
from datetime import UTC, datetime
from functools import lru_cache
from uuid import uuid4

import chromadb
from chromadb.api.client import SharedSystemClient
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.rag.config import (
    ACTIVE_COLLECTION_FILE,
    CHROMA_DIR,
    COLLECTION_DISTANCE,
    COLLECTION_NAME,
)
from app.rag.embeddings import get_embeddings


logger = logging.getLogger(__name__)


def _collection_names(
    client: chromadb.ClientAPI,
) -> set[str]:
    return {
        (
            item.name
            if hasattr(item, "name")
            else str(item)
        )
        for item in client.list_collections()
    }


def _read_active_collection_name(
    collection_names: set[str],
) -> str:
    if ACTIVE_COLLECTION_FILE.is_file():
        active_name = ACTIVE_COLLECTION_FILE.read_text(
            encoding="utf-8"
        ).strip()

        if not active_name:
            raise FileNotFoundError(
                "Chroma 活跃集合指针为空"
            )

        if active_name not in collection_names:
            raise FileNotFoundError(
                "Chroma 活跃集合不存在: "
                f"{active_name}"
            )

        return active_name

    if COLLECTION_NAME in collection_names:
        return COLLECTION_NAME

    raise FileNotFoundError(
        "Chroma 知识库集合尚未初始化"
    )


def _write_active_collection_name(
    collection_name: str,
) -> None:
    temporary_path = ACTIVE_COLLECTION_FILE.with_name(
        f".{ACTIVE_COLLECTION_FILE.name}."
        f"{uuid4().hex}.tmp"
    )

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as file:
            file.write(collection_name)
            file.flush()
            os.fsync(file.fileno())

        os.replace(
            temporary_path,
            ACTIVE_COLLECTION_FILE,
        )
    finally:
        temporary_path.unlink(missing_ok=True)


def _new_collection_name() -> str:
    timestamp = datetime.now(UTC).strftime(
        "%Y%m%d%H%M%S"
    )
    return (
        f"{COLLECTION_NAME}_{timestamp}_"
        f"{uuid4().hex[:8]}"
    )


def _open_collection(
    client: chromadb.ClientAPI,
    collection_name: str,
    *,
    create: bool,
) -> Chroma:
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        client=client,
        collection_configuration={
            "hnsw": {
                "space": COLLECTION_DISTANCE,
            },
        },
        create_collection_if_not_exists=create,
    )


def tenant_build_collection_name(*, tenant_id: int, build_id: int) -> str:
    if tenant_id <= 0 or build_id <= 0:
        raise ValueError("租户和知识库构建标识必须大于 0")
    return f"{COLLECTION_NAME}_t{tenant_id}_build_{build_id}"


def open_vector_store_by_name(collection_name: str) -> Chroma:
    """只打开已存在且非空的指定集合，不创建空集合。"""
    client = _get_chroma_client()
    if collection_name not in _collection_names(client):
        raise FileNotFoundError(
            f"Chroma 知识库集合不存在: {collection_name}"
        )
    collection = client.get_collection(name=collection_name)
    if collection.count() == 0:
        raise FileNotFoundError(
            f"Chroma 知识库集合为空: {collection_name}"
        )
    return _get_active_vector_store(collection_name)


def build_vector_store_collection(
    documents: list[Document],
    *,
    collection_name: str,
) -> Chroma:
    """构建候选集合；成功或失败都不会切换任何活跃版本。"""
    if not documents:
        raise ValueError("没有可以写入的 chunk")
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if collection_name in _collection_names(client):
        raise ValueError(f"Chroma 候选集合已存在: {collection_name}")
    vector_store = _open_collection(client, collection_name, create=True)
    try:
        for start in range(0, len(documents), 100):
            batch = documents[start:start + 100]
            vector_store.add_documents(
                documents=batch,
                ids=[str(document.id) for document in batch],
            )
        collection = client.get_collection(name=collection_name)
        actual_count = collection.count()
        if actual_count != len(documents):
            raise RuntimeError(
                "Chroma 候选集合文档数校验失败: "
                f"expected={len(documents)}, actual={actual_count}"
            )
        hnsw_configuration = collection.configuration.get("hnsw") or {}
        actual_distance = hnsw_configuration.get("space")
        if actual_distance != COLLECTION_DISTANCE:
            raise RuntimeError(
                "Chroma 距离算法校验失败: "
                f"expected={COLLECTION_DISTANCE}, actual={actual_distance}"
            )
        _get_active_vector_store.cache_clear()
        return vector_store
    except Exception:
        try:
            client.delete_collection(name=collection_name)
        except Exception:
            logger.warning(
                "失败的候选 Chroma 集合清理失败: %s",
                collection_name,
                exc_info=True,
            )
        _get_active_vector_store.cache_clear()
        raise


def delete_vector_store_collection(collection_name: str) -> None:
    """删除明确指定的候选集合。"""
    if not CHROMA_DIR.is_dir():
        return
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    if collection_name in _collection_names(client):
        client.delete_collection(name=collection_name)
    _get_active_vector_store.cache_clear()


def reset_vector_store_clients() -> None:
    """清理进程内向量库缓存；主要用于测试和受控维护。"""
    _get_active_vector_store.cache_clear()
    SharedSystemClient.clear_system_cache()


def _get_chroma_client() -> chromadb.ClientAPI:
    if not CHROMA_DIR.is_dir():
        raise FileNotFoundError(
            f"Chroma 数据目录不存在: {CHROMA_DIR}"
        )

    return chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )


@lru_cache
def _get_active_vector_store(
    active_name: str,
) -> Chroma:
    client = _get_chroma_client()
    return _open_collection(
        client,
        active_name,
        create=False,
    )


def get_vector_store() -> Chroma:
    """打开当前活跃向量库，不自动创建空集合。"""

    client = _get_chroma_client()
    collection_names = _collection_names(client)
    active_name = _read_active_collection_name(
        collection_names
    )
    collection = client.get_collection(
        name=active_name
    )

    if collection.count() == 0:
        raise FileNotFoundError(
            "Chroma 知识库集合尚未写入文档: "
            f"{active_name}"
        )

    return _get_active_vector_store(
        active_name
    )


def _delete_old_collections(
    client: chromadb.ClientAPI,
    active_name: str,
) -> None:
    for collection_name in _collection_names(client):
        if (
            collection_name == active_name
            or not collection_name.startswith(
                COLLECTION_NAME
            )
            or collection_name.startswith(
                f"{COLLECTION_NAME}_t"
            )
        ):
            continue

        try:
            client.delete_collection(
                name=collection_name
            )
        except Exception:
            logger.warning(
                "旧 Chroma 集合清理失败: %s",
                collection_name,
                exc_info=True,
            )


def rebuild_vector_store(
    documents: list[Document],
) -> Chroma:
    """完整构建新集合，验证后原子切换活跃版本。"""

    if not documents:
        raise ValueError("没有可以写入的 chunk")

    CHROMA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )
    new_collection_name = _new_collection_name()
    vector_store = _open_collection(
        client,
        new_collection_name,
        create=True,
    )

    try:
        batch_size = 100

        for start in range(
            0,
            len(documents),
            batch_size,
        ):
            batch = documents[
                start:start + batch_size
            ]

            vector_store.add_documents(
                documents=batch,
                ids=[str(doc.id) for doc in batch],
            )

        collection = client.get_collection(
            name=new_collection_name
        )
        actual_count = collection.count()

        if actual_count != len(documents):
            raise RuntimeError(
                "Chroma 新集合文档数校验失败: "
                f"expected={len(documents)}, "
                f"actual={actual_count}"
            )

        hnsw_configuration = (
            collection.configuration.get("hnsw")
            or {}
        )
        actual_distance = hnsw_configuration.get(
            "space"
        )

        if actual_distance != COLLECTION_DISTANCE:
            raise RuntimeError(
                "Chroma 距离算法校验失败: "
                f"expected={COLLECTION_DISTANCE}, "
                f"actual={actual_distance}"
            )

        _write_active_collection_name(
            new_collection_name
        )
    except Exception:
        try:
            client.delete_collection(
                name=new_collection_name
            )
        except Exception:
            logger.warning(
                "失败的新 Chroma 集合清理失败: %s",
                new_collection_name,
                exc_info=True,
            )
        raise

    _delete_old_collections(
        client,
        new_collection_name,
    )

    return vector_store
