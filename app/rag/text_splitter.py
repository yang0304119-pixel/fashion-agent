
from collections import defaultdict
from collections.abc import Iterable
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from transformers import (
    AutoConfig,
    AutoTokenizer,
    PreTrainedTokenizerBase,
)

from app.rag.config import (
    CHUNK_OVERLAP_TOKENS,
    CHUNK_SEPARATORS,
    CHUNK_SIZE_TOKENS,
    EMBEDDING_MODEL_PATH,
)


MARKDOWN_FILE_TYPES = {
    "md",
    "pdf",
    "docx",
    "pptx",
    "html",
    "htm",
}

CHROMA_METADATA_TYPES = (
    str,
    int,
    float,
    bool,
)


@lru_cache(maxsize=1)
def get_embedding_tokenizer() -> PreTrainedTokenizerBase:
    """加载本地 Embedding 模型对应的 Tokenizer。"""

    if not EMBEDDING_MODEL_PATH.is_dir():
        raise FileNotFoundError(
            f"Embedding 模型目录不存在："
            f"{EMBEDDING_MODEL_PATH}"
        )

    tokenizer = AutoTokenizer.from_pretrained(
        str(EMBEDDING_MODEL_PATH),
        local_files_only=True,
        use_fast=True,
    )

    if tokenizer is None:
        raise RuntimeError(
            "Tokenizer 加载失败：返回结果为 None"
        )

    return cast(
        PreTrainedTokenizerBase,
        tokenizer,
    )


@lru_cache(maxsize=1)
def get_model_token_limit() -> int:
    """读取模型最大输入长度。"""

    config = AutoConfig.from_pretrained(
        str(EMBEDDING_MODEL_PATH),
        local_files_only=True,
    )

    max_tokens = getattr(
        config,
        "max_position_embeddings",
        None,
    )

    if not isinstance(max_tokens, int):
        raise ValueError(
            "无法从模型配置读取 "
            "max_position_embeddings"
        )

    if max_tokens <= 0:
        raise ValueError(
            "模型最大 Token 长度必须大于 0"
        )

    return max_tokens


def count_tokens(
    text: str,
    *,
    add_special_tokens: bool = True,
) -> int:
    """使用 BGE Tokenizer 计算 Token 数量。"""

    tokenizer = get_embedding_tokenizer()

    encoded = tokenizer(
        text,
        add_special_tokens=add_special_tokens,
        truncation=False,
        return_attention_mask=False,
        return_token_type_ids=False,
    )

    return len(encoded["input_ids"])


@lru_cache(maxsize=1)
def get_markdown_splitter() -> MarkdownHeaderTextSplitter:
    """创建 Markdown 标题切分器。"""

    return MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "header_1"),
            ("##", "header_2"),
            ("###", "header_3"),
        ],
        strip_headers=False,
    )


@lru_cache(maxsize=1)
def get_token_text_splitter(
) -> RecursiveCharacterTextSplitter:
    """创建按自然边界切分、按 Token 计数的切分器。"""

    model_token_limit = get_model_token_limit()

    if CHUNK_SIZE_TOKENS <= 0:
        raise ValueError(
            "CHUNK_SIZE_TOKENS 必须大于 0"
        )

    if CHUNK_SIZE_TOKENS >= model_token_limit:
        raise ValueError(
            "CHUNK_SIZE_TOKENS 必须小于模型最大长度。"
            f"当前值：{CHUNK_SIZE_TOKENS}，"
            f"模型上限：{model_token_limit}"
        )

    if not (
        0
        <= CHUNK_OVERLAP_TOKENS
        < CHUNK_SIZE_TOKENS
    ):
        raise ValueError(
            "CHUNK_OVERLAP_TOKENS 必须大于等于 0，"
            "并且小于 CHUNK_SIZE_TOKENS"
        )

    return (
        RecursiveCharacterTextSplitter
        .from_huggingface_tokenizer(
            tokenizer=get_embedding_tokenizer(),
            chunk_size=CHUNK_SIZE_TOKENS,
            chunk_overlap=CHUNK_OVERLAP_TOKENS,
            separators=CHUNK_SEPARATORS,
            keep_separator=True,
            strip_whitespace=True,
        )
    )


def clean_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """只保留 Chroma 支持的 metadata 类型。"""

    cleaned: dict[str, Any] = {}

    for key, value in metadata.items():
        if not isinstance(key, str):
            continue

        if isinstance(value, Path):
            cleaned[key] = str(value)
        elif isinstance(
            value,
            CHROMA_METADATA_TYPES,
        ):
            cleaned[key] = value

    return cleaned


def split_markdown_sections(
    document: Document,
) -> list[Document]:
    """按 Markdown 标题切分文档。"""

    file_type = str(
        document.metadata.get(
            "file_type",
            "",
        )
    ).lower()

    if file_type not in MARKDOWN_FILE_TYPES:
        return [document]

    sections = get_markdown_splitter().split_text(
        document.page_content
    )

    if not sections:
        return [document]

    return [
        Document(
            page_content=section.page_content,
            metadata={
                **document.metadata,
                **section.metadata,
            },
        )
        for section in sections
    ]


def split_knowledge_documents(
        documents: Iterable[Document],
) -> list[Document]:
    """切分知识文档、清理 metadata 并过滤重复块。"""

    text_splitter = get_token_text_splitter()
    model_token_limit = get_model_token_limit()

    chunk_counters: dict[str, int] = defaultdict(int)
    seen_hashes_by_doc: dict[str, set[str]] = defaultdict(set)

    result: list[Document] = []

    for document in documents:
        raw_doc_id = document.metadata.get("doc_id")

        if not raw_doc_id:
            raise ValueError(
                "待切分 Document 缺少 doc_id metadata"
            )

        doc_id = str(raw_doc_id)

        sections = split_markdown_sections(document)
        chunks = text_splitter.split_documents(sections)

        for chunk in chunks:
            content = chunk.page_content.strip()

            if not content:
                continue

            full_content_hash = sha256(
                content.encode("utf-8")
            ).hexdigest()

            # 过滤同一来源文件内完全重复的文本块
            if full_content_hash in seen_hashes_by_doc[doc_id]:
                continue

            seen_hashes_by_doc[doc_id].add(
                full_content_hash
            )

            token_count = count_tokens(
                content,
                add_special_tokens=True,
            )

            if token_count > model_token_limit:
                raise ValueError(
                    "文本块超过模型 Token 上限："
                    f"doc_id={doc_id}, "
                    f"token_count={token_count}, "
                    f"model_limit={model_token_limit}"
                )

            chunk_index = chunk_counters[doc_id]
            chunk_counters[doc_id] += 1

            content_hash = full_content_hash[:24]
            chunk_id = f"{doc_id}_{content_hash}"

            metadata = clean_metadata(chunk.metadata)

            metadata.update({
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "token_count": token_count,
                "content_hash": content_hash,
            })

            result.append(
                Document(
                    id=chunk_id,
                    page_content=content,
                    metadata=metadata,
                )
            )

    return result


def split_one_document(
        document: Document,
) -> list[Document]:
    """切分单个 Document。"""

    return split_knowledge_documents([document])


def split_documents(
        documents: Iterable[Document],
) -> list[Document]:
    """兼容原来的函数调用名称。"""

    return split_knowledge_documents(documents)
