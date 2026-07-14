"""
知识库文档切分器

将 loader 加载的整篇 Markdown 文档按二级标题（##）切分为 chunk。
每个 chunk 继承原文档的 type/category 等 metadata，并记录来源 ID。

# 关键设计说明
# ─────────────────────────────
# 为什么按 ## 切分而非按字数：
# - 中文技术文档的天然语义边界是标题，而非字数
# - 保持语义完整性，避免将一个主题的内容切到两个 chunk 中
# - 有利于 RAG 召回：用户问题通常对应一个完整的子话题
# 权衡：
# - 长段落未再拆分，段落过长的 chunk 可能超出 embedding 窗口
#   （本项目的知识库文档以表格和短段落为主，无此问题）
# - 无标题的导言部分作为独立 chunk 保留，避免信息丢失
# ─────────────────────────────
"""

import re
from typing import Any


def split_docs(
    documents: list[dict[str, Any]],
    heading_pattern: str = r"^##\s+(.+)$",
) -> list[dict[str, Any]]:
    """将文档列表按 Markdown 二级标题切分为多个 chunk。

    每篇文档被拆分为若干 chunk，每个 chunk 对应一个二级标题下的内容。
    文档开头的导言部分（第一个 ## 之前）作为独立 chunk 保留。
    每个 chunk 继承原文档的 metadata，并附加 source_doc_id 和 chunk_index 用于追溯。

    Args:
        documents: load_knowledge() 返回的文档列表，
                    每项包含 id/title/type/category/content。
        heading_pattern: 标题行的正则，默认匹配 "## 标题" 格式的二级标题。

    Returns:
        list[dict]，每项包含：
        - id: chunk 唯一标识（"{doc_id}_{序号}"）
        - title: chunk 的标题（导言部分标记为 "导言"）
        - doc_title: 所属文档的原始标题
        - type: 继承自原文档
        - category: 继承自原文档
        - source_doc_id: 来源文档 ID
        - chunk_index: 在该文档中的序号
        - content: chunk 的 Markdown 正文

    边界情况：
        - 文档无 ## 标题时，整篇作为一个 chunk
        - 标题下内容为空时，仅含标题文本
        - 空文档返回空列表
    """
    chunks: list[dict[str, Any]] = []

    for doc in documents:
        content: str = doc.get("content", "")
        if not content.strip():
            continue

        doc_id: str = doc.get("id", "unknown")

        # 用正则匹配所有 ## 标题行及其位置
        heading_re = re.compile(heading_pattern, re.MULTILINE)
        matches = list(heading_re.finditer(content))

        if not matches:
            # 无标题：整篇作为一个 chunk
            chunks.append({
                "id": f"{doc_id}_0",
                "title": doc.get("title", ""),
                "doc_title": doc.get("title", ""),
                "type": doc.get("type", ""),
                "category": doc.get("category", ""),
                "source_doc_id": doc_id,
                "chunk_index": 0,
                "content": content.strip(),
            })
            continue

        # 处理导言部分（第一个 ## 之前的内容）
        first_heading_start = matches[0].start()
        preamble = content[:first_heading_start].strip()
        chunk_idx = 0

        if preamble:
            chunks.append({
                "id": f"{doc_id}_{chunk_idx}",
                "title": "导言",
                "doc_title": doc.get("title", ""),
                "type": doc.get("type", ""),
                "category": doc.get("category", ""),
                "source_doc_id": doc_id,
                "chunk_index": chunk_idx,
                "content": preamble,
            })
            chunk_idx += 1

        # 逐个处理标题及下方内容
        for i, match in enumerate(matches):
            title_text: str = match.group(1).strip()

            # 当前标题的起始位置
            chunk_start = match.start()
            # 下一个标题的开始位置，或文档末尾
            if i + 1 < len(matches):
                chunk_end = matches[i + 1].start()
            else:
                chunk_end = len(content)

            chunk_content = content[chunk_start:chunk_end].strip()
            if not chunk_content:
                continue

            chunks.append({
                "id": f"{doc_id}_{chunk_idx}",
                "title": title_text,
                "doc_title": doc.get("title", ""),
                "type": doc.get("type", ""),
                "category": doc.get("category", ""),
                "source_doc_id": doc_id,
                "chunk_index": chunk_idx,
                "content": chunk_content,
            })
            chunk_idx += 1

    return chunks
