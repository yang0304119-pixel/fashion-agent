"""将原始知识Document持久化为可审核Markdown。"""

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from langchain_core.documents import Document

from app.rag.config import (
    PROCESSED_KNOWLEDGE_DIR,
    QUALITY_REPORT_FILE,
    RAW_KNOWLEDGE_DIR,
)
from app.rag.loader import iter_knowledge_files, lazy_load_knowledge


REPORT_VERSION = "1.0"
REPLACEMENT_CHARACTER = "\ufffd"
MOJIBAKE_PATTERN = re.compile(r"(?:Ã.|Â.|锟斤拷|ï¿½)")


def extract_processed_knowledge(
    *,
    raw_root: Path = RAW_KNOWLEDGE_DIR,
    processed_root: Path = PROCESSED_KNOWLEDGE_DIR,
    report_path: Path = QUALITY_REPORT_FILE,
    force: bool = False,
) -> dict:
    """解析raw文件并写入processed Markdown，默认保留人工修订。"""
    raw_root = raw_root.resolve(strict=True)
    processed_root.mkdir(parents=True, exist_ok=True)
    existing_report = _read_report(report_path)
    existing_entries = {
        entry["source_relative_path"]: entry
        for entry in existing_report.get("documents", [])
        if isinstance(entry, dict) and entry.get("source_relative_path")
    }

    loaded_by_source: dict[str, list[Document]] = defaultdict(list)
    for document in lazy_load_knowledge(raw_root):
        source = str(document.metadata.get("relative_source", ""))
        if source:
            loaded_by_source[source].append(document)

    entries: list[dict] = []
    for source_path in iter_knowledge_files(raw_root):
        source_relative = source_path.relative_to(raw_root).as_posix()
        source_hash = _file_sha256(source_path)
        processed_relative = _processed_relative_path(source_relative)
        processed_path = processed_root / processed_relative
        previous = existing_entries.get(source_relative, {})

        can_preserve = (
            not force
            and processed_path.is_file()
            and previous.get("source_sha256") == source_hash
        )
        documents = loaded_by_source.get(source_relative, [])
        if can_preserve:
            processed_text = processed_path.read_text(encoding="utf-8")
            extracted_document_count = int(
                previous.get("extracted_document_count", len(documents))
            )
        else:
            processed_text = _combine_documents(documents)
            if not processed_text:
                raise RuntimeError(f"文件没有提取出有效文本: {source_relative}")
            _atomic_write_text(processed_path, processed_text)
            extracted_document_count = len(documents)

        processed_hash = _text_sha256(processed_text)
        review_status = "pending_review"
        reviewed_at = None
        approved_processed_sha256 = None
        if can_preserve:
            previous_approved_hash = previous.get(
                "approved_processed_sha256"
            )
            if (
                previous.get("review_status") == "approved"
                and previous_approved_hash == processed_hash
            ):
                review_status = "approved"
                reviewed_at = previous.get("reviewed_at")
                approved_processed_sha256 = previous_approved_hash

        directory_parts = Path(source_relative).parts[:-1]
        metrics, warnings = analyze_processed_text(processed_text)
        entries.append({
            "source_relative_path": source_relative,
            "source_sha256": source_hash,
            "source_file_type": source_path.suffix.lower().removeprefix("."),
            "title": source_path.stem,
            "type": directory_parts[0] if directory_parts else "未分类",
            "category": directory_parts[1] if len(directory_parts) >= 2 else "通用",
            "processed_relative_path": processed_relative,
            "processed_sha256": processed_hash,
            "approved_processed_sha256": approved_processed_sha256,
            "extracted_document_count": extracted_document_count,
            "quality_status": "warning" if warnings else "passed",
            "quality_metrics": metrics,
            "warnings": warnings,
            "review_status": review_status,
            "reviewed_at": reviewed_at,
        })

    report = {
        "version": REPORT_VERSION,
        "generated_at": _utc_now_iso(),
        "raw_root": str(raw_root),
        "processed_root": str(processed_root.resolve()),
        "documents": entries,
    }
    _atomic_write_json(report_path, report)
    return report


def approve_processed_knowledge(
    *,
    sources: list[str] | None = None,
    approve_all: bool = False,
    raw_root: Path = RAW_KNOWLEDGE_DIR,
    processed_root: Path = PROCESSED_KNOWLEDGE_DIR,
    report_path: Path = QUALITY_REPORT_FILE,
) -> dict:
    """人工检查后批准指定处理文件，并锁定当前内容哈希。"""
    if not approve_all and not sources:
        raise ValueError("必须指定 --all 或至少一个 --source")
    raw_root = raw_root.resolve(strict=True)
    report = _read_report(report_path, required=True)
    requested = set(sources or [])
    matched: set[str] = set()

    for entry in report.get("documents", []):
        source_relative = entry["source_relative_path"]
        if not approve_all and source_relative not in requested:
            continue
        source_path = raw_root / source_relative
        processed_path = processed_root / entry["processed_relative_path"]
        _validate_source_and_processed(entry, source_path, processed_path)
        current_hash = _file_sha256(processed_path)
        entry["processed_sha256"] = current_hash
        entry["approved_processed_sha256"] = current_hash
        entry["review_status"] = "approved"
        entry["reviewed_at"] = _utc_now_iso()
        metrics, warnings = analyze_processed_text(
            processed_path.read_text(encoding="utf-8")
        )
        entry["quality_metrics"] = metrics
        entry["warnings"] = warnings
        entry["quality_status"] = "warning" if warnings else "passed"
        matched.add(source_relative)

    missing = requested - matched
    if missing:
        raise ValueError(f"质量报告中不存在来源: {sorted(missing)}")
    report["generated_at"] = _utc_now_iso()
    _atomic_write_json(report_path, report)
    return report


def analyze_processed_text(text: str) -> tuple[dict[str, int], list[str]]:
    lines = text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    replacement_count = text.count(REPLACEMENT_CHARACTER)
    mojibake_count = len(MOJIBAKE_PATTERN.findall(text))
    long_line_count = sum(len(line) > 1000 for line in lines)
    repeated_line_count = len(non_empty_lines) - len(set(non_empty_lines))
    metrics = {
        "character_count": len(text),
        "line_count": len(lines),
        "non_empty_line_count": len(non_empty_lines),
        "heading_count": sum(
            line.lstrip().startswith("#") for line in lines
        ),
        "table_row_count": sum("|" in line for line in lines),
        "replacement_character_count": replacement_count,
        "mojibake_pattern_count": mojibake_count,
        "long_line_count": long_line_count,
        "repeated_line_count": repeated_line_count,
    }
    warnings: list[str] = []
    if len(text.strip()) < 80:
        warnings.append("extracted_text_too_short")
    if replacement_count:
        warnings.append("replacement_characters_detected")
    if mojibake_count:
        warnings.append("possible_mojibake_detected")
    if long_line_count:
        warnings.append("very_long_lines_detected")
    if non_empty_lines and repeated_line_count / len(non_empty_lines) > 0.25:
        warnings.append("high_repeated_line_ratio")
    return metrics, warnings


def _combine_documents(documents: list[Document]) -> str:
    return "\n\n".join(
        document.page_content.strip()
        for document in documents
        if document.page_content.strip()
    ).strip() + ("\n" if documents else "")


def _processed_relative_path(source_relative: str) -> str:
    source = Path(source_relative)
    if source.suffix.lower() == ".md":
        return source.as_posix()
    return source.with_name(f"{source.name}.md").as_posix()


def _validate_source_and_processed(
    entry: dict,
    source_path: Path,
    processed_path: Path,
) -> None:
    if not source_path.is_file():
        raise FileNotFoundError(f"原始知识文件不存在: {source_path}")
    if not processed_path.is_file():
        raise FileNotFoundError(f"处理后知识文件不存在: {processed_path}")
    if _file_sha256(source_path) != entry.get("source_sha256"):
        raise RuntimeError(
            f"原始知识文件已变化，请重新提取: {source_path}"
        )
    if not processed_path.read_text(encoding="utf-8").strip():
        raise RuntimeError(f"处理后知识文件为空: {processed_path}")


def _read_report(path: Path, *, required: bool = False) -> dict:
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"质量报告不存在: {path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _text_sha256(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: dict) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _print_status(report: dict) -> None:
    for entry in report.get("documents", []):
        print(
            f'{entry["review_status"]:14} '
            f'{entry["quality_status"]:8} '
            f'{entry["source_relative_path"]}'
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="知识文档处理与审核")
    subparsers = parser.add_subparsers(dest="command", required=True)
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--force", action="store_true")
    approve_parser = subparsers.add_parser("approve")
    approve_parser.add_argument("--all", action="store_true")
    approve_parser.add_argument("--source", action="append")
    subparsers.add_parser("status")
    args = parser.parse_args()

    if args.command == "extract":
        report = extract_processed_knowledge(force=args.force)
    elif args.command == "approve":
        report = approve_processed_knowledge(
            sources=args.source,
            approve_all=args.all,
        )
    else:
        report = _read_report(QUALITY_REPORT_FILE, required=True)
    _print_status(report)


if __name__ == "__main__":
    main()
