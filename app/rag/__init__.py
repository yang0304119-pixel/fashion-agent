"""
FashionAgent RAG 模块

知识库加载 → 文本切分 → 向量化存储 → 语义检索。
"""

import os

# 国内网络环境：HuggingFace 模型下载走 hf-mirror 镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
