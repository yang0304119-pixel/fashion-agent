import unittest

from app.agent.nodes.fallback_node import fallback_node


class FallbackNodeTests(unittest.TestCase):
    def test_greeting_uses_fixed_reply_without_tool(self):
        result = fallback_node({"message": "您好！"})
        self.assertEqual(result["tool_status"], "skipped")
        self.assertTrue(result["fallback_handled"])
        self.assertIn("查询订单", result["final_answer"])

    def test_thanks_and_goodbye_are_handled(self):
        self.assertTrue(
            fallback_node({"message": "谢谢"})["fallback_handled"]
        )
        self.assertTrue(
            fallback_node({"message": "再见。"})["fallback_handled"]
        )

    def test_unknown_message_remains_bad_case(self):
        result = fallback_node({"message": "帮我写一首诗"})
        self.assertFalse(result["fallback_handled"])
        self.assertIn("没有理解", result["final_answer"])


if __name__ == "__main__":
    unittest.main()
