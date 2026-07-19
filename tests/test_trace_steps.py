import unittest
from unittest.mock import patch

try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.database import Base
    from app.models import AgentTrace, AgentTraceStep, Tenant, User
    from app.services.trace_service import (
        create_request_trace,
        finalize_request_trace,
        traced_node,
    )
except ModuleNotFoundError as error:
    if error.name in {"sqlalchemy", "pydantic_settings"}:
        raise unittest.SkipTest(f"当前解释器未安装项目依赖 {error.name}")
    raise


class TraceStepTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)
        db = self.Session()
        db.add(Tenant(id=1, name="测试租户", industry="服装"))
        db.flush()
        db.add(
            User(
                id=1,
                tenant_id=1,
                username="测试用户",
                password_hash="test",
                role="customer",
                is_active=True,
            )
        )
        db.commit()
        db.close()
        self.session_patch = patch(
            "app.services.trace_service.SessionLocal",
            self.Session,
        )
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()

    def test_records_actual_node_order_slots_and_rag_sources(self):
        trace_id = create_request_trace(
            tenant_id=1,
            user_id=1,
            session_id="session-trace-order",
            message="这件衣服怎么洗",
        )
        state = {
            "trace_id": trace_id,
            "tenant_id": 1,
            "user_id": 1,
            "session_id": "session-trace-order",
            "message": "这件衣服怎么洗",
        }
        router = traced_node(
            "router",
            lambda current: {
                "intent": "knowledge_query",
                "confidence": 0.98,
                "missing_slots": [],
            },
        )
        rag = traced_node(
            "rag",
            lambda current: {
                "retrieved_sources": [{"title": "洗护指南", "id": "doc-1"}],
                "retrieved_doc_ids": ["doc-1"],
                "retrieved_scores": [0.91],
                "final_answer": "建议低温手洗。",
            },
        )
        router_result = router(state)
        state.update(router_result)
        rag_result = rag(state)
        state.update(rag_result)
        finalize_request_trace(state)

        db = self.Session()
        trace = db.get(AgentTrace, trace_id)
        steps = db.query(AgentTraceStep).order_by(AgentTraceStep.sequence).all()
        self.assertEqual([step.node_name for step in steps], ["router", "rag"])
        self.assertEqual(trace.workflow_name, "rag_workflow")
        self.assertEqual(trace.status, "succeeded")
        self.assertEqual(trace.rag_sources[0]["title"], "洗护指南")
        self.assertEqual(steps[1].rag_sources[0]["id"], "doc-1")
        db.close()

    def test_business_error_marks_only_business_step_and_summary_failed(self):
        trace_id = create_request_trace(
            tenant_id=1,
            user_id=1,
            session_id="session-trace-error",
            message="查询订单 99999",
        )
        state = {
            "trace_id": trace_id,
            "tenant_id": 1,
            "user_id": 1,
            "session_id": "session-trace-error",
            "message": "查询订单 99999",
            "intent": "order_query",
            "confidence": 0.99,
            "missing_slots": [],
        }
        order = traced_node(
            "order",
            lambda current: {
                "tool_status": "error",
                "tool_result": {"error": "订单不存在"},
                "final_answer": "订单不存在。",
            },
        )
        answer = traced_node(
            "answer",
            lambda current: {"final_answer": current["final_answer"]},
        )
        state.update(order(state))
        state.update(answer(state))
        finalize_request_trace(state)

        db = self.Session()
        trace = db.get(AgentTrace, trace_id)
        steps = db.query(AgentTraceStep).order_by(AgentTraceStep.sequence).all()
        self.assertEqual(trace.status, "failed")
        self.assertEqual(trace.error_stage, "order_query")
        self.assertEqual(steps[0].status, "failed")
        self.assertEqual(steps[0].error_message, "订单不存在")
        self.assertEqual(steps[1].status, "succeeded")
        db.close()


if __name__ == "__main__":
    unittest.main()
