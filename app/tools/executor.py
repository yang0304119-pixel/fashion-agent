"""统一的工具调用保护层：校验、分类、重试、熔断和恢复决策。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import random
import threading
import time
from time import perf_counter
from typing import Any, Callable

from pydantic import BaseModel, ValidationError


class ToolErrorCategory(StrEnum):
    VALIDATION = "validation"
    TRANSIENT = "transient"
    BUSINESS = "business"
    AUTH = "auth"
    FATAL = "fatal"


@dataclass(frozen=True)
class ToolErrorDetail:
    category: ToolErrorCategory
    code: str
    message: str
    retryable: bool = False
    correction_hint: str | None = None
    handoff_required: bool = False
    retry_after_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "correction_hint": self.correction_hint,
            "handoff_required": self.handoff_required,
            "retry_after_seconds": self.retry_after_seconds,
        }


def failure_result(detail: ToolErrorDetail) -> dict[str, Any]:
    """构造兼容旧工具契约、同时可供恢复路由使用的结构化错误。"""
    return {
        "success": False,
        "data": None,
        "error": detail.message,
        "error_detail": detail.to_dict(),
    }


@dataclass(frozen=True)
class ToolExecutionOutcome:
    result: dict[str, Any]
    attempts: list[dict[str, Any]]
    status: str
    human_required: bool
    halted: bool


@dataclass(frozen=True)
class OperationOutcome:
    value: Any | None
    attempts: list[dict[str, Any]]
    error: ToolErrorDetail | None
    human_required: bool
    halted: bool


@dataclass
class _CircuitState:
    consecutive_failures: int = 0
    opened_until: float = 0.0


class CircuitBreakerRegistry:
    """进程内轻量熔断器；多进程部署时应替换为 Redis 等共享状态。"""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(0.1, cooldown_seconds)
        self.clock = clock
        self._states: dict[str, _CircuitState] = {}
        self._lock = threading.Lock()

    def remaining_open_seconds(self, operation_name: str) -> float:
        with self._lock:
            state = self._states.setdefault(operation_name, _CircuitState())
            now = self.clock()
            if state.opened_until <= now:
                if state.opened_until:
                    state.opened_until = 0.0
                    state.consecutive_failures = 0
                return 0.0
            return state.opened_until - now

    def record_success(self, operation_name: str) -> None:
        with self._lock:
            self._states[operation_name] = _CircuitState()

    def record_transient_failure(self, operation_name: str) -> bool:
        with self._lock:
            state = self._states.setdefault(operation_name, _CircuitState())
            state.consecutive_failures += 1
            if state.consecutive_failures >= self.failure_threshold:
                state.opened_until = self.clock() + self.cooldown_seconds
                return True
            return False

    def reset(self) -> None:
        with self._lock:
            self._states.clear()


GLOBAL_CIRCUIT_BREAKERS = CircuitBreakerRegistry()


class ToolFirewall:
    """LLM工具防火墙；默认只允许显式标记为低风险只读的工具。"""

    def authorize(self, spec: Any) -> ToolErrorDetail | None:
        action_type = str(getattr(spec, "action_type", "read"))
        risk_level = str(getattr(spec, "risk_level", "low"))
        approval_required = bool(getattr(spec, "approval_required", False))
        if action_type != "read" or risk_level not in {"low", "medium"} or approval_required:
            return ToolErrorDetail(
                category=ToolErrorCategory.AUTH,
                code="tool_firewall_denied",
                message="工具防火墙拒绝LLM执行写入、高风险或需要审批的工具",
                retryable=False,
                correction_hint="改用只读工具，或转入确定性业务工作流和人工审批",
                handoff_required=True,
            )
        return None


GLOBAL_TOOL_FIREWALL = ToolFirewall()


def classify_exception(error: Exception) -> ToolErrorDetail:
    """按恢复语义分类第三方异常，避免对所有异常无脑重试。"""
    error_name = type(error).__name__
    message = str(error).strip() or error_name

    if isinstance(error, (TimeoutError, ConnectionError)) or error_name in {
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
        "ServiceUnavailableError",
        "OperationalError",
    }:
        retry_after = getattr(error, "retry_after", None)
        try:
            retry_after_value = float(retry_after) if retry_after is not None else None
        except (TypeError, ValueError):
            retry_after_value = None
        return ToolErrorDetail(
            category=ToolErrorCategory.TRANSIENT,
            code=_exception_code(error_name),
            message="上游服务暂时不可用",
            retryable=True,
            correction_hint="保持原参数，等待退避后重试",
            retry_after_seconds=retry_after_value,
        )

    if isinstance(error, PermissionError) or error_name in {
        "AuthenticationError",
        "PermissionDeniedError",
    }:
        return ToolErrorDetail(
            category=ToolErrorCategory.AUTH,
            code=_exception_code(error_name),
            message="工具鉴权或权限校验失败",
            retryable=False,
            handoff_required=True,
        )

    if error_name in {"BadRequestError", "UnprocessableEntityError"}:
        return ToolErrorDetail(
            category=ToolErrorCategory.VALIDATION,
            code=_exception_code(error_name),
            message=message[:300],
            retryable=True,
            correction_hint="根据错误信息修正请求参数后重新生成",
        )

    return ToolErrorDetail(
        category=ToolErrorCategory.FATAL,
        code=_exception_code(error_name),
        message="工具执行发生未分类异常",
        retryable=False,
        handoff_required=True,
    )


class ToolExecutor:
    def __init__(
        self,
        *,
        max_transient_retries: int = 2,
        retry_base_seconds: float = 0.25,
        retry_max_seconds: float = 2.0,
        circuit_breakers: CircuitBreakerRegistry = GLOBAL_CIRCUIT_BREAKERS,
        firewall: ToolFirewall = GLOBAL_TOOL_FIREWALL,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        self.max_transient_retries = max(0, max_transient_retries)
        self.retry_base_seconds = max(0.0, retry_base_seconds)
        self.retry_max_seconds = max(self.retry_base_seconds, retry_max_seconds)
        self.circuit_breakers = circuit_breakers
        self.firewall = firewall
        self.sleeper = sleeper
        self.jitter = jitter

    def execute(
        self,
        *,
        spec: Any,
        raw_arguments: str,
        trusted_context: dict[str, Any],
    ) -> ToolExecutionOutcome:
        denied = self.firewall.authorize(spec)
        if denied is not None:
            attempt = _attempt_record(
                attempt=1,
                status="blocked",
                arguments={},
                duration_ms=0,
                error=denied,
                recovery_action="halt_and_handoff",
            )
            return ToolExecutionOutcome(
                result=failure_result(denied),
                attempts=[attempt],
                status="error",
                human_required=True,
                halted=True,
            )
        validation = _validate_arguments(spec.args_model, raw_arguments)
        if isinstance(validation, ToolErrorDetail):
            attempt = _attempt_record(
                attempt=1,
                status="failed",
                arguments={},
                duration_ms=0,
                error=validation,
                recovery_action="reflect",
            )
            return ToolExecutionOutcome(
                result=failure_result(validation),
                attempts=[attempt],
                status="error",
                human_required=False,
                halted=False,
            )

        model_arguments = validation
        trusted_arguments = dict(model_arguments)
        for field in spec.trusted_fields:
            value = trusted_context.get(field)
            if not value:
                detail = ToolErrorDetail(
                    category=ToolErrorCategory.AUTH,
                    code="missing_trusted_identity",
                    message=f"服务端可信字段 {field} 缺失",
                    handoff_required=True,
                )
                return ToolExecutionOutcome(
                    result=failure_result(detail),
                    attempts=[
                        _attempt_record(
                            attempt=1,
                            status="failed",
                            arguments=model_arguments,
                            duration_ms=0,
                            error=detail,
                            recovery_action="halt_and_handoff",
                        )
                    ],
                    status="error",
                    human_required=True,
                    halted=True,
                )
            trusted_arguments[field] = value

        remaining = self.circuit_breakers.remaining_open_seconds(spec.name)
        if remaining > 0:
            detail = ToolErrorDetail(
                category=ToolErrorCategory.TRANSIENT,
                code="circuit_open",
                message="工具连续失败，熔断器已开启",
                retryable=False,
                handoff_required=True,
                retry_after_seconds=round(remaining, 3),
            )
            return ToolExecutionOutcome(
                result=failure_result(detail),
                attempts=[
                    _attempt_record(
                        attempt=1,
                        status="blocked",
                        arguments=model_arguments,
                        duration_ms=0,
                        error=detail,
                        recovery_action="circuit_open_handoff",
                    )
                ],
                status="error",
                human_required=True,
                halted=True,
            )

        attempts: list[dict[str, Any]] = []
        maximum_attempts = 1 + self.max_transient_retries
        for attempt_number in range(1, maximum_attempts + 1):
            started = perf_counter()
            try:
                result = spec.handler(**trusted_arguments)
            except Exception as error:
                detail = classify_exception(error)
                result = failure_result(detail)
            duration_ms = max(0, round((perf_counter() - started) * 1000))

            if not isinstance(result, dict) or not isinstance(result.get("success"), bool):
                detail = ToolErrorDetail(
                    category=ToolErrorCategory.FATAL,
                    code="invalid_tool_response",
                    message="工具返回格式无效，缺少布尔型success字段",
                    retryable=False,
                    handoff_required=True,
                )
                result = failure_result(detail)

            if result.get("success") is True:
                self.circuit_breakers.record_success(spec.name)
                attempts.append(
                    _attempt_record(
                        attempt=attempt_number,
                        status="succeeded",
                        arguments=model_arguments,
                        duration_ms=duration_ms,
                        output=_safe_output(result),
                        recovery_action="completed",
                    )
                )
                return ToolExecutionOutcome(
                    result=result,
                    attempts=attempts,
                    status="success",
                    human_required=False,
                    halted=False,
                )

            detail = _detail_from_result(result)
            can_retry = (
                detail.category == ToolErrorCategory.TRANSIENT
                and detail.retryable
                and attempt_number < maximum_attempts
            )
            opened = False
            if detail.category == ToolErrorCategory.TRANSIENT:
                opened = self.circuit_breakers.record_transient_failure(spec.name)
                can_retry = can_retry and not opened

            if can_retry:
                delay = _retry_delay(
                    attempt_number=attempt_number,
                    detail=detail,
                    base=self.retry_base_seconds,
                    maximum=self.retry_max_seconds,
                    jitter=self.jitter(),
                )
                attempts.append(
                    _attempt_record(
                        attempt=attempt_number,
                        status="failed",
                        arguments=model_arguments,
                        duration_ms=duration_ms,
                        output=_safe_output(result),
                        error=detail,
                        recovery_action="retry_with_backoff",
                        retry_delay_seconds=delay,
                    )
                )
                self.sleeper(delay)
                continue

            exhausted = (
                detail.category == ToolErrorCategory.TRANSIENT
                and (attempt_number >= maximum_attempts or opened)
            )
            human_required = detail.handoff_required or exhausted
            recovery_action = _terminal_recovery_action(detail, opened=opened)
            attempts.append(
                _attempt_record(
                    attempt=attempt_number,
                    status="failed",
                    arguments=model_arguments,
                    duration_ms=duration_ms,
                    output=_safe_output(result),
                    error=detail,
                    recovery_action=recovery_action,
                )
            )
            if exhausted and not detail.handoff_required:
                detail = ToolErrorDetail(
                    category=detail.category,
                    code=detail.code,
                    message=detail.message,
                    retryable=False,
                    correction_hint=detail.correction_hint,
                    handoff_required=True,
                    retry_after_seconds=detail.retry_after_seconds,
                )
                result = failure_result(detail)
            return ToolExecutionOutcome(
                result=result,
                attempts=attempts,
                status="error",
                human_required=human_required,
                halted=(
                    detail.category in {ToolErrorCategory.AUTH, ToolErrorCategory.FATAL}
                    or exhausted
                    or opened
                ),
            )

        raise RuntimeError("unreachable tool execution state")


def execute_resilient_operation(
    *,
    operation_name: str,
    operation: Callable[[], Any],
    max_transient_retries: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
    circuit_breakers: CircuitBreakerRegistry = GLOBAL_CIRCUIT_BREAKERS,
    sleeper: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
    input_summary: dict[str, Any] | None = None,
) -> OperationOutcome:
    """为 LLM/API 等非业务工具调用提供相同的分类重试和熔断语义。"""
    remaining = circuit_breakers.remaining_open_seconds(operation_name)
    if remaining > 0:
        detail = ToolErrorDetail(
            category=ToolErrorCategory.TRANSIENT,
            code="circuit_open",
            message="上游服务熔断中",
            retryable=False,
            handoff_required=True,
            retry_after_seconds=round(remaining, 3),
        )
        return OperationOutcome(
            value=None,
            attempts=[
                _attempt_record(
                    attempt=1,
                    status="blocked",
                    arguments=input_summary or {},
                    duration_ms=0,
                    error=detail,
                    recovery_action="circuit_open_handoff",
                )
            ],
            error=detail,
            human_required=True,
            halted=True,
        )

    attempts: list[dict[str, Any]] = []
    maximum_attempts = 1 + max(0, max_transient_retries)
    for attempt_number in range(1, maximum_attempts + 1):
        started = perf_counter()
        try:
            value = operation()
        except Exception as error:
            detail = classify_exception(error)
        else:
            circuit_breakers.record_success(operation_name)
            attempts.append(
                _attempt_record(
                    attempt=attempt_number,
                    status="succeeded",
                    arguments=input_summary or {},
                    duration_ms=max(0, round((perf_counter() - started) * 1000)),
                    output={"completed": True},
                    recovery_action="completed",
                )
            )
            return OperationOutcome(value, attempts, None, False, False)

        duration_ms = max(0, round((perf_counter() - started) * 1000))
        retryable = (
            detail.category == ToolErrorCategory.TRANSIENT
            and detail.retryable
            and attempt_number < maximum_attempts
        )
        opened = False
        if detail.category == ToolErrorCategory.TRANSIENT:
            opened = circuit_breakers.record_transient_failure(operation_name)
            retryable = retryable and not opened
        if retryable:
            delay = _retry_delay(
                attempt_number=attempt_number,
                detail=detail,
                base=max(0.0, retry_base_seconds),
                maximum=max(retry_base_seconds, retry_max_seconds),
                jitter=jitter(),
            )
            attempts.append(
                _attempt_record(
                    attempt=attempt_number,
                    status="failed",
                    arguments=input_summary or {},
                    duration_ms=duration_ms,
                    error=detail,
                    recovery_action="retry_with_backoff",
                    retry_delay_seconds=delay,
                )
            )
            sleeper(delay)
            continue
        exhausted = detail.category == ToolErrorCategory.TRANSIENT
        attempts.append(
            _attempt_record(
                attempt=attempt_number,
                status="failed",
                arguments=input_summary or {},
                duration_ms=duration_ms,
                error=detail,
                recovery_action=_terminal_recovery_action(detail, opened=opened),
            )
        )
        return OperationOutcome(
            value=None,
            attempts=attempts,
            error=detail,
            human_required=detail.handoff_required or exhausted or opened,
            halted=True,
        )

    raise RuntimeError("unreachable operation execution state")


def _validate_arguments(
    model: type[BaseModel],
    raw_arguments: str,
) -> dict[str, Any] | ToolErrorDetail:
    try:
        parsed = model.model_validate_json(raw_arguments)
    except ValidationError as error:
        problems = []
        for item in error.errors()[:5]:
            location = ".".join(str(value) for value in item.get("loc", ())) or "arguments"
            problems.append(f"{location}: {item.get('msg', '参数无效')}")
        message = "；".join(problems) or "工具参数格式无效"
        return ToolErrorDetail(
            category=ToolErrorCategory.VALIDATION,
            code="invalid_tool_arguments",
            message=message[:500],
            retryable=True,
            correction_hint="只修正上述字段，严格按照工具 JSON Schema 重新生成参数",
        )
    return parsed.model_dump()


def _detail_from_result(result: dict[str, Any]) -> ToolErrorDetail:
    raw = result.get("error_detail")
    if isinstance(raw, dict):
        try:
            category = ToolErrorCategory(str(raw.get("category")))
        except ValueError:
            category = ToolErrorCategory.FATAL
        return ToolErrorDetail(
            category=category,
            code=str(raw.get("code") or "tool_error"),
            message=str(raw.get("message") or result.get("error") or "工具执行失败"),
            retryable=bool(raw.get("retryable", False)),
            correction_hint=(str(raw.get("correction_hint")) if raw.get("correction_hint") else None),
            handoff_required=bool(raw.get("handoff_required", False)),
            retry_after_seconds=(
                float(raw["retry_after_seconds"])
                if raw.get("retry_after_seconds") is not None
                else None
            ),
        )
    return ToolErrorDetail(
        category=ToolErrorCategory.FATAL,
        code="unstructured_tool_error",
        message=str(result.get("error") or "工具执行失败"),
        handoff_required=True,
    )


def _attempt_record(
    *,
    attempt: int,
    status: str,
    arguments: dict[str, Any],
    duration_ms: int,
    recovery_action: str,
    output: dict[str, Any] | None = None,
    error: ToolErrorDetail | None = None,
    retry_delay_seconds: float | None = None,
) -> dict[str, Any]:
    return {
        "attempt": attempt,
        "status": status,
        "input": _safe_output(arguments),
        "output": output,
        "duration_ms": duration_ms,
        "error": error.to_dict() if error else None,
        "recovery_action": recovery_action,
        "retry_delay_seconds": retry_delay_seconds,
    }


def _retry_delay(
    *,
    attempt_number: int,
    detail: ToolErrorDetail,
    base: float,
    maximum: float,
    jitter: float,
) -> float:
    if detail.retry_after_seconds is not None:
        return min(maximum, max(0.0, detail.retry_after_seconds))
    exponential = min(maximum, base * (2 ** max(0, attempt_number - 1)))
    return round(min(maximum, exponential + exponential * 0.2 * max(0.0, jitter)), 3)


def _terminal_recovery_action(detail: ToolErrorDetail, *, opened: bool) -> str:
    if opened:
        return "circuit_open_handoff"
    if detail.category == ToolErrorCategory.VALIDATION:
        return "reflect"
    if detail.category == ToolErrorCategory.BUSINESS:
        return "return_business_error"
    if detail.category in {ToolErrorCategory.AUTH, ToolErrorCategory.FATAL}:
        return "halt_and_handoff"
    return "retry_exhausted_handoff"


def _safe_output(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, dict):
        return {
            str(key)[:100]: _safe_output(item, depth=depth + 1)
            for key, item in list(value.items())[:20]
        }
    if isinstance(value, (list, tuple)):
        return [_safe_output(item, depth=depth + 1) for item in list(value)[:10]]
    return str(value)[:1000]


def _exception_code(error_name: str) -> str:
    pieces = []
    for index, character in enumerate(error_name):
        if character.isupper() and index:
            pieces.append("_")
        pieces.append(character.lower())
    return "".join(pieces)
