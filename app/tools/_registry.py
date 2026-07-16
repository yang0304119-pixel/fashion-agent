"""
工具注册表

定义所有业务工具的 OpenAI function-calling 格式描述，
供 ReAct 节点驱动 LLM 自主选择工具并生成参数。

# 关键设计说明
# ─────────────────────────────
# 为什么用 function-calling 格式：
# - OpenAI / DeepSeek 原生支持，LLM 输出结构化参数，无需正则提取
# - 新增工具只需在此注册一行描述 + handler 映射，不改路由逻辑
# - tools 参数让 LLM 在不确定时选择"不调用"直接回答，不会硬猜参数
# 权衡：
# - 依赖 LLM 的 function calling 能力（当前模型支持良好）
# - 多步编排（如退款三步）交给 LLM 决策，结果不可 100% 确定
# - 通过工具描述中的"前置条件"提示（如"先调用 risk_check"）引导 LLM
# ─────────────────────────────
"""

from typing import Any

from app.tools.order_tool import query_order
from app.tools.size_tool import size_recommend
from app.tools.inventory_tool import query_inventory
from app.tools.refund_tool import risk_check, create_ticket


# ── OpenAI function-calling 格式的工具定义 ──

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "query_order",
            "description": "查询订单状态（待发货/已发货/已签收/已退款/已取消）。用户提到「订单」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "订单号，如 10001",
                    },
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "size_recommend",
            "description": "根据身高、体重和版型偏好推荐服装尺码。用户询问「穿什么码」「尺码」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "height": {"type": "integer", "description": "身高，单位 cm，如 175"},
                    "weight": {"type": "integer", "description": "体重，单位 kg，如 70"},
                    "style": {
                        "type": "string",
                        "enum": ["修身", "标准", "宽松"],
                        "description": "版型偏好，默认标准",
                    },
                },
                "required": ["height", "weight", "style"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_inventory",
            "description": "查询商品库存数量。用户问「有货吗」「有现货吗」「库存」时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "商品 ID：1=极寒加厚羽绒服, 2=轻薄都市羽绒服, 3=三合一冲锋羽绒服, 4=商务修身羽绒服, 5=连帽短款羽绒服, 6=加长保暖羽绒服, 7=纯色羊毛围巾",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "risk_check",
            "description": "判断退款风险等级。调用前必须先调用 query_order 确认订单信息。金额≤100 元自动审批，>100 元需人工审核。同时校验订单归属和重复退款。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "订单号"},
                    "reason": {"type": "string", "description": "退款原因"},
                    "user_id": {"type": "integer", "description": "用户 ID，从上下文中的当前用户 ID 获取"},
                },
                "required": ["order_id", "reason", "user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "创建售后工单。只有在 risk_check 返回 human_required=true 时才调用。调用前先确认用户身份和订单信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer", "description": "订单号"},
                    "user_id": {"type": "integer", "description": "用户 ID"},
                    "reason": {"type": "string", "description": "退款原因"},
                    "amount": {"type": "number", "description": "退款金额，从 query_order 结果中获取"},
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "风险等级，从 risk_check 结果中获取",
                    },
                },
                "required": ["order_id", "user_id", "reason", "amount", "risk_level"],
            },
        },
    },
]


# ── 工具名 → 处理函数 映射表 ──

TOOL_HANDLERS: dict[str, Any] = {
    "query_order": query_order,
    "size_recommend": size_recommend,
    "query_inventory": query_inventory,
    "risk_check": risk_check,
    "create_ticket": create_ticket,
}
