"""
最终回复节点

对上游节点生成的 final_answer 做兜底和格式化：
- RAG 链路已由 rag_node 生成回答，直接通过
- fallback 链路生成友好提示

# 关键设计说明
# ─────────────────────────────
# 为什么需要这个节点：
# - 统一回复出口，后续所有链路（tool/refund）都汇聚到这里
# - fallback 场景需要生成回复，不能让用户空等
# - 后续可在此节点添加敏感词过滤、回复润色等通用逻辑
# ─────────────────────────────
"""

from app.agent.state import AgentState


# fallback 友好提示列表（随机选择一个，避免每次一样）
_FALLBACK_REPLIES: list[str] = [
    "抱歉，我没有理解您的意思。您可以试试问商品信息、尺码推荐或查询订单。",
    "不好意思，我没能明白您的问题。请问您想咨询哪方面的内容？",
    "我没太理解，您可以换种方式描述一下吗？比如查订单、问尺码或者了解商品。",
]


def answer_node(state: AgentState) -> dict:
    """最终回复节点：兜底回复格式，确保 final_answer 非空。

    Args:
        state: 当前 AgentState。

    Returns:
        更新 state 的字典，主要确保 final_answer 有值。
    """
    intent: str = state.get("intent", "")

    # fallback 但上游没生成回复
    if intent == "fallback" and not state.get("final_answer"):
        import random
        reply = _FALLBACK_REPLIES[hash(state.get("message", "")) % len(_FALLBACK_REPLIES)]
        return {"final_answer": reply}

    # 其他链路：确保 final_answer 非空
    if not state.get("final_answer"):
        return {"final_answer": "已收到您的请求，请稍候..."}

    return {"final_answer": state["final_answer"]}
