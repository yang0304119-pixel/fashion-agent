"""
知识库文档加载器

将 data/knowledge/ 下的 Markdown 知识文档加载为结构化 dict 列表。
只加载 index.json 中登记的文档，不加载游离的 .md 文件。

# 关键设计说明
# ─────────────────────────────
# 为什么以 index.json 为过滤依据：
# - index.json 是知识库的"注册表"，登记了文档的类型、分类等 metadata
# - 防止因目录中存在临时或废弃 .md 文件导致脏数据进入 RAG
# - 为后续多租户场景预留：每个租户可有独立的 index.json
# 权衡：
# - 新增知识文档时需要同步更新 index.json（可接受的手动步骤）
# - 严格模式：索引中有但文件缺失会报错，而不是静默忽略
# ─────────────────────────────
"""

import json
from pathlib import Path
from typing import Any


def load_knowledge(knowledge_dir: str | Path | None = None) -> list[dict[str, Any]]:
    """加载知识库文档，返回结构化文档列表。

    读取 index.json 获取文档注册信息，然后逐个加载 .md 文件内容。
    索引中登记的文件必须存在磁盘上，否则抛出 FileNotFoundError。

    Args:
        knowledge_dir: 知识库目录路径。默认为项目 data/knowledge/。

    Returns:
        list[dict]，每项包含：
        - id: 文档唯一标识（不含扩展名的文件名）
        - title: 文档标题（来自 index.json）
        - type: 文档类型（如 "商品知识" / "售后规则"）
        - category: 文档分类（如 "通用"）
        - content: 完整 Markdown 正文

    Raises:
        FileNotFoundError: index.json 不存在，或索引中登记的 .md 文件缺失
        json.JSONDecodeError: index.json 格式错误
    """
    # ── 确定知识库目录 ──
    if knowledge_dir is None:
        knowledge_dir = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge"
    knowledge_dir = Path(knowledge_dir)

    if not knowledge_dir.exists():
        raise FileNotFoundError(f"知识库目录不存在: {knowledge_dir}")

    # ── 加载 index.json ──
    index_path = knowledge_dir / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"知识库索引文件不存在: {index_path}")

    with open(index_path, "r", encoding="utf-8") as f:
        index_data: dict = json.load(f)

    documents: list[dict[str, Any]] = []
    for doc_info in index_data.get("documents", []):
        filename: str = doc_info.get("filename", "")
        if not filename:
            continue

        file_path = knowledge_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(
                f"索引中登记的文档不存在: {file_path}（请检查 index.json 或补充文件）"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 清理文件头 metadata 行（> 开头的引用行和空行前的元信息区域）
        # 保留第一个标题（#）之后的内容作为正文，文件头 metadata 行自动被正文包含
        documents.append({
            "id": file_path.stem,  # 不含扩展名的文件名
            "title": doc_info.get("title", ""),
            "type": doc_info.get("type", ""),
            "category": doc_info.get("category", ""),
            "content": content,
        })

    return documents
