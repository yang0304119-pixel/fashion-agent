"""One-click retrieval evaluation for the current tenant knowledge index.

Run this file directly in PyCharm, or use:
    D:\\CondaEnvs\\fashionagent\\python.exe -X utf8 scripts\\evaluate_rag.py

The default run is deterministic and offline after model loading: it evaluates
the current active tenant build with the production dense + BM25 + RRF
retriever, while disabling remote LLM query rewriting.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from unittest.mock import patch

from langchain_core.documents import Document


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.models.knowledge_document import KnowledgeDocument, KnowledgeRevision
from app.rag.config import EMBEDDING_MODEL_PATH
from app.rag.retriever import retrieve
from app.rag.vector_store import open_vector_store_by_name
from app.services.knowledge_index_service import KnowledgeIndexService
from app.services.rag_evaluation_service import RagEvaluationRunner, load_rag_cases


DEFAULT_CASES = PROJECT_ROOT / "data" / "evaluation" / "rag_cases.jsonl"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "evaluation" / "rag-report.json"
DEFAULT_SUMMARY = PROJECT_ROOT / "data" / "evaluation" / "rag-summary.md"
DEFAULT_TENANT_ID = 1
KNOWLEDGE_TYPE_LABELS = {
    "product_knowledge": "商品知识",
    "size_guide": "尺码知识",
    "after_sales_policy": "售后规则",
    "logistics_policy": "物流规则",
    "store_rule": "店铺规则",
    "faq": "FAQ",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Recall/Precision/Hit/MRR on a tenant RAG index."
    )
    parser.add_argument("--tenant-id", type=int, default=DEFAULT_TENANT_ID)
    parser.add_argument(
        "--build-id",
        type=int,
        default=None,
        help="Evaluate a ready/active/superseded build; defaults to active.",
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--enable-query-rewrite",
        action="store_true",
        help="Call the configured remote LLM rewriter (disabled by default).",
    )
    args = parser.parse_args()

    if args.tenant_id <= 0:
        parser.error("--tenant-id must be greater than zero")

    cases = load_rag_cases(args.cases)
    build, source_aliases = _load_build_context(
        tenant_id=args.tenant_id,
        build_id=args.build_id,
    )
    vector_store = open_vector_store_by_name(build.collection_name)

    def retrieve_from_tenant_build(query: str, top_k: int) -> list[Document]:
        def run() -> list[Document]:
            return retrieve(
                query,
                tenant_id=args.tenant_id,
                build_id=build.id,
                top_k=top_k,
            )

        if args.enable_query_rewrite:
            documents = run()
        else:
            with patch(
                "app.rag.retriever.rewrite_query",
                side_effect=lambda value: value,
            ):
                documents = run()
        return [_with_labeled_source(document, source_aliases) for document in documents]

    print(
        f"Evaluating tenant={args.tenant_id} build={build.id} "
        f"collection={build.collection_name} cases={len(cases)} ..."
    )
    evaluation = RagEvaluationRunner().run(
        cases,
        retrieve=retrieve_from_tenant_build,
    ).to_dict()
    generated_at = datetime.now(UTC).isoformat()
    report = {
        "generated_at": generated_at,
        "scope": (
            "current tenant knowledge index; production dense+BM25+RRF "
            "retrieval; remote query rewrite "
            + ("enabled" if args.enable_query_rewrite else "disabled")
            + "; retrieval metrics only, not answer accuracy or production SLA"
        ),
        "tenant_id": args.tenant_id,
        "build": {
            "id": build.id,
            "status": build.status,
            "collection_name": build.collection_name,
            "document_count": build.document_count,
            "chunk_count": build.chunk_count,
            "revision_snapshot": build.revision_snapshot,
            "activated_at": (
                build.activated_at.isoformat() if build.activated_at else None
            ),
        },
        "indexed_chunks": vector_store._collection.count(),
        "embedding_model": str(EMBEDDING_MODEL_PATH),
        "cases_file": str(args.cases.resolve()),
        **evaluation,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(_markdown_summary(report), encoding="utf-8")
    _print_summary(report, report_path=args.report, summary_path=args.summary)


def _load_build_context(*, tenant_id: int, build_id: int | None):
    db = SessionLocal()
    try:
        service = KnowledgeIndexService(db)
        build = service.resolve_read_build(tenant_id=tenant_id, build_id=build_id)
        if not build.collection_name:
            raise RuntimeError("Knowledge index build has no Chroma collection")
        revisions = (
            db.query(KnowledgeRevision)
            .join(KnowledgeDocument)
            .filter(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeRevision.id.in_(build.revision_snapshot),
            )
            .all()
        )
        if len(revisions) != len(build.revision_snapshot):
            raise RuntimeError("Knowledge index revision snapshot is incomplete")
        aliases = {
            f"documents/{revision.document_id}/revisions/{revision.id}": (
                _labeled_source(revision)
            )
            for revision in revisions
        }
        db.expunge(build)
        return build, aliases
    finally:
        db.close()


def _labeled_source(revision: KnowledgeRevision) -> str:
    document = revision.document
    type_label = KNOWLEDGE_TYPE_LABELS.get(
        document.knowledge_type,
        document.knowledge_type,
    )
    return f"{type_label}/{document.category}/{revision.original_filename}"


def _with_labeled_source(
    document: Document,
    aliases: dict[str, str],
) -> Document:
    runtime_source = str(document.metadata.get("relative_source", ""))
    labeled_source = aliases.get(runtime_source, runtime_source)
    metadata = dict(document.metadata)
    metadata["runtime_source"] = runtime_source
    metadata["relative_source"] = labeled_source
    return Document(
        id=document.id,
        page_content=document.page_content,
        metadata=metadata,
    )


def _print_summary(report: dict, *, report_path: Path, summary_path: Path) -> None:
    metrics = report["metrics"]
    latency = report["latency_ms"]
    print("\nRAG retrieval evaluation completed")
    print(f"Cases: {report['cases']} | Errors: {report['errors']}")
    for cutoff in (1, 3, 5):
        print(
            f"@{cutoff}: Recall={metrics[f'recall_at_{cutoff}']:.2%}  "
            f"Precision={metrics[f'precision_at_{cutoff}']:.2%}  "
            f"Hit={metrics[f'hit_rate_at_{cutoff}']:.2%}"
        )
    print(f"MRR@5: {metrics['mrr_at_5']:.4f}")
    print(f"Latency P50/P95: {latency['p50']:.2f}/{latency['p95']:.2f} ms")
    print(f"JSON report: {report_path.resolve()}")
    print(f"Markdown summary: {summary_path.resolve()}")


def _markdown_summary(report: dict) -> str:
    metrics = report["metrics"]
    latency = report["latency_ms"]
    failed = [
        detail
        for detail in report["details"]
        if detail["metrics"]["hit_at_5"] == 0
    ]
    lines = [
        "# RAG Retrieval Evaluation",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Tenant/build: `{report['tenant_id']}` / `{report['build']['id']}`",
        f"- Collection: `{report['build']['collection_name']}`",
        f"- Corpus: {report['build']['document_count']} documents, "
        f"{report['indexed_chunks']} chunks",
        f"- Labeled cases: {report['cases']}; retrieval errors: {report['errors']}",
        "- Scope: retrieval quality only; not answer accuracy or production SLA",
        "",
        "| K | Recall@K | Precision@K | Hit@K |",
        "|---:|---:|---:|---:|",
    ]
    for cutoff in (1, 3, 5):
        lines.append(
            f"| {cutoff} | {metrics[f'recall_at_{cutoff}']:.2%} | "
            f"{metrics[f'precision_at_{cutoff}']:.2%} | "
            f"{metrics[f'hit_rate_at_{cutoff}']:.2%} |"
        )
    lines.extend([
        "",
        f"- MRR@5: `{metrics['mrr_at_5']:.4f}`",
        f"- Local retrieval latency P50/P95: "
        f"`{latency['p50']:.2f}/{latency['p95']:.2f} ms`",
        "",
        "## Top-5 Misses",
        "",
    ])
    if failed:
        for detail in failed:
            lines.append(f"- `{detail['id']}`: {detail['query']}")
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
