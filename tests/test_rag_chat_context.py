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
                "tenant_id": 7,
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
        self.assertEqual(answer_question.call_args.kwargs["tenant_id"], 7)
        self.assertEqual(result["final_answer"], "适合寒冷天气。")

    def test_conversation_history_is_forwarded_to_rag_service(self):
        recent_turns = [
            {"role": "user", "content": "这款羽绒服是什么填充？"},
            {"role": "assistant", "content": "填充物是白鸭绒。"},
            {"role": "user", "content": "它可以机洗吗？"},
        ]
        summary = {"user_goal": "咨询羽绒服洗护"}
        with patch(
            "app.agent.nodes.rag_node.answer_question",
            return_value={
                "answer": "建议手洗。",
                "documents": [],
                "sources": [],
            },
        ) as answer_question:
            rag_node({
                "message": "它可以机洗吗？",
                "tenant_id": 7,
                "recent_turns": recent_turns,
                "conversation_summary": summary,
            })

        self.assertEqual(
            answer_question.call_args.kwargs["recent_turns"],
            recent_turns,
        )
        self.assertEqual(
            answer_question.call_args.kwargs["conversation_summary"],
            summary,
        )


if __name__ == "__main__":
    unittest.main()
