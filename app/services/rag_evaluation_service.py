"""Offline retrieval metrics computed from an auditable JSONL label set."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from langchain_core.documents import Document


RetrieveFn = Callable[[str, int], list[Document]]


@dataclass(frozen=True)
class RagEvaluationReport:
    cases: int
    metrics: dict[str, float]
    latency_ms: dict[str, float]
    errors: int
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cases": self.cases,
            "metrics": self.metrics,
            "latency_ms": self.latency_ms,
            "errors": self.errors,
            "details": self.details,
        }


def load_rag_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = line.strip()
            if not value:
                continue
            case = json.loads(value)
            case.setdefault("id", f"line-{line_number}")
            _validate_case(case, line_number=line_number)
            cases.append(case)
    if not cases:
        raise ValueError("RAG evaluation set is empty")
    return cases


class RagEvaluationRunner:
    def __init__(self, *, cutoffs: tuple[int, ...] = (1, 3, 5)) -> None:
        if not cutoffs or any(value <= 0 for value in cutoffs):
            raise ValueError("cutoffs must contain positive integers")
        self.cutoffs = tuple(sorted(set(cutoffs)))

    def run(
        self,
        cases: list[dict[str, Any]],
        *,
        retrieve: RetrieveFn,
    ) -> RagEvaluationReport:
        if not cases:
            raise ValueError("RAG evaluation set is empty")

        details: list[dict[str, Any]] = []
        latencies: list[float] = []
        error_count = 0
        fetch_k = max(self.cutoffs)

        for case in cases:
            started = perf_counter()
            error: str | None = None
            try:
                documents = retrieve(case["query"], fetch_k)
                source_sequence = _chunk_source_sequence(documents)
            except Exception as exc:  # The error remains visible in the report.
                source_sequence = []
                error = f"{type(exc).__name__}: {exc}"
                error_count += 1
            elapsed_ms = (perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            details.append(
                _case_detail(
                    case,
                    source_sequence=source_sequence,
                    latency_ms=elapsed_ms,
                    cutoffs=self.cutoffs,
                    error=error,
                )
            )

        metrics: dict[str, float] = {}
        for cutoff in self.cutoffs:
            metrics[f"recall_at_{cutoff}"] = _mean(
                detail["metrics"][f"recall_at_{cutoff}"]
                for detail in details
            )
            metrics[f"precision_at_{cutoff}"] = _mean(
                detail["metrics"][f"precision_at_{cutoff}"]
                for detail in details
            )
            metrics[f"hit_rate_at_{cutoff}"] = _mean(
                detail["metrics"][f"hit_at_{cutoff}"]
                for detail in details
            )
        maximum = max(self.cutoffs)
        metrics[f"mrr_at_{maximum}"] = _mean(
            detail["metrics"][f"reciprocal_rank_at_{maximum}"]
            for detail in details
        )

        return RagEvaluationReport(
            cases=len(cases),
            metrics=metrics,
            latency_ms={
                "mean": round(sum(latencies) / len(latencies), 2),
                "p50": round(_percentile(latencies, 0.50), 2),
                "p95": round(_percentile(latencies, 0.95), 2),
                "max": round(max(latencies), 2),
            },
            errors=error_count,
            details=details,
        )


def _validate_case(case: dict[str, Any], *, line_number: int) -> None:
    query = case.get("query")
    expected = case.get("expected_sources")
    evidence = case.get("evidence")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"line {line_number}: query must be non-empty")
    if (
        not isinstance(expected, list)
        or not expected
        or any(not isinstance(item, str) or not item.strip() for item in expected)
    ):
        raise ValueError(
            f"line {line_number}: expected_sources must be a non-empty string list"
        )
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError(
            f"line {line_number}: evidence is required so labels remain auditable"
        )


def _chunk_source_sequence(documents: list[Document]) -> list[str]:
    sequence: list[str] = []
    for document in documents:
        source = str(document.metadata.get("relative_source", "")).strip()
        if not source:
            continue
        sequence.append(source)
    return sequence


def _case_detail(
    case: dict[str, Any],
    *,
    source_sequence: list[str],
    latency_ms: float,
    cutoffs: tuple[int, ...],
    error: str | None,
) -> dict[str, Any]:
    expected = set(case["expected_sources"])
    metrics: dict[str, float] = {}
    for cutoff in cutoffs:
        retrieved_sequence = source_sequence[:cutoff]
        retrieved = set(retrieved_sequence)
        relevant_count = len(expected & retrieved)
        metrics[f"recall_at_{cutoff}"] = round(
            relevant_count / len(expected), 4
        )
        metrics[f"precision_at_{cutoff}"] = round(
            sum(source in expected for source in retrieved_sequence)
            / cutoff,
            4,
        )
        metrics[f"hit_at_{cutoff}"] = float(relevant_count > 0)

    maximum = max(cutoffs)
    first_relevant_rank = next(
        (
            index
            for index, source in enumerate(source_sequence[:maximum], start=1)
            if source in expected
        ),
        None,
    )
    metrics[f"reciprocal_rank_at_{maximum}"] = round(
        1 / first_relevant_rank if first_relevant_rank else 0.0,
        4,
    )
    return {
        "id": case["id"],
        "query": case["query"],
        "expected_sources": case["expected_sources"],
        "evidence": case["evidence"],
        "retrieved_chunk_sources": source_sequence,
        "retrieved_unique_sources": list(dict.fromkeys(source_sequence)),
        "first_relevant_rank": first_relevant_rank,
        "latency_ms": round(latency_ms, 2),
        "metrics": metrics,
        "error": error,
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
