"""
工具调度节点

根据 intent 调用对应的业务工具，并将结果写回 state。

# 关键设计说明
# ─────────────────────────────
# 为什么调度逻辑写在一个节点而非分散到多个节点：
# - 3 个工具的逻辑是"调工具→写结果"，差异只在调用哪个函数
# - 一个节点 + 分发表，新增工具只需加一行映射，不改流程
# 为什么参数提取用正则而非 LLM：
# - Phase 4 的消息中参数格式简单（"订单 10001"、"175cm 70kg"）
# - 正则零成本，等 Phase 5 复杂场景再考虑 LLM 提取
# ─────────────────────────────
"""

import re

from app.agent.state import AgentState
from app.tools.order_tool import query_order
from app.tools.size_tool import size_recommend
from app.tools.inventory_tool import query_inventory


# intent → (工具函数, 参数提取函数) 映射表
# 新增工具时在此注册即可
_TOOL_DISPATCH: dict[str, tuple] = {
    "order_query": (query_order, lambda msg: _extract_order_id(msg)),
    "size_recommend": (size_recommend, lambda msg: _extract_size_params(msg)),
    # query_inventory 暂不自动调度，后续用户明确问库存时再接入
}


def tool_node(state: AgentState) -> dict:
    """工具调度节点：根据 intent 调用对应工具。

    Args:
        state: 当前 AgentState，至少包含 intent 和 message。

    Returns:
        更新 state 的字典，包含 tool_result 和 tool_status。
    """
    intent: str = state.get("intent", "")
    message: str = state.get("message", "")

    if intent not in _TOOL_DISPATCH:
        return {
            "tool_result": None,
            "tool_status": "skipped",
        }

    tool_func, param_extractor = _TOOL_DISPATCH[intent]
    params = param_extractor(message)

    if "error" in params:
        return {
            "tool_result": None,
            "tool_status": "error",
        }

    result = tool_func(**params)
    status = "success" if result.get("success") else "error"

    return {
        "tool_result": result,
        "tool_status": status,
    }


def _extract_order_id(message: str) -> dict:
    """从消息中提取订单号。"""
    # 匹配"订单 10001"、"10001号"、"订单号 10001" 等模式
    patterns = [
        r"订单[号#\s]*(\d{5,})",
        r"(\d{5,})[号#]",
        r"订单[\s:：]*(\d{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return {"order_id": int(match.group(1))}

    return {"error": "未找到订单号"}


def _extract_size_params(message: str) -> dict:
    """从消息中提取身高、体重和版型偏好。"""
    height = None
    weight = None
    style = "标准"

    # 提取身高：175cm / 175厘米 / 1米75
    height_match = re.search(r"(\d{3})\s*(cm|厘米)", message)
    if height_match:
        h = int(height_match.group(1))
        if 100 <= h <= 250:
            height = h

    # 提取体重：70kg / 70公斤（必须带单位，否则会误抓身高数字）
    weight_match = re.search(r"(\d{2,3})\s*(kg|公斤)", message, re.IGNORECASE)
    if weight_match:
        w = int(weight_match.group(1))
        if 30 <= w <= 200:
            weight = w

    # 提取版型偏好
    if any(k in message for k in ["修身", "贴身"]):
        style = "修身"
    elif any(k in message for k in ["宽松", "休闲"]):
        style = "宽松"

    if not height or not weight:
        return {"error": "未提取到完整的身高体重信息"}

    return {"height": height, "weight": weight, "style": style}
