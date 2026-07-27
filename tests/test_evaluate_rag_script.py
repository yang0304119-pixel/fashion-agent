import unittest

from langchain_core.documents import Document

from scripts.evaluate_rag import _with_labeled_source


class EvaluateRagScriptTests(unittest.TestCase):
    def test_runtime_revision_source_is_mapped_to_labeled_source(self):
        document = Document(
            id="chunk-1",
            page_content="content",
            metadata={
                "relative_source": "documents/10/revisions/10",
                "chunk_id": "chunk-1",
            },
        )

        mapped = _with_labeled_source(
            document,
            {
                "documents/10/revisions/10": (
                    "物流规则/通用/物流与配送规则.md"
                )
            },
        )

        self.assertEqual(
            mapped.metadata["relative_source"],
            "物流规则/通用/物流与配送规则.md",
        )
        self.assertEqual(
            mapped.metadata["runtime_source"],
            "documents/10/revisions/10",
        )
        self.assertEqual(
            document.metadata["relative_source"],
            "documents/10/revisions/10",
        )


if __name__ == "__main__":
    unittest.main()
