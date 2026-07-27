"""目标边界守卫：路由完成后、任何业务执行前做最终授权。"""

from app.agent.boundary_policy import evaluate_goal
from app.agent.state import AgentState


def boundary_guard_node(state: AgentState) -> dict:
    original_intent = str(state.get("intent") or "fallback")
    decision = evaluate_goal(
        message=str(state.get("message") or ""),
        intent=original_intent,
    )
    result = {
        "boundary_status": decision.status,
        "boundary_action_class": decision.action_class,
        "boundary_risk_level": decision.risk_level,
        "boundary_reason": decision.reason,
        "approval_required": decision.approval_required,
        "boundary_original_intent": original_intent,
    }
    if decision.blocked:
        result.update({
            "intent": "human_handoff",
            "intents": ["human_handoff"],
            "confidence": 1.0,
            "router_source": "goal_boundary",
            "router_evidence": [decision.reason],
            "requires_planning": False,
            "human_required": True,
            "tool_status": "pending",
        })
    elif decision.approval_required:
        result["human_required"] = True
    return result


def route_after_goal_guard(state: AgentState) -> str:
    return "handoff" if state.get("boundary_status") == "blocked" else "continue"
