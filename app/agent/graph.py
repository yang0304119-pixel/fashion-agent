"""
LangGraph 工作流定义

将 router / rag / answer 三个节点串联为完整流程：
  用户输入 → Router(规则+LLM) → RAG(检索+生成) → Answer(格式回复)

# 关键设计说明
# ─────────────────────────────
# 为什么 Phase 3 只设 3 个节点：
# - 当前只实现了 knowledge_query 和 fallback 两条路径
# - 其他意图（order_query/size_recommend/refund_request）等
#   Phase 4/5 加 tool_node 和 human_node 时逐步加入
# 为什么 route_by_intent 这么简单还要独立成函数：
# - LangGraph 的 add_conditional_edges 需要可调用对象
# - 后续增加复杂路由逻辑（如多意图拆分）时直接改这个函数
# ─────────────────────────────
"""

from langgraph.graph import StateGraph

from app.agent.state import AgentState
from app.agent.nodes.router_node import router_node
from app.agent.nodes.rag_node import rag_node
from app.agent.nodes.answer_node import answer_node


def route_by_intent(state: AgentState) -> str:
    """根据 intent 决定下一个节点。

    当前只处理 knowledge_query 和 fallback 两条路径，
    其他意图在 Phase 4/5 的 tool_node 和 human_node 加入时扩展。
    """
    intent: str = state.get("intent", "fallback")

    # 目前只有 knowledge_query 走 RAG 链路
    if intent == "knowledge_query":
        return "rag"

    # size_recommend / order_query / refund_request 暂未实现，
    # 先统一走 fallback（Phase 4/5 各加入对应节点后改这里）
    return "answer"


# ── 构建工作流 ──

workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("router", router_node)
workflow.add_node("rag", rag_node)
workflow.add_node("answer", answer_node)

# 设置入口
workflow.set_entry_point("router")

# 条件路由：router 的输出决定下一步
workflow.add_conditional_edges(
    "router",
    route_by_intent,
    {
        "rag": "rag",
        "answer": "answer",
    },
)

# RAG 走完后到 answer
workflow.add_edge("rag", "answer")

# answer 到结束
workflow.set_finish_point("answer")

# 编译
app = workflow.compile()
