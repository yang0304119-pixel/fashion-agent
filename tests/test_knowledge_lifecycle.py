import tempfile
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.models import KnowledgeDocument, KnowledgeRevision
from tests.api_test_support import ADMIN_PASSWORD, ApiTestCase


class KnowledgeLifecycleApiTests(ApiTestCase):
    def setUp(self):
        self.knowledge_temporary = tempfile.TemporaryDirectory()
        self.original_storage_root = settings.KNOWLEDGE_STORAGE_ROOT
        settings.KNOWLEDGE_STORAGE_ROOT = Path(
            self.knowledge_temporary.name
        )
        super().setUp()
        self.admin_a_token = self.login("admin_a", ADMIN_PASSWORD)
        self.admin_b_token = self.login("admin_b", ADMIN_PASSWORD)
        self.admin_a_headers = self.auth_headers(self.admin_a_token)
        self.admin_b_headers = self.auth_headers(self.admin_b_token)

    def tearDown(self):
        super().tearDown()
        settings.KNOWLEDGE_STORAGE_ROOT = self.original_storage_root
        self.knowledge_temporary.cleanup()

    def test_upload_parse_edit_approve_and_reject_lifecycle(self):
        with patch(
            "app.rag.vector_store.rebuild_vector_store"
        ) as rebuild_vector_store:
            created = self._upload_markdown()
            document_id = created["id"]
            revision_id = created["latest_revision"]["id"]
            self.assertEqual(
                created["latest_revision"]["parse_status"],
                "pending",
            )
            self.assertEqual(
                created["latest_revision"]["review_status"],
                "pending",
            )

            parsed = self.client.post(
                f"/api/admin/knowledge/revisions/{revision_id}/parse",
                headers=self.admin_a_headers,
            )
            self.assertEqual(parsed.status_code, 200, parsed.text)
            parsed_revision = parsed.json()["data"]
            self.assertEqual(parsed_revision["parse_status"], "succeeded")
            self.assertIn(
                parsed_revision["quality_status"],
                {"passed", "warning"},
            )
            self.assertGreater(
                parsed_revision["quality_report"]["metrics"]["character_count"],
                20,
            )

            content = self.client.get(
                f"/api/admin/knowledge/revisions/{revision_id}/content",
                headers=self.admin_a_headers,
            )
            self.assertEqual(content.status_code, 200, content.text)
            self.assertIn("七天内可以申请退款", content.json()["data"]["content"])

            updated = self.client.put(
                f"/api/admin/knowledge/revisions/{revision_id}/content",
                headers=self.admin_a_headers,
                json={
                    "content": (
                        "# 退款规则\n\n七天内可以申请退款。\n\n"
                        "## 人工补充\n质量问题请上传凭证。"
                    )
                },
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["data"]["review_status"], "pending")

            approved = self.client.post(
                f"/api/admin/knowledge/revisions/{revision_id}/approve",
                headers=self.admin_a_headers,
            )
            self.assertEqual(approved.status_code, 200, approved.text)
            self.assertEqual(approved.json()["data"]["review_status"], "approved")
            self.assertEqual(approved.json()["data"]["reviewed_by"], 3)

            edited_again = self.client.put(
                f"/api/admin/knowledge/revisions/{revision_id}/content",
                headers=self.admin_a_headers,
                json={"content": "# 退款规则\n\n修改后需要重新审核。"},
            )
            self.assertEqual(edited_again.status_code, 200, edited_again.text)
            self.assertEqual(
                edited_again.json()["data"]["review_status"],
                "pending",
            )
            self.assertIsNone(edited_again.json()["data"]["reviewed_by"])

            rejected = self.client.post(
                f"/api/admin/knowledge/revisions/{revision_id}/reject",
                headers=self.admin_a_headers,
                json={"reason": "缺少活动商品例外说明"},
            )
            self.assertEqual(rejected.status_code, 200, rejected.text)
            self.assertEqual(rejected.json()["data"]["review_status"], "rejected")
            self.assertEqual(
                rejected.json()["data"]["review_reason"],
                "缺少活动商品例外说明",
            )

            detail = self.client.get(
                f"/api/admin/knowledge/documents/{document_id}",
                headers=self.admin_a_headers,
            )
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(len(detail.json()["data"]["revisions"]), 1)
            rebuild_vector_store.assert_not_called()

    def test_tenant_boundary_protects_document_revision_and_files(self):
        created = self._upload_markdown()
        document_id = created["id"]
        revision_id = created["latest_revision"]["id"]
        parsed = self.client.post(
            f"/api/admin/knowledge/revisions/{revision_id}/parse",
            headers=self.admin_a_headers,
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)

        tenant_b_list = self.client.get(
            "/api/admin/knowledge/documents",
            headers=self.admin_b_headers,
        )
        self.assertEqual(tenant_b_list.status_code, 200, tenant_b_list.text)
        self.assertEqual(tenant_b_list.json()["total"], 0)

        for method, path in (
            ("get", f"/api/admin/knowledge/documents/{document_id}"),
            ("get", f"/api/admin/knowledge/revisions/{revision_id}/content"),
            ("post", f"/api/admin/knowledge/revisions/{revision_id}/parse"),
            ("post", f"/api/admin/knowledge/revisions/{revision_id}/approve"),
        ):
            response = getattr(self.client, method)(
                path,
                headers=self.admin_b_headers,
            )
            self.assertEqual(response.status_code, 404, response.text)

        db = self.Session()
        try:
            revision = db.get(KnowledgeRevision, revision_id)
            self.assertTrue(revision.raw_storage_key.startswith("1/"))
            self.assertFalse(revision.raw_storage_key.startswith("2/"))
        finally:
            db.close()

    def test_upload_validation_and_customer_authorization(self):
        invalid_pdf = self.client.post(
            "/api/admin/knowledge/documents",
            headers=self.admin_a_headers,
            data={
                "title": "伪造 PDF",
                "knowledge_type": "faq",
                "category": "通用",
            },
            files={"file": ("fake.pdf", b"not a pdf", "application/pdf")},
        )
        self.assertEqual(invalid_pdf.status_code, 422, invalid_pdf.text)
        self.assertIn("扩展名不匹配", invalid_pdf.text)

        unsafe_name = self.client.post(
            "/api/admin/knowledge/documents",
            headers=self.admin_a_headers,
            data={
                "title": "越界文件",
                "knowledge_type": "faq",
                "category": "通用",
            },
            files={"file": ("../escape.md", b"# bad", "text/markdown")},
        )
        self.assertEqual(unsafe_name.status_code, 422, unsafe_name.text)

        customer_token = self.login("customer_a", "CustomerPassword123!")
        forbidden = self.client.get(
            "/api/admin/knowledge/documents",
            headers=self.auth_headers(customer_token),
        )
        self.assertEqual(forbidden.status_code, 403, forbidden.text)

    def test_new_revision_preserves_document_and_increments_version(self):
        created = self._upload_markdown()
        document_id = created["id"]
        response = self.client.post(
            f"/api/admin/knowledge/documents/{document_id}/revisions",
            headers=self.admin_a_headers,
            files={
                "file": (
                    "refund-v2.md",
                    "# 新版退款规则\n\n活动商品以页面说明为准。".encode(),
                    "text/markdown",
                )
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        data = response.json()["data"]
        self.assertEqual(data["id"], document_id)
        self.assertEqual(data["latest_revision"]["version_no"], 2)
        self.assertEqual(len(data["revisions"]), 2)

    def _upload_markdown(self) -> dict:
        response = self.client.post(
            "/api/admin/knowledge/documents",
            headers=self.admin_a_headers,
            data={
                "title": "退款规则",
                "knowledge_type": "after_sales_policy",
                "category": "通用",
            },
            files={
                "file": (
                    "refund-policy.md",
                    (
                        "# 退款规则\n\n## 时效\n"
                        "七天内可以申请退款。\n"
                    ).encode("utf-8"),
                    "text/markdown",
                )
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]


if __name__ == "__main__":
    import unittest

    unittest.main()
