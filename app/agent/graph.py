"""
LangGraph 工作流定义

当前主流程：
  用户输入 → Router → 确定性业务节点 / RAG / RefundWorkflow / ReAct
  → Answer → ConversationState → Trace

# 关键设计说明
# ─────────────────────────────
# 退款单独路由的原因：
# - 退款涉及身份、金额、幂等、审批和状态变化，不能由LLM自主编排
# - RefundService在单一事务边界内执行确定性业务规则
# - 当前有意保持单节点Workflow；只有需要长时暂停、自动恢复、重试或
#   节点级可视化时，才升级为LangGraph退款子图
# 订单、库存、尺码单独路由的原因：
# - 单一业务意图不需要LLM自主选择工具，固定节点更快、更便宜、更可测
# - ReAct保留给下一步的组合型只读问题，普通fallback不再调用LLM
# ─────────────────────────────
"""

from langgraph.graph import StateGraph

from app.agent.routing import route_by_intent
from app.agent.state import AgentState
from app.agent.nodes.fallback_node import fallback_node
from app.agent.nodes.inventory_node import inventory_node
from app.agent.nodes.order_node import order_node
from app.agent.nodes.router_node import router_node
from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.react_node import react_node
from app.agent.nodes.refund_node import refund_node
from app.agent.nodes.size_node import size_node
from app.agent.nodes.handoff_node import handoff_node
from app.agent.nodes.refund_status_node import refund_status_node
from app.agent.nodes.trace_node import trace_node
from app.agent.nodes.answer_node import answer_node
from app.agent.nodes.conversation_state_node import conversation_state_node
from app.agent.nodes.memory_load_node import memory_load_node
from app.agent.nodes.memory_retrieve_node import memory_retrieve_node
from app.agent.nodes.memory_commit_node import memory_commit_node
from app.agent.nodes.boundary_guard_node import boundary_guard_node, route_after_goal_guard
from app.services.trace_service import traced_node


# ── 构建工作流 ──

workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("memory_load", traced_node("memory_load", memory_load_node))
workflow.add_node("goal_guard", traced_node("goal_guard", boundary_guard_node))
workflow.add_node("router", traced_node("router", router_node))
workflow.add_node("boundary_guard", traced_node("boundary_guard", boundary_guard_node))
workflow.add_node("memory_retrieve", traced_node("memory_retrieve", memory_retrieve_node))
workflow.add_node("rag", traced_node("rag", rag_node))
workflow.add_node("react", traced_node("react", react_node))
workflow.add_node("refund", traced_node("refund", refund_node))
workflow.add_node("fallback", traced_node("fallback", fallback_node))
workflow.add_node("order", traced_node("order", order_node))
workflow.add_node("inventory", traced_node("inventory", inventory_node))
workflow.add_node("size", traced_node("size", size_node))
workflow.add_node("handoff", traced_node("handoff", handoff_node))
workflow.add_node(
    "refund_status",
    traced_node("refund_status", refund_status_node),
)
workflow.add_node("answer", traced_node("answer", answer_node))
workflow.add_node("memory_commit", traced_node("memory_commit", memory_commit_node))
workflow.add_node(
    "conversation_state",
    traced_node("conversation_state", conversation_state_node),
)
workflow.add_node("trace", traced_node("trace", trace_node))

# 设置入口
workflow.set_entry_point("goal_guard")
workflow.add_conditional_edges(
    "goal_guard",
    route_after_goal_guard,
    {"continue": "memory_load", "handoff": "handoff"},
)
workflow.add_edge("memory_load", "router")
workflow.add_edge("router", "boundary_guard")
workflow.add_edge("boundary_guard", "memory_retrieve")

# 条件路由：router 的输出决定下一步
workflow.add_conditional_edges(
    "memory_retrieve",
    route_by_intent,
    {
        "rag": "rag",
        "react": "react",
        "refund": "refund",
        "fallback": "fallback",
        "order": "order",
        "inventory": "inventory",
        "size": "size",
        "handoff": "handoff",
        "refund_status": "refund_status",
    },
)

# 所有业务节点完成后统一进入Answer和Trace
workflow.add_edge("rag", "answer")
workflow.add_edge("react", "answer")
workflow.add_edge("refund", "answer")
workflow.add_edge("fallback", "answer")
workflow.add_edge("order", "answer")
workflow.add_edge("inventory", "answer")
workflow.add_edge("size", "answer")
workflow.add_edge("handoff", "answer")
workflow.add_edge("refund_status", "answer")

# answer → memory_commit → conversation_state → trace → 结束
workflow.add_edge("answer", "memory_commit")
workflow.add_edge("memory_commit", "conversation_state")
workflow.add_edge("conversation_state", "trace")
workflow.set_finish_point("trace")

# 编译
app = workflow.compile()
