import unittest

from app.agent.intent_rules import classify_by_rules, detect_all_intents


class IntentRuleTests(unittest.TestCase):
    def test_order_and_inventory_are_composite(self):
        message = "帮我看看订单10001发货了吗，另外围巾还有库存吗？"
        self.assertEqual(classify_by_rules(message), "composite_query")
        self.assertEqual(
            set(detect_all_intents(message)),
            {"order_query", "inventory_query"},
        )

    def test_size_and_inventory_are_composite(self):
        self.assertEqual(
            classify_by_rules("我身高175体重70穿什么码，这款还有货吗"),
            "composite_query",
        )

    def test_refund_overrides_order_and_never_enters_react(self):
        self.assertEqual(
            classify_by_rules("订单10001申请退款"),
            "refund_request",
        )

    def test_single_order_intent_stays_deterministic(self):
        self.assertEqual(classify_by_rules("订单10001发货了吗"), "order_query")

    def test_greeting_does_not_turn_order_into_composite(self):
        self.assertEqual(
            classify_by_rules("你好，帮我查一下订单10001"),
            "order_query",
        )

    def test_refund_policy_is_knowledge_not_refund_action(self):
        self.assertEqual(classify_by_rules("退款规则是什么"), "knowledge_query")

    def test_structured_product_questions_use_deterministic_product_service(self):
        for message in ("这件多少钱", "有哪些颜色", "有哪些尺码"):
            self.assertEqual(classify_by_rules(message), "product_query")

    def test_measurement_only_size_question_does_not_need_llm(self):
        self.assertEqual(
            classify_by_rules("我175cm、70kg，喜欢正常合身"),
            "size_recommend",
        )


if __name__ == "__main__":
    unittest.main()
