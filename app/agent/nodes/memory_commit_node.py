"""回答后持久化会话Turn、任务检查点、长期记忆候选并执行压缩遗忘。"""

import json
import logging

from app.agent.state import AgentState
from app.core.database import SessionLocal
from app.services.memory_service import (
    ConversationMemoryService,
    LongTermMemoryService,
    TaskCheckpointService,
)


logger = logging.getLogger(__name__)


def memory_commit_node(state: AgentState) -> dict:
    tenant_id = int(state.get("tenant_id") or 0)
    user_id = int(state.get("user_id") or 0)
    session_id = str(state.get("session_id") or "")
    if not tenant_id or not user_id or not session_id:
        return {}
    db = SessionLocal()
    try:
        conversations = ConversationMemoryService(db)
        tool_result = state.get("tool_result")
        if isinstance(tool_result, dict):
            tool_names = list(dict.fromkeys(
                str(attempt.get("tool_name"))
                for attempt in state.get("tool_attempts") or []
                if attempt.get("tool_name") and attempt.get("tool_name") != "react_llm"
            ))
            conversations.append_turn(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                role="tool",
                content=json.dumps({
                    "status": state.get("tool_status"),
                    "conclusion": _tool_summary(tool_result),
                }, ensure_ascii=False),
                message_type="tool_result",
                tool_name=",".join(tool_names)[:50] or str(state.get("intent") or "tool"),
                tool_result_summary=_tool_summary(tool_result),
            )
        answer = str(state.get("final_answer") or "").strip()
        if answer:
            conversations.append_turn(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                role="assistant",
                content=answer,
                message_type=(
                    "refund_status"
                    if state.get("intent") == "refund_request" and state.get("refund_status")
                    else "text"
                ),
            )
        checkpoint = TaskCheckpointService(db).save_from_state(dict(state))
        long_term = LongTermMemoryService(db)
        candidates = long_term.extract_candidates(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            message=str(state.get("message") or ""),
            state=dict(state),
        )
        writes = long_term.write_candidates(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            candidates=candidates,
        )
        summary = conversations.compact_if_needed(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            task_checkpoint=checkpoint,
        )
        conversations.cleanup_expired(tenant_id=tenant_id, user_id=user_id)
        TaskCheckpointService(db).cleanup_expired(tenant_id=tenant_id, user_id=user_id)
        long_term.apply_forgetting(tenant_id=tenant_id, user_id=user_id)
        return {
            "task_checkpoint": checkpoint,
            "conversation_summary": summary or state.get("conversation_summary"),
            "memory_candidates": [
                {
                    "memory_type": candidate.memory_type,
                    "subject_key": candidate.subject_key,
                    "content": candidate.content,
                    "write_score": candidate.write_score,
                }
                for candidate in candidates
            ],
            "memory_write_results": writes,
        }
    except Exception:
        db.rollback()
        logger.exception("提交分层记忆失败")
        return {"memory_write_results": [{"status": "error"}]}
    finally:
        db.close()


def _tool_summary(result: dict) -> dict:
    data = result.get("data")
    if isinstance(data, dict):
        safe_data = {
            str(key): value
            for key, value in list(data.items())[:12]
            if key not in {"content", "documents"}
        }
    else:
        safe_data = data
    return {
        "success": bool(result.get("success")),
        "data": safe_data,
        "error": str(result.get("error") or "")[:300] or None,
    }
