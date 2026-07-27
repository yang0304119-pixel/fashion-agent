from app.core.config import settings
from app.models import ConversationTurn, MemoryRecord, TaskCheckpoint
from tests.api_test_support import ADMIN_PASSWORD, CUSTOMER_PASSWORD, ApiTestCase


class MemoryApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.original_semantic = settings.MEMORY_SEMANTIC_ENABLED
        settings.MEMORY_SEMANTIC_ENABLED = False

    def tearDown(self):
        settings.MEMORY_SEMANTIC_ENABLED = self.original_semantic
        super().tearDown()

    def customer_headers(self, username="customer_a"):
        return self.auth_headers(self.login(username, CUSTOMER_PASSWORD))

    def admin_headers(self, username="admin_a"):
        return self.auth_headers(self.login(username, ADMIN_PASSWORD))

    def developer_headers(self):
        return self.auth_headers(self.login("developer_a", ADMIN_PASSWORD))

    def test_user_can_create_update_list_and_delete_own_memory(self):
        headers = self.customer_headers()
        created = self.client.post(
            "/api/memories",
            headers=headers,
            json={
                "memory_type": "user_preference",
                "subject_key": "clothing.color_preference",
                "content": {"value": "黑色"},
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        memory_id = created.json()["data"]["id"]
        other = self.client.get(
            "/api/memories",
            headers=self.customer_headers("customer_b"),
        )
        self.assertEqual(other.json()["data"], [])

        updated = self.client.patch(
            f"/api/memories/{memory_id}",
            headers=headers,
            json={"content": {"value": "驼色"}},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["content"]["value"], "驼色")
        deleted = self.client.delete(f"/api/memories/{memory_id}", headers=headers)
        self.assertEqual(deleted.status_code, 200)
        active = self.client.get("/api/memories", headers=headers)
        self.assertEqual(active.json()["data"], [])
        db = self.Session()
        deleted_row = db.query(MemoryRecord).filter_by(id=memory_id).one()
        self.assertEqual(deleted_row.status, "deleted")
        self.assertEqual(deleted_row.content, {"deleted": True})
        self.assertEqual(deleted_row.searchable_text, "")
        self.assertIsNone(deleted_row.embedding)
        db.close()

    def test_preference_memory_affects_size_recommendation(self):
        headers = self.customer_headers()
        created = self.client.post(
            "/api/memories",
            headers=headers,
            json={
                "memory_type": "user_preference",
                "subject_key": "clothing.fit_preference",
                "content": {"value": "宽松", "label": "版型偏好"},
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        response = self.client.post(
            "/api/chat",
            headers=headers,
            json={
                "session_id": "memory-size-session",
                "message": "我175cm、70kg穿什么码",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("宽松版型", response.json()["answer"])
        self.assertIn("XL", response.json()["answer"])

    def test_chat_persists_turns_checkpoint_and_session_api(self):
        headers = self.customer_headers()
        first = self.client.post(
            "/api/chat",
            headers=headers,
            json={"session_id": "memory-task-session", "message": "查询订单"},
        )
        self.assertEqual(first.status_code, 200, first.text)
        snapshot = self.client.get(
            "/api/memories/sessions/memory-task-session",
            headers=headers,
        )
        self.assertEqual(snapshot.status_code, 200, snapshot.text)
        data = snapshot.json()["data"]
        self.assertEqual([turn["role"] for turn in data["recent_turns"]], ["user", "tool", "assistant"])
        self.assertEqual(data["task_checkpoint"]["status"], "waiting_user")
        self.assertIn("order_id", data["task_checkpoint"]["missing_slots"])

        db = self.Session()
        self.assertEqual(db.query(ConversationTurn).filter_by(user_id=1).count(), 3)
        self.assertEqual(db.query(TaskCheckpoint).filter_by(user_id=1).count(), 1)
        db.close()

        deleted = self.client.delete(
            "/api/memories/sessions/memory-task-session",
            headers=headers,
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["data"]["turns"], 3)

    def test_admin_can_create_shared_rule_and_view_stats(self):
        admin_headers = self.admin_headers()
        created = self.client.post(
            "/api/admin/memories",
            headers=admin_headers,
            json={
                "scope_type": "tenant",
                "scope_id": "ignored",
                "memory_type": "project_rule",
                "subject_key": "refund.server_validation",
                "content": {"value": "退款必须重新校验订单归属"},
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        stats = self.client.get(
            "/api/admin/memories/stats",
            headers=self.developer_headers(),
        )
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertEqual(stats.json()["data"]["by_type"]["project_rule"], 1)
        forbidden = self.client.get(
            "/api/admin/memories/stats",
            headers=self.customer_headers(),
        )
        self.assertEqual(forbidden.status_code, 403)

    def test_dynamic_business_fact_cannot_be_saved_as_memory(self):
        response = self.client.post(
            "/api/memories",
            headers=self.customer_headers(),
            json={
                "memory_type": "long_term_goal",
                "subject_key": "unsafe.order_status",
                "content": {"value": "记住订单状态是已发货"},
            },
        )
        self.assertEqual(response.status_code, 400)
        db = self.Session()
        self.assertEqual(db.query(MemoryRecord).count(), 0)
        db.close()

    def test_invalid_session_path_is_rejected(self):
        headers = self.customer_headers()
        too_short = self.client.get("/api/memories/sessions/short", headers=headers)
        invalid_chars = self.client.get(
            "/api/memories/sessions/invalid.session",
            headers=headers,
        )

        self.assertEqual(too_short.status_code, 422)
        self.assertEqual(invalid_chars.status_code, 422)


if __name__ == "__main__":
    import unittest
    unittest.main()
