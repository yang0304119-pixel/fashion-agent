"""
Trace 节点 — 工作流收尾节点

在 answer_node 之后执行，将请求完整状态写入 agent_trace 表，
fallback 或低置信度同时写入 unresolved_case 表。

# 关键设计说明
# ─────────────────────────────
# 为什么 trace_node 放在最后而非嵌入每个节点：
# - 不干扰业务节点的逻辑（router/rag/tool 只需要管自己的事）
# - 如果后续需要节点级追踪，加中间件模式即可
# - 写入失败不影响主流程，Trace 是附加能力不是核心依赖
# ─────────────────────────────
"""

from app.agent.state import AgentState
from app.services.trace_service import record_trace, record_unresolved


def trace_node(state: AgentState) -> dict:
    """Trace 节点：记录请求日志和未解决问题。

    纯副作用操作，不修改 state，写入失败不影响主流程。

    Args:
        state: 当前 AgentState。

    Returns:
        空字典（trace 是副作用，不修改 state）。
    """
    record_trace(state)
    record_unresolved(state)

    # Trace 是纯副作用，不修改 state
    return {}
