"""Evaluate deterministic rules plus local semantic routing without the LLM planner."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agent.nodes.router_node import router_node
from app.rag.config import EMBEDDING_MODEL_PATH
from app.services.intent_evaluation_service import (
    IntentEvaluationRunner,
    load_intent_cases,
)


DEFAULT_CASES = PROJECT_ROOT / "data" / "evaluation" / "intent_cases.jsonl"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "evaluation" / "intent-report.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    cases = load_intent_cases(args.cases)

    def predict(message: str):
        with patch("app.agent.nodes.router_node.plan_intents", return_value=None):
            return router_node({"message": message})

    report = IntentEvaluationRunner().run(cases, predict=predict).to_dict()
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": (
            "held-out single-turn utterances; deterministic rules plus local BGE "
            "semantic router; remote LLM planner disabled"
        ),
        "embedding_model": str(EMBEDDING_MODEL_PATH),
        **report,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
