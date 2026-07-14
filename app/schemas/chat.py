"""
聊天接口请求/响应模型
"""

from pydantic import BaseModel


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
