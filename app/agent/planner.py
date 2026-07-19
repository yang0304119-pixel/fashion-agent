"""第三层结构化 LLM Planner，只负责理解和生成只读执行计划。"""

import json
from dataclasses import dataclass

from openai import OpenAI

from app.core.config import settings


READONLY_INTENTS = frozenset({
    "knowledge_query",
    "product_query",
    "inventory_query",
    "size_recommend",
    "order_query",
    "refund_status_query",
})
PROTECTED_INTENTS = frozenset({
    "refund_request",
    "after_sales_request",
    "human_handoff",
})
ALL_INTENTS = READONLY_INTENTS | PROTECTED_INTENTS | {"fallback"}


@dataclass(frozen=True)
class PlannerDecision:
    intents: list[str]
    confidence: float
    evidence: list[str]
    requires_clarification: bool
    clarification_question: str | None


def plan_intents(
    *,
    message: str,
    semantic_intents: list[str],
    context_summary: str,
) -> PlannerDecision | None:
    if not settings.LLM_API_KEY:
        return None
    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
    )
    prompt = f"""你是电商客服路由 Planner。只输出 JSON，不执行工具。
允许意图：{sorted(ALL_INTENTS)}
规则：
1. refund_request 仅用于用户明确要求申请/办理退款或退货。
2. after_sales_request 用于换货、换尺码、取消订单等当前必须转人工的写操作。
3. refund_status_query 是查询已有退款进度，不能重新发起退款。
4. 支持多个只读意图；写意图不能和只读工具混合自动执行。
5. 表达不清时 requires_clarification=true，并给出简短追问。

上下文：{context_summary or '无'}
语义路由候选：{semantic_intents}
用户输入：{message}

输出格式：
{{"intents":["intent"],"confidence":0.0,"evidence":["原因"],"requires_clarification":false,"clarification_question":null}}
"""
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return None
        payload = json.loads(raw)
    except Exception:
        return None
    intents = [
        str(intent)
        for intent in payload.get("intents", [])
        if str(intent) in ALL_INTENTS
    ]
    if not intents:
        intents = ["fallback"]
    try:
        confidence = max(0.0, min(float(payload.get("confidence", 0.0)), 1.0))
    except (TypeError, ValueError):
        confidence = 0.0
    raw_evidence = payload.get("evidence", [])
    if not isinstance(raw_evidence, list):
        raw_evidence = []
    return PlannerDecision(
        intents=list(dict.fromkeys(intents)),
        confidence=confidence,
        evidence=[str(value)[:200] for value in raw_evidence[:5]],
        requires_clarification=bool(payload.get("requires_clarification", False)),
        clarification_question=(
            str(payload.get("clarification_question", "")).strip() or None
        ),
    )
