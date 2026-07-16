"""
工具模块共享工具函数

当前包含：
- extract_order_id: 从消息中提取订单号（正则实现）

将 tool_node 和 refund_node 中重复的提取逻辑统一到此模块，
新增订单号格式支持时只需要改这一处。
"""

import re


def extract_order_id(message: str) -> int | None:
    """从消息中提取订单号。

    支持格式：
    - 订单 10001 / 订单号 10001 / 订单#10001
    - 10001 号 / 10001#
    - 订单：10001 / 订单:10001

    Args:
        message: 用户输入文本。

    Returns:
        订单号（int），未找到时返回 None。
    """
    patterns = [
        r"订单[号#\s]*(\d{5,})",
        r"(\d{5,})[号#]",
        r"订单[\s:：]*(\d{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            return int(match.group(1))
    return None
