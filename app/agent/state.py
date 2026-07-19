"""
Agent 状态定义

LangGraph 工作流中所有节点共用的数据结构。
Phase 3 只用到当前字段，其余在后续 Phase 逐步追加。

# 关键设计说明
# ─────────────────────────────
# 为什么用 TypedDict 而非 Pydantic BaseModel：
# - LangGraph 原生推荐 TypedDict，与 StateGraph 配合最紧密
# - TypedDict 轻量，不需要额外的序列化/反序列化
# - Phase 3 阶段字段少，不需要 Pydantic 的校验能力
# 权衡：
# - TypedDict 无运行时校验，传入错误类型不会自动报错
# - 后续字段增多可考虑迁移到 Pydantic BaseModel
# ─────────────────────────────
"""

from typing import Any, TypedDict


class AgentState(TypedDict):
    """Agent 工作流的共享状态，所有节点读取和写入此结构。

    Phase 3 基础字段：session_id / user_id / message / intent / confidence
    Phase 4 追加：tool_result / tool_status
    Phase 5 追加：risk_level / human_required
    """
    # ── 基础信息 ──
    session_id: str
    user_id: int
    tenant_id: int
    message: str
    trace_id: int | None

    # ── 路由结果（Phase 3 核心） ──
    intent: str                 # knowledge/order/inventory/size/refund/composite/fallback
    confidence: float           # 0~1
    missing_slots: list[str]    # 需要的参数缺失（如订单号、身高体重）
    pending_intent: str | None  # 上一轮等待补参的确定性业务意图
    collected_slots: dict       # 当前会话已经收集并验证的槽位
    chat_context: dict[str, Any] | None  # 服务端重新查询后的可信卡片上下文

    # ── RAG 检索结果（Phase 2） ──
    retrieved_docs: list[str]
    retrieved_doc_ids: list[str]
    retrieved_scores: list[float]
    retrieved_sources: list[dict[str, str]]
    rag_error_code: str | None
    rag_error_stage: str | None
    rag_error_type: str | None

    # ── 工具调用（Phase 4） ──
    tool_result: dict | None          # 工具返回的结构化数据
    tool_status: str                  # success / error / pending

    # ── 退款流程（Phase 5） ──
    risk_level: str                   # low / medium / high
    human_required: bool              # 是否需要人工审核
    refund_request_id: int
    refund_status: str

    # ── 固定Fallback是否已成功处理问候/致谢等闲聊 ──
    fallback_handled: bool

    # ── 最终回复 ──
    final_answer: str

    # ── Phase 5 会追加：risk_level, human_required ──
