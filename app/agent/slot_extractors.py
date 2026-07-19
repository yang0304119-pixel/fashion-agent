"""确定性节点共享的槽位提取函数。"""

import re
from dataclasses import dataclass
from typing import Any

from app.tools._utils import extract_order_id


PRODUCT_NAME_MAP: tuple[tuple[tuple[str, ...], int], ...] = (
    (("极寒", "加厚"), 1),
    (("轻薄", "都市"), 2),
    (("三合一", "冲锋"), 3),
    (("商务", "修身"), 4),
    (("连帽", "短款"), 5),
    (("加长", "长款"), 6),
    (("围巾", "羊毛"), 7),
)

REQUIRED_SLOTS: dict[str, tuple[str, ...]] = {
    "order_query": ("order_id",),
    "inventory_query": ("product_id",),
    "size_recommend": ("height", "weight"),
    "refund_request": ("order_id",),
}


@dataclass(frozen=True)
class SizeSlots:
    height: int | None
    weight: int | None
    style: str


def extract_product_id(message: str) -> int | None:
    patterns = (
        r"商品[号#\s]*(\d+)",
        r"商品编号[\s:：]*(\d+)",
        r"[iI][dD][\s:：]*(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))

    for keywords, product_id in PRODUCT_NAME_MAP:
        if any(keyword in message for keyword in keywords):
            return product_id
    return None


def extract_size_slots(message: str) -> SizeSlots:
    height = _extract_height(message)
    weight = _extract_weight(message)

    if any(keyword in message for keyword in ("修身", "贴身")):
        style = "修身"
    elif any(keyword in message for keyword in ("宽松", "休闲")):
        style = "宽松"
    else:
        style = "标准"

    return SizeSlots(height=height, weight=weight, style=style)


def collect_slots(
    intent: str,
    message: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将当前消息中新出现的槽位合并到历史槽位。"""
    collected = dict(existing or {})

    if intent in {"order_query", "refund_request"}:
        order_id = extract_order_id(message) or _extract_bare_integer(
            message,
            minimum_digits=5,
        )
        if order_id is not None:
            collected["order_id"] = order_id

    if intent == "inventory_query":
        product_id = extract_product_id(message) or _extract_bare_integer(
            message,
            minimum_digits=1,
        )
        if product_id is not None:
            collected["product_id"] = product_id

    if intent == "size_recommend":
        size_slots = extract_size_slots(message)
        if size_slots.height is not None:
            collected["height"] = size_slots.height
        if size_slots.weight is not None:
            collected["weight"] = size_slots.weight
        explicit_style = _extract_explicit_style(message)
        if explicit_style is not None:
            collected["style"] = explicit_style

    if intent == "refund_request":
        reason = extract_refund_reason(message)
        if reason is not None:
            collected["reason"] = reason

    return collected


def missing_slots_for_intent(
    intent: str,
    collected_slots: dict[str, Any],
) -> list[str]:
    """返回指定意图仍未收集的必填槽位。"""
    return [
        slot
        for slot in REQUIRED_SLOTS.get(intent, ())
        if collected_slots.get(slot) is None
    ]


def extract_refund_reason(message: str) -> str | None:
    reasons = {
        "质量问题": ("质量问题", "破了", "坏了", "破损", "脱线", "起球", "褪色", "掉色"),
        "发错货": ("发错", "发的不对", "不是我买的", "错发"),
        "不想要了": ("不想要了", "不喜欢", "买错了", "后悔了"),
        "尺寸不合适": ("太大", "太小", "不合身", "穿不了", "太紧", "太松"),
    }
    for category, keywords in reasons.items():
        if any(keyword in message for keyword in keywords):
            return category
    return None


def _extract_height(message: str) -> int | None:
    centimeters = re.search(
        r"(\d{3})\s*(?:cm|厘米|公分)",
        message,
        flags=re.IGNORECASE,
    )
    if centimeters:
        return int(centimeters.group(1))

    meters = re.search(r"([12])\s*(?:米|m)\s*(\d{2})", message)
    if meters:
        return int(meters.group(1)) * 100 + int(meters.group(2))
    return None


def _extract_weight(message: str) -> int | None:
    kilograms = re.search(
        r"(\d{2,3})\s*(?:kg|公斤|千克)",
        message,
        flags=re.IGNORECASE,
    )
    if kilograms:
        return int(kilograms.group(1))

    jin = re.search(r"(\d{2,3})\s*斤", message)
    if jin:
        return round(int(jin.group(1)) / 2)
    return None


def _extract_explicit_style(message: str) -> str | None:
    if any(keyword in message for keyword in ("修身", "贴身")):
        return "修身"
    if any(keyword in message for keyword in ("宽松", "休闲")):
        return "宽松"
    if "标准" in message:
        return "标准"
    return None


def _extract_bare_integer(
    message: str,
    *,
    minimum_digits: int,
) -> int | None:
    match = re.fullmatch(rf"\s*(\d{{{minimum_digits},}})\s*[号#]?\s*", message)
    if match:
        return int(match.group(1))
    return None
