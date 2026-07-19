"""第一层高精度意图规则。

规则层只处理命令式、上下文明确或几乎无歧义的请求。模糊表达留给
上下文语义路由和 LLM Planner，尤其不能因为出现“退款”二字就执行写操作。
"""

import re
from collections.abc import Iterable


READONLY_INTENTS = frozenset({
    "knowledge_query",
    "product_query",
    "order_query",
    "refund_status_query",
    "inventory_query",
    "size_recommend",
})

GREETING_KEYWORDS = ("你好", "您好", "在吗", "嗨", "哈喽", "hello", "hi")
THANKS_OR_GOODBYE = ("谢谢", "感谢", "再见", "拜拜")
HUMAN_HANDOFF_PATTERNS = (
    r"^(?:请|麻烦)?(?:帮我)?转(?:接)?人工(?:客服)?[。！! ]*$",
    r"^(?:我要|找|联系)人工(?:客服)?[。！! ]*$",
)

EXPLICIT_REFUND_PATTERNS = (
    r"(?:帮我|给我|替我|我要|我想|申请|办理|发起).{0,8}(?:退款|退货)",
    r"(?:退款|退货).{0,8}(?:申请|办理|发起)",
    r"(?:帮我|给我|替我|我要|我想).{0,4}退(?:掉)?(?:这个|该)?订单\s*\d*",
)
AFTER_SALES_WRITE_PATTERNS = (
    r"(?:帮我|给我|替我|我要|我想|申请|办理|发起).{0,8}(?:换货|换码|换尺码|取消订单)",
    r"(?:换成|改成).{0,6}[0-9A-Za-z]{1,4}码",
    r"取消.{0,6}订单|订单.{0,6}取消",
)
REFUND_STATUS_PATTERNS = (
    r"(?:我的|这笔|订单\s*\d+的?).{0,6}退款.{0,8}(?:进度|状态|到哪|到账|成功|处理)",
    r"退款单.{0,8}(?:进度|状态|到哪|到账|成功|处理)",
)
POLICY_PATTERNS = (
    r"(?:退款|退货|换货).{0,8}(?:规则|政策|条件|期限|要求|流程|多久到账)",
    r"(?:规则|政策|条件|期限|要求|流程).{0,8}(?:退款|退货|换货)",
    r"七天无理由|运费.{0,6}(?:多少|谁出|规则)|发票.{0,6}(?:怎么|如何|能否)",
)
ORDER_PATTERNS = (
    r"(?:查|查询|看看|我的|这个).{0,6}订单",
    r"订单\s*\d+.{0,10}(?:状态|发货|物流|快递|到哪|没到|签收)",
    r"(?:发货|物流|快递).{0,8}(?:了吗|状态|到哪|查询|查一下)",
)
INVENTORY_PATTERNS = (
    r"(?:库存|现货).{0,6}(?:多少|有吗|还有|查询|查一下)",
    r"(?:还有|有没有|是否有).{0,4}(?:库存|现货)",
    r"(?:有货|还有货|缺货|补货)",
)
PRODUCT_PATTERNS = (
    r"(?:这件|这个|商品\s*\d+).{0,8}(?:多少钱|价格|售价|颜色|哪些尺码|尺码范围)",
    r"(?:多少钱|什么价格|有哪些颜色|哪些颜色|有哪些尺码|哪些尺码)",
)
SIZE_PATTERNS = (
    r"(?:穿|选|推荐).{0,8}(?:什么码|多大码|哪个码|哪一码)",
    r"(?:身高|体重).{0,20}(?:尺码|穿|选|推荐)",
)
KNOWLEDGE_PATTERNS = (
    r"(?:材质|面料|成分|洗护|怎么洗|保暖|防风|防水|起球|掉色).{0,10}(?:吗|么|如何|怎么|正常|效果)?",
    r"(?:适合|能穿).{0,10}(?:冬天|东北|零下|多少度)",
    r"客服.{0,8}(?:几点|时间|上班)",
)


def detect_all_intents(message: str) -> list[str]:
    normalized = _normalize(message)
    if not normalized:
        return ["fallback"]

    if _matches_any(normalized, HUMAN_HANDOFF_PATTERNS):
        return ["human_handoff"]
    if _matches_any(normalized, AFTER_SALES_WRITE_PATTERNS):
        return ["after_sales_request"]
    if _matches_any(normalized, EXPLICIT_REFUND_PATTERNS):
        return ["refund_request"]
    if _matches_any(normalized, REFUND_STATUS_PATTERNS):
        return ["refund_status_query"]

    intents: list[str] = []
    for intent, patterns in (
        ("knowledge_query", POLICY_PATTERNS),
        ("order_query", ORDER_PATTERNS),
        ("inventory_query", INVENTORY_PATTERNS),
        ("product_query", PRODUCT_PATTERNS),
        ("size_recommend", SIZE_PATTERNS),
        ("knowledge_query", KNOWLEDGE_PATTERNS),
    ):
        if _matches_any(normalized, patterns):
            intents.append(intent)

    if _looks_like_size_measurements(normalized):
        intents.append("size_recommend")

    if _contains_any(normalized, GREETING_KEYWORDS + THANKS_OR_GOODBYE):
        intents.append("fallback")
    return _deduplicate(intents)


def classify_by_rules(message: str) -> str | None:
    intents = detect_all_intents(message)
    for protected_intent in (
        "human_handoff",
        "after_sales_request",
        "refund_request",
        "refund_status_query",
    ):
        if protected_intent in intents:
            return protected_intent

    readonly = {intent for intent in intents if intent in READONLY_INTENTS}
    if len(readonly) > 1:
        return "composite_query"
    if len(readonly) == 1:
        return next(iter(readonly))
    if "fallback" in intents:
        return "fallback"
    return None


def is_explicit_refund_action(message: str) -> bool:
    return _matches_any(_normalize(message), EXPLICIT_REFUND_PATTERNS)


def is_after_sales_write_action(message: str) -> bool:
    return _matches_any(_normalize(message), AFTER_SALES_WRITE_PATTERNS)


def _normalize(message: str) -> str:
    return " ".join(str(message or "").strip().lower().split())


def _matches_any(message: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, message, flags=re.IGNORECASE) for pattern in patterns)


def _contains_any(message: str, keywords: Iterable[str]) -> bool:
    return any(keyword in message for keyword in keywords)


def _deduplicate(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _looks_like_size_measurements(message: str) -> bool:
    height = r"(?:\d{3}\s*(?:cm|厘米|公分)|[12]\s*(?:米|m)\s*\d{2})"
    weight = r"\d{2,3}\s*(?:kg|公斤|千克|斤)"
    return bool(
        re.search(height, message, flags=re.IGNORECASE)
        or re.search(weight, message, flags=re.IGNORECASE)
    )
