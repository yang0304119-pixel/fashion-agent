"""
FashionAgent RAG 模块

知识库加载 → 文本切分 → 向量化存储 → 语义检索 → LLM 回答。
"""

import os

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
