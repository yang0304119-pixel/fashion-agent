"""
全局配置管理

使用 pydantic-settings 从环境变量读取配置，支持 .env 文件覆盖。
开发阶段无需 .env 文件，所有配置均有默认值。

# 关键设计说明
# ─────────────────────────────
# 为什么用 pydantic-settings：
# - 类型校验自动完成，不会出现 str 当 int 用的问题
# - 支持环境变量覆盖，方便后续容器化部署
# - 无需手动解析 os.environ，减少样板代码
# 权衡：
# - 依赖 pydantic-settings 包，但已在 requirements.txt 中
# - 如果将来配置项过多，可拆分为 CoreSettings / RagSettings / LLMSettings 多个类
# ─────────────────────────────
"""

from pathlib import Path
from decimal import Decimal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── 项目路径 ──
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

    # ── 数据库 ──
    DATABASE_URL: str = ""

    # ── LLM 配置（占位，Phase 3 启用） ──
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    # ── 退款策略 ──
    # 小于等于此金额的退款自动审批，超过则触发人工审核
    REFUND_AUTO_LIMIT: Decimal = Decimal("100.00")

    # ── RAG 配置（占位，Phase 2 启用） ──
    CHROMA_PATH: str = ""
    TOP_K: int = 3

    # ── FastAPI ──
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # ── 日志 ──
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def resolved_database_url(self) -> str:
        """返回实际数据库 URL，空值时构造默认 SQLite 路径"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        db_dir = self.PROJECT_ROOT / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_dir / 'fashion.db'}"


settings = Settings()
