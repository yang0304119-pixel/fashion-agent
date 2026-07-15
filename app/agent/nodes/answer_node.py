"""
最终回复节点

对上游节点生成的 final_answer 做兜底和格式化：
- RAG 链路已由 rag_node 生成回答，直接通过
- Tool 链路根据 tool_result 组装回复
- fallback 链路生成友好提示

# 关键设计说明
# ─────────────────────────────
# 为什么工具回复在 answer_node 组装而非 tool_node：
# - tool_node 只负责调工具、写数据，不负责自然语言生成
# - 后续接 LLM 润色时，只需要改 answer_node，不改调度逻辑
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
    tool_result: dict | None = state.get("tool_result")
    tool_status: str = state.get("tool_status", "")

    # ── 工具调用链路：根据工具结果组装回复 ──
    if tool_status == "success" and tool_result and tool_result.get("success"):
        reply = _format_tool_reply(intent, tool_result)
        if reply:
            return {"final_answer": reply}

    # ── 工具调用失败 ──
    if tool_status == "error":
        error_msg = tool_result.get("error", "查询失败") if tool_result else "查询失败"
        return {"final_answer": f"抱歉，查询时遇到问题：{error_msg}。请稍后再试或联系客服。"}

    # ── fallback 但上游没生成回复 ──
    if intent == "fallback" and not state.get("final_answer"):
        import random
        reply = _FALLBACK_REPLIES[hash(state.get("message", "")) % len(_FALLBACK_REPLIES)]
        return {"final_answer": reply}

    # ── 其他链路：确保 final_answer 非空 ──
    if not state.get("final_answer"):
        return {"final_answer": "已收到您的请求，请稍候..."}

    return {"final_answer": state["final_answer"]}


def _format_tool_reply(intent: str, result: dict) -> str | None:
    """根据工具结果生成自然语言回复。

    Args:
        intent: 当前意图。
        result: 工具返回的结构化数据（data 字段）。

    Returns:
        自然语言回复字符串，无法生成时返回 None。
    """
    data = result.get("data")
    if not data:
        return None

    if intent == "order_query":
        status_map = {
            "pending": "待发货",
            "shipped": "已发货",
            "delivered": "已签收",
            "refunded": "已退款",
            "cancelled": "已取消",
        }
        cn_status = status_map.get(str(data.get("status", "")), data.get("status", "未知"))
        return (
            f"订单 {data['order_id']} 当前状态为「{cn_status}」。"
            f"商品数量：{data.get('quantity', '?')} 件，"
            f"总金额：{data.get('total_price', '?')} 元。"
        )

    if intent == "size_recommend":
        return f"推荐您选择 {data['size']} 码。{data['reason']}"

    if intent == "refund_request":
        return _format_refund_reply(data, result)

    return None


def _format_refund_reply(data: dict, result: dict) -> str | None:
    """根据退款结果生成回复。

    Args:
        data: 工具返回的 data 字段。
        result: 工具返回的完整结果。

    Returns:
        自然语言回复字符串。
    """
    # 自动审批（≤100 元）
    if data.get("auto_approved"):
        return f"已为您自动处理退款，{data.get('message', '请查收')}。"

    # 创建了人工审核工单（>100 元）
    ticket_id = data.get("ticket_id")
    if ticket_id:
        return (
            f"已为您创建退款工单（编号 {ticket_id}），"
            f"金额超过自动审批限额，需要客服审核后才能处理。"
            f"请耐心等待，审核结果会第一时间通知您。"
        )

    return None
