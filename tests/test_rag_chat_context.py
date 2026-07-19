import unittest
from unittest.mock import patch

from app.agent.nodes.rag_node import rag_node


class RagChatContextTests(unittest.TestCase):
    def test_trusted_product_context_is_added_to_rag_question(self):
        with patch(
            "app.agent.nodes.rag_node.answer_question",
            return_value={"answer": "适合寒冷天气。", "documents": [], "sources": []},
        ) as answer_question:
            result = rag_node({
                "message": "这件适合东北冬天吗？",
                "chat_context": {
                    "context_type": "product",
                    "product_id": 1,
                    "product_name": "极寒系列加厚羽绒服",
                },
            })

        question = answer_question.call_args.args[0]
        self.assertIn("极寒系列加厚羽绒服", question)
        self.assertIn("商品编号 1", question)
        self.assertIn("这件适合东北冬天吗", question)
        self.assertEqual(result["final_answer"], "适合寒冷天气。")


if __name__ == "__main__":
    unittest.main()
