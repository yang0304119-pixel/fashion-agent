"""聊天接口请求/响应模型。"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProductChatContext(BaseModel):
    """浏览器只提交商品主键，其他商品字段全部由服务端重查。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["product"]
    product_id: int = Field(gt=0)


class OrderChatContext(BaseModel):
    """浏览器只提交订单主键，身份和订单归属来自访问令牌。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["order"]
    order_id: int = Field(gt=0)


ChatContext = Annotated[
    ProductChatContext | OrderChatContext,
    Field(discriminator="type"),
]


class RagSource(BaseModel):
    id: str
    title: str
    type: str
    category: str
    relative_source: str
    chunk_id: str
    source_sha256: str


class ChatRequest(BaseModel):
    """聊天请求"""

    model_config = ConfigDict(extra="forbid")

    session_id: str | None = Field(
        default=None,
        min_length=8,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    message: str = Field(min_length=1, max_length=4000)
    context: ChatContext | None = None


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: str
    intent: str
    confidence: float
    answer: str
    message_type: Literal["text", "refund_status"] = "text"
    payload: dict[str, Any] | None = None
    sources: list[RagSource] = Field(
        default_factory=list
    )
