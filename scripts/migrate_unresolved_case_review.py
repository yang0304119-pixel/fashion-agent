"""为已有SQLite未解决案例表增加人工标注审计字段。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REVIEW_COLUMNS = {
    "reviewed_by": "INTEGER",
    "reviewed_at": "DATETIME",
    "updated_at": "DATETIME",
}


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _require_table(connection)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(unresolved_case)")
        }
        for column, definition in REVIEW_COLUMNS.items():
            if column not in columns:
                connection.execute(
                    f"ALTER TABLE unresolved_case ADD COLUMN {column} {definition}"
                )
        connection.execute(
            "UPDATE unresolved_case SET updated_at = COALESCE(updated_at, created_at, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_unresolved_case_reviewed_by "
            "ON unresolved_case (reviewed_by)"
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
        _require_table(connection)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(unresolved_case)")
        }
        missing = set(REVIEW_COLUMNS) - columns
        if missing:
            raise RuntimeError(f"未解决案例表缺少审核字段: {sorted(missing)}")
        print("未解决案例数据库结构验证通过。")
    finally:
        connection.close()


def _require_table(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='unresolved_case'"
    ).fetchone()
    if row is None:
        raise RuntimeError("未解决案例表不存在")


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
