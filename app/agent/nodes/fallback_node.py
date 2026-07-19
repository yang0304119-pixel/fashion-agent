"""零LLM成本的问候、致谢、告别和无法识别问题兜底节点。"""

import re

from app.agent.state import AgentState


GREETING_MESSAGES = {
    "你好",
    "您好",
    "在吗",
    "嗨",
    "哈喽",
    "hello",
    "hi",
}
THANK_MESSAGES = {"谢谢", "感谢", "多谢", "谢谢你"}
GOODBYE_MESSAGES = {"再见", "拜拜", "下次见"}


def fallback_node(state: AgentState) -> dict:
    """对常见闲聊使用固定回复，其余问题给出业务范围引导。"""
    message = _normalize_message(state.get("message", ""))

    if state.get("clarification_question"):
        return _response(str(state["clarification_question"]), handled=True)

    if message in GREETING_MESSAGES:
        return _response(
            "您好，我可以帮您查询订单、库存、推荐尺码，"
            "也可以处理退款和商品知识咨询。",
            handled=True,
        )

    if message in THANK_MESSAGES:
        return _response(
            "不客气。如果还需要查询订单、库存、尺码或处理退款，"
            "可以继续告诉我。",
            handled=True,
        )

    if message in GOODBYE_MESSAGES:
        return _response("好的，再见！有需要时随时联系我。", handled=True)

    return _response(
        "抱歉，我没有理解您的问题。您可以提供订单号，"
        "或者咨询商品、库存、尺码和退款。",
        handled=False,
    )


def _response(answer: str, *, handled: bool) -> dict:
    return {
        "missing_slots": [],
        "tool_result": None,
        "tool_status": "skipped",
        "fallback_handled": handled,
        "final_answer": answer,
    }


def _normalize_message(message: str) -> str:
    normalized = message.strip().lower()
    return re.sub(r"[\s，。！？,.!?~～]+$", "", normalized)
