import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.agent.nodes.conversation_state_node import conversation_state_node
    from app.agent.nodes.router_node import router_node
    from app.core.database import Base
    from app.models import ConversationState, Tenant, User
    from app.services.conversation_state_service import ConversationStateService
except ModuleNotFoundError as error:
    if error.name in {"sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class ConversationStateTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.db.add(Tenant(id=1, name="租户一", industry="服装"))
        self.db.add(Tenant(id=2, name="租户二", industry="服装"))
        self.db.flush()
        self.db.add(User(
            id=1,
            tenant_id=1,
            username="用户一",
            password_hash="test",
            role="customer",
            is_active=True,
        ))
        self.db.add(User(
            id=2,
            tenant_id=2,
            username="用户二",
            password_hash="test",
            role="customer",
            is_active=True,
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_router_resumes_bare_order_id_without_llm(self):
        with patch(
            "app.agent.nodes.conversation_state_node.SessionLocal",
            return_value=self.db,
        ):
            conversation_state_node({
                "tenant_id": 1,
                "user_id": 1,
                "session_id": "session-1",
                "intent": "order_query",
                "missing_slots": ["order_id"],
                "collected_slots": {},
            })

        with patch(
            "app.agent.nodes.router_node.SessionLocal",
            return_value=self.db,
        ), patch(
            "app.agent.nodes.router_node._classify_by_llm",
        ) as classify_llm:
            result = router_node({
                "tenant_id": 1,
                "user_id": 1,
                "session_id": "session-1",
                "message": "10001",
            })

        self.assertEqual(result["intent"], "order_query")
        self.assertEqual(result["collected_slots"], {"order_id": 10001})
        self.assertEqual(result["missing_slots"], [])
        classify_llm.assert_not_called()

    def test_owner_boundary_prevents_cross_user_resume(self):
        ConversationStateService(self.db).save_pending(
            tenant_id=1,
            user_id=1,
            session_id="shared-session",
            pending_intent="order_query",
            missing_slots=["order_id"],
            collected_slots={},
        )
        other_user = ConversationStateService(self.db).load_active(
            tenant_id=2,
            user_id=2,
            session_id="shared-session",
        )
        self.assertIsNone(other_user)

    def test_expired_state_is_deleted(self):
        ConversationStateService(self.db).save_pending(
            tenant_id=1,
            user_id=1,
            session_id="expired-session",
            pending_intent="order_query",
            missing_slots=["order_id"],
            collected_slots={},
        )
        record = self.db.query(ConversationState).filter_by(
            session_id="expired-session"
        ).one()
        record.expires_at = datetime.utcnow() - timedelta(seconds=1)
        self.db.commit()

        result = ConversationStateService(self.db).load_active(
            tenant_id=1,
            user_id=1,
            session_id="expired-session",
        )
        self.assertIsNone(result)
        self.assertEqual(
            self.db.query(ConversationState).filter_by(
                session_id="expired-session"
            ).count(),
            0,
        )

    def test_order_card_can_resume_pending_refund_intent(self):
        ConversationStateService(self.db).save_pending(
            tenant_id=1,
            user_id=1,
            session_id="refund-card-session",
            pending_intent="refund_request",
            missing_slots=["order_id"],
            collected_slots={"reason": "不想要了"},
        )
        with patch(
            "app.agent.nodes.router_node.SessionLocal",
            return_value=self.db,
        ), patch("app.agent.nodes.router_node._classify_by_llm") as classify_llm:
            result = router_node({
                "tenant_id": 1,
                "user_id": 1,
                "session_id": "refund-card-session",
                "message": "继续处理",
                "chat_context": {"context_type": "order", "order_id": 10001},
                "collected_slots": {"order_id": 10001},
            })

        self.assertEqual(result["intent"], "refund_request")
        self.assertEqual(result["missing_slots"], [])
        self.assertEqual(result["collected_slots"]["order_id"], 10001)
        classify_llm.assert_not_called()

    def test_switching_to_product_card_drops_conflicting_refund_resume(self):
        ConversationStateService(self.db).save_pending(
            tenant_id=1,
            user_id=1,
            session_id="switch-card-session",
            pending_intent="refund_request",
            missing_slots=["order_id"],
            collected_slots={"reason": "不想要了"},
        )
        with patch(
            "app.agent.nodes.router_node.SessionLocal",
            return_value=self.db,
        ):
            result = router_node({
                "tenant_id": 1,
                "user_id": 1,
                "session_id": "switch-card-session",
                "message": "这件商品有货吗",
                "chat_context": {"context_type": "product", "product_id": 1},
                "collected_slots": {"product_id": 1},
            })

        self.assertEqual(result["intent"], "inventory_query")
        self.assertNotEqual(result.get("pending_intent"), "refund_request")


if __name__ == "__main__":
    unittest.main()
