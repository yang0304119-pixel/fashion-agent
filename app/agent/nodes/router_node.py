"""
意图路由节点

采用"规则优先 + LLM 兜底"的混合策略判断用户意图：
1. 先过关键词规则（零成本、可解释、高置信度）
2. 未命中则调 LLM 语义分类
3. 仍无法识别 → fallback

# 关键设计说明
# ─────────────────────────────
# 为什么规则优先于 LLM：
# - 关键词匹配 0 成本、0 延迟，LLM 调用有费用和延迟
# - 规则命中直接输出高置信度（0.95），无需 LLM 确认
# - 规则可解释、可调试；LLM 分类可能出现意外结果
# 为什么路由和分类放一个函数而非两个：
# - 调用方只需要"给我意图"，不需要知道内部是规则还是 LLM
# - 后续加规则或改 prompt 只需要改这一个文件
# ─────────────────────────────
"""

import logging

from openai import OpenAI

from app.agent.intent_rules import classify_by_rules
from app.agent.slot_extractors import collect_slots, missing_slots_for_intent
from app.agent.state import AgentState
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.conversation_state_service import ConversationStateService


logger = logging.getLogger(__name__)

# LLM 意图分类 prompt（只输出意图名称，方便解析）
_CLASSIFY_PROMPT: str = """你是一个服装电商客服意图分类器。
请判断用户输入的意图，只输出以下 intent 名称之一，不要输出其他内容：

- knowledge_query: 询问商品知识、面料材质、洗护方式、产品详情
- size_recommend: 询问尺码推荐、身高体重对应尺码
- order_query: 查询订单状态、物流信息、发货情况
- refund_request: 申请退款、退货、质量问题售后
- inventory_query: 查询商品库存、是否有货
- fallback: 闲聊、问候、非业务问题或无法判断

用户输入：{message}

intent："""


def router_node(state: AgentState) -> dict:
    """意图路由节点：规则匹配 → LLM 兜底 → 输出 intent 和置信度。

    Args:
        state: 当前 AgentState，至少包含 message 字段。

    Returns:
        更新 state 的字典，包含：
        - intent: 识别的意图
        - confidence: 置信度（0~1）
        - missing_slots: 缺失的槽位（如需要订单号但未提供）
    """
    message: str = state.get("message", "").strip()

    if not message:
        return {
            "intent": "fallback",
            "confidence": 1.0,
            "missing_slots": [],
        }

    # ── 阶段 0：恢复上一轮待补参数 ──
    pending_result = _resume_pending_conversation(state, message)
    if pending_result is not None:
        return pending_result

    # ── 阶段 1：关键词规则匹配 ──
    matched = classify_by_rules(message)
    if matched:
        return {
            "intent": matched,
            "confidence": 0.95,
            "missing_slots": [],
        }

    # ── 阶段 2：LLM 语义分类 ──
    intent, confidence = _classify_by_llm(message)

    return {
        "intent": intent,
        "confidence": confidence,
        "missing_slots": [],
    }


def _resume_pending_conversation(
    state: AgentState,
    message: str,
) -> dict | None:
    tenant_id = state.get("tenant_id", 0)
    user_id = state.get("user_id", 0)
    session_id = state.get("session_id", "")
    if not tenant_id or not user_id or not session_id:
        return None

    db = SessionLocal()
    try:
        pending = ConversationStateService(db).load_active(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        db.rollback()
        logger.exception("读取待补槽位会话失败，降级为普通意图分类")
        return None
    finally:
        db.close()

    if pending is None:
        return None

    context_type = (state.get("chat_context") or {}).get("context_type")
    if _context_conflicts_with_pending(context_type, pending.pending_intent):
        return None

    current_rule_intent = classify_by_rules(message)
    existing_slots = dict(pending.collected_slots)
    existing_slots.update(state.get("collected_slots") or {})
    collected_slots = collect_slots(
        pending.pending_intent,
        message,
        existing_slots,
    )

    # 明确表达了另一个意图时允许换话题。退款流程回复“订单10001”会被
    # 规则识别成订单查询，但它实际上是在补退款所需的order_id。
    compatible_followup = (
        current_rule_intent in {None, pending.pending_intent}
        or (
            pending.pending_intent == "refund_request"
            and current_rule_intent == "order_query"
            and collected_slots.get("order_id") is not None
            and not any(
                keyword in message
                for keyword in ("查询", "查一下", "发货", "物流", "快递", "状态")
            )
        )
    )
    if not compatible_followup:
        return None

    return {
        "intent": pending.pending_intent,
        "pending_intent": pending.pending_intent,
        "confidence": 1.0,
        "missing_slots": missing_slots_for_intent(
            pending.pending_intent,
            collected_slots,
        ),
        "collected_slots": collected_slots,
    }


def _context_conflicts_with_pending(
    context_type: str | None,
    pending_intent: str,
) -> bool:
    if context_type == "product":
        return pending_intent in {"order_query", "refund_request"}
    if context_type == "order":
        return pending_intent in {"inventory_query", "size_recommend"}
    return False


def _classify_by_llm(message: str) -> tuple[str, float]:
    """LLM 语义分类，返回 (intent, confidence)。

    调用 DeepSeek 等兼容 OpenAI 格式的模型，
    解析 LLM 输出为意图名称和置信度。

    Returns:
        (intent, confidence)，识别失败时返回 ("fallback", 0.0)。
    """
    try:
        client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_API_BASE,
        )
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(message=message)}],
            max_tokens=20,
            temperature=0,
        )
        raw = response.choices[0].message.content.strip().lower()

        # 解析 LLM 输出
        valid_intents = {"knowledge_query", "size_recommend", "order_query", "refund_request", "inventory_query", "fallback"}
        if raw in valid_intents:
            return raw, 0.85

        # LLM 输出不在预期范围内，尝试模糊匹配
        for intent in valid_intents:
            if intent in raw or raw in intent:
                return intent, 0.80

        return "fallback", 0.3

    except Exception:
        # LLM 调用失败时 fallback 降级
        return "fallback", 0.0
