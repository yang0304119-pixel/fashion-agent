import unittest

from langchain_core.documents import Document

from app.rag.query_rewriter import infer_knowledge_type, infer_knowledge_type_scores
from app.rag.retriever import _fuse_results, _select_diverse_documents


def _document(chunk: str, source: str, knowledge_type: str) -> Document:
    return Document(
        id=chunk,
        page_content=chunk,
        metadata={
            "chunk_id": chunk,
            "revision_id": source,
            "type": knowledge_type,
        },
    )


class RagRetrieverRankingTests(unittest.TestCase):
    def test_multiple_matched_types_are_kept_as_soft_weights(self):
        scores = infer_knowledge_type_scores(
            "羽绒服偶尔钻出几根绒算质量问题吗？"
        )

        self.assertEqual(scores["售后规则"], 1.0)
        self.assertEqual(scores["商品知识"], 1.0)

    def test_generic_product_word_does_not_dilute_policy_type(self):
        scores = infer_knowledge_type_scores(
            "定制商品能走七天无理由退货吗？"
        )

        self.assertEqual(scores, {"售后规则": 1.0})

    def test_size_language_can_coexist_with_product_type(self):
        scores = infer_knowledge_type_scores(
            "冲锋衣为什么建议选大一码？"
        )

        self.assertEqual(scores["尺码知识"], 1.0)
        self.assertEqual(scores["商品知识"], 0.5)
        self.assertEqual(
            infer_knowledge_type("冲锋衣为什么建议选大一码？"),
            "尺码知识",
        )

    def test_soft_type_boost_does_not_remove_other_types(self):
        after_sales = _document("a", "source-a", "售后规则")
        product = _document("b", "source-b", "商品知识")

        ranked = _fuse_results(
            [(after_sales, 0.8), (product, 0.8)],
            [],
            top_k=2,
            knowledge_type_scores={"商品知识": 1.0},
        )

        self.assertEqual([item.id for item in ranked], ["b", "a"])
        self.assertEqual(ranked[0].metadata["knowledge_type_weight"], 1.0)
        self.assertEqual(ranked[1].metadata["knowledge_type_weight"], 0.0)

    def test_diversity_prefers_distinct_sources_before_filling(self):
        documents = [
            _document("a1", "source-a", "商品知识"),
            _document("a2", "source-a", "商品知识"),
            _document("b1", "source-b", "商品知识"),
            _document("c1", "source-c", "商品知识"),
        ]
        for rank, document in enumerate(documents, start=1):
            document.metadata["fusion_rank"] = rank

        selected = _select_diverse_documents(documents, top_k=3)

        self.assertEqual([item.id for item in selected], ["a1", "b1", "c1"])
        self.assertEqual(
            [item.metadata["pre_diversity_rank"] for item in selected],
            [1, 3, 4],
        )
        self.assertEqual(
            [item.metadata["fusion_rank"] for item in selected],
            [1, 2, 3],
        )


if __name__ == "__main__":
    unittest.main()
