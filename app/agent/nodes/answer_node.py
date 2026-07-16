"""
最终回复节点

确保 final_answer 有值，对上游各节点的输出做兜底。
- rag_node（知识查询）：已生成 final_answer，直接通过
- react_node（工具类意图）：已生成 final_answer，直接通过
- fallback：上游未生成回答时给出友好提示

# 关键设计说明
# ─────────────────────────────
# 为什么现在这么简单：
# - ReAct 节点已承担回答生成职责（LLM 基于工具结果直接回复用户）
# - answer_node 退化为纯兜底：确保 final_answer 非空
# ─────────────────────────────
"""

from app.agent.state import AgentState


_FALLBACK_REPLIES: list[str] = [
    "抱歉，我没有理解您的意思。您可以试试问商品信息、尺码推荐或查询订单。",
    "不好意思，我没能明白您的问题。请问您想咨询哪方面的内容？",
    "我没太理解，您可以换种方式描述一下吗？比如查订单、问尺码或者了解商品。",
]


def answer_node(state: AgentState) -> dict:
    """最终回复节点：确保 final_answer 非空。

    Args:
        state: 当前 AgentState。

    Returns:
        更新 state 的字典，主要确保 final_answer 有值。
    """
    intent: str = state.get("intent", "")

    # ── RAG / ReAct 已生成回答 → 直接通过 ──
    if state.get("final_answer"):
        return {"final_answer": state["final_answer"]}

    # ── fallback 链路 → 友好提示 ──
    if intent == "fallback":
        reply = _FALLBACK_REPLIES[hash(state.get("message", "")) % len(_FALLBACK_REPLIES)]
        return {"final_answer": reply}

    # ── 极端兜底 ──
    return {"final_answer": "已收到您的请求，请稍候..."}

