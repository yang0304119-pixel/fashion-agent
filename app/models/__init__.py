"""
SQLAlchemy 模型统一导出

所有模型继承 app.core.database.Base，init_db() 时自动建表。
"""

from app.models.user import User
from app.models.tenant import Tenant
from app.models.product import Product
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.agent_trace import AgentTrace
from app.models.unresolved_case import UnresolvedCase

__all__ = [
    "User",
    "Tenant",
    "Product",
    "Order",
    "Ticket",
    "AgentTrace",
    "UnresolvedCase",
]
