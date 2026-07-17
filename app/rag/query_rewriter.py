import logging
import re
from functools import lru_cache

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import settings


logger = logging.getLogger(__name__)

PROTECTED_QUERY_TOKEN_PATTERN = re.compile(
    r"(?<![A-Z0-9])"
    r"FA-[A-Z0-9]+-[A-Z0-9-]+"
    r"(?![A-Z0-9-])"
    r"|\d+(?:\.\d+)?"
    r"(?:天|小时|分钟|工作日|元|cm|kg|斤|码)?",
    flags=re.IGNORECASE,
)


KNOWLEDGE_TYPE_KEYWORDS = {
    "售后规则": (
        "退款",
        "退货",
        "换货",
        "售后",
        "赔付",
        "七天无理由",
        "质量问题",
    ),
    "物流规则": (
        "物流",
        "快递",
        "配送",
        "发货",
        "签收",
        "运单",
        "包邮",
    ),
    "尺码知识": (
        "尺码",
        "尺寸",
        "身高",
        "体重",
        "胸围",
        "腰围",
        "衣长",
        "穿什么码",
    ),
    "商品知识": (
        "商品",
        "材质",
        "面料",
        "成分",
        "保暖",
        "填充",
        "洗护",
        "清洗",
        "起球",
        "羽绒服",
        "围巾",
        "冲锋衣",
    ),
}


rewrite_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        """
你是服装电商知识库的检索查询改写器。
把用户问题改写成一条简洁、完整、适合检索知识库的中文查询。
必须保留 SKU、商品型号、政策编号、时间、金额和所有数字。
不要回答问题，不要添加用户未提供的事实，只输出改写后的查询。
""",
    ),
    ("human", "用户问题：{query}"),
])


@lru_cache(maxsize=1)
def _get_rewrite_chain():
    llm = ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
        temperature=0,
        max_tokens=120,
        timeout=10,
        max_retries=1,
    )
    return rewrite_prompt | llm | StrOutputParser()


def rewrite_query(query: str) -> str:
    query = query.strip()

    if not query:
        return ""

    try:
        rewritten = _get_rewrite_chain().invoke({
            "query": query,
        }).strip()
    except Exception:
        logger.warning(
            "RAG 查询改写失败，使用原查询",
            exc_info=True,
        )
        return query

    if not rewritten:
        return query

    protected_tokens = (
        PROTECTED_QUERY_TOKEN_PATTERN.findall(query)
    )
    missing_tokens = [
        token
        for token in protected_tokens
        if token.lower() not in rewritten.lower()
    ]

    if missing_tokens:
        rewritten = (
            f"{rewritten} 关键标识："
            + " ".join(missing_tokens)
        )

    return rewritten


def infer_knowledge_type(
    original_query: str,
    rewritten_query: str = "",
) -> str | None:
    text = f"{original_query} {rewritten_query}".lower()
    scores = {
        knowledge_type: sum(
            keyword.lower() in text
            for keyword in keywords
        )
        for knowledge_type, keywords
        in KNOWLEDGE_TYPE_KEYWORDS.items()
    }
    best_type, best_score = max(
        scores.items(),
        key=lambda item: item[1],
    )

    if best_score > 0:
        return best_type

    if re.search(
        r"(?<![A-Z0-9])"
        r"FA-[A-Z0-9]+-[A-Z0-9-]+"
        r"(?![A-Z0-9-])",
        text,
        flags=re.IGNORECASE,
    ):
        return "商品知识"

    return None
