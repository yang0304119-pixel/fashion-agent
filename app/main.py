"""
FashionAgent FastAPI 应用入口

启动时自动初始化数据库表结构（init_db）。
Phase 1 仅提供健康检查端点，后续 Phase 逐步注册业务路由。

# 关键设计说明
# ─────────────────────────────
# 为什么 startup 时 init_db：
# - 开发阶段省去手动建表步骤，运行即用
# - 生产环境部署前应改为 Alembic migration
# ─────────────────────────────
"""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db, SessionLocal
from app.agent.graph import app as agent_app
from app.schemas.chat import ChatRequest, ChatResponse
from app.models.order import Order
from app.models.ticket import Ticket
from app.models.agent_trace import AgentTrace

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)

fastapi_app = FastAPI(
    title="FashionAgent",
    description="服装电商智能客服 Agent API",
    version="0.3.0",
)


@fastapi_app.on_event("startup")
def on_startup():
    """应用启动时自动初始化数据库"""
    init_db()
    logger.info("FashionAgent 服务已启动 - %s", settings.resolved_database_url)


@fastapi_app.get("/api/health")
def health():
    """健康检查端点"""
    return {"status": "ok", "version": "0.3.0"}


@fastapi_app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """用户发送消息，走完 Agent 工作流后返回回答。

    Args:
        request: 包含 session_id / user_id / message 的 JSON。

    Returns:
        intent / confidence / answer 等业务字段。
    """
    state = {
        "session_id": request.session_id,
        "user_id": request.user_id,
        "message": request.message,
    }
    result = agent_app.invoke(state)
    return ChatResponse(
        session_id=result.get("session_id", ""),
        intent=result.get("intent", "fallback"),
        confidence=result.get("confidence", 0.0),
        answer=result.get("final_answer", ""),
    )


@fastapi_app.get("/api/orders/{order_id}")
def get_order(order_id: int):
    """查询订单信息（绕过 Agent，直接查数据库）。"""
    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail=f"订单 {order_id} 不存在")
        return {
            "success": True,
            "data": {
                "id": order.id,
                "user_id": order.user_id,
                "product_id": order.product_id,
                "quantity": order.quantity,
                "total_price": float(order.total_price),
                "status": order.status,
                "created_at": str(order.created_at) if order.created_at else None,
            },
        }
    finally:
        db.close()


@fastapi_app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int):
    """查询售后工单信息。"""
    db = SessionLocal()
    try:
        ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        if not ticket:
            raise HTTPException(status_code=404, detail=f"工单 {ticket_id} 不存在")
        return {
            "success": True,
            "data": {
                "id": ticket.id,
                "order_id": ticket.order_id,
                "user_id": ticket.user_id,
                "type": ticket.type,
                "reason": ticket.reason,
                "amount": float(ticket.amount),
                "risk_level": ticket.risk_level,
                "status": ticket.status,
                "human_review": ticket.human_review,
                "created_at": str(ticket.created_at) if ticket.created_at else None,
            },
        }
    finally:
        db.close()


@fastapi_app.get("/api/traces/{session_id}")
def get_traces(session_id: str):
    """查询指定会话的 Agent 执行轨迹。"""
    db = SessionLocal()
    try:
        traces = (
            db.query(AgentTrace)
            .filter(AgentTrace.session_id == session_id)
            .order_by(AgentTrace.created_at)
            .all()
        )
        return {
            "success": True,
            "data": [
                {
                    "id": t.id,
                    "node_name": t.node_name,
                    "intent": t.intent,
                    "confidence": float(t.confidence) if t.confidence else None,
                    "tool_status": t.tool_status,
                    "human_required": t.human_required,
                    "final_answer": t.final_answer,
                    "created_at": str(t.created_at) if t.created_at else None,
                }
                for t in traces
            ],
        }
    finally:
        db.close()


# ── 挂载前端静态页面 ──
# FastAPI 按路由注册顺序匹配，API 路由优先于静态文件
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    fastapi_app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:fastapi_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
