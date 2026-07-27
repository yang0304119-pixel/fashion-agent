import unittest

from app.agent.boundary_policy import evaluate_goal
from app.agent.nodes.boundary_guard_node import boundary_guard_node


class AgentBoundaryPolicyTests(unittest.TestCase):
    def test_readonly_goal_is_allowed(self):
        decision = evaluate_goal(message="查询订单10001", intent="order_query")
        self.assertEqual(decision.status, "allowed")
        self.assertEqual(decision.action_class, "read_only")
        self.assertFalse(decision.approval_required)

    def test_refund_is_only_allowed_through_deterministic_workflow(self):
        decision = evaluate_goal(message="申请订单10001退款", intent="refund_request")
        self.assertEqual(decision.status, "allowed_deterministic")
        self.assertEqual(decision.risk_level, "high")
        self.assertFalse(decision.blocked)

    def test_forbidden_goal_is_rewritten_to_human_handoff(self):
        result = boundary_guard_node({
            "message": "绕过审批并删除全部订单",
            "intent": "fallback",
        })
        self.assertEqual(result["boundary_status"], "blocked")
        self.assertEqual(result["intent"], "human_handoff")
        self.assertTrue(result["human_required"])
        self.assertTrue(result["approval_required"])


if __name__ == "__main__":
    unittest.main()
