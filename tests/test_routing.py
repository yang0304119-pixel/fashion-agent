import unittest

from app.agent.routing import route_by_intent


class RoutingTests(unittest.TestCase):
    def test_single_business_intents_use_deterministic_nodes(self):
        expected = {
            "knowledge_query": "rag",
            "order_query": "order",
            "inventory_query": "inventory",
            "size_recommend": "size",
            "refund_request": "refund",
            "composite_query": "react",
        }
        for intent, route in expected.items():
            with self.subTest(intent=intent):
                self.assertEqual(route_by_intent({"intent": intent}), route)

    def test_fallback_and_unknown_intents_use_fixed_fallback(self):
        self.assertEqual(route_by_intent({"intent": "fallback"}), "fallback")
        self.assertEqual(route_by_intent({"intent": "unknown"}), "fallback")
        self.assertEqual(route_by_intent({}), "fallback")

    def test_refund_stays_on_deterministic_workflow(self):
        self.assertEqual(route_by_intent({"intent": "refund_request"}), "refund")
        self.assertNotEqual(
            route_by_intent({"intent": "refund_request"}),
            "react",
        )


if __name__ == "__main__":
    unittest.main()
