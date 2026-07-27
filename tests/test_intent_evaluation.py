import unittest

from app.services.intent_evaluation_service import IntentEvaluationRunner


class IntentEvaluationTests(unittest.TestCase):
    def test_accuracy_macro_f1_and_write_metrics(self):
        cases = [
            {"id": "1", "message": "a", "expected_intent": "order_query", "label_reason": "clear order lookup"},
            {"id": "2", "message": "b", "expected_intent": "refund_request", "label_reason": "explicit action"},
            {"id": "3", "message": "c", "expected_intent": "fallback", "label_reason": "out of scope"},
        ]
        decisions = {
            "a": {"intent": "order_query", "router_source": "rule", "confidence": 1},
            "b": {"intent": "knowledge_query", "router_source": "semantic", "confidence": 0.5},
            "c": {"intent": "fallback", "router_source": "rule", "confidence": 1},
        }

        report = IntentEvaluationRunner().run(
            cases,
            predict=lambda message: decisions[message],
        )

        self.assertEqual(report.metrics["accuracy"], 0.6667)
        self.assertEqual(report.metrics["write_intent_recall"], 0.0)
        self.assertEqual(report.metrics["fallback_rate"], 0.3333)
        self.assertEqual(report.source_counts, {"rule": 2, "semantic": 1})


if __name__ == "__main__":
    unittest.main()
