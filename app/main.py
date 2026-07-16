"""
FashionAgent FastAPI 应用入口

启动时自动初始化数据库表结构（init_db），注册业务路由模块。

# 关键设计说明
# ─────────────────────────────
# 为什么路由从 main.py 拆分到 app/routers/：
# - main.py 只做"组装应用"一件事，业务接口分别归入对应路由文件
# - 新增接口时不需要改 main.py，只需要新建/修改路由文件
# - 每个路由文件聚焦一类资源，长度可控
# ─────────────────────────────
"""

import logging
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_db
from app.routers import chat, orders, tickets, traces

# ── 日志配置 ──
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)

# ── 应用实例 ──
fastapi_app = FastAPI(
    title="FashionAgent",
    description="服装电商智能客服 Agent API",
    version="0.3.0",
)


@fastapi_app.on_event("startup")
def on_startup() -> None:
    """应用启动时自动初始化数据库。"""
    init_db()
    logger.info("FashionAgent 服务已启动 - %s", settings.resolved_database_url)


# ── 系统端点 ──


@fastapi_app.get("/api/health", tags=["system"])
def health():
    """健康检查端点。"""
    return {"status": "ok", "version": "0.3.0"}


# ── 注册业务路由 ──

fastapi_app.include_router(chat.router, prefix="/api")
fastapi_app.include_router(orders.router, prefix="/api")
fastapi_app.include_router(tickets.router, prefix="/api")
fastapi_app.include_router(traces.router, prefix="/api")

# ── 可选的静态文件挂载（前端） ──

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.exists():
    fastapi_app.mount(
        "/",
        StaticFiles(directory=str(frontend_dir), html=True),
        name="frontend",
    )

# ── 直接启动 ──

if __name__ == "__main__":
    uvicorn.run(
        "app.main:fastapi_app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
