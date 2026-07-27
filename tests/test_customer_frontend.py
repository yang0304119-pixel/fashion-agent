import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"


class CustomerFrontendTests(unittest.TestCase):
    def test_demo_chat_page_and_module_assets_exist(self):
        html = (FRONTEND_ROOT / "demo-chat.html").read_text(encoding="utf-8")
        self.assertIn('id="messages"', html)
        self.assertIn('id="currentProductSlot"', html)
        self.assertIn('id="currentOrderSlot"', html)
        self.assertIn('id="productPickerDialog"', html)
        self.assertIn('id="orderPickerDialog"', html)
        self.assertIn('id="memoryDialog"', html)
        self.assertIn('id="openMemoryPanel"', html)
        self.assertIn('src="/js/demo-chat.js"', html)
        for relative_path in (
            "css/app.css",
            "css/demo-chat.css",
            "js/api.js",
            "js/auth.js",
            "js/chat.js",
            "js/demo-chat.js",
            "js/message-renderer.js",
            "js/product-picker.js",
            "js/order-picker.js",
            "js/merchant-login.js",
        ):
            self.assertTrue((FRONTEND_ROOT / relative_path).is_file())

    def test_demo_chat_has_no_fashionagent_customer_login(self):
        html = (FRONTEND_ROOT / "demo-chat.html").read_text(encoding="utf-8")
        self.assertNotIn('id="loginForm"', html)
        self.assertNotIn('id="password"', html)
        self.assertNotIn("登录客户中心", html)
        self.assertNotIn("FashionAgent 客户中心", html)
        self.assertIn("模拟消费者", html)

    def test_token_uses_session_storage_and_password_is_not_persisted(self):
        api_script = (FRONTEND_ROOT / "js" / "api.js").read_text(
            encoding="utf-8"
        )
        auth_script = (FRONTEND_ROOT / "js" / "auth.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("sessionStorage.setItem(ACCESS_TOKEN_KEY", api_script)
        self.assertIn("Authorization", api_script)
        self.assertNotIn("localStorage", api_script + auth_script)
        self.assertNotIn("setItem('password'", api_script + auth_script)

    def test_demo_chat_uses_context_aware_session_orders_and_chat(self):
        demo_script = (FRONTEND_ROOT / "js" / "demo-chat.js").read_text(
            encoding="utf-8"
        )
        chat_script = (FRONTEND_ROOT / "js" / "chat.js").read_text(
            encoding="utf-8"
        )
        product_picker = (FRONTEND_ROOT / "js" / "product-picker.js").read_text(
            encoding="utf-8"
        )
        order_picker = (FRONTEND_ROOT / "js" / "order-picker.js").read_text(
            encoding="utf-8"
        )
        renderer = (FRONTEND_ROOT / "js" / "message-renderer.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("/api/demo-store/session", demo_script)
        self.assertIn("/api/demo-store/products", product_picker)
        self.assertIn("/api/orders", order_picker)
        self.assertIn("/api/chat", chat_script)
        self.assertIn("product_id", chat_script)
        self.assertIn("order_id", chat_script)
        for message_type in ("product_card", "order_card", "refund_status", "system"):
            self.assertIn(message_type, renderer + demo_script)
        self.assertNotIn("user_id", chat_script)
        self.assertNotIn("tenant_id", chat_script)
        self.assertIn("/api/memories", demo_script)
        self.assertIn("editMemory", demo_script)
        self.assertIn("deleteMemory", demo_script)

    def test_store_redirects_to_demo_chat(self):
        html = (FRONTEND_ROOT / "store.html").read_text(encoding="utf-8")
        self.assertIn("/demo-chat.html", html)
        self.assertNotIn('id="products"', html)
        self.assertNotIn('id="my-orders"', html)

    def test_admin_refund_workspace_and_actions_exist(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        for status in ("reviewing", "approved", "succeeded", "rejected", "failed"):
            self.assertIn(f'data-status="{status}"', html)
        self.assertIn("当前为Mock演示环境，本操作不会产生真实资金变动。", script)
        self.assertIn("/approve", script)
        self.assertIn("/reject", script)
        self.assertIn("请填写拒绝原因", script)
        self.assertIn("username", script)
        self.assertIn("product_name", script)

    def test_admin_dashboard_is_default_and_uses_summary_api(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-view="dashboard"', html)
        self.assertIn('data-admin-panel="dashboard"', html)
        self.assertIn("orders_total", script)
        self.assertIn("today_sessions", script)
        self.assertIn("pending_knowledge_reviews", script)
        self.assertIn("expiring_soon_knowledge", script)
        self.assertIn("/api/admin/dashboard", script)
        self.assertIn("view: 'dashboard'", script)

    def test_admin_order_workspace_filters_and_links_related_business_data(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-view="orders"', html)
        self.assertIn('data-admin-panel="orders"', html)
        self.assertIn('id="adminOrderStatusFilter"', html)
        for status in ("pending", "shipped", "delivered", "refunded", "cancelled"):
            self.assertIn(f'<option value="{status}">', html)
        self.assertIn("/api/admin/orders", script)
        self.assertIn("openOrderDetail", script)
        self.assertIn("openRefundDetailById", script)
        self.assertIn("openTicketDetailById", script)
        self.assertIn("ticket_count", script)

    def test_admin_ticket_workspace_links_business_data_without_duplicate_approval(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-view="tickets"', html)
        self.assertIn('id="adminTicketStatusFilter"', html)
        self.assertIn('id="adminTicketTypeFilter"', html)
        self.assertIn("/api/admin/tickets", script)
        self.assertIn("openRefundDetailById", script)
        self.assertIn("openOrderDetail", script)
        self.assertIn("reviewer_username", script)
        self.assertIn("review_reason", script)

    def test_admin_trace_workspace_exposes_required_diagnostics(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-view="traces"', html)
        self.assertIn('data-permission="agent.trace.read"', html)
        self.assertIn('id="traceSessionSearch"', html)
        self.assertIn("/api/agentops/traces", script)
        self.assertIn("/api/agentops/trace-sessions", script)
        self.assertIn("实际节点步骤", script)
        self.assertIn("缺失槽位", script)
        self.assertIn("RAG 来源", script)
        self.assertIn("最终回答", script)
        self.assertIn("错误阶段", script)

    def test_admin_memory_governance_workspace_exists(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-view="memory"', html)
        self.assertIn('data-admin-panel="memory"', html)
        self.assertIn('id="memoryTotal"', html)
        self.assertIn('/api/admin/memories/stats', script)
        self.assertIn('loadMemoryStats', script)

    def test_admin_unresolved_case_queue_only_marks_knowledge_candidates(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        self.assertIn('data-admin-view="cases"', html)
        self.assertIn('id="caseResolvedFilter"', html)
        self.assertIn('id="caseIntentFilter"', html)
        self.assertIn('id="caseKnowledgeFilter"', html)
        self.assertIn("/api/admin/unresolved-cases", script)
        self.assertIn("method: 'PATCH'", script)
        self.assertIn("should_add_to_kb", script)
        case_workspace_script = script[
            script.index("async function loadCases"):
            script.index("function renderCasePagination")
        ]
        self.assertNotIn("chroma", case_workspace_script.lower())
        self.assertNotIn("vector_store", case_workspace_script.lower())

    def test_admin_knowledge_document_lifecycle_workspace_exists(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-admin-view="knowledge"', html)
        self.assertIn('data-admin-panel="knowledge"', html)
        self.assertIn('id="knowledgeUploadForm"', html)
        self.assertIn('id="knowledgeContentEditor"', html)
        self.assertIn('id="createKnowledgeBuildBtn"', html)
        self.assertIn('id="rollbackKnowledgeBuildBtn"', html)
        self.assertIn('id="knowledgeTestForm"', html)
        self.assertIn('id="knowledgeTestBuild"', html)
        self.assertIn('id="knowledgeTestResult"', html)
        self.assertIn('id="knowledgeEffectiveAt"', html)
        self.assertIn('id="knowledgeExpiresAt"', html)
        self.assertIn('id="approveKnowledgeBtn"', html)
        self.assertIn('id="rejectKnowledgeBtn"', html)
        self.assertIn("/api/admin/knowledge/documents", script)
        self.assertIn("/parse", script)
        self.assertIn("/content", script)
        self.assertIn("/approve", script)
        self.assertIn("/reject", script)
        self.assertIn("/api/admin/knowledge/index-builds", script)
        self.assertIn("/activate", script)
        self.assertIn("/rollback", script)
        self.assertIn("/api/admin/knowledge/question-tests", script)
        self.assertIn("dense_score", script)
        self.assertIn("bm25_score", script)
        self.assertIn("fusion_score", script)
        self.assertIn("/validity", script)
        self.assertIn("/knowledge-draft", script)
        self.assertIn("当前线上版本未受影响", script)
        self.assertNotIn("tenant_id", html)

    def test_customer_and_admin_pages_show_mock_money_warning(self):
        customer_html = (FRONTEND_ROOT / "demo-chat.html").read_text(encoding="utf-8")
        admin_html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        for html in (customer_html, admin_html):
            self.assertIn("演示环境", html)
            self.assertIn("模拟退款", html)
            self.assertIn("不涉及真实资金", html)

    def test_refund_chat_reply_contains_mock_money_warning(self):
        refund_node = (
            PROJECT_ROOT / "app" / "agent" / "nodes" / "refund_node.py"
        ).read_text(encoding="utf-8")
        self.assertIn("当前为演示环境", refund_node)
        self.assertIn("模拟退款", refund_node)
        self.assertIn("不涉及真实资金", refund_node)

    def test_admin_login_redirect_and_static_module_exist(self):
        merchant_script = (FRONTEND_ROOT / "js" / "merchant-login.js").read_text(
            encoding="utf-8"
        )
        index_html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("window.location.href = '/admin.html'", merchant_script)
        self.assertIn('id="merchantLoginForm"', index_html)
        self.assertIn("该入口仅供商户授权的员工账号使用", merchant_script)
        self.assertIn("permissionSet", merchant_script)
        self.assertNotIn("role !== 'admin'", merchant_script)
        self.assertTrue((FRONTEND_ROOT / "js" / "admin.js").is_file())
        self.assertTrue((FRONTEND_ROOT / "js" / "admin-permissions.js").is_file())

    def test_admin_shell_is_permission_driven_and_has_role_workspaces(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        script = (FRONTEND_ROOT / "js" / "admin.js").read_text(encoding="utf-8")
        permission_script = (
            FRONTEND_ROOT / "js" / "admin-permissions.js"
        ).read_text(encoding="utf-8")

        for permission in (
            "workbench.read",
            "ticket.read",
            "order.read",
            "case.handle",
            "quality.business.read",
            "refund.review",
            "knowledge.draft",
            "user.manage",
            "tenant.settings",
            "audit.read",
            "agent.trace.read",
            "system.health.read",
            "memory.diagnostics.read",
        ):
            self.assertIn(f'data-permission="{permission}"', html)

        for panel in ("quality", "users", "settings", "audit", "agentops", "forbidden"):
            self.assertIn(f'data-admin-panel="{panel}"', html)

        self.assertIn('data-permission="knowledge.publish"', html)
        self.assertIn("applyPermissionVisibility", script)
        self.assertIn("permittedViews", script)
        self.assertIn("state.view = 'forbidden'", script)
        self.assertIn("home_view", script)
        self.assertIn("/api/admin/quality-report", script)
        self.assertIn("loadBusinessQuality", script)
        self.assertIn("export function permissionSet", permission_script)

    def test_ai_customer_service_positioning_is_consistent(self):
        index_html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
        admin_html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        demo_html = (FRONTEND_ROOT / "demo-chat.html").read_text(
            encoding="utf-8"
        )
        design_doc = (
            PROJECT_ROOT / "docs" / "01-项目设计文档.md"
        ).read_text(encoding="utf-8")

        self.assertIn("电商 AI 客服自动化与辅助系统", index_html)
        self.assertIn("AI 客服运营台", index_html + admin_html + demo_html)
        self.assertIn("业务上下文", admin_html)
        self.assertIn("高风险操作审核", admin_html)
        self.assertIn("模拟消费者", demo_html)
        self.assertIn("Mock 外部电商系统", demo_html + design_doc)
        self.assertIn("不是售后管理平台", design_doc)

        for outdated_label in (
            "商户管理后台",
            "订单管理",
            "退款审核工作台",
            "商城会员",
            "模拟商城",
        ):
            self.assertNotIn(
                outdated_label,
                index_html + admin_html + demo_html,
            )

    def test_admin_page_is_registered_as_static_asset(self):
        html = (FRONTEND_ROOT / "admin.html").read_text(encoding="utf-8")
        self.assertIn('src="/js/admin.js"', html)
        self.assertIn('id="approveDialog"', html)
        self.assertIn('id="rejectReason"', html)


if __name__ == "__main__":
    unittest.main()
