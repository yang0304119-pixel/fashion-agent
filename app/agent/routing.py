"""主Agent的纯意图路由映射，不加载LLM、RAG或数据库依赖。"""

from app.agent.state import AgentState


INTENT_ROUTES = {
    "knowledge_query": "rag",
    "product_query": "inventory",
    "order_query": "order",
    "inventory_query": "inventory",
    "size_recommend": "size",
    "refund_request": "refund",
    "refund_status_query": "refund_status",
    "after_sales_request": "handoff",
    "human_handoff": "handoff",
    "composite_query": "react",
    "fallback": "fallback",
}


def route_by_intent(state: AgentState) -> str:
    """单意图进入固定节点，组合只读意图进入ReAct。"""
    return INTENT_ROUTES.get(state.get("intent", "fallback"), "fallback")
