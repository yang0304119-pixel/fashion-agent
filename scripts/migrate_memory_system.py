"""为已有SQLite数据库创建完整分层记忆表。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCHEMA = r'''
CREATE TABLE IF NOT EXISTS conversation_turn (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(50) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    message_type VARCHAR(30) NOT NULL DEFAULT 'text',
    tool_name VARCHAR(50),
    tool_result_summary JSON,
    context_summary JSON,
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id)
);
CREATE INDEX IF NOT EXISTS ix_conversation_turn_owner_session_created
    ON conversation_turn (tenant_id, user_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS ix_conversation_turn_expires_at
    ON conversation_turn (expires_at);

CREATE TABLE IF NOT EXISTS conversation_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(50) NOT NULL,
    summary JSON NOT NULL DEFAULT '{}',
    source_turn_ids JSON NOT NULL DEFAULT '[]',
    last_turn_id INTEGER,
    token_count INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    CONSTRAINT uq_conversation_summary_owner_session
        UNIQUE (tenant_id, user_id, session_id),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id)
);
CREATE INDEX IF NOT EXISTS ix_conversation_summary_expires_at
    ON conversation_summary (expires_at);

CREATE TABLE IF NOT EXISTS task_checkpoint (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(50) NOT NULL,
    task_id VARCHAR(100) NOT NULL UNIQUE,
    intent VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL,
    goal TEXT NOT NULL,
    completed_steps JSON NOT NULL DEFAULT '[]',
    current_step VARCHAR(200),
    missing_slots JSON NOT NULL DEFAULT '[]',
    collected_slots JSON NOT NULL DEFAULT '{}',
    tool_conclusions JSON NOT NULL DEFAULT '[]',
    open_issues JSON NOT NULL DEFAULT '[]',
    next_action VARCHAR(500),
    final_result_summary JSON,
    business_critical BOOLEAN NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    completed_at DATETIME,
    CONSTRAINT uq_task_checkpoint_owner_session
        UNIQUE (tenant_id, user_id, session_id),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id)
);
CREATE INDEX IF NOT EXISTS ix_task_checkpoint_status
    ON task_checkpoint (tenant_id, status);
CREATE INDEX IF NOT EXISTS ix_task_checkpoint_expires_at
    ON task_checkpoint (expires_at);

CREATE TABLE IF NOT EXISTS memory_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    scope_type VARCHAR(30) NOT NULL DEFAULT 'user',
    scope_id VARCHAR(100) NOT NULL,
    memory_type VARCHAR(50) NOT NULL,
    subject_key VARCHAR(150) NOT NULL,
    content JSON NOT NULL,
    searchable_text TEXT NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    source_id VARCHAR(150),
    confidence FLOAT NOT NULL DEFAULT 1.0,
    importance FLOAT NOT NULL DEFAULT 0.5,
    stability FLOAT NOT NULL DEFAULT 0.5,
    sensitivity VARCHAR(30) NOT NULL DEFAULT 'low',
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    embedding JSON,
    valid_from DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    supersedes_id INTEGER,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_used_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id),
    FOREIGN KEY(supersedes_id) REFERENCES memory_record(id)
);
CREATE INDEX IF NOT EXISTS ix_memory_record_owner_status_type
    ON memory_record (tenant_id, user_id, status, memory_type);
CREATE INDEX IF NOT EXISTS ix_memory_record_scope
    ON memory_record (tenant_id, scope_type, scope_id);
CREATE INDEX IF NOT EXISTS ix_memory_record_subject
    ON memory_record (tenant_id, user_id, subject_key);
CREATE INDEX IF NOT EXISTS ix_memory_record_expires_at
    ON memory_record (expires_at);

CREATE TABLE IF NOT EXISTS memory_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(50),
    memory_id INTEGER,
    event_type VARCHAR(30) NOT NULL,
    reason VARCHAR(300),
    details JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id),
    FOREIGN KEY(memory_id) REFERENCES memory_record(id)
);
CREATE INDEX IF NOT EXISTS ix_memory_event_owner_created
    ON memory_event (tenant_id, user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_memory_event_type
    ON memory_event (tenant_id, event_type);
'''

TABLES = {
    "conversation_turn",
    "conversation_summary",
    "task_checkpoint",
    "memory_record",
    "memory_event",
}


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


def verify(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        missing = TABLES - existing
        if missing:
            raise RuntimeError(f"记忆系统缺少表: {sorted(missing)}")
    finally:
        connection.close()


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
    print("记忆系统数据库结构验证通过。")


if __name__ == "__main__":
    main()
