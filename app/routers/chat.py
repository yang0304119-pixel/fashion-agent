"""
聊天接口

接收用户消息，走完 Agent 工作流后返回回答。
"""

from fastapi import APIRouter

from app.agent.graph import app as agent_app
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
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
