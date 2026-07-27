"""基于标注JSONL的记忆系统离线评测，不凭主观感觉声明准确率。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base
from app.models import Tenant, User
from app.services.memory_service import (
    LongTermMemoryService,
    MemoryCandidate,
    MemoryContextBuilder,
    TaskCheckpointService,
)


@dataclass(frozen=True)
class MemoryEvaluationReport:
    cases: int
    metrics: dict[str, float]
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"cases": self.cases, "metrics": self.metrics, "details": self.details}


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = line.strip()
            if not value:
                continue
            payload = json.loads(value)
            payload.setdefault("id", f"line-{line_number}")
            cases.append(payload)
    return cases


class MemoryEvaluationRunner:
    def run(self, cases: list[dict[str, Any]]) -> MemoryEvaluationReport:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        db.add_all([
            Tenant(id=1, name="评测租户一", industry="服装"),
            Tenant(id=2, name="评测租户二", industry="服装"),
        ])
        db.flush()
        db.add_all([
            User(id=1, tenant_id=1, username="eval-a", password_hash="x", role="customer", is_active=True),
            User(id=2, tenant_id=1, username="eval-b", password_hash="x", role="customer", is_active=True),
            User(id=3, tenant_id=2, username="eval-c", password_hash="x", role="customer", is_active=True),
        ])
        db.commit()
        original_semantic = settings.MEMORY_SEMANTIC_ENABLED
        settings.MEMORY_SEMANTIC_ENABLED = False
        details = []
        counters: dict[str, list[bool]] = {}
        try:
            for case in cases:
                result = self._run_case(db, case)
                details.append(result)
                counters.setdefault(case["kind"], []).append(bool(result["passed"]))
        finally:
            settings.MEMORY_SEMANTIC_ENABLED = original_semantic
            db.close()
            engine.dispose()
        metrics = {
            _metric_name(kind): round(sum(values) / len(values), 4)
            for kind, values in counters.items()
            if values
        }
        return MemoryEvaluationReport(len(cases), metrics, details)

    def _run_case(self, db, case: dict[str, Any]) -> dict[str, Any]:
        kind = case["kind"]
        service = LongTermMemoryService(db)
        if kind in {"extraction", "block"}:
            candidates = service.extract_candidates(
                tenant_id=1,
                user_id=1,
                session_id=case["id"],
                message=case["message"],
                state={},
            )
            actual = sorted(candidate.subject_key for candidate in candidates)
            expected = sorted(case.get("expected_subjects", []))
            return _detail(case, actual == expected, {"expected": expected, "actual": actual})
        if kind in {"retrieval", "tenant_isolation"}:
            for item in case.get("memories", []):
                service.write_candidates(
                    tenant_id=item.get("tenant_id", 1),
                    user_id=item.get("user_id", 1),
                    session_id=case["id"],
                    candidates=[MemoryCandidate(
                        memory_type=item["memory_type"],
                        subject_key=item["subject_key"],
                        content=item["content"],
                        searchable_text=item["searchable_text"],
                        source_type=item.get("source_type", "verified_code"),
                        confidence=1.0,
                        importance=0.9,
                        stability=0.9,
                        scope_type=item.get("scope_type", "user"),
                        scope_id=item.get("scope_id", str(item.get("user_id", 1))),
                    )],
                )
            results = service.retrieve(
                tenant_id=case.get("query_tenant_id", 1),
                user_id=case.get("query_user_id", 1),
                session_id=case["id"],
                query=case["query"],
                intent=case.get("intent", "composite_query"),
            )
            actual = [item["subject_key"] for item in results]
            expected = case.get("expected_subject")
            passed = expected in actual if expected else not actual
            return _detail(case, passed, {"expected": expected, "actual": actual})
        if kind == "context_budget":
            _, budget = MemoryContextBuilder().build(
                recent_turns=case.get("recent_turns", []),
                conversation_summary=case.get("conversation_summary"),
                task_checkpoint=case.get("task_checkpoint"),
                memories=case.get("memories", []),
                chat_context={},
                budget=case["budget"],
            )
            return _detail(case, budget["used"] <= case["budget"], budget)
        if kind == "task_resume":
            checkpoint = TaskCheckpointService(db)
            checkpoint.save_from_state({
                "tenant_id": 1,
                "user_id": 1,
                "session_id": case["id"],
                "intent": case["intent"],
                "message": case["message"],
                "missing_slots": case["missing_slots"],
                "collected_slots": case.get("collected_slots", {}),
                "final_answer": "等待补参",
            })
            loaded = checkpoint.load_active(
                tenant_id=1,
                user_id=1,
                session_id=case["id"],
            )
            actual = loaded.get("missing_slots") if loaded else None
            return _detail(case, actual == case["missing_slots"], {"actual": actual})
        raise ValueError(f"未知记忆评测类型: {kind}")


def _detail(case: dict[str, Any], passed: bool, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "kind": case["kind"],
        "passed": passed,
        "evidence": evidence,
    }


def _metric_name(kind: str) -> str:
    return {
        "extraction": "write_extraction_accuracy",
        "block": "unsafe_write_block_rate",
        "retrieval": "retrieval_hit_at_k",
        "tenant_isolation": "tenant_isolation_pass_rate",
        "context_budget": "context_budget_pass_rate",
        "task_resume": "task_resume_success_rate",
    }.get(kind, f"{kind}_pass_rate")
