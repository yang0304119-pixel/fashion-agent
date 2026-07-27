"""Offline intent metrics for labeled, held-out customer utterances."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable


PredictFn = Callable[[str], dict[str, Any]]
WRITE_INTENTS = frozenset({"refund_request", "after_sales_request"})


@dataclass(frozen=True)
class IntentEvaluationReport:
    cases: int
    metrics: dict[str, float]
    source_counts: dict[str, int]
    confusion_matrix: dict[str, dict[str, int]]
    latency_ms: dict[str, float]
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "metrics": self.metrics,
            "source_counts": self.source_counts,
            "confusion_matrix": self.confusion_matrix,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


def load_intent_cases(path: Path) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = line.strip()
            if not value:
                continue
            case = json.loads(value)
            case.setdefault("id", f"line-{line_number}")
            for field in ("message", "expected_intent", "label_reason"):
                if not isinstance(case.get(field), str) or not case[field].strip():
                    raise ValueError(f"line {line_number}: {field} is required")
            cases.append(case)
    if not cases:
        raise ValueError("intent evaluation set is empty")
    return cases


class IntentEvaluationRunner:
    def run(
        self,
        cases: list[dict[str, str]],
        *,
        predict: PredictFn,
    ) -> IntentEvaluationReport:
        if not cases:
            raise ValueError("intent evaluation set is empty")
        details: list[dict[str, Any]] = []
        latencies: list[float] = []
        sources: Counter[str] = Counter()

        for case in cases:
            started = perf_counter()
            decision = predict(case["message"])
            elapsed_ms = (perf_counter() - started) * 1000
            actual = str(decision.get("intent", "fallback"))
            source = str(decision.get("router_source", "unknown"))
            sources[source] += 1
            latencies.append(elapsed_ms)
            details.append({
                "id": case["id"],
                "message": case["message"],
                "expected_intent": case["expected_intent"],
                "actual_intent": actual,
                "label_reason": case["label_reason"],
                "router_source": source,
                "confidence": float(decision.get("confidence", 0.0)),
                "passed": actual == case["expected_intent"],
                "latency_ms": round(elapsed_ms, 2),
            })

        expected = [detail["expected_intent"] for detail in details]
        actual = [detail["actual_intent"] for detail in details]
        labels = sorted(set(expected) | set(actual))
        matrix = {
            label: {
                predicted: sum(
                    1
                    for truth, guess in zip(expected, actual, strict=True)
                    if truth == label and guess == predicted
                )
                for predicted in labels
            }
            for label in labels
        }
        per_label = [_classification_metrics(label, expected, actual) for label in labels]
        write_tp = sum(
            truth in WRITE_INTENTS and guess == truth
            for truth, guess in zip(expected, actual, strict=True)
        )
        write_predictions = sum(guess in WRITE_INTENTS for guess in actual)
        write_truth = sum(truth in WRITE_INTENTS for truth in expected)

        metrics = {
            "accuracy": round(
                sum(truth == guess for truth, guess in zip(expected, actual, strict=True))
                / len(cases),
                4,
            ),
            "macro_precision": _mean(item["precision"] for item in per_label),
            "macro_recall": _mean(item["recall"] for item in per_label),
            "macro_f1": _mean(item["f1"] for item in per_label),
            "write_intent_precision": round(
                write_tp / write_predictions if write_predictions else 0.0,
                4,
            ),
            "write_intent_recall": round(
                write_tp / write_truth if write_truth else 0.0,
                4,
            ),
            "fallback_rate": round(
                sum(guess == "fallback" for guess in actual) / len(cases),
                4,
            ),
        }
        return IntentEvaluationReport(
            cases=len(cases),
            metrics=metrics,
            source_counts=dict(sorted(sources.items())),
            confusion_matrix=matrix,
            latency_ms={
                "mean": round(sum(latencies) / len(latencies), 2),
                "p50": round(_percentile(latencies, 0.50), 2),
                "p95": round(_percentile(latencies, 0.95), 2),
                "max": round(max(latencies), 2),
            },
            details=details,
        )


def _classification_metrics(
    label: str,
    expected: list[str],
    actual: list[str],
) -> dict[str, float]:
    tp = sum(
        truth == label and guess == label
        for truth, guess in zip(expected, actual, strict=True)
    )
    fp = sum(
        truth != label and guess == label
        for truth, guess in zip(expected, actual, strict=True)
    )
    fn = sum(
        truth == label and guess != label
        for truth, guess in zip(expected, actual, strict=True)
    )
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0,
    }


def _mean(values) -> float:
    collected = list(values)
    return round(sum(collected) / len(collected), 4)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
