import unittest
from types import SimpleNamespace

from pydantic import BaseModel, ConfigDict

from app.tools.executor import (
    CircuitBreakerRegistry,
    ToolErrorCategory,
    ToolErrorDetail,
    ToolExecutor,
    execute_resilient_operation,
    failure_result,
)


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: int


def spec(
    handler,
    *,
    trusted_fields=(),
    action_type="read",
    risk_level="low",
    approval_required=False,
):
    return SimpleNamespace(
        name="test_tool",
        handler=handler,
        args_model=StrictArguments,
        trusted_fields=trusted_fields,
        action_type=action_type,
        risk_level=risk_level,
        approval_required=approval_required,
    )


class ToolExecutorTests(unittest.TestCase):
    def executor(self, *, threshold=10, retries=2):
        return ToolExecutor(
            max_transient_retries=retries,
            retry_base_seconds=0,
            retry_max_seconds=0,
            circuit_breakers=CircuitBreakerRegistry(
                failure_threshold=threshold,
                cooldown_seconds=30,
            ),
            sleeper=lambda delay: None,
            jitter=lambda: 0,
        )

    def test_validation_error_returns_structured_reflection_hint(self):
        called = []
        outcome = self.executor().execute(
            spec=spec(lambda **kwargs: called.append(kwargs)),
            raw_arguments='{"value":"1","extra":true}',
            trusted_context={},
        )

        self.assertEqual(called, [])
        detail = outcome.result["error_detail"]
        self.assertEqual(detail["category"], "validation")
        self.assertEqual(detail["code"], "invalid_tool_arguments")
        self.assertTrue(detail["retryable"])
        self.assertEqual(outcome.attempts[0]["recovery_action"], "reflect")

    def test_tool_firewall_denies_llm_write_tool_before_validation_or_execution(self):
        called = []
        outcome = self.executor().execute(
            spec=spec(
                lambda **kwargs: called.append(kwargs),
                action_type="write",
                risk_level="high",
                approval_required=True,
            ),
            raw_arguments='{"value":1}',
            trusted_context={},
        )

        self.assertEqual(called, [])
        self.assertTrue(outcome.halted)
        self.assertTrue(outcome.human_required)
        self.assertEqual(
            outcome.result["error_detail"]["code"],
            "tool_firewall_denied",
        )

    def test_transient_error_retries_with_limit_then_recovers(self):
        calls = []

        def handler(**kwargs):
            calls.append(kwargs)
            if len(calls) < 3:
                return failure_result(ToolErrorDetail(
                    category=ToolErrorCategory.TRANSIENT,
                    code="temporary_failure",
                    message="暂时失败",
                    retryable=True,
                ))
            return {"success": True, "data": {"value": kwargs["value"]}, "error": None}

        outcome = self.executor().execute(
            spec=spec(handler),
            raw_arguments='{"value":1}',
            trusted_context={},
        )

        self.assertEqual(len(calls), 3)
        self.assertEqual(outcome.status, "success")
        self.assertEqual(
            [attempt["recovery_action"] for attempt in outcome.attempts],
            ["retry_with_backoff", "retry_with_backoff", "completed"],
        )

    def test_circuit_opens_and_blocks_followup_call(self):
        calls = []

        def handler(**kwargs):
            calls.append(kwargs)
            return failure_result(ToolErrorDetail(
                category=ToolErrorCategory.TRANSIENT,
                code="upstream_down",
                message="上游故障",
                retryable=True,
            ))

        executor = self.executor(threshold=2, retries=0)
        first = executor.execute(
            spec=spec(handler), raw_arguments='{"value":1}', trusted_context={}
        )
        second = executor.execute(
            spec=spec(handler), raw_arguments='{"value":1}', trusted_context={}
        )
        third = executor.execute(
            spec=spec(handler), raw_arguments='{"value":1}', trusted_context={}
        )

        self.assertEqual(first.result["error_detail"]["code"], "upstream_down")
        self.assertTrue(second.halted)
        self.assertEqual(third.result["error_detail"]["code"], "circuit_open")
        self.assertEqual(len(calls), 2)

    def test_missing_server_identity_halts_without_calling_handler(self):
        called = []
        outcome = self.executor().execute(
            spec=spec(lambda **kwargs: called.append(kwargs), trusted_fields=("tenant_id",)),
            raw_arguments='{"value":1}',
            trusted_context={},
        )

        self.assertEqual(called, [])
        self.assertTrue(outcome.halted)
        self.assertTrue(outcome.human_required)
        self.assertEqual(outcome.result["error_detail"]["category"], "auth")

    def test_malformed_tool_response_is_fatal_and_not_retried(self):
        calls = []

        def handler(**kwargs):
            calls.append(kwargs)
            return "broken response"

        outcome = self.executor().execute(
            spec=spec(handler),
            raw_arguments='{"value":1}',
            trusted_context={},
        )

        self.assertEqual(len(calls), 1)
        self.assertTrue(outcome.halted)
        self.assertTrue(outcome.human_required)
        self.assertEqual(
            outcome.result["error_detail"]["code"],
            "invalid_tool_response",
        )

    def test_rate_limit_operation_uses_bounded_backoff_retry(self):
        rate_limit_error = type("RateLimitError", (Exception,), {})
        calls = []

        def operation():
            calls.append(1)
            if len(calls) == 1:
                raise rate_limit_error("429")
            return "ok"

        outcome = execute_resilient_operation(
            operation_name="test_llm",
            operation=operation,
            max_transient_retries=2,
            retry_base_seconds=0,
            retry_max_seconds=0,
            circuit_breakers=CircuitBreakerRegistry(
                failure_threshold=10,
                cooldown_seconds=30,
            ),
            sleeper=lambda delay: None,
            jitter=lambda: 0,
        )

        self.assertEqual(outcome.value, "ok")
        self.assertEqual(len(calls), 2)
        self.assertEqual(outcome.attempts[0]["recovery_action"], "retry_with_backoff")


if __name__ == "__main__":
    unittest.main()
