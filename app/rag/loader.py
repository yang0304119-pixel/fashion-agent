from collections.abc import Iterator
from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
)
from docling.document_converter import (
    DocumentConverter,
    PdfFormatOption,
)
from langchain_community.document_loaders import (
    CSVLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

from app.core.config import settings
from app.rag.config import (
    KNOWLEDGE_DIR,
    MAX_KNOWLEDGE_FILE_BYTES,
    SUPPORTED_SUFFIXES,
)
from app.rag.security import sanitize_document_content


TEXT_SUFFIXES = {".txt", ".md"}
CSV_SUFFIXES = {".csv"}

DOCLING_SUFFIXES = {
    ".pdf",
    ".docx",
    ".pptx",
    ".html",
    ".htm",
}


@lru_cache(maxsize=1)
def get_docling_converter() -> DocumentConverter:
    """创建只使用本地模型文件的 Docling 转换器。"""

    artifacts_path = (
        settings.DOCLING_ARTIFACTS_PATH
        .expanduser()
        .resolve()
    )

    if not artifacts_path.is_dir():
        raise FileNotFoundError(
            "Docling 本地模型目录不存在: "
            f"{artifacts_path}"
        )

    pdf_options = PdfPipelineOptions(
        artifacts_path=artifacts_path,
    )

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pdf_options,
            ),
        },
    )


def iter_knowledge_files(
    root: Path = KNOWLEDGE_DIR,
) -> Iterator[Path]:
    """递归扫描所有支持的知识文件。"""

    root = root.resolve()

    if not root.is_dir():
        raise FileNotFoundError(
            f"知识库目录不存在: {root}"
        )

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue

        relative_path = path.relative_to(root)

        if any(
            (root / parent).is_symlink()
            for parent in (
                Path(*relative_path.parts[:index])
                for index in range(
                    1,
                    len(relative_path.parts) + 1,
                )
            )
        ):
            continue

        if path.name.startswith((".", "~$")):
            continue

        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue

        if path.stat().st_size > MAX_KNOWLEDGE_FILE_BYTES:
            raise ValueError(
                "知识文件超过大小限制: "
                f"{relative_path.as_posix()}"
            )

        resolved_path = path.resolve(strict=True)

        try:
            resolved_path.relative_to(root)
        except ValueError as error:
            raise ValueError(
                "知识文件路径越界: "
                f"{path}"
            ) from error

        yield resolved_path


def create_loader(
    path: Path,
    root: Path = KNOWLEDGE_DIR,
):
    """根据文件扩展名创建 LangChain Loader。"""

    root = root.resolve(strict=True)
    path = path.resolve(strict=True)

    try:
        path.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"拒绝加载知识库目录外的文件: {path}"
        ) from error

    suffix = path.suffix.lower()

    if suffix in TEXT_SUFFIXES:
        return TextLoader(
            file_path=str(path),
            encoding="utf-8",
            autodetect_encoding=True,
        )

    if suffix in CSV_SUFFIXES:
        return CSVLoader(
            file_path=str(path),
            encoding="utf-8-sig",
            autodetect_encoding=True,
        )

    if suffix in DOCLING_SUFFIXES:
        return DoclingLoader(
            file_path=str(path),
            converter=get_docling_converter(),
            export_type=ExportType.MARKDOWN,
        )

    raise ValueError(f"不支持的文件格式: {suffix}")


def lazy_load_knowledge(
    root: Path = KNOWLEDGE_DIR,
) -> Iterator[Document]:
    """扫描目录并统一生成 LangChain Document。"""

    root = root.resolve()

    for file_path in iter_knowledge_files(root):
        relative_path = file_path.relative_to(root)
        directory_parts = relative_path.parts[:-1]

        knowledge_type = (
            directory_parts[0]
            if len(directory_parts) >= 1
            else "未分类"
        )

        category = (
            directory_parts[1]
            if len(directory_parts) >= 2
            else "通用"
        )

        source_key = relative_path.as_posix()
        doc_id = sha256(
            source_key.encode("utf-8")
        ).hexdigest()[:16]

        source_sha256 = sha256(
            file_path.read_bytes()
        ).hexdigest()
        loader = create_loader(
            file_path,
            root=root,
        )

        for document in loader.lazy_load():
            sanitized = sanitize_document_content(
                document.page_content
            )

            if not sanitized.text:
                continue

            document.page_content = sanitized.text
            document.metadata.update({
                "doc_id": doc_id,
                "title": file_path.stem,
                "type": knowledge_type,
                "category": category,
                "source": str(file_path),
                "relative_source": source_key,
                "file_name": file_path.name,
                "source_sha256": source_sha256,
                "sanitized_instruction_lines": (
                    sanitized.removed_instruction_lines
                ),
                "sanitized_control_characters": (
                    sanitized.removed_control_characters
                ),
                "file_type": (
                    file_path.suffix
                    .lower()
                    .removeprefix(".")
                ),
            })

            yield document


def load_knowledge(
    root: Path = KNOWLEDGE_DIR,
) -> list[Document]:
    return list(lazy_load_knowledge(root))
