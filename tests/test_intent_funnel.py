import unittest
from unittest.mock import patch

from app.agent.nodes.router_node import router_node
from app.agent.planner import PlannerDecision
from app.agent.semantic_router import SemanticRouteResult


class IntentFunnelTests(unittest.TestCase):
    def test_high_precision_rules_separate_refund_semantics(self):
        cases = {
            "退款规则是什么？": "knowledge_query",
            "退款多久到账？": "knowledge_query",
            "我的退款到哪了？": "refund_status_query",
            "衣服起球正常吗？": "knowledge_query",
            "帮我退订单10001": "refund_request",
            "帮我换成L码": "after_sales_request",
            "取消订单10001": "after_sales_request",
            "转人工客服": "human_handoff",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                result = router_node({"message": message})
                self.assertEqual(result["intent"], expected)
                self.assertEqual(result["router_source"], "deterministic_rule")

    def test_semantic_router_can_direct_route_contextual_product_question(self):
        semantic = SemanticRouteResult(
            intents=["inventory_query"],
            confidence=0.88,
            source="semantic_router",
            evidence=["当前商品上下文"],
            requires_planning=False,
        )
        with patch(
            "app.agent.nodes.router_node.semantic_router.route",
            return_value=semantic,
        ), patch("app.agent.nodes.router_node.plan_intents") as planner:
            result = router_node({
                "message": "黑色L呢？",
                "chat_context": {"context_type": "product", "product_id": 1},
                "collected_slots": {"product_id": 1},
            })
        self.assertEqual(result["intent"], "inventory_query")
        self.assertEqual(result["router_source"], "semantic_router")
        planner.assert_not_called()

    def test_low_confidence_multi_intent_uses_planner(self):
        semantic = SemanticRouteResult(
            intents=["inventory_query", "knowledge_query"],
            confidence=0.66,
            source="semantic_router",
            evidence=["语义冲突"],
            requires_planning=True,
        )
        planner = PlannerDecision(
            intents=["inventory_query", "knowledge_query"],
            confidence=0.91,
            evidence=["需要库存和洗护知识"],
            requires_clarification=False,
            clarification_question=None,
        )
        with patch(
            "app.agent.nodes.router_node.semantic_router.route",
            return_value=semantic,
        ), patch(
            "app.agent.nodes.router_node.plan_intents",
            return_value=planner,
        ):
            result = router_node({"message": "这件的情况帮我一起看看。"})
        self.assertEqual(result["intent"], "composite_query")
        self.assertEqual(result["intents"], ["inventory_query", "knowledge_query"])
        self.assertTrue(result["requires_planning"])

    def test_explicit_multi_intent_can_be_caught_by_rules(self):
        result = router_node({"message": "这件还有货吗，应该怎么洗？"})
        self.assertEqual(result["intent"], "composite_query")
        self.assertEqual(
            result["intents"],
            ["inventory_query", "knowledge_query"],
        )
        self.assertEqual(result["router_source"], "deterministic_rule")
        self.assertTrue(result["requires_planning"])

    def test_planner_cannot_turn_ambiguous_refund_text_into_write_action(self):
        semantic = SemanticRouteResult(
            intents=["refund_request"],
            confidence=0.62,
            source="semantic_router",
            evidence=[],
            requires_planning=True,
        )
        planner = PlannerDecision(
            intents=["refund_request"],
            confidence=0.9,
            evidence=["提到退款"],
            requires_clarification=False,
            clarification_question=None,
        )
        with patch(
            "app.agent.nodes.router_node.semantic_router.route",
            return_value=semantic,
        ), patch(
            "app.agent.nodes.router_node.plan_intents",
            return_value=planner,
        ):
            result = router_node({"message": "这个可以退吗？"})
        self.assertEqual(result["intent"], "knowledge_query")

    def test_empty_or_unavailable_planner_falls_back_safely(self):
        with patch(
            "app.agent.nodes.router_node.semantic_router.route",
            return_value=None,
        ), patch(
            "app.agent.nodes.router_node.plan_intents",
            return_value=None,
        ):
            result = router_node({"message": "这个不太对劲怎么办"})
        self.assertEqual(result["intent"], "fallback")
        self.assertEqual(result["router_source"], "safe_fallback")


if __name__ == "__main__":
    unittest.main()
