import tempfile
from pathlib import Path
from unittest.mock import patch

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.core.config import settings
from app.models import KnowledgeIndexBuild
from app.rag import vector_store
from app.rag.retriever import retrieve
from app.services.knowledge_index_service import KnowledgeIndexService
from tests.api_test_support import ADMIN_PASSWORD, ApiTestCase


class DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    @staticmethod
    def _embed(text: str) -> list[float]:
        keywords = ("租户一", "租户二", "退款", "物流")
        values = [float(text.count(keyword)) for keyword in keywords]
        values.append(float(len(text) % 17) / 17.0 + 0.01)
        return values


class KnowledgeIndexLifecycleTests(ApiTestCase):
    def setUp(self):
        self.knowledge_temporary = tempfile.TemporaryDirectory()
        self.chroma_temporary = tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        )
        self.original_storage_root = settings.KNOWLEDGE_STORAGE_ROOT
        settings.KNOWLEDGE_STORAGE_ROOT = Path(self.knowledge_temporary.name)
        self.fake_embeddings = DeterministicEmbeddings()
        super().setUp()
        self.admin_a_headers = self.auth_headers(
            self.login("admin_a", ADMIN_PASSWORD)
        )
        self.admin_b_headers = self.auth_headers(
            self.login("admin_b", ADMIN_PASSWORD)
        )
        self.vector_patches = [
            patch(
                "app.rag.vector_store.CHROMA_DIR",
                Path(self.chroma_temporary.name),
            ),
            patch(
                "app.rag.vector_store.get_embeddings",
                return_value=self.fake_embeddings,
            ),
            patch(
                "app.rag.retriever.get_embeddings",
                return_value=self.fake_embeddings,
            ),
            patch(
                "app.rag.retriever.rewrite_query",
                side_effect=lambda query: query,
            ),
            patch(
                "app.services.knowledge_index_service.split_knowledge_documents",
                side_effect=lambda documents: [
                    Document(
                        id=str(document.id),
                        page_content=document.page_content,
                        metadata={**document.metadata, "chunk_id": str(document.id)},
                    )
                    for document in documents
                ],
            ),
        ]
        for vector_patch in self.vector_patches:
            vector_patch.start()
        vector_store._get_active_vector_store.cache_clear()

    def tearDown(self):
        vector_store.reset_vector_store_clients()
        for vector_patch in reversed(self.vector_patches):
            vector_patch.stop()
        super().tearDown()
        settings.KNOWLEDGE_STORAGE_ROOT = self.original_storage_root
        self.chroma_temporary.cleanup()
        self.knowledge_temporary.cleanup()

    def test_candidate_uses_only_approved_revisions_and_pending_does_not_block(self):
        approved = self._create_approved_document(
            headers=self.admin_a_headers,
            title="租户一退款规则",
            content="# 租户一退款规则\n\n租户一支持七天退款。",
        )
        self._upload_document(
            headers=self.admin_a_headers,
            title="待审核物流规则",
            content="# 物流规则\n\n这是尚未审核的内容。",
            knowledge_type="logistics_policy",
        )
        pending_revision = self._upload_revision(
            headers=self.admin_a_headers,
            document_id=approved["id"],
            filename="refund-v2.md",
            content="# 新版退款规则\n\n该版本尚未审核。",
        )["latest_revision"]

        candidate = self._create_candidate(self.admin_a_headers)
        self.assertEqual(candidate["status"], "ready")
        self.assertEqual(candidate["document_count"], 1)
        self.assertEqual(candidate["chunk_count"], 1)
        self.assertEqual(
            candidate["revision_snapshot"],
            [approved["revisions"][0]["id"]],
        )
        self.assertNotIn(pending_revision["id"], candidate["revision_snapshot"])

    def test_tenant_active_indexes_are_isolated_in_retrieval_and_api(self):
        self._create_approved_document(
            headers=self.admin_a_headers,
            title="租户一退款规则",
            content="# 租户一退款规则\n\n租户一专属退款答案。",
        )
        self._create_approved_document(
            headers=self.admin_b_headers,
            title="租户二退款规则",
            content="# 租户二退款规则\n\n租户二专属退款答案。",
        )
        build_a = self._create_candidate(self.admin_a_headers)
        build_b = self._create_candidate(self.admin_b_headers)
        self._activate(self.admin_a_headers, build_a["id"])
        self._activate(self.admin_b_headers, build_b["id"])

        docs_a = retrieve("退款规则", tenant_id=1)
        docs_b = retrieve("退款规则", tenant_id=2)
        self.assertTrue(any("租户一专属" in doc.page_content for doc in docs_a))
        self.assertFalse(any("租户二专属" in doc.page_content for doc in docs_a))
        self.assertTrue(any("租户二专属" in doc.page_content for doc in docs_b))
        self.assertFalse(any("租户一专属" in doc.page_content for doc in docs_b))

        forbidden = self.client.get(
            f"/api/admin/knowledge/index-builds/{build_a['id']}",
            headers=self.admin_b_headers,
        )
        self.assertEqual(forbidden.status_code, 404, forbidden.text)

    def test_failed_candidate_keeps_old_active_index_available(self):
        document = self._create_approved_document(
            headers=self.admin_a_headers,
            title="旧版退款规则",
            content="# 旧版退款规则\n\n旧版答案持续可用。",
        )
        first = self._create_candidate(self.admin_a_headers)
        self._activate(self.admin_a_headers, first["id"])
        old_docs = retrieve("退款规则", tenant_id=1)
        self.assertTrue(any("旧版答案持续可用" in doc.page_content for doc in old_docs))

        new_revision = self._upload_revision(
            headers=self.admin_a_headers,
            document_id=document["id"],
            filename="new.md",
            content="# 新版退款规则\n\n新版答案。",
        )["latest_revision"]
        self._parse_and_approve(self.admin_a_headers, new_revision["id"])

        original_builder = __import__(
            "app.services.knowledge_index_service",
            fromlist=["build_vector_store_collection"],
        ).build_vector_store_collection

        def fail_after_check(documents, *, collection_name):
            during_build = retrieve("退款规则", tenant_id=1)
            self.assertTrue(
                any("旧版答案持续可用" in doc.page_content for doc in during_build)
            )
            raise RuntimeError("simulated candidate failure")

        with patch(
            "app.services.knowledge_index_service.build_vector_store_collection",
            side_effect=fail_after_check,
        ):
            failed = self.client.post(
                "/api/admin/knowledge/index-builds",
                headers=self.admin_a_headers,
            )
        self.assertEqual(failed.status_code, 422, failed.text)

        db = self.Session()
        try:
            active = KnowledgeIndexService(db).get_active_for_tenant(tenant_id=1)
            self.assertEqual(active.id, first["id"])
            failed_build = db.query(KnowledgeIndexBuild).filter(
                KnowledgeIndexBuild.tenant_id == 1,
                KnowledgeIndexBuild.status == "failed",
            ).one()
            self.assertEqual(failed_build.error_code, "index_build_failed")
        finally:
            db.close()
        after_failure = retrieve("退款规则", tenant_id=1)
        self.assertTrue(
            any("旧版答案持续可用" in doc.page_content for doc in after_failure)
        )
        self.assertIsNotNone(original_builder)

    def test_activation_preserves_previous_version_and_rollback_restores_it(self):
        document = self._create_approved_document(
            headers=self.admin_a_headers,
            title="退款规则",
            content="# 退款规则\n\n第一版规则。",
        )
        first = self._create_candidate(self.admin_a_headers)
        self._activate(self.admin_a_headers, first["id"])

        second_revision = self._upload_revision(
            headers=self.admin_a_headers,
            document_id=document["id"],
            filename="v2.md",
            content="# 退款规则\n\n第二版规则。",
        )["latest_revision"]
        self._parse_and_approve(self.admin_a_headers, second_revision["id"])
        second = self._create_candidate(self.admin_a_headers)
        activated = self._activate(self.admin_a_headers, second["id"])
        self.assertEqual(activated["previous_active_build_id"], first["id"])
        self.assertTrue(any("第二版规则" in doc.page_content for doc in retrieve("退款", tenant_id=1)))

        rolled_back = self.client.post(
            "/api/admin/knowledge/index-builds/rollback",
            headers=self.admin_a_headers,
            json={"target_build_id": first["id"]},
        )
        self.assertEqual(rolled_back.status_code, 200, rolled_back.text)
        self.assertEqual(rolled_back.json()["data"]["id"], first["id"])
        self.assertTrue(any("第一版规则" in doc.page_content for doc in retrieve("退款", tenant_id=1)))

    def test_ready_candidate_can_be_queried_without_changing_active_consumers(self):
        document = self._create_approved_document(
            headers=self.admin_a_headers,
            title="退款规则",
            content="# 退款规则\n\n线上第一版答案。",
        )
        first = self._create_candidate(self.admin_a_headers)
        self._activate(self.admin_a_headers, first["id"])

        second_revision = self._upload_revision(
            headers=self.admin_a_headers,
            document_id=document["id"],
            filename="candidate.md",
            content="# 退款规则\n\n候选第二版答案。",
        )["latest_revision"]
        self._parse_and_approve(self.admin_a_headers, second_revision["id"])
        candidate = self._create_candidate(self.admin_a_headers)

        active_docs = retrieve("退款", tenant_id=1)
        candidate_docs = retrieve(
            "退款",
            tenant_id=1,
            build_id=candidate["id"],
        )
        self.assertTrue(
            any("线上第一版答案" in doc.page_content for doc in active_docs)
        )
        self.assertFalse(
            any("候选第二版答案" in doc.page_content for doc in active_docs)
        )
        self.assertTrue(
            any("候选第二版答案" in doc.page_content for doc in candidate_docs)
        )

    def _create_candidate(self, headers: dict[str, str]) -> dict:
        response = self.client.post(
            "/api/admin/knowledge/index-builds",
            headers=headers,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    def _activate(self, headers: dict[str, str], build_id: int) -> dict:
        response = self.client.post(
            f"/api/admin/knowledge/index-builds/{build_id}/activate",
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["data"]

    def _create_approved_document(
        self,
        *,
        headers: dict[str, str],
        title: str,
        content: str,
    ) -> dict:
        document = self._upload_document(
            headers=headers,
            title=title,
            content=content,
        )
        self._parse_and_approve(headers, document["latest_revision"]["id"])
        detail = self.client.get(
            f"/api/admin/knowledge/documents/{document['id']}",
            headers=headers,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        return detail.json()["data"]

    def _upload_document(
        self,
        *,
        headers: dict[str, str],
        title: str,
        content: str,
        knowledge_type: str = "after_sales_policy",
    ) -> dict:
        response = self.client.post(
            "/api/admin/knowledge/documents",
            headers=headers,
            data={
                "title": title,
                "knowledge_type": knowledge_type,
                "category": "通用",
            },
            files={"file": (f"{title}.md", content.encode(), "text/markdown")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    def _upload_revision(
        self,
        *,
        headers: dict[str, str],
        document_id: int,
        filename: str,
        content: str,
    ) -> dict:
        response = self.client.post(
            f"/api/admin/knowledge/documents/{document_id}/revisions",
            headers=headers,
            files={"file": (filename, content.encode(), "text/markdown")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["data"]

    def _parse_and_approve(self, headers: dict[str, str], revision_id: int) -> None:
        parsed = self.client.post(
            f"/api/admin/knowledge/revisions/{revision_id}/parse",
            headers=headers,
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        approved = self.client.post(
            f"/api/admin/knowledge/revisions/{revision_id}/approve",
            headers=headers,
        )
        self.assertEqual(approved.status_code, 200, approved.text)


if __name__ == "__main__":
    import unittest

    unittest.main()
