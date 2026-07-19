import tempfile
import unittest
from pathlib import Path

from app.rag.processed_loader import load_approved_knowledge
from app.rag.processor import (
    approve_processed_knowledge,
    extract_processed_knowledge,
)


class KnowledgeProcessingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.raw_root = root / "raw"
        self.processed_root = root / "processed"
        self.report_path = self.processed_root / "quality-report.json"
        self.source_relative = "商品知识/通用/测试指南.md"
        self.source_path = self.raw_root / self.source_relative
        self.source_path.parent.mkdir(parents=True)
        self.source_path.write_text(
            "# 测试指南\n\n## 洗护规则\n请使用中性洗涤剂低温手洗。\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_processed_document_requires_review_before_loading(self):
        report = self._extract()
        entry = report["documents"][0]
        self.assertEqual(entry["review_status"], "pending_review")
        processed_path = self.processed_root / entry["processed_relative_path"]
        self.assertTrue(processed_path.is_file())

        with self.assertRaisesRegex(RuntimeError, "未人工审核"):
            self._load()

        processed_path.write_text(
            processed_path.read_text(encoding="utf-8")
            + "\n## 人工补充\n不可漂白。\n",
            encoding="utf-8",
        )
        approve_processed_knowledge(
            sources=[self.source_relative],
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
        )
        documents = self._load()
        self.assertEqual(len(documents), 1)
        self.assertIn("人工补充", documents[0].page_content)
        self.assertEqual(
            documents[0].metadata["relative_source"],
            self.source_relative,
        )

    def test_changes_after_approval_invalidate_processed_document(self):
        report = self._extract()
        approve_processed_knowledge(
            approve_all=True,
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
        )
        entry = report["documents"][0]
        processed_path = self.processed_root / entry["processed_relative_path"]
        processed_path.write_text("# 审核后又被修改\n", encoding="utf-8")

        with self.assertRaisesRegex(RuntimeError, "审核后发生变化"):
            self._load()

    def test_source_change_requires_reextract(self):
        self._extract()
        approve_processed_knowledge(
            approve_all=True,
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
        )
        self.source_path.write_text(
            "# 新版本\n\n退款规则已经更新。\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(RuntimeError, "原始知识文件已变化"):
            self._load()

    def test_force_extract_resets_approval(self):
        self._extract()
        approve_processed_knowledge(
            approve_all=True,
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
        )
        report = extract_processed_knowledge(
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
            force=True,
        )
        self.assertEqual(
            report["documents"][0]["review_status"],
            "pending_review",
        )

    def _extract(self):
        return extract_processed_knowledge(
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
        )

    def _load(self):
        return load_approved_knowledge(
            raw_root=self.raw_root,
            processed_root=self.processed_root,
            report_path=self.report_path,
        )


if __name__ == "__main__":
    unittest.main()
