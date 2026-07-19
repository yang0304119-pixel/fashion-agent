"""零成本、可测试的客服意图规则。

这里只负责识别消息中出现的所有业务意图，并决定哪些消息可以进入
组合型只读 ReAct。退款始终拥有最高优先级，问候不参与组合意图计数。
"""

import re
from collections.abc import Iterable


POLICY_KEYWORDS = (
    "退款规则",
    "退款政策",
    "退货规则",
    "退货政策",
    "换货规则",
    "售后规则",
    "七天无理由",
)

REFUND_ACTION_KEYWORDS = (
    "申请退款",
    "我要退款",
    "想退款",
    "办理退款",
    "给我退款",
    "申请退货",
    "我要退货",
    "想退货",
    "不想要了",
    "质量问题",
    "起球",
    "破损",
)

PRODUCT_DETAIL_KEYWORDS = (
    "多少钱",
    "价格",
    "售价",
    "什么颜色",
    "哪些颜色",
    "可选颜色",
    "有哪些尺码",
    "哪些尺码",
    "可选尺码",
    "尺码范围",
)

INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("order_query", ("订单", "发货", "物流", "快递")),
    ("size_recommend", ("身高", "体重", "尺码", "穿什么码", "穿多大码")),
    ("inventory_query", ("库存", "有货", "现货", "还有吗")),
    (
        "knowledge_query",
        (
            "材质", "面料", "保暖", "洗护", "怎么洗", "成分", "款式",
            "适合", "东北", "冬天", "防风", "防水", "怎么搭",
        ),
    ),
)

FALLBACK_KEYWORDS = (
    "你好",
    "您好",
    "在吗",
    "嗨",
    "哈喽",
    "谢谢",
    "再见",
    "hello",
)

COMPOSITE_CAPABLE_INTENTS = frozenset(
    {
        "knowledge_query",
        "order_query",
        "inventory_query",
        "size_recommend",
    }
)


def detect_all_intents(message: str) -> list[str]:
    """返回消息命中的全部意图，顺序稳定且不重复。"""
    normalized = message.strip().lower()
    if not normalized:
        return ["fallback"]

    intents: list[str] = []

    policy_query = _contains_any(normalized, POLICY_KEYWORDS)
    if policy_query:
        intents.append("knowledge_query")

    message_without_policy = _remove_phrases(normalized, POLICY_KEYWORDS)
    if _is_refund_request(message_without_policy):
        intents.append("refund_request")

    product_detail_query = _contains_any(normalized, PRODUCT_DETAIL_KEYWORDS)
    if product_detail_query:
        intents.append("inventory_query")
    if _looks_like_size_measurements(normalized):
        intents.append("size_recommend")

    for intent, keywords in INTENT_KEYWORDS:
        if intent == "knowledge_query" and policy_query:
            continue
        if product_detail_query and intent in {"inventory_query", "size_recommend"}:
            continue
        if _contains_any(normalized, keywords):
            intents.append(intent)

    if _contains_any(normalized, FALLBACK_KEYWORDS):
        intents.append("fallback")

    return _deduplicate(intents)


def classify_by_rules(message: str) -> str | None:
    """按安全优先级将规则命中归并为一个路由意图。

    退款申请不论还命中多少只读意图都进入确定性退款工作流。只有
    ReAct 白名单覆盖的多个只读意图才会返回 ``composite_query``。
    """
    intents = detect_all_intents(message)

    if "refund_request" in intents:
        return "refund_request"

    readonly_intents = {
        intent for intent in intents if intent in COMPOSITE_CAPABLE_INTENTS
    }

    # 退款/售后政策应由RAG回答，不能被组合路由带入只读业务ReAct。
    if _contains_any(message.lower(), POLICY_KEYWORDS):
        return "knowledge_query"

    if len(readonly_intents) > 1:
        return "composite_query"
    if len(readonly_intents) == 1:
        return next(iter(readonly_intents))
    if "fallback" in intents:
        return "fallback"
    return None


def _is_refund_request(message_without_policy: str) -> bool:
    if _contains_any(message_without_policy, REFUND_ACTION_KEYWORDS):
        return True
    return "退款" in message_without_policy or "退货" in message_without_policy


def _contains_any(message: str, keywords: Iterable[str]) -> bool:
    return any(keyword in message for keyword in keywords)


def _remove_phrases(message: str, phrases: Iterable[str]) -> str:
    for phrase in phrases:
        message = message.replace(phrase, "")
    return message


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _looks_like_size_measurements(message: str) -> bool:
    height_pattern = r"(?:\d{3}\s*(?:cm|厘米|公分)|[12]\s*(?:米|m)\s*\d{2})"
    weight_pattern = r"\d{2,3}\s*(?:kg|公斤|千克|斤)"
    return bool(
        re.search(height_pattern, message, flags=re.IGNORECASE)
        or re.search(weight_pattern, message, flags=re.IGNORECASE)
    )
