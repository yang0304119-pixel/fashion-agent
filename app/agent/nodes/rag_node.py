"""
RAG 知识检索节点

当 Router 判断意图为 knowledge_query 时，此节点负责：
1. 调 Phase 2 retriever 语义检索知识库
2. 将召回内容作为上下文拼入 prompt
3. 调 LLM 生成基于知识库的回答

# 关键设计说明
# ─────────────────────────────
# 为什么把检索和生成放一个节点而非两个：
# - 检索和生成在业务上是一个完整动作：查了就要回答
# - 分开会导致多一次 state 流转，值传递更复杂
# - 后续如果要做 RAG 优化（如 Query Rewrite）可以在此节点内扩展
# 为什么不用 LangChain 的 RetrievalQA：
# - 就这一个 RAG 场景，LangChain 封装反而增加了抽象层
# - 直接调 retriever + OpenAI 更直观，出错时好定位
# ─────────────────────────────
"""

from openai import OpenAI

from app.agent.state import AgentState
from app.core.config import settings
from app.rag.retriever import retrieve


# RAG 回答生成 prompt
_RAG_PROMPT: str = """你是一个服装电商客服。请基于以下知识内容回答用户问题。

知识内容：
{context}

用户问题：{message}

回答要求：
- 基于提供的知识内容回答，不要编造知识库中没有的信息
- 如果知识内容不足以回答，如实说"知识库中未找到相关信息"
- 回答简洁自然，像客服在和用户对话
回答："""


def rag_node(state: AgentState) -> dict:
    """RAG 检索节点：检索知识库 → LLM 生成回答。

    Args:
        state: 当前 AgentState，至少包含 message 字段。

    Returns:
        更新 state 的字典，包含：
        - retrieved_docs: 召回文档内容列表
        - retrieved_doc_ids: 召回文档 ID 列表
        - retrieved_scores: 召回分数列表
        - final_answer: LLM 生成的回答
    """
    message: str = state.get("message", "").strip()

    # ── 1. 语义检索 ──
    try:
        docs = retrieve(message, top_k=3)
    except FileNotFoundError:
        # Chroma 集合不存在（未初始化），返回友好降级提示而非 500
        return {
            "retrieved_docs": [],
            "retrieved_doc_ids": [],
            "retrieved_scores": [],
            "final_answer": "抱歉，知识库尚未初始化，请联系管理员导入知识库后再试。",
        }

    if not docs:
        return {
            "retrieved_docs": [],
            "retrieved_doc_ids": [],
            "retrieved_scores": [],
            "final_answer": "抱歉，知识库中没有找到相关信息，请稍后再试或转人工客服。",
        }

    # ── 2. 拼装上下文 ──
    context = "\n\n".join(
        f"[{d.get('doc_title', '')} - {d.get('title', '')}]\n{d.get('content', '')}"
        for d in docs
    )

    # ── 3. LLM 生成回答 ──
    try:
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
        )
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": _RAG_PROMPT.format(context=context, message=message)}],
            max_tokens=500,
            temperature=0.3,
        )
        answer: str = response.choices[0].message.content.strip()
    except Exception:
        answer = "抱歉，我现在无法处理您的请求，请稍后再试。"

    return {
        "retrieved_docs": [d["content"] for d in docs],
        "retrieved_doc_ids": [d["doc_id"] for d in docs],
        "retrieved_scores": [d["score"] for d in docs],
        "final_answer": answer,
    }
