"""RAG 知识问答节点。"""

import logging

from app.agent.state import AgentState
from app.rag.errors import RagError
from app.rag.service import answer_question


logger = logging.getLogger(__name__)


def _error_state(
    *,
    answer: str,
    code: str,
    stage: str,
    error_type: str,
) -> dict:
    return {
        "retrieved_docs": [],
        "retrieved_doc_ids": [],
        "retrieved_scores": [],
        "retrieved_sources": [],
        "rag_error_code": code,
        "rag_error_stage": stage,
        "rag_error_type": error_type,
        "final_answer": answer,
    }


def rag_node(state: AgentState) -> dict:
    """调用 RAG 服务并将结果映射到 AgentState。"""

    message: str = state.get("message", "").strip()

    try:
        result = answer_question(message)
    except FileNotFoundError as error:
        logger.exception(
            "RAG 知识库未初始化",
            extra={
                "rag_error_code": "knowledge_base_uninitialized",
                "rag_error_stage": "initialization",
            },
        )
        return _error_state(
            answer=(
                "抱歉，知识库尚未初始化，"
                "请联系管理员导入知识库后再试。"
            ),
            code="knowledge_base_uninitialized",
            stage="initialization",
            error_type=type(error).__name__,
        )
    except RagError as error:
        logger.exception(
            "RAG 阶段执行失败: %s",
            error.info.stage,
            extra={
                "rag_error_code": error.info.code,
                "rag_error_stage": error.info.stage,
                "rag_error_type": error.info.error_type,
            },
        )
        return _error_state(
            answer=(
                "抱歉，我现在无法处理您的请求，"
                "请稍后再试。"
            ),
            code=error.info.code,
            stage=error.info.stage,
            error_type=error.info.error_type,
        )
    except Exception as error:
        logger.exception(
            "RAG 未分类异常",
            extra={
                "rag_error_code": "unexpected_error",
                "rag_error_stage": "unknown",
                "rag_error_type": type(error).__name__,
            },
        )
        return _error_state(
            answer=(
                "抱歉，我现在无法处理您的请求，"
                "请稍后再试。"
            ),
            code="unexpected_error",
            stage="unknown",
            error_type=type(error).__name__,
        )

    try:
        documents = result["documents"]
        answer = result["answer"]
        sources = result.get("sources", [])

        if not isinstance(documents, list):
            raise TypeError("documents must be a list")
        if not isinstance(answer, str):
            raise TypeError("answer must be a string")
        if not isinstance(sources, list):
            raise TypeError("sources must be a list")
    except (KeyError, TypeError) as error:
        logger.exception(
            "RAG 返回格式错误",
            extra={
                "rag_error_code": "invalid_response",
                "rag_error_stage": "response_validation",
                "rag_error_type": type(error).__name__,
            },
        )
        return _error_state(
            answer=(
                "抱歉，我现在无法处理您的请求，"
                "请稍后再试。"
            ),
            code="invalid_response",
            stage="response_validation",
            error_type=type(error).__name__,
        )

    return {
        "retrieved_docs": [
            document.page_content
            for document in documents
        ],
        "retrieved_doc_ids": [
            str(
                document.metadata.get("chunk_id")
                or document.id
                or document.metadata.get("doc_id", "")
            )
            for document in documents
        ],
        "retrieved_scores": [
            float(
                document.metadata.get(
                    "relevance_score",
                    0.0,
                )
            )
            for document in documents
        ],
        "retrieved_sources": sources,
        "rag_error_code": None,
        "rag_error_stage": None,
        "rag_error_type": None,
        "final_answer": answer,
    }
