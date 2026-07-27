"""
聊天接口

接收用户消息，走完 Agent 工作流后返回回答。
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.graph import app as agent_app
from app.core.config import settings
from app.dependencies import get_current_user, get_db
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_context_service import (
    ChatContextNotFoundError,
    ChatContextService,
)
from app.services.trace_service import create_request_trace, finalize_request_failure

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatResponse:
    """用户发送消息，走完 Agent 工作流后返回回答。

    Args:
        request: 包含可选 session_id 和 message 的 JSON。

    Returns:
        intent / confidence / answer 等业务字段。
    """
    session_id = request.session_id or uuid4().hex
    started_at = datetime.now(UTC)
    state = {
        "session_id": session_id,
        "user_id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "message": request.message,
        "execution_started_at": started_at.isoformat(),
        "execution_deadline_at": (
            started_at + timedelta(seconds=settings.AGENT_MAX_EXECUTION_SECONDS)
        ).isoformat(),
        "execution_budget": {
            "max_iterations": settings.AGENT_MAX_ITERATIONS,
            "max_tool_calls": settings.AGENT_MAX_TOOL_CALLS,
            "max_execution_seconds": settings.AGENT_MAX_EXECUTION_SECONDS,
            "max_llm_output_tokens": settings.AGENT_MAX_LLM_OUTPUT_TOKENS,
        },
    }
    if request.context is not None:
        try:
            resolved_context = ChatContextService(db).resolve(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                context=request.context,
            )
        except ChatContextNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        state["chat_context"] = resolved_context.trusted_data
        state["collected_slots"] = resolved_context.collected_slots

    trace_id = create_request_trace(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        session_id=session_id,
        message=request.message,
    )
    state["trace_id"] = trace_id

    try:
        result = agent_app.invoke(state)
    except Exception as error:
        finalize_request_failure(trace_id, error)
        raise

    tool_result = result.get("tool_result") or {}
    tool_payload = tool_result.get("data") if isinstance(tool_result, dict) else None
    is_refund = result.get("intent") == "refund_request" and tool_payload

    return ChatResponse(
        session_id=result.get("session_id", session_id),
        intent=result.get("intent", "fallback"),
        confidence=result.get("confidence", 0.0),
        answer=result.get("final_answer", ""),
        message_type="refund_status" if is_refund else "text",
        payload=tool_payload if is_refund else None,
        sources=result.get("retrieved_sources", []),
    )
