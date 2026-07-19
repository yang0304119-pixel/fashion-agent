"""知识文档按租户、文档和版本安全落盘。"""

import os
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from app.core.config import settings
from app.rag.config import MAX_KNOWLEDGE_FILE_BYTES, SUPPORTED_SUFFIXES


class KnowledgeStorageError(ValueError):
    pass


@dataclass(frozen=True)
class StoredKnowledgeFile:
    storage_key: str
    source_sha256: str
    file_type: str
    size_bytes: int


class KnowledgeStorage:
    def __init__(self, root: Path | None = None) -> None:
        configured_root = root or settings.KNOWLEDGE_STORAGE_ROOT
        self.root = configured_root.expanduser().resolve()

    def save_upload(
        self,
        *,
        tenant_id: int,
        document_id: int,
        revision_id: int,
        original_filename: str,
        stream: BinaryIO,
    ) -> StoredKnowledgeFile:
        filename = _validate_filename(original_filename)
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise KnowledgeStorageError(f"不支持的文件格式: {suffix or '无扩展名'}")

        raw_root = self.revision_root(
            tenant_id=tenant_id,
            document_id=document_id,
            revision_id=revision_id,
        ) / "raw"
        raw_root.mkdir(parents=True, exist_ok=True)
        target = self._ensure_within_root(raw_root / filename)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        digest = sha256()
        size = 0
        prefix = b""
        try:
            with temporary.open("wb") as output:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    if not isinstance(chunk, bytes):
                        raise KnowledgeStorageError("上传文件流无效")
                    if len(prefix) < 16:
                        prefix += chunk[:16 - len(prefix)]
                    size += len(chunk)
                    if size > MAX_KNOWLEDGE_FILE_BYTES:
                        raise KnowledgeStorageError("知识文件超过 25MB 大小限制")
                    digest.update(chunk)
                    output.write(chunk)
                if size == 0:
                    raise KnowledgeStorageError("上传文件不能为空")
                output.flush()
                os.fsync(output.fileno())
            _validate_file_signature(suffix=suffix, prefix=prefix)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

        return StoredKnowledgeFile(
            storage_key=self.storage_key(target),
            source_sha256=digest.hexdigest(),
            file_type=suffix.removeprefix("."),
            size_bytes=size,
        )

    def revision_root(
        self,
        *,
        tenant_id: int,
        document_id: int,
        revision_id: int,
    ) -> Path:
        if min(tenant_id, document_id, revision_id) <= 0:
            raise KnowledgeStorageError("知识文件存储标识无效")
        return self._ensure_within_root(
            self.root
            / str(tenant_id)
            / "documents"
            / str(document_id)
            / "revisions"
            / str(revision_id)
        )

    def path_for_key(self, storage_key: str) -> Path:
        key = Path(storage_key)
        if key.is_absolute() or ".." in key.parts:
            raise KnowledgeStorageError("知识文件存储路径无效")
        return self._ensure_within_root(self.root / key)

    def storage_key(self, path: Path) -> str:
        resolved = self._ensure_within_root(path)
        return resolved.relative_to(self.root).as_posix()

    def write_text(self, path: Path, content: str) -> None:
        target = self._ensure_within_root(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def remove_revision(
        self,
        *,
        tenant_id: int,
        document_id: int,
        revision_id: int,
    ) -> None:
        revision_root = self.revision_root(
            tenant_id=tenant_id,
            document_id=document_id,
            revision_id=revision_id,
        )
        if revision_root.is_dir():
            shutil.rmtree(revision_root)

    def _ensure_within_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as error:
            raise KnowledgeStorageError("知识文件路径越界") from error
        return resolved


def _validate_filename(filename: str) -> str:
    normalized = str(filename or "").strip()
    if not normalized or len(normalized) > 255:
        raise KnowledgeStorageError("文件名无效")
    if (
        normalized != Path(normalized).name
        or "/" in normalized
        or "\\" in normalized
        or "\x00" in normalized
        or normalized.startswith((".", "~$"))
    ):
        raise KnowledgeStorageError("文件名包含不安全路径或临时文件标记")
    return normalized


def _validate_file_signature(*, suffix: str, prefix: bytes) -> None:
    if suffix == ".pdf" and not prefix.startswith(b"%PDF-"):
        raise KnowledgeStorageError("PDF 文件内容与扩展名不匹配")
    if suffix in {".docx", ".pptx"} and not prefix.startswith(b"PK"):
        raise KnowledgeStorageError("Office 文件内容与扩展名不匹配")
