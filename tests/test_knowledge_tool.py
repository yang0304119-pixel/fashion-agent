import unittest
from unittest.mock import patch

from langchain_core.documents import Document

from app.tools.knowledge_tool import retrieve_knowledge


class KnowledgeToolTests(unittest.TestCase):
    def test_retrieval_uses_trusted_tenant_and_returns_safe_metadata(self):
        document = Document(
            page_content="洗护说明",
            metadata={
                "title": "商品手册",
                "chunk_id": "chunk-1",
                "relevance_score": 0.87,
                "source_path": "C:/secret/knowledge.pdf",
            },
        )
        with patch(
            "app.tools.knowledge_tool.retrieve",
            return_value=[document],
        ) as retrieve:
            result = retrieve_knowledge("怎么洗", tenant_id=9)

        retrieve.assert_called_once_with("怎么洗", tenant_id=9, top_k=3)
        returned = result["data"]["documents"][0]
        self.assertEqual(returned["chunk_id"], "chunk-1")
        self.assertNotIn("source_path", returned)
        self.assertNotIn("C:/secret", str(result))


if __name__ == "__main__":
    unittest.main()

