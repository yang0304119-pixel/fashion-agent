"""为已有 SQLite 数据库创建知识文档生命周期表。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

KNOWLEDGE_LIFECYCLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_document (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    knowledge_type VARCHAR(50) NOT NULL,
    category VARCHAR(100) NOT NULL DEFAULT '通用',
    created_by INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(created_by) REFERENCES "user"(id)
);
CREATE INDEX IF NOT EXISTS ix_knowledge_document_tenant_id
    ON knowledge_document (tenant_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_document_knowledge_type
    ON knowledge_document (knowledge_type);
CREATE INDEX IF NOT EXISTS ix_knowledge_document_created_by
    ON knowledge_document (created_by);
CREATE INDEX IF NOT EXISTS ix_knowledge_document_tenant_updated
    ON knowledge_document (tenant_id, updated_at);

CREATE TABLE IF NOT EXISTS knowledge_revision (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    version_no INTEGER NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    source_file_type VARCHAR(20) NOT NULL,
    raw_storage_key VARCHAR(500) NOT NULL,
    processed_storage_key VARCHAR(500),
    source_sha256 VARCHAR(64) NOT NULL,
    processed_sha256 VARCHAR(64),
    parse_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    parse_error_code VARCHAR(100),
    parse_error_message VARCHAR(500),
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    quality_status VARCHAR(20),
    quality_report JSON,
    created_by INTEGER NOT NULL,
    reviewed_by INTEGER,
    reviewed_at DATETIME,
    review_reason TEXT,
    effective_at DATETIME,
    expires_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_knowledge_revision_document_version
        UNIQUE (document_id, version_no),
    CONSTRAINT ck_knowledge_revision_parse_status
        CHECK (parse_status IN ('pending', 'running', 'succeeded', 'failed')),
    CONSTRAINT ck_knowledge_revision_review_status
        CHECK (review_status IN ('pending', 'approved', 'rejected')),
    FOREIGN KEY(document_id) REFERENCES knowledge_document(id) ON DELETE CASCADE,
    FOREIGN KEY(created_by) REFERENCES "user"(id),
    FOREIGN KEY(reviewed_by) REFERENCES "user"(id)
);
CREATE INDEX IF NOT EXISTS ix_knowledge_revision_document_id
    ON knowledge_revision (document_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_revision_parse_status
    ON knowledge_revision (parse_status);
CREATE INDEX IF NOT EXISTS ix_knowledge_revision_review_status
    ON knowledge_revision (review_status);
CREATE INDEX IF NOT EXISTS ix_knowledge_revision_created_by
    ON knowledge_revision (created_by);
CREATE INDEX IF NOT EXISTS ix_knowledge_revision_reviewed_by
    ON knowledge_revision (reviewed_by);
CREATE INDEX IF NOT EXISTS ix_knowledge_revision_document_created
    ON knowledge_revision (document_id, created_at);
CREATE TABLE IF NOT EXISTS knowledge_index_build (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'building',
    collection_name VARCHAR(200),
    revision_snapshot JSON NOT NULL DEFAULT '[]',
    document_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    triggered_by INTEGER NOT NULL,
    error_code VARCHAR(100),
    error_message VARCHAR(500),
    previous_active_build_id INTEGER,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    activated_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_knowledge_index_build_collection UNIQUE (collection_name),
    CONSTRAINT ck_knowledge_index_build_status
        CHECK (status IN ('building', 'ready', 'active', 'failed', 'superseded')),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(triggered_by) REFERENCES "user"(id),
    FOREIGN KEY(previous_active_build_id) REFERENCES knowledge_index_build(id)
);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_build_tenant_id
    ON knowledge_index_build (tenant_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_build_status
    ON knowledge_index_build (status);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_build_triggered_by
    ON knowledge_index_build (triggered_by);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_build_previous_active
    ON knowledge_index_build (previous_active_build_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_index_build_tenant_created
    ON knowledge_index_build (tenant_id, created_at);
"""


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(KNOWLEDGE_LIFECYCLE_SCHEMA)
        _ensure_columns(connection, "knowledge_revision", {
            "effective_at": "DATETIME",
            "expires_at": "DATETIME",
        })
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS ix_knowledge_revision_effective_at
                ON knowledge_revision (effective_at);
            CREATE INDEX IF NOT EXISTS ix_knowledge_revision_expires_at
                ON knowledge_revision (expires_at);
            """
        )
        if _table_exists(connection, "unresolved_case"):
            _ensure_columns(connection, "unresolved_case", {
                "knowledge_document_id": "INTEGER",
                "knowledge_revision_id": "INTEGER",
                "resolved_by_build_id": "INTEGER",
                "auto_resolved_at": "DATETIME",
            })
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS ix_unresolved_case_knowledge_document
                    ON unresolved_case (knowledge_document_id);
                CREATE INDEX IF NOT EXISTS ix_unresolved_case_knowledge_revision
                    ON unresolved_case (knowledge_revision_id);
                CREATE INDEX IF NOT EXISTS ix_unresolved_case_resolved_build
                    ON unresolved_case (resolved_by_build_id);
                """
            )
        connection.commit()
    finally:
        connection.close()


def verify(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        expected = {
            "knowledge_document": {
                "tenant_id",
                "title",
                "knowledge_type",
                "category",
                "created_by",
                "created_at",
                "updated_at",
            },
            "knowledge_revision": {
                "document_id",
                "version_no",
                "original_filename",
                "raw_storage_key",
                "processed_storage_key",
                "source_sha256",
                "processed_sha256",
                "parse_status",
                "review_status",
                "quality_report",
                "created_by",
                "reviewed_by",
                "effective_at",
                "expires_at",
            },
            "knowledge_index_build": {
                "tenant_id",
                "status",
                "collection_name",
                "revision_snapshot",
                "document_count",
                "chunk_count",
                "triggered_by",
                "previous_active_build_id",
                "started_at",
                "finished_at",
                "activated_at",
            },
        }
        for table, columns in expected.items():
            row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if row is None:
                raise RuntimeError(f"{table}表不存在")
            actual = {
                item[1]
                for item in connection.execute(f"PRAGMA table_info({table})")
            }
            missing = columns - actual
            if missing:
                raise RuntimeError(f"{table}表缺少字段: {sorted(missing)}")
        if _table_exists(connection, "unresolved_case"):
            actual = {
                item[1]
                for item in connection.execute(
                    "PRAGMA table_info(unresolved_case)"
                )
            }
            expected_case = {
                "knowledge_document_id",
                "knowledge_revision_id",
                "resolved_by_build_id",
                "auto_resolved_at",
            }
            missing = expected_case - actual
            if missing:
                raise RuntimeError(
                    f"unresolved_case表缺少知识闭环字段: {sorted(missing)}"
                )
    finally:
        connection.close()


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def _ensure_columns(
    connection: sqlite3.Connection,
    table: str,
    columns: dict[str, str],
) -> None:
    actual = {
        item[1]
        for item in connection.execute(f"PRAGMA table_info({table})")
    }
    for name, definition in columns.items():
        if name not in actual:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "fashion.db",
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if not args.verify_only:
        migrate(args.database)
    verify(args.database)
    print("知识文档生命周期数据库结构验证通过。")


if __name__ == "__main__":
    main()
