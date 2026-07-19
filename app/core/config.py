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
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT_PATH = (
    Path(__file__).resolve().parent.parent.parent
)


class Settings(BaseSettings):
    PROJECT_ROOT: Path = PROJECT_ROOT_PATH

    # ── 运行环境 ──
    ENVIRONMENT: str = "development"

    # ── 数据库 ──
    DATABASE_URL: str = ""

    # ── LLM 配置（占位，Phase 3 启用） ──
    LLM_API_KEY: str
    LLM_API_BASE: str
    LLM_MODEL: str

    # ── 身份认证 ──
    # 生产环境必须通过环境变量设置不少于 32 字符的随机密钥。
    # 开发环境未设置时，会在 data/.jwt_secret 中生成本机密钥。
    JWT_SECRET_KEY: str = ""
    JWT_ISSUER: str = "fashion-agent"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, gt=0, le=1440)

    # 仅用于初始化本地演示账号；生产环境不要配置公共默认密码。
    SEED_CUSTOMER_PASSWORD: str = ""
    SEED_ADMIN_PASSWORD: str = ""

    # ── Mock 外部电商系统 ──
    # 仅非生产环境使用；模拟外部渠道已识别的固定消费者。
    DEMO_STORE_TENANT_ID: int = Field(default=1, gt=0)
    DEMO_STORE_USER_ID: int = Field(default=1, gt=0)

    # ── 退款策略 ──
    # 小于等于此金额的退款自动审批，超过则触发人工审核
    REFUND_AUTO_LIMIT: Decimal = Decimal("100.00")
    # 当前项目明确为Demo；生产环境仍由网关工厂禁止mock。
    REFUND_GATEWAY_MODE: Literal["manual", "mock"] = "mock"
    # Mock默认结果；failed订单列表用于同一Demo稳定展示渠道失败场景。
    MOCK_REFUND_RESULT: Literal["succeeded", "pending", "failed"] = "succeeded"
    MOCK_REFUND_FAILED_ORDER_IDS: str = "10002"

    @property
    def mock_refund_failed_order_ids(self) -> frozenset[int]:
        values: set[int] = set()
        for raw_value in self.MOCK_REFUND_FAILED_ORDER_IDS.split(","):
            value = raw_value.strip()
            if not value:
                continue
            try:
                order_id = int(value)
            except ValueError as error:
                raise ValueError(
                    "MOCK_REFUND_FAILED_ORDER_IDS必须是逗号分隔的整数"
                ) from error
            if order_id <= 0:
                raise ValueError("Mock失败订单号必须大于0")
            values.add(order_id)
        return frozenset(values)

    # ── 多轮槽位会话 ──
    CONVERSATION_STATE_TTL_MINUTES: int = Field(
        default=30,
        ge=5,
        le=1440,
    )

    # ── RAG 配置（占位，Phase 2 启用） ──
    DOCLING_ARTIFACTS_PATH: Path = Path(
        r"D:\docling_models"
    )
    KNOWLEDGE_STORAGE_ROOT: Path = (
        PROJECT_ROOT_PATH / "data" / "knowledge" / "tenants"
    )

    # ── FastAPI ──
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # ── 日志 ──
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT_PATH / ".env",
        env_file_encoding="utf-8",
    )

    @property
    def resolved_database_url(self) -> str:
        """返回实际数据库 URL，空值时构造默认 SQLite 路径"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        db_dir = self.PROJECT_ROOT / "data"
        db_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_dir / 'fashion.db'}"

settings = Settings()
