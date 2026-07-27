from app.integrations.refund_gateway import GatewayRefundResult
from app.models import AdminAuditEvent, AgentTrace, User
from app.services.refund_service import RefundService
from app.services.tenant_user_service import TenantUserError, TenantUserService
from tests.api_test_support import ADMIN_PASSWORD, ApiTestCase


class PendingGateway:
    mode = "test"

    def execute(self, **kwargs):
        return GatewayRefundResult(status="pending")


class StaffRbacTests(ApiTestCase):
    def headers(self, username: str):
        return self.auth_headers(self.login(username, ADMIN_PASSWORD))

    def test_auth_me_returns_role_permissions_and_home_view(self):
        response = self.client.get(
            "/api/auth/me",
            headers=self.headers("service_a"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["role"], "customer_service")
        self.assertEqual(data["role_label"], "客服运营")
        self.assertIn("order.read", data["permissions"])
        self.assertNotIn("refund.review", data["permissions"])
        self.assertEqual(data["home_view"], "dashboard")

    def test_customer_service_cannot_review_refunds_or_view_trace(self):
        headers = self.headers("service_a")
        self.assertEqual(self.client.get("/api/admin/orders", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/refunds", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/agentops/traces", headers=headers).status_code, 403)

    def test_supervisor_can_review_but_cannot_manage_users(self):
        headers = self.headers("supervisor_a")
        self.assertEqual(self.client.get("/api/admin/refunds", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/knowledge/documents", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/quality-report", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/users", headers=headers).status_code, 403)

    def test_business_quality_report_is_sanitized_and_permission_scoped(self):
        db = self.Session()
        db.add(AgentTrace(
            tenant_id=1,
            user_id=1,
            session_id="quality-session",
            node_name="trace_node",
            message="Can I return this order?",
            status="failed",
            intent="knowledge_query",
            input={"message": "Can I return this order?", "router_source": "planner"},
            retrieved_scores=[0.91],
            tool_name="search_knowledge",
            error_message="internal provider detail",
            rag_sources=[{
                "title": "Return policy",
                "source": "returns.md",
                "score": 0.91,
                "chunk_id": "secret-technical-id",
            }],
        ))
        db.add(AgentTrace(
            tenant_id=2,
            user_id=4,
            session_id="other-tenant-quality",
            node_name="trace_node",
            status="failed",
        ))
        db.commit()
        db.close()

        service = self.client.get(
            "/api/admin/quality-report",
            headers=self.headers("service_a"),
        )
        self.assertEqual(service.status_code, 403, service.text)
        report = self.client.get(
            "/api/admin/quality-report",
            headers=self.headers("supervisor_a"),
        )
        self.assertEqual(report.status_code, 200, report.text)
        data = report.json()["data"]
        sessions = {item["session_id"] for item in data["cases"]}
        self.assertIn("quality-session", sessions)
        self.assertNotIn("other-tenant-quality", sessions)
        item = next(row for row in data["cases"] if row["session_id"] == "quality-session")
        self.assertEqual(item["citations"], [{"title": "Return policy", "source": "returns.md"}])
        for technical_field in (
            "input",
            "retrieved_scores",
            "tool_name",
            "error_message",
            "steps",
            "confidence",
        ):
            self.assertNotIn(technical_field, item)

    def test_tenant_admin_manages_users_but_cannot_view_technical_trace(self):
        headers = self.headers("admin_a")
        self.assertEqual(self.client.get("/api/admin/users", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/agentops/traces", headers=headers).status_code, 403)

    def test_developer_can_view_agentops_but_cannot_review_refund(self):
        headers = self.headers("developer_a")
        self.assertEqual(self.client.get("/api/agentops/traces", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/agentops/health", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/agentops/memories/stats", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/memories/stats", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/admin/refunds", headers=headers).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/users", headers=headers).status_code, 403)

    def test_tenant_settings_require_admin_and_write_audit(self):
        admin_headers = self.headers("admin_a")
        supervisor_headers = self.headers("supervisor_a")
        self.assertEqual(
            self.client.get("/api/admin/tenant-settings", headers=supervisor_headers).status_code,
            403,
        )
        current = self.client.get("/api/admin/tenant-settings", headers=admin_headers)
        self.assertEqual(current.status_code, 200, current.text)
        updated = self.client.patch(
            "/api/admin/tenant-settings",
            headers=admin_headers,
            json={
                "name": "Tenant One Fashion",
                "contact": "service@example.com",
                "refund_auto_limit": "600.00",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["refund_auto_limit"], "600.00")

        audit = self.client.get("/api/admin/audit-events", headers=admin_headers)
        actions = [item["action"] for item in audit.json()["data"]]
        self.assertIn("tenant.settings_updated", actions)

    def test_tenant_refund_threshold_is_used_by_refund_service(self):
        response = self.client.patch(
            "/api/admin/tenant-settings",
            headers=self.headers("admin_a"),
            json={"refund_auto_limit": "600.00"},
        )
        self.assertEqual(response.status_code, 200, response.text)

        db = self.Session()
        try:
            outcome = RefundService(db, PendingGateway()).submit(
                tenant_id=1,
                user_id=1,
                order_id=10001,
                reason="threshold test",
                idempotency_key="tenant-threshold-test",
            )
            self.assertEqual(outcome.refund.risk_level, "low")
            self.assertEqual(outcome.refund.status, "approved")
            self.assertFalse(outcome.refund.human_review)
        finally:
            db.close()

    def test_supervisor_has_publish_permission_but_service_does_not(self):
        supervisor = self.client.post(
            "/api/admin/knowledge/index-builds",
            headers=self.headers("supervisor_a"),
        )
        self.assertNotEqual(supervisor.status_code, 403, supervisor.text)
        self.assertIn(supervisor.status_code, {201, 409, 422})
        service = self.client.post(
            "/api/admin/knowledge/index-builds",
            headers=self.headers("service_a"),
        )
        self.assertEqual(service.status_code, 403, service.text)

    def test_tenant_admin_creates_updates_and_audits_staff_account(self):
        headers = self.headers("admin_a")
        created = self.client.post(
            "/api/admin/users",
            headers=headers,
            json={
                "username": "new_service",
                "password": "NewServicePassword123!",
                "role": "customer_service",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        user_id = created.json()["data"]["id"]
        updated = self.client.patch(
            f"/api/admin/users/{user_id}",
            headers=headers,
            json={"role": "supervisor", "reason": "晋升客服主管"},
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["data"]["role"], "supervisor")
        audit = self.client.get("/api/admin/audit-events", headers=headers)
        self.assertEqual(audit.status_code, 200, audit.text)
        actions = {item["action"] for item in audit.json()["data"]}
        self.assertIn("staff_user.created", actions)
        self.assertIn("staff_user.updated", actions)

    def test_staff_user_queries_are_tenant_scoped(self):
        created = self.client.post(
            "/api/admin/users",
            headers=self.headers("admin_a"),
            json={
                "username": "tenant_one_only",
                "password": "TenantOnePassword123!",
                "role": "customer_service",
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        other = self.client.get("/api/admin/users", headers=self.headers("admin_b"))
        self.assertNotIn("tenant_one_only", {row["username"] for row in other.json()["data"]})

    def test_username_is_unique_per_tenant_not_globally(self):
        payload = {
            "username": "shared_service",
            "password": "SharedServicePassword123!",
            "role": "customer_service",
        }
        first = self.client.post(
            "/api/admin/users",
            headers=self.headers("admin_a"),
            json=payload,
        )
        duplicate = self.client.post(
            "/api/admin/users",
            headers=self.headers("admin_a"),
            json=payload,
        )
        other_tenant = self.client.post(
            "/api/admin/users",
            headers=self.headers("admin_b"),
            json=payload,
        )
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(other_tenant.status_code, 200, other_tenant.text)

    def test_admin_cannot_downgrade_or_disable_self(self):
        headers = self.headers("admin_a")
        downgrade = self.client.patch(
            "/api/admin/users/3",
            headers=headers,
            json={"role": "supervisor"},
        )
        disable = self.client.patch(
            "/api/admin/users/3",
            headers=headers,
            json={"is_active": False},
        )
        self.assertEqual(downgrade.status_code, 422, downgrade.text)
        self.assertEqual(disable.status_code, 422, disable.text)

    def test_service_protects_last_active_tenant_admin(self):
        db = self.Session()
        try:
            actor = db.get(User, 8)
            with self.assertRaises(TenantUserError):
                TenantUserService(db).update_staff(
                    actor=actor,
                    user_id=3,
                    username=None,
                    role="supervisor",
                    is_active=None,
                    reason="must be rejected",
                    ip_address=None,
                )
        finally:
            db.close()

    def test_database_role_change_invalidates_old_token(self):
        token = self.login("service_a", ADMIN_PASSWORD)
        db = self.Session()
        row = db.query(User).filter_by(username="service_a", tenant_id=1).one()
        row.role = "supervisor"
        db.commit()
        db.close()
        response = self.client.get("/api/auth/me", headers=self.auth_headers(token))
        self.assertEqual(response.status_code, 401)

    def test_audit_is_tenant_scoped(self):
        db = self.Session()
        self.assertEqual(db.query(AdminAuditEvent).count(), 0)
        db.close()
        self.client.post(
            "/api/admin/users",
            headers=self.headers("admin_a"),
            json={
                "username": "audit_service",
                "password": "AuditServicePassword123!",
                "role": "customer_service",
            },
        )
        tenant_two = self.client.get("/api/admin/audit-events", headers=self.headers("admin_b"))
        self.assertEqual(tenant_two.json()["data"], [])

    def test_agentops_trace_queries_are_tenant_scoped(self):
        db = self.Session()
        db.add_all([
            AgentTrace(
                tenant_id=1,
                user_id=1,
                session_id="tenant-one-trace",
                node_name="trace_node",
                status="completed",
            ),
            AgentTrace(
                tenant_id=2,
                user_id=4,
                session_id="tenant-two-trace",
                node_name="trace_node",
                status="completed",
            ),
        ])
        db.commit()
        db.close()

        response = self.client.get(
            "/api/agentops/traces",
            headers=self.headers("developer_a"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        sessions = {item["session_id"] for item in response.json()["data"]}
        self.assertIn("tenant-one-trace", sessions)
        self.assertNotIn("tenant-two-trace", sessions)
