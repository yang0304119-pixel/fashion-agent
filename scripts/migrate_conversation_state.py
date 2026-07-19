"""为已有SQLite数据库创建多轮槽位会话表。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONVERSATION_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversation_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    session_id VARCHAR(50) NOT NULL,
    pending_intent VARCHAR(50) NOT NULL,
    missing_slots JSON NOT NULL DEFAULT '[]',
    collected_slots JSON NOT NULL DEFAULT '{}',
    updated_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    CONSTRAINT uq_conversation_state_owner_session
        UNIQUE (tenant_id, user_id, session_id),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id)
);
CREATE INDEX IF NOT EXISTS ix_conversation_state_tenant_id
    ON conversation_state (tenant_id);
CREATE INDEX IF NOT EXISTS ix_conversation_state_user_id
    ON conversation_state (user_id);
CREATE INDEX IF NOT EXISTS ix_conversation_state_expires_at
    ON conversation_state (expires_at);
"""


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(CONVERSATION_STATE_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def verify(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='conversation_state'"
        ).fetchone()
        if row is None:
            raise RuntimeError("conversation_state表不存在")

        expected = {
            "tenant_id",
            "user_id",
            "session_id",
            "pending_intent",
            "missing_slots",
            "collected_slots",
            "updated_at",
            "expires_at",
        }
        columns = {
            item[1]
            for item in connection.execute(
                "PRAGMA table_info(conversation_state)"
            )
        }
        missing = expected - columns
        if missing:
            raise RuntimeError(
                f"conversation_state表缺少字段: {sorted(missing)}"
            )
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
    print("多轮会话数据库结构验证通过。")


if __name__ == "__main__":
    main()
