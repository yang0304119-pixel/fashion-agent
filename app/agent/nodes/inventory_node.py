"""确定性库存查询节点。"""

import logging

from app.agent.slot_extractors import collect_slots
from app.agent.state import AgentState
from app.providers.factory import get_inventory_provider
from app.providers.inventory_provider import (
    InventoryNotFoundError,
    InventoryProvider,
    InventoryResult,
)


logger = logging.getLogger(__name__)


def inventory_node(
    state: AgentState,
    provider: InventoryProvider | None = None,
) -> dict:
    collected_slots = collect_slots(
        state.get("intent", "inventory_query"),
        state.get("message", ""),
        state.get("collected_slots"),
    )
    product_id = collected_slots.get("product_id")
    if product_id is None:
        return {
            "missing_slots": ["product_id"],
            "collected_slots": collected_slots,
            "tool_status": "pending",
            "tool_result": {
                "success": False,
                "data": None,
                "error": "缺少商品信息",
            },
            "final_answer": "请提供商品名称或商品编号，我才能查询库存。",
        }

    try:
        inventory = (provider or get_inventory_provider()).get_inventory(
            tenant_id=state.get("tenant_id", 0),
            product_id=product_id,
        )
        data = {
            "product_id": inventory.product_id,
            "name": inventory.product_name,
            "category": inventory.category,
            "price": inventory.price,
            "stock": inventory.stock,
            "colors": inventory.colors,
            "sizes": inventory.sizes,
        }
        answer = _format_product_answer(
            inventory=inventory,
            message=state.get("message", ""),
        )
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "success",
            "tool_result": {"success": True, "data": data, "error": None},
            "final_answer": answer,
        }
    except InventoryNotFoundError:
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "error",
            "tool_result": {
                "success": False,
                "data": None,
                "error": "商品不存在",
            },
            "final_answer": "没有找到该商品，请确认商品名称或编号。",
        }
    except Exception:
        logger.exception("确定性库存节点执行失败")
        return {
            "missing_slots": [],
            "collected_slots": collected_slots,
            "tool_status": "error",
            "tool_result": {
                "success": False,
                "data": None,
                "error": "库存查询暂时失败",
            },
            "final_answer": "库存查询暂时失败，请稍后重试。",
        }


def _format_product_answer(*, inventory: InventoryResult, message: str) -> str:
    """结构化商品字段由数据库确定，按用户问题选择需要展示的部分。"""
    parts: list[str] = []
    if any(keyword in message for keyword in ("多少钱", "价格", "售价")):
        parts.append(f"当前售价为 {inventory.price:.2f} 元")
    if any(keyword in message for keyword in ("颜色", "配色")):
        parts.append(f"可选颜色有{'、'.join(inventory.colors)}")
    if any(
        keyword in message
        for keyword in ("有哪些尺码", "哪些尺码", "可选尺码", "尺码范围")
    ):
        parts.append(f"可选尺码有{'、'.join(inventory.sizes)}")
    if any(keyword in message for keyword in ("库存", "有货", "现货", "还有吗")):
        parts.append(
            f"当前有库存 {inventory.stock} 件"
            if inventory.stock > 0
            else "当前暂时缺货"
        )

    if not parts:
        parts = [
            (
                f"当前有库存 {inventory.stock} 件"
                if inventory.stock > 0
                else "当前暂时缺货"
            ),
            f"可选颜色：{'、'.join(inventory.colors)}",
            f"可选尺码：{'、'.join(inventory.sizes)}",
        ]
    return f"{inventory.product_name}：{'；'.join(parts)}。"
