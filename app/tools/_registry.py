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
# - 运行时严格校验由Pydantic完成；不发送OpenAI专有strict字段，保持DeepSeek兼容
# ─────────────────────────────
"""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.tools.order_tool import query_order
from app.tools.size_tool import size_recommend
from app.tools.inventory_tool import query_inventory
from app.tools.product_search_tool import search_products
from app.tools.knowledge_tool import retrieve_knowledge


class _StrictToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RetrieveKnowledgeArguments(_StrictToolArguments):
    query: str = Field(min_length=1, max_length=4000)


class QueryOrderArguments(_StrictToolArguments):
    order_id: int = Field(gt=0)


class SizeRecommendArguments(_StrictToolArguments):
    height: int = Field(ge=100, le=250)
    weight: int = Field(ge=30, le=200)
    style: Literal["修身", "标准", "宽松"]


class QueryInventoryArguments(_StrictToolArguments):
    product_id: int = Field(gt=0)


class SearchProductsArguments(_StrictToolArguments):
    query: str = Field(min_length=1, max_length=200)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Any
    args_model: type[BaseModel]
    trusted_fields: tuple[str, ...] = ()
    action_type: Literal["read", "write", "delete", "payment", "external"] = "read"
    risk_level: Literal["low", "medium", "high", "critical"] = "low"
    approval_required: bool = False


# ── OpenAI function-calling 格式的工具定义 ──

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_knowledge",
            "description": "查询当前租户已上线的商品知识、店铺规则、洗护和售后政策。",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "需要检索的知识问题",
                        "minLength": 1,
                        "maxLength": 4000,
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
                "additionalProperties": False,
                "properties": {
                    "order_id": {
                        "type": "integer",
                        "description": "订单号，如 10001",
                        "minimum": 1,
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
                "additionalProperties": False,
                "properties": {
                    "height": {
                        "type": "integer",
                        "description": "身高，单位 cm，如 175",
                        "minimum": 100,
                        "maximum": 250,
                    },
                    "weight": {
                        "type": "integer",
                        "description": "体重，单位 kg，如 70",
                        "minimum": 30,
                        "maximum": 200,
                    },
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
                "additionalProperties": False,
                "properties": {
                    "product_id": {
                        "type": "integer",
                        "description": "search_products 返回的商品 ID",
                        "minimum": 1,
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
                "additionalProperties": False,
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "商品名称或关键词，如 围巾、羊毛、羽绒服",
                        "minLength": 1,
                        "maxLength": 200,
                    },
                },
                "required": ["query"],
            },
        },
    },
]


# ── 工具名 → 处理函数 映射表 ──

TOOL_SPECS: dict[str, ToolSpec] = {
    "query_order": ToolSpec(
        "query_order",
        query_order,
        QueryOrderArguments,
        ("user_id", "tenant_id"),
    ),
    "size_recommend": ToolSpec(
        "size_recommend",
        size_recommend,
        SizeRecommendArguments,
    ),
    "query_inventory": ToolSpec(
        "query_inventory",
        query_inventory,
        QueryInventoryArguments,
        ("tenant_id",),
    ),
    "search_products": ToolSpec(
        "search_products",
        search_products,
        SearchProductsArguments,
        ("tenant_id",),
    ),
    "retrieve_knowledge": ToolSpec(
        "retrieve_knowledge",
        retrieve_knowledge,
        RetrieveKnowledgeArguments,
        ("tenant_id",),
    ),
}

TOOL_HANDLERS: dict[str, Any] = {
    name: spec.handler for name, spec in TOOL_SPECS.items()
}
