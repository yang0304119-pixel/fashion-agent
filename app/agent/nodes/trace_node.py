"""
Trace 节点 — 工作流收尾节点

在 answer_node 之后执行，更新预先创建的请求汇总 Trace，
fallback 或低置信度同时写入 unresolved_case 表。

# 关键设计说明
# ─────────────────────────────
# 每个节点由统一包装器记录Step，trace_node只负责汇总收尾。
# 写入失败不影响主流程，Trace是附加能力不是核心依赖。
# ─────────────────────────────
"""

from app.agent.state import AgentState
from app.services.trace_service import finalize_request_trace, record_unresolved


def trace_node(state: AgentState) -> dict:
    """Trace 节点：记录请求日志和未解决问题。

    纯副作用操作，不修改 state，写入失败不影响主流程。

    Args:
        state: 当前 AgentState。

    Returns:
        空字典（trace 是副作用，不修改 state）。
    """
    finalize_request_trace(state)
    record_unresolved(state)

    # Trace 是纯副作用，不修改 state
    return {}
