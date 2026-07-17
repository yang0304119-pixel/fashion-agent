from functools import lru_cache

from langchain_huggingface import (
    HuggingFaceEmbeddings,
)

from app.rag.config import (
    BGE_QUERY_INSTRUCTION,
    EMBEDDING_MODEL_PATH,
)


@lru_cache
def get_embeddings() -> HuggingFaceEmbeddings:
    if not EMBEDDING_MODEL_PATH.is_dir():
        raise FileNotFoundError(
            "本地 embedding 模型不存在: "
            f"{EMBEDDING_MODEL_PATH}"
        )

    return HuggingFaceEmbeddings(
        model_name=str(EMBEDDING_MODEL_PATH),
        model_kwargs={
            "device": "cpu",
        },
        encode_kwargs={
            "normalize_embeddings": True,
        },
        query_encode_kwargs={
            "normalize_embeddings": True,
            "prompt": BGE_QUERY_INSTRUCTION,
        },
    )
