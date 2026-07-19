"""第二层上下文语义路由器。

使用本地 BGE Embedding 与少量可维护的意图样例进行相似度匹配，不依赖远程
LLM。它支持多标签输出，并将会话状态、可信商品/订单上下文作为路由证据。
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.rag.embeddings import get_embeddings


# 本地 BGE query instruction 与样例中心的余弦分数通常低于通用模型的
# 绝对相似度直觉。以下只是基于本地冒烟样例设置的初始工程阈值，必须再用
# 标注意图集校准，不能据此声称准确率或流量覆盖率。
SEMANTIC_DIRECT_THRESHOLD = 0.52
SEMANTIC_PLANNER_THRESHOLD = 0.40
MULTI_INTENT_MARGIN = 0.05

INTENT_EXAMPLES: dict[str, tuple[str, ...]] = {
    "knowledge_query": (
        "可以退吗", "退货条件是什么", "退款多久到账", "这个怎么清洗",
        "衣服起球正常吗", "适合零下二十度吗", "运费谁承担", "发票怎么开",
        "你们客服几点上班", "这件和另一件哪个好",
    ),
    "product_query": (
        "这件多少钱", "有哪些颜色", "有哪些尺码", "商品是什么面料",
        "这款的价格和颜色", "给我看看商品详情",
    ),
    "inventory_query": (
        "有黑色L码吗", "黑色还有吗", "这件有货吗", "什么时候补货",
        "库存还剩多少", "有现货吗",
    ),
    "size_recommend": (
        "我平时穿L该选什么码", "L码适合多重的人", "帮我推荐尺码",
        "一米七五七十公斤穿多大码", "喜欢宽松一点穿什么码",
    ),
    "order_query": (
        "一般几天到", "订单怎么还没到", "查一下我的订单", "什么时候发货",
        "快递到哪里了", "这个订单是什么状态",
    ),
    "refund_status_query": (
        "我的退款到哪了", "退款进度怎么样", "退款到账了吗", "退款单状态",
    ),
    "refund_request": (
        "帮我申请退款", "我要退订单", "给我办理退货", "帮我退掉这个订单",
    ),
    "after_sales_request": (
        "帮我换成L码", "想换个尺码", "取消这个订单", "我要申请换货",
    ),
    "human_handoff": (
        "转人工", "我要人工客服", "帮我联系人工", "找人工客服",
    ),
}

WRITE_INTENTS = frozenset({"refund_request", "after_sales_request"})


@dataclass(frozen=True)
class SemanticRouteResult:
    intents: list[str]
    confidence: float
    source: str
    evidence: list[str]
    requires_planning: bool


class ContextualSemanticRouter:
    def route(
        self,
        *,
        message: str,
        pending_intent: str | None,
        chat_context: dict | None,
        collected_slots: dict | None,
        recent_messages: list[str] | None = None,
    ) -> SemanticRouteResult | None:
        enriched, evidence = _enrich_message(
            message=message,
            pending_intent=pending_intent,
            chat_context=chat_context,
            collected_slots=collected_slots,
            recent_messages=recent_messages,
        )
        try:
            scores = _semantic_scores(enriched)
        except Exception:
            return None
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if not ranked:
            return None
        best_intent, best_score = ranked[0]
        intents = [best_intent]
        for intent, score in ranked[1:]:
            if (
                intent not in WRITE_INTENTS
                and best_intent not in WRITE_INTENTS
                and score >= SEMANTIC_PLANNER_THRESHOLD
                and best_score - score <= MULTI_INTENT_MARGIN
            ):
                intents.append(intent)
        requires_planning = (
            len(intents) > 1
            or best_score < SEMANTIC_DIRECT_THRESHOLD
            or best_intent in WRITE_INTENTS
        )
        return SemanticRouteResult(
            intents=intents,
            confidence=round(float(best_score), 4),
            source="semantic_router",
            evidence=evidence + [f"语义样例匹配:{best_intent}"],
            requires_planning=requires_planning,
        )


@lru_cache(maxsize=1)
def _example_vectors() -> dict[str, np.ndarray]:
    embeddings = get_embeddings()
    result: dict[str, np.ndarray] = {}
    for intent, examples in INTENT_EXAMPLES.items():
        vectors = np.asarray(embeddings.embed_documents(list(examples)), dtype=float)
        centroid = vectors.mean(axis=0)
        norm = np.linalg.norm(centroid) or 1.0
        result[intent] = centroid / norm
    return result


def _semantic_scores(message: str) -> dict[str, float]:
    query = np.asarray(get_embeddings().embed_query(message), dtype=float)
    query_norm = np.linalg.norm(query) or 1.0
    query = query / query_norm
    return {
        intent: float(np.dot(query, vector))
        for intent, vector in _example_vectors().items()
    }


def _enrich_message(
    *,
    message: str,
    pending_intent: str | None,
    chat_context: dict | None,
    collected_slots: dict | None,
    recent_messages: list[str] | None,
) -> tuple[str, list[str]]:
    parts = [message.strip()]
    evidence: list[str] = []
    context = chat_context or {}
    if pending_intent:
        parts.append(f"待补充意图:{pending_intent}")
        evidence.append(f"待补充意图:{pending_intent}")
    if context.get("context_type") == "product":
        parts.append(f"当前商品:{context.get('product_name', '')}")
        evidence.append("当前商品上下文")
    elif context.get("context_type") == "order":
        parts.append(f"当前订单:{context.get('order_id', '')}")
        evidence.append("当前订单上下文")
    if collected_slots:
        parts.append(f"已收集参数:{','.join(sorted(collected_slots))}")
        evidence.append("已收集槽位")
    if recent_messages:
        parts.append("最近对话:" + " | ".join(recent_messages[-3:]))
        evidence.append("最近对话历史")
    return "\n".join(part for part in parts if part), evidence


semantic_router = ContextualSemanticRouter()
