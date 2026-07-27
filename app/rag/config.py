from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_KNOWLEDGE_DIR = (
    PROJECT_ROOT / "data" / "knowledge" / "raw"
)

PROCESSED_KNOWLEDGE_DIR = (
    PROJECT_ROOT / "data" / "knowledge" / "processed"
)

QUALITY_REPORT_FILE = (
    PROCESSED_KNOWLEDGE_DIR / "quality-report.json"
)

# 向后兼容已有调用；原始格式文件始终从 raw 目录加载。
KNOWLEDGE_DIR = RAW_KNOWLEDGE_DIR

CHROMA_DIR = (
    PROJECT_ROOT / "data" / "chroma"
)

EMBEDDING_MODEL_PATH = (
    PROJECT_ROOT
    / "models"
    / "bge-small-zh-v1.5"
)

COLLECTION_NAME = "fashion_knowledge"
ACTIVE_COLLECTION_FILE = (
    CHROMA_DIR / "active_collection.txt"
)
COLLECTION_DISTANCE = "cosine"
BGE_QUERY_INSTRUCTION = (
    "为这个句子生成表示以用于检索相关文章："
)

SUPPORTED_SUFFIXES = {
    ".txt",
    ".md",
    ".pdf",
    ".docx",
    ".pptx",
    ".html",
    ".htm",
    ".csv",
}
MAX_KNOWLEDGE_FILE_BYTES = 25 * 1024 * 1024

# 单位为 BGE Token，不是字符
CHUNK_SIZE_TOKENS = 400
CHUNK_OVERLAP_TOKENS = 60

CHUNK_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    "，",
    " ",
    "",
]

RAG_FETCH_K = 20
RAG_TOP_K = 3
# 暂定值，后续应通过标注评测集校准
RAG_MIN_RELEVANCE = 0.4
RAG_DENSE_WEIGHT = 1.0
RAG_BM25_WEIGHT = 1.0
RAG_RRF_K = 60
RAG_KNOWLEDGE_TYPE_BOOST = 0.08
RAG_LLM_TIMEOUT_SECONDS = 20
RAG_LLM_MAX_RETRIES = 1
