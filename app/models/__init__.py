"""
SQLAlchemy 模型统一导出

所有模型继承 app.core.database.Base，init_db() 时自动建表。
"""

from app.models.user import User
from app.models.tenant import Tenant
from app.models.product import Product
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.refund_request import RefundRequest
from app.models.agent_trace import AgentTrace
from app.models.agent_trace_step import AgentTraceStep
from app.models.unresolved_case import UnresolvedCase
from app.models.conversation_state import ConversationState
from app.models.knowledge_document import (
    KnowledgeDocument,
    KnowledgeIndexBuild,
    KnowledgeRevision,
)

__all__ = [
    "User",
    "Tenant",
    "Product",
    "Order",
    "Ticket",
    "RefundRequest",
    "AgentTrace",
    "AgentTraceStep",
    "UnresolvedCase",
    "ConversationState",
    "KnowledgeDocument",
    "KnowledgeRevision",
    "KnowledgeIndexBuild",
]
