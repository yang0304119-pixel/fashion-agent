import unittest
from unittest.mock import Mock, patch

from app.rag.query_rewriter import rewrite_query


class QueryRewriterHistoryTests(unittest.TestCase):
    def test_recent_history_is_available_for_coreference_resolution(self):
        chain = Mock()
        chain.invoke.return_value = "极寒系列加厚羽绒服可以机洗吗？"
        turns = [
            {"role": "user", "content": "极寒系列加厚羽绒服是什么填充？"},
            {"role": "assistant", "content": "填充物是白鸭绒。"},
            {"role": "user", "content": "它可以机洗吗？"},
        ]

        with patch(
            "app.rag.query_rewriter._get_rewrite_chain",
            return_value=chain,
        ):
            rewritten = rewrite_query(
                "它可以机洗吗？",
                recent_turns=turns,
            )

        payload = chain.invoke.call_args.args[0]
        context = payload["conversation_context"]
        self.assertEqual(rewritten, "极寒系列加厚羽绒服可以机洗吗？")
        self.assertIn("极寒系列加厚羽绒服是什么填充", context)
        self.assertIn("填充物是白鸭绒", context)
        self.assertNotIn('"content": "它可以机洗吗？"', context)

    def test_summary_is_available_for_ellipsis_completion(self):
        chain = Mock()
        chain.invoke.return_value = "定制商品是否支持七天无理由退货？"

        with patch(
            "app.rag.query_rewriter._get_rewrite_chain",
            return_value=chain,
        ):
            rewritten = rewrite_query(
                "那定制款呢？",
                conversation_summary={
                    "user_goal": "了解七天无理由退货的适用范围",
                },
            )

        payload = chain.invoke.call_args.args[0]
        self.assertEqual(rewritten, "定制商品是否支持七天无理由退货？")
        self.assertIn("七天无理由退货", payload["conversation_context"])

    def test_single_turn_rewrite_uses_explicit_empty_history_context(self):
        chain = Mock()
        chain.invoke.return_value = "羽绒服怎么清洗？"

        with patch(
            "app.rag.query_rewriter._get_rewrite_chain",
            return_value=chain,
        ):
            rewrite_query("羽绒服怎么洗？")

        payload = chain.invoke.call_args.args[0]
        self.assertIn("无可用对话历史", payload["conversation_context"])


if __name__ == "__main__":
    unittest.main()
