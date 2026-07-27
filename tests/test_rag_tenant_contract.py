import unittest
from unittest.mock import patch

from app.rag.service import answer_question


class RagTenantContractTests(unittest.TestCase):
    def test_answer_question_forwards_tenant_and_candidate_build(self):
        with patch("app.rag.service.retrieve", return_value=[]) as retrieve:
            result = answer_question(
                "退款政策是什么？",
                tenant_id=7,
                build_id=19,
            )

        retrieve.assert_called_once_with(
            "退款政策是什么？",
            tenant_id=7,
            build_id=19,
            top_k=3,
        )
        self.assertEqual(result["answer"], "知识库中没有找到相关信息。")

    def test_answer_question_forwards_rewrite_context(self):
        recent_turns = [{"role": "user", "content": "退款条件是什么？"}]
        summary = {"user_goal": "了解退款政策"}
        with patch("app.rag.service.retrieve", return_value=[]) as retrieve:
            answer_question(
                "那定制款呢？",
                tenant_id=7,
                recent_turns=recent_turns,
                conversation_summary=summary,
            )

        retrieve.assert_called_once_with(
            "那定制款呢？",
            tenant_id=7,
            build_id=None,
            top_k=3,
            recent_turns=recent_turns,
            conversation_summary=summary,
        )


if __name__ == "__main__":
    unittest.main()
