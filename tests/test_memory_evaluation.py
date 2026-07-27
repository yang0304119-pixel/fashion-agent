import unittest
from pathlib import Path

from app.services.memory_evaluation_service import MemoryEvaluationRunner, load_cases


class MemoryEvaluationTests(unittest.TestCase):
    def test_labeled_memory_cases_are_computable(self):
        path = Path(__file__).resolve().parent.parent / "data" / "evaluation" / "memory_cases.jsonl"
        report = MemoryEvaluationRunner().run(load_cases(path))
        self.assertEqual(report.cases, 8)
        for metric in (
            "write_extraction_accuracy",
            "unsafe_write_block_rate",
            "retrieval_hit_at_k",
            "tenant_isolation_pass_rate",
            "context_budget_pass_rate",
            "task_resume_success_rate",
        ):
            self.assertIn(metric, report.metrics)
            self.assertEqual(report.metrics[metric], 1.0)


if __name__ == "__main__":
    unittest.main()
