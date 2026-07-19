"""为已有SQLite工单表增加审核审计字段。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEW_COLUMNS = {
    "reviewed_by": "INTEGER",
    "reviewed_at": "DATETIME",
    "review_reason": "TEXT",
}


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_ticket_table(connection)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(ticket)")
        }
        for column, definition in REVIEW_COLUMNS.items():
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE ticket ADD COLUMN {column} {definition}"
                )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_ticket_reviewed_by "
            "ON ticket (reviewed_by)"
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
        _require_ticket_table(connection)
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(ticket)")
        }
        missing = set(REVIEW_COLUMNS) - columns
        if missing:
            raise RuntimeError(f"工单表缺少审核字段: {sorted(missing)}")
        print("工单审核数据库结构验证通过。")
    finally:
        connection.close()


def _require_ticket_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ticket'"
    ).fetchone()
    if row is None:
        raise RuntimeError("工单表不存在")


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
