import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.agent.planner import plan_intents


def _client_with_payload(payload):
    message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    completions = SimpleNamespace(create=lambda **kwargs: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class PlannerTests(unittest.TestCase):
    def test_structured_multilabel_output_is_parsed(self):
        payload = {
            "intents": ["inventory_query", "knowledge_query"],
            "confidence": 0.91,
            "evidence": ["需要库存和洗护知识"],
            "requires_clarification": False,
            "clarification_question": None,
        }
        with patch("app.agent.planner.settings.LLM_API_KEY", "test-key"), patch(
            "app.agent.planner.OpenAI",
            return_value=_client_with_payload(payload),
        ):
            decision = plan_intents(
                message="一起看看库存和洗护",
                semantic_intents=["inventory_query", "knowledge_query"],
                context_summary="当前商品=1",
            )

        self.assertIsNotNone(decision)
        self.assertEqual(
            decision.intents,
            ["inventory_query", "knowledge_query"],
        )
        self.assertEqual(decision.confidence, 0.91)

    def test_empty_or_invalid_model_output_fails_closed(self):
        invalid_message = SimpleNamespace(content="not-json")
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=invalid_message)]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: response)
            )
        )
        with patch("app.agent.planner.settings.LLM_API_KEY", "test-key"), patch(
            "app.agent.planner.OpenAI",
            return_value=client,
        ):
            decision = plan_intents(
                message="模糊请求",
                semantic_intents=[],
                context_summary="",
            )
        self.assertIsNone(decision)

    def test_malformed_confidence_does_not_raise(self):
        payload = {
            "intents": ["order_query"],
            "confidence": "unknown",
            "evidence": "not-a-list",
        }
        with patch("app.agent.planner.settings.LLM_API_KEY", "test-key"), patch(
            "app.agent.planner.OpenAI",
            return_value=_client_with_payload(payload),
        ):
            decision = plan_intents(
                message="查订单",
                semantic_intents=["order_query"],
                context_summary="",
            )
        self.assertEqual(decision.confidence, 0.0)
        self.assertEqual(decision.evidence, [])


if __name__ == "__main__":
    unittest.main()

