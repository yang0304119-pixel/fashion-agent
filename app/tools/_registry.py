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
# - 这里只注册只读或低风险工具；退款等资金操作由确定性工作流处理
# ─────────────────────────────
"""

from typing import Any

from app.tools.order_tool import query_order
from app.tools.size_tool import size_recommend
from app.tools.inventory_tool import query_inventory
from app.tools.product_search_tool import search_products
from app.tools.knowledge_tool import retrieve_knowledge


# ── OpenAI function-calling 格式的工具定义 ──

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "查询当前租户已上线的商品知识、店铺规则、洗护和售后政策。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "需要检索的知识问题",
                    },
                },
                "required": ["query"],
            },
        },
    },
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
            "description": (
                "按商品ID查询库存数量。若用户只提供商品名称，"
                "必须先调用 search_products 获取当前租户内的商品ID。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "search_products 返回的商品 ID",
                    },
                },
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "按名称、分类、描述或材质搜索商品目录，只读取商品信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "商品名称或关键词，如 围巾、羊毛、羽绒服",
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ── 工具名 → 处理函数 映射表 ──

TOOL_HANDLERS: dict[str, Any] = {
    "query_order": query_order,
    "size_recommend": size_recommend,
    "query_inventory": query_inventory,
    "search_products": search_products,
    "retrieve_knowledge": retrieve_knowledge,
}
