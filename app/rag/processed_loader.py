"""加载已经人工审核通过的processed知识文档。"""

import json
from collections.abc import Iterator
from hashlib import sha256
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document

from app.rag.config import (
    PROCESSED_KNOWLEDGE_DIR,
    QUALITY_REPORT_FILE,
    RAW_KNOWLEDGE_DIR,
)
from app.rag.security import sanitize_document_content


def lazy_load_approved_knowledge(
    *,
    raw_root: Path = RAW_KNOWLEDGE_DIR,
    processed_root: Path = PROCESSED_KNOWLEDGE_DIR,
    report_path: Path = QUALITY_REPORT_FILE,
) -> Iterator[Document]:
    if not report_path.is_file():
        raise FileNotFoundError(
            "processed质量报告不存在，请先运行: "
            "python -m app.rag.processor extract"
        )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    entries = report.get("documents")
    if not isinstance(entries, list) or not entries:
        raise RuntimeError("processed质量报告中没有知识文档")

    pending = [
        entry.get("source_relative_path", "unknown")
        for entry in entries
        if entry.get("review_status") != "approved"
    ]
    if pending:
        raise RuntimeError(
            "存在未人工审核的processed知识文档: "
            + ", ".join(pending)
        )

    for entry in entries:
        source_relative = str(entry["source_relative_path"])
        source_path = raw_root / source_relative
        processed_path = processed_root / str(
            entry["processed_relative_path"]
        )
        if not source_path.is_file() or not processed_path.is_file():
            raise FileNotFoundError(
                f"知识源或processed文件不存在: {source_relative}"
            )
        if _file_sha256(source_path) != entry.get("source_sha256"):
            raise RuntimeError(
                f"原始知识文件已变化，需要重新提取: {source_relative}"
            )
        processed_hash = _file_sha256(processed_path)
        if processed_hash != entry.get("approved_processed_sha256"):
            raise RuntimeError(
                f"processed文件在审核后发生变化，需要重新批准: {source_relative}"
            )

        loader = TextLoader(
            file_path=str(processed_path),
            encoding="utf-8",
            autodetect_encoding=False,
        )
        for document in loader.lazy_load():
            sanitized = sanitize_document_content(document.page_content)
            if not sanitized.text:
                raise RuntimeError(
                    f"processed文件清洗后为空: {source_relative}"
                )
            document.page_content = sanitized.text
            document.metadata.update({
                "doc_id": sha256(
                    source_relative.encode("utf-8")
                ).hexdigest()[:16],
                "title": entry["title"],
                "type": entry["type"],
                "category": entry["category"],
                "source": str(source_path.resolve()),
                "processed_source": str(processed_path.resolve()),
                "relative_source": source_relative,
                "file_name": source_path.name,
                "source_sha256": entry["source_sha256"],
                "processed_sha256": processed_hash,
                "file_type": entry["source_file_type"],
                "sanitized_instruction_lines": (
                    sanitized.removed_instruction_lines
                ),
                "sanitized_control_characters": (
                    sanitized.removed_control_characters
                ),
            })
            yield document


def load_approved_knowledge(**kwargs) -> list[Document]:
    return list(lazy_load_approved_knowledge(**kwargs))


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()
