import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from langchain_core.documents import Document

from app.services.rag_evaluation_service import (
    RagEvaluationRunner,
    load_rag_cases,
)


class RagEvaluationTests(unittest.TestCase):
    def test_metrics_use_actual_chunk_cutoffs(self):
        cases = [{
            "id": "RAG-001",
            "query": "question",
            "expected_sources": ["relevant-a", "relevant-b"],
            "evidence": "labeled from source text",
        }]
        documents = [
            Document(page_content="a1", metadata={"relative_source": "relevant-a"}),
            Document(page_content="a2", metadata={"relative_source": "relevant-a"}),
            Document(page_content="x", metadata={"relative_source": "irrelevant"}),
            Document(page_content="b", metadata={"relative_source": "relevant-b"}),
        ]

        report = RagEvaluationRunner().run(
            cases,
            retrieve=lambda _query, _top_k: documents,
        )

        self.assertEqual(report.metrics["recall_at_1"], 0.5)
        self.assertEqual(report.metrics["recall_at_3"], 0.5)
        self.assertEqual(report.metrics["recall_at_5"], 1.0)
        self.assertEqual(report.metrics["precision_at_1"], 1.0)
        self.assertEqual(report.metrics["precision_at_3"], 0.6667)
        self.assertEqual(report.metrics["precision_at_5"], 0.6)
        self.assertEqual(report.metrics["hit_rate_at_1"], 1.0)
        self.assertEqual(report.metrics["mrr_at_5"], 1.0)
        self.assertEqual(
            report.details[0]["retrieved_chunk_sources"],
            ["relevant-a", "relevant-a", "irrelevant", "relevant-b"],
        )

    def test_retrieval_error_counts_as_a_miss(self):
        cases = [{
            "id": "RAG-001",
            "query": "question",
            "expected_sources": ["relevant"],
            "evidence": "labeled from source text",
        }]

        def fail(_query, _top_k):
            raise RuntimeError("offline")

        report = RagEvaluationRunner().run(cases, retrieve=fail)

        self.assertEqual(report.errors, 1)
        self.assertEqual(report.metrics["recall_at_5"], 0.0)
        self.assertEqual(report.metrics["precision_at_5"], 0.0)
        self.assertIn("RuntimeError", report.details[0]["error"])

    def test_case_loader_requires_label_evidence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text(
                json.dumps({
                    "query": "question",
                    "expected_sources": ["source"],
                }),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "evidence"):
                load_rag_cases(path)


if __name__ == "__main__":
    unittest.main()
