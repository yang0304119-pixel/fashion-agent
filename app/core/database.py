"""
数据库引擎与会话管理

使用 SQLAlchemy 2.0 同步引擎。开发阶段 SQLite 不需要异步，
同步代码更简洁、调试更方便。后续如需高性能可迁移到异步引擎。

# 关键设计说明
# ─────────────────────────────
# 为什么开发阶段用 init_db() 而非 Alembic：
# - Phase 1~7 表结构频繁变动，手写 migration 增加 3 倍工作量
# - create_all() 负责新表，已有SQLite表的增量字段由幂等迁移脚本处理
# - 生产准备阶段再引入 Alembic 做真实 migration
# 为什么用 check_same_thread=False：
# - FastAPI 多线程处理请求，SQLite 默认只允许创建线程访问
# - 开发阶段用此参数即可，生产换 MySQL 后不再需要
# ─────────────────────────────
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.resolved_database_url,
    connect_args={"check_same_thread": False},
    echo=False,  # 生产环境设为 False；调试时可改为 True 查看 SQL
)

# SQLite 默认不强制外键约束，需在每次连接时手动启用
# 否则 ForeignKey 只存在于表结构定义中，实际插入脏数据不会报错
@event.listens_for(engine, "connect")
def _enable_sqlite_fks(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_db():
    """初始化数据库表结构

    基于所有继承 Base 的模型自动建表。幂等操作——表已存在则跳过。
    在 FastAPI 启动时调用，确保数据库可用。
    """
    # 延迟导入确保所有模型注册到 Base.metadata
    from app.models import (  # noqa: F401
        Tenant, User, Product, Order, Ticket, RefundRequest,
        AgentTrace, AgentTraceStep, UnresolvedCase, ConversationState,
        KnowledgeDocument, KnowledgeRevision,
    )

    Base.metadata.create_all(bind=engine)
    if engine.dialect.name == "sqlite":
        database_path = engine.url.database
        if database_path and database_path != ":memory:":
            from scripts.migrate_agent_trace_steps import migrate as migrate_trace
            from scripts.migrate_ticket_review import migrate as migrate_ticket
            from scripts.migrate_unresolved_case_review import (
                migrate as migrate_unresolved_case,
            )
            from scripts.migrate_knowledge_lifecycle import (
                migrate as migrate_knowledge_lifecycle,
            )

            migrate_ticket(Path(database_path))
            migrate_trace(Path(database_path))
            migrate_unresolved_case(Path(database_path))
            migrate_knowledge_lifecycle(Path(database_path))
    logger.info("数据库表结构已就绪 - %s", settings.resolved_database_url)
