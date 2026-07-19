"""确定性尺码推荐节点。"""

from app.agent.slot_extractors import collect_slots, missing_slots_for_intent
from app.agent.state import AgentState
from app.services.size_service import SizeService, SizeServiceError


def size_node(state: AgentState) -> dict:
    collected_slots = collect_slots(
        "size_recommend",
        state.get("message", ""),
        state.get("collected_slots"),
    )
    missing_slots = missing_slots_for_intent(
        "size_recommend",
        collected_slots,
    )

    if missing_slots:
        labels = {
            "height": "身高",
            "weight": "体重",
        }
        missing_text = "和".join(labels[item] for item in missing_slots)
        return {
            "missing_slots": missing_slots,
            "collected_slots": collected_slots,
            "tool_status": "pending",
            "tool_result": {
                "success": False,
                "data": None,
                "error": f"缺少{missing_text}",
            },
            "final_answer": (
                f"请提供您的{missing_text}，例如：175cm、70kg，"
                "也可以说明喜欢修身还是宽松。"
            ),
        }

    try:
        recommendation = SizeService().recommend(
            height=collected_slots["height"],
            weight=collected_slots["weight"],
            style=collected_slots.get("style", "标准"),
        )
    except SizeServiceError as error:
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "error",
            "tool_result": {
                "success": False,
                "data": None,
                "error": str(error),
            },
            "final_answer": f"暂时无法推荐尺码：{error}。",
        }

    data = {
        "height": recommendation.height,
        "weight": recommendation.weight,
        "style": recommendation.style,
        "base_size": recommendation.base_size,
        "size": recommendation.size,
    }
    return {
        "missing_slots": [],
        "collected_slots": collected_slots,
        "tool_status": "success",
        "tool_result": {"success": True, "data": data, "error": None},
        "final_answer": (
            f"根据身高 {recommendation.height}cm、"
            f"体重 {recommendation.weight}kg，"
            f"{recommendation.style}版型建议选择 "
            f"{recommendation.size} 码。"
        ),
    }
