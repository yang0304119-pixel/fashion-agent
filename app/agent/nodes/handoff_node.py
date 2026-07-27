"""人工接管和暂不支持写操作的安全兜底节点。"""

from app.agent.state import AgentState


def handoff_node(state: AgentState) -> dict:
    intent = state.get("intent", "human_handoff")
    boundary_reason = str(state.get("boundary_reason") or "")
    if state.get("boundary_status") == "blocked":
        answer = (
            "该请求超出客服Agent的授权范围，系统没有执行任何操作，"
            "已保存为人工处理事项。"
        )
    elif intent == "after_sales_request":
        answer = (
            "该请求涉及换货、修改尺码或取消订单等业务写操作，"
            "当前需要人工客服核实订单状态后处理，已为您转入人工处理队列。"
        )
    else:
        answer = "好的，已记录您的人工客服请求，请等待人工客服继续处理。"
    return {
        "missing_slots": [],
        "tool_status": "pending",
        "human_required": True,
        "approval_required": True,
        "boundary_reason": boundary_reason or "用户主动要求人工处理",
        "final_answer": answer,
    }
