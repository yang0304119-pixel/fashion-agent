import unittest

from app.agent.nodes.size_node import size_node


class SizeNodeTests(unittest.TestCase):
    def test_missing_weight_returns_pending_slot(self):
        result = size_node({"message": "我身高175cm，穿什么码"})
        self.assertEqual(result["tool_status"], "pending")
        self.assertEqual(result["missing_slots"], ["weight"])

    def test_complete_input_returns_fixed_answer(self):
        result = size_node({"message": "175cm 70kg，喜欢宽松"})
        self.assertEqual(result["tool_status"], "success")
        self.assertEqual(result["tool_result"]["data"]["size"], "XL")
        self.assertIn("XL 码", result["final_answer"])

    def test_uses_slots_collected_in_previous_turn(self):
        result = size_node({
            "message": "70kg",
            "collected_slots": {
                "height": 175,
                "style": "宽松",
            },
        })
        self.assertEqual(result["tool_status"], "success")
        self.assertEqual(result["collected_slots"]["weight"], 70)
        self.assertEqual(result["tool_result"]["data"]["style"], "宽松")


if __name__ == "__main__":
    unittest.main()
