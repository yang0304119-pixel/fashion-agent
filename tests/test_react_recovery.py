import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import app.agent.nodes.react_node as react_module
from app.tools._registry import QueryOrderArguments, ToolSpec
from app.tools.executor import CircuitBreakerRegistry, ToolExecutor


react_function = react_module.react_node


def response(*, tool_name=None, arguments=None, content=None, call_id="call-1"):
    tool_calls = []
    if tool_name is not None:
        tool_calls = [SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=tool_name, arguments=arguments),
        )]
    message = SimpleNamespace(tool_calls=tool_calls, content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


class ReactRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.breakers = CircuitBreakerRegistry(
            failure_threshold=10,
            cooldown_seconds=30,
        )
        self.executor = ToolExecutor(
            max_transient_retries=0,
            retry_base_seconds=0,
            retry_max_seconds=0,
            circuit_breakers=self.breakers,
            sleeper=lambda delay: None,
            jitter=lambda: 0,
        )

    def test_invalid_arguments_are_reflected_then_corrected(self):
        handler_calls = []

        def handler(order_id, *, user_id, tenant_id):
            handler_calls.append((order_id, user_id, tenant_id))
            return {
                "success": True,
                "data": {"order_id": order_id, "status": "pending"},
                "error": None,
            }

        completions = FakeCompletions([
            response(tool_name="query_order", arguments="{bad-json", call_id="bad"),
            response(
                tool_name="query_order",
                arguments='{"order_id":10001}',
                call_id="good",
            ),
            response(content="订单 10001 当前待发货。"),
        ])
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        specs = {
            "query_order": ToolSpec(
                "query_order",
                handler,
                QueryOrderArguments,
                ("user_id", "tenant_id"),
            )
        }

        with (
            patch.object(react_module, "OpenAI", return_value=fake_client),
            patch.object(react_module, "TOOL_SPECS", specs),
            patch.object(react_module, "tool_executor", self.executor),
            patch.object(react_module, "_circuit_breakers", self.breakers),
        ):
            result = react_function({
                "message": "查询订单10001和其他信息",
                "user_id": 7,
                "tenant_id": 9,
                "intents": ["order_query", "knowledge_query"],
            })

        self.assertEqual(handler_calls, [(10001, 7, 9)])
        self.assertEqual(result["tool_status"], "success")
        self.assertIn("待发货", result["final_answer"])
        query_attempts = [
            attempt for attempt in result["tool_attempts"]
            if attempt["tool_name"] == "query_order"
        ]
        self.assertEqual(query_attempts[0]["error"]["category"], "validation")
        self.assertEqual(query_attempts[0]["recovery_action"], "reflect")
        self.assertEqual(query_attempts[1]["status"], "succeeded")

    def test_direct_answer_is_rejected_until_a_tool_is_used(self):
        handler_calls = []

        def handler(order_id, *, user_id, tenant_id):
            handler_calls.append(order_id)
            return {"success": True, "data": {"order_id": order_id}, "error": None}

        completions = FakeCompletions([
            response(content="我猜订单已经发货。"),
            response(tool_name="query_order", arguments='{"order_id":10001}'),
            response(content="根据订单系统，订单仍待发货。"),
        ])
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        specs = {
            "query_order": ToolSpec(
                "query_order", handler, QueryOrderArguments, ("user_id", "tenant_id")
            )
        }

        with (
            patch.object(react_module, "OpenAI", return_value=fake_client),
            patch.object(react_module, "TOOL_SPECS", specs),
            patch.object(react_module, "tool_executor", self.executor),
            patch.object(react_module, "_circuit_breakers", self.breakers),
        ):
            result = react_function({
                "message": "订单10001状态和其他信息",
                "user_id": 1,
                "tenant_id": 1,
                "intents": ["order_query", "knowledge_query"],
            })

        self.assertEqual(handler_calls, [10001])
        self.assertEqual(completions.calls, 3)
        self.assertIn("订单系统", result["final_answer"])

    def test_expired_execution_deadline_stops_before_llm_or_tool_call(self):
        completions = FakeCompletions([
            response(tool_name="query_order", arguments='{"order_id":10001}'),
        ])
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        )
        with patch.object(react_module, "OpenAI", return_value=fake_client):
            result = react_function({
                "message": "查询订单10001和库存",
                "user_id": 1,
                "tenant_id": 1,
                "intents": ["order_query", "inventory_query"],
                "execution_deadline_at": (
                    datetime.now(UTC) - timedelta(seconds=1)
                ).isoformat(),
            })

        self.assertEqual(completions.calls, 0)
        self.assertTrue(result["human_required"])
        self.assertIn("最大执行时间", result["final_answer"])


if __name__ == "__main__":
    unittest.main()
