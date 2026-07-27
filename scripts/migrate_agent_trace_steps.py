"""为已有SQLite Trace表增加请求汇总字段和节点步骤表。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_COLUMNS = {
    "message": "TEXT",
    "workflow_name": "VARCHAR(50)",
    "status": "VARCHAR(20)",
    "missing_slots": "JSON",
    "rag_sources": "JSON",
    "error_stage": "VARCHAR(50)",
    "error_code": "VARCHAR(100)",
    "error_type": "VARCHAR(100)",
    "error_message": "TEXT",
    "finished_at": "DATETIME",
}
STEP_COLUMNS = {
    "attempt": "INTEGER",
    "input": "JSON",
    "output": "JSON",
    "error_category": "VARCHAR(30)",
    "retryable": "BOOLEAN",
    "recovery_action": "VARCHAR(50)",
    "retry_delay_ms": "INTEGER",
}
STEP_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_trace_step (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    node_name VARCHAR(50) NOT NULL,
    workflow_name VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    missing_slots JSON,
    tool_name VARCHAR(50),
    attempt INTEGER,
    input JSON,
    output JSON,
    error_category VARCHAR(30),
    retryable BOOLEAN,
    recovery_action VARCHAR(50),
    retry_delay_ms INTEGER,
    rag_sources JSON,
    error_stage VARCHAR(50),
    error_code VARCHAR(100),
    error_type VARCHAR(100),
    error_message TEXT,
    started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at DATETIME,
    duration_ms INTEGER,
    FOREIGN KEY(trace_id) REFERENCES agent_trace(id) ON DELETE CASCADE,
    UNIQUE(trace_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_agent_trace_step_trace_id
    ON agent_trace_step (trace_id);
CREATE INDEX IF NOT EXISTS ix_agent_trace_workflow_name
    ON agent_trace (workflow_name);
CREATE INDEX IF NOT EXISTS ix_agent_trace_status
    ON agent_trace (status);
"""


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_trace_table(connection)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_trace)")
        }
        for column, definition in SUMMARY_COLUMNS.items():
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE agent_trace ADD COLUMN {column} {definition}"
                )
        connection.executescript(STEP_SCHEMA)
        step_columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(agent_trace_step)"
            )
        }
        for column, definition in STEP_COLUMNS.items():
            if column not in step_columns:
                connection.execute(
                    f"ALTER TABLE agent_trace_step ADD COLUMN {column} {definition}"
                )
        connection.execute(
            "UPDATE agent_trace SET workflow_name = tool_name "
            "WHERE workflow_name IS NULL"
        )
        connection.execute(
            "UPDATE agent_trace SET status = CASE "
            "WHEN tool_status = 'error' THEN 'failed' "
            "WHEN tool_status = 'pending' THEN 'pending' "
            "ELSE 'succeeded' END WHERE status IS NULL"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def verify(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        _require_trace_table(connection)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(agent_trace)")
        }
        missing = set(SUMMARY_COLUMNS) - columns
        if missing:
            raise RuntimeError(f"Trace汇总表缺少字段: {sorted(missing)}")
        step = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='agent_trace_step'"
        ).fetchone()
        if step is None:
            raise RuntimeError("Trace步骤表不存在")
        step_columns = {
            row[1] for row in connection.execute(
                "PRAGMA table_info(agent_trace_step)"
            )
        }
        missing_step_columns = set(STEP_COLUMNS) - step_columns
        if missing_step_columns:
            raise RuntimeError(
                f"Trace步骤表缺少字段: {sorted(missing_step_columns)}"
            )
        print("Trace数据库结构验证通过。")
    finally:
        connection.close()


def _require_trace_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_trace'"
    ).fetchone()
    if row is None:
        raise RuntimeError("Trace汇总表不存在")


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


if __name__ == "__main__":
    main()
