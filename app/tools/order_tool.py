"""
订单查询工具

根据订单号查询订单状态、物流信息等数据。

# 关键设计说明
# ─────────────────────────────
# 为什么输入输出用结构化 dict：
# - 统一接口，tool_node 不需要为每个工具写不同的解析逻辑
# - 返回结构包含 error 字段，调用方统一判断 success/error
# 为什么不直接返回 ORM 对象：
# - ORM 对象含 SQLAlchemy 内部状态，序列化后传给 LLM 不安全
# - dict 是纯数据，可控、可序列化、可记录到 Agent Trace
# ─────────────────────────────
"""

from app.core.database import SessionLocal
from app.models.order import Order


def query_order(order_id: int) -> dict:
    """查询订单状态信息。

    Args:
        order_id: 订单号（如 10001）。

    Returns:
        结构化结果 dict：
        - success: bool
        - data: {order_id, status, product_name, quantity, total_price, created_at} | None
        - error: str | None
    """
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()

        if not order:
            return {
                "success": False,
                "data": None,
                "error": f"订单 {order_id} 不存在",
            }

        return {
            "success": True,
            "data": {
                "order_id": order.id,
                "status": order.status,
                "product_id": order.product_id,
                "quantity": order.quantity,
                "total_price": float(order.total_price),
                "created_at": str(order.created_at) if order.created_at else None,
            },
            "error": None,
        }

    except Exception as e:
        return {
            "success": False,
            "data": None,
            "error": f"查询订单失败：{str(e)}",
        }

    finally:
        db.close()
