from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

KNOWLEDGE_DIR = (
    PROJECT_ROOT / "data" / "knowledge" / "raw"
)

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

RAG_FETCH_K = 8
RAG_TOP_K = 3
# 暂定值，后续应通过标注评测集校准
RAG_MIN_RELEVANCE = 0.4
RAG_DENSE_WEIGHT = 1.0
RAG_BM25_WEIGHT = 1.0
RAG_RRF_K = 60
RAG_LLM_TIMEOUT_SECONDS = 20
RAG_LLM_MAX_RETRIES = 1
