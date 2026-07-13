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

import uvicorn
from fastapi import FastAPI

from app.core.config import settings
from app.core.database import init_db

# 配置日志
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FashionAgent",
    description="服装电商智能客服 Agent API",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    """应用启动时自动初始化数据库"""
    init_db()
    logger.info("FashionAgent 服务已启动 - %s", settings.resolved_database_url)


@app.get("/api/health")
def health():
    """健康检查端点"""
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
        log_level=settings.LOG_LEVEL.lower(),
    )
