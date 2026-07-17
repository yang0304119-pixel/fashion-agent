"""
聊天接口请求/响应模型
"""

from pydantic import BaseModel, Field


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
    session_id: str
    user_id: int
    message: str


class ChatResponse(BaseModel):
    """聊天响应"""
    session_id: str
    intent: str
    confidence: float
    answer: str
    sources: list[RagSource] = Field(
        default_factory=list
    )
