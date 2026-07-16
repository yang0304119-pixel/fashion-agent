"""
ReAct 循环节点

LLM 自主决策：调用工具 → 结果反馈给 LLM → 再决策 → 直到生成最终回答。
替代 Phase 4 tool_node（硬编码调度）和 Phase 5 refund_node（硬编码编排）。

# 关键设计说明
# ─────────────────────────────
# 为什么引入 ReAct 而非继续用 Python 编排：
# - 原来 tool_node + refund_node 本质是 if-else 调用链，新增工具要改代码
# - ReAct 下 LLM 根据工具描述自主选择参数和调用顺序，新增工具只注册一行
# - 退款三步（查单→风险判断→建工单）由 LLM 根据中间结果动态决策
# 为什么限定最大迭代次数：
# - 防止 LLM 陷入循环或无限调用工具
# - 超限后返回兜底提示，不影响用户体验
# ─────────────────────────────
"""

import json
import logging

from openai import OpenAI

from app.agent.state import AgentState
from app.core.config import settings
from app.tools._registry import TOOL_DEFINITIONS, TOOL_HANDLERS

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


def react_node(state: AgentState) -> dict:
    """ReAct 循环：LLM 选择工具 → 执行 → 反馈 → 再决策 → 回答。

    Args:
        state: 当前 AgentState，至少包含 message 和 user_id。

    Returns:
        更新 state 的字典，包含 final_answer。
    """
    message: str = state.get("message", "").strip()
    user_id: int = state.get("user_id", 0)

    if not message:
        return {"final_answer": "您好，请问有什么可以帮您的？"}

    # ── 系统 prompt ──
    system_prompt = (
        f"你是一个服装电商客服助手。当前用户 ID 为 {user_id}。\n\n"
        "你可以使用以下工具帮助用户。当用户的问题需要查询数据或执行业务操作时，"
        "选择正确的工具并传入参数。\n"
        "每次只调用一个工具，等待返回结果后再决定下一步。\n"
        "当已经获取足够信息时，直接给用户最终回答。\n\n"
        "可用工具：\n"
        f"{_format_tool_descriptions()}\n\n"
        "注意：\n"
        "- 工具参数必须从用户消息中提取，不要编造\n"
        "- 如果用户缺少必要信息（如未提供订单号），先询问用户补充\n"
        "- 退款流程分三步：先 query_order 查订单 → 再 risk_check 判断风险 "
        "→ 高风险时 create_ticket 创建工单\n"
        "- 回答简洁自然，像客服在和用户对话"
    )

    # ── 构造消息历史 ──
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_API_BASE,
    )

    for iteration in range(MAX_ITERATIONS):
        try:
            response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                max_tokens=1000,
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"ReAct LLM 调用失败 (第 {iteration} 轮): {e}")
            return {"final_answer": "抱歉，我现在无法处理您的请求，请稍后再试。"}

        choice = response.choices[0]
        assistant_msg = choice.message

        # ── LLM 选择直接回答 → 结束循环 ──
        if not assistant_msg.tool_calls:
            answer = (assistant_msg.content or "").strip()
            if answer:
                return {"final_answer": answer}
            # 空回答继续循环，由兜底逻辑截断
            continue

        # ── LLM 选择调用工具 ──
        for tool_call in assistant_msg.tool_calls:
            func_name = tool_call.function.name
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}

            logger.info(
                "ReAct 调用工具: %s, 参数: %s (第 %d 轮)",
                func_name, args, iteration + 1,
            )

            # 执行工具
            handler = TOOL_HANDLERS.get(func_name)
            if not handler:
                result = {"success": False, "error": f"未知工具：{func_name}"}
            else:
                try:
                    result = handler(**args)
                except Exception as e:
                    result = {"success": False, "error": f"工具执行异常：{str(e)}"}

            # 将 assistant 消息（含 tool_call）和工具结果追加到历史
            messages.append(assistant_msg)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

        # 下一轮循环：LLM 根据工具结果继续决策

    # 超过最大迭代次数 → 兜底
    logger.warning(f"ReAct 超过最大迭代次数 ({MAX_ITERATIONS})，返回兜底提示")
    return {"final_answer": "抱歉，处理您的请求耗时过长，请稍后再试或联系客服。"}


def _format_tool_descriptions() -> str:
    """将工具注册表格式化为 LLM 可读的描述文本。"""
    lines = []
    for t in TOOL_DEFINITIONS:
        func = t["function"]
        params = func.get("parameters", {}).get("properties", {})
        required = func.get("parameters", {}).get("required", [])

        parts = []
        for name, info in params.items():
            required_mark = "（必填）" if name in required else "（可选）"
            parts.append(f"{name}: {info.get('description', '')}{required_mark}")

        param_str = ", ".join(parts) if parts else "无参数"
        lines.append(f"- {func['name']}({param_str}): {func['description']}")

    return "\n".join(lines)
