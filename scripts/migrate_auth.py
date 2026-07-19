"""为已有SQLite演示库增加认证与租户隔离字段。

示例：
    python scripts/migrate_auth.py --generate-passwords \
        --credentials-output data/dev_auth_credentials.txt

该脚本只执行加列、补值和加索引，不删除业务数据。
生产数据库应改用正式迁移工具（如 Alembic）。
"""

import argparse
import secrets
import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.passwords import hash_password


def migrate(
    database_path: Path,
    *,
    tenant_id: int,
    customer_password: str,
    admin_username: str,
    admin_password: str,
) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN IMMEDIATE")

        _require_table(connection, "tenant")
        _require_table(connection, "user")
        _add_column(connection, "user", "tenant_id", "INTEGER NOT NULL DEFAULT 1")
        _add_column(connection, "user", "password_hash", "VARCHAR(255) NOT NULL DEFAULT ''")
        _add_column(connection, "user", "role", "VARCHAR(20) NOT NULL DEFAULT 'customer'")
        _add_column(connection, "user", "is_active", "BOOLEAN NOT NULL DEFAULT 1")

        customer_hash = hash_password(customer_password)
        connection.execute(
            'UPDATE "user" SET tenant_id = ?, role = \'customer\', '
            "is_active = 1, password_hash = CASE "
            "WHEN password_hash = '' THEN ? ELSE password_hash END "
            "WHERE username <> ?",
            (tenant_id, customer_hash, admin_username),
        )

        admin_hash = hash_password(admin_password)
        admin = connection.execute(
            'SELECT id FROM "user" WHERE username = ?',
            (admin_username,),
        ).fetchone()
        if admin:
            connection.execute(
                'UPDATE "user" SET tenant_id = ?, password_hash = ?, '
                "role = 'admin', is_active = 1 WHERE id = ?",
                (tenant_id, admin_hash, admin[0]),
            )
        else:
            connection.execute(
                'INSERT INTO "user" '
                "(tenant_id, username, password_hash, role, is_active) "
                "VALUES (?, ?, ?, 'admin', 1)",
                (tenant_id, admin_username, admin_hash),
            )

        _migrate_audit_table(connection, "agent_trace", tenant_id)
        _migrate_audit_table(connection, "unresolved_case", tenant_id)

        connection.execute(
            'CREATE INDEX IF NOT EXISTS ix_user_tenant_id ON "user" (tenant_id)'
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_trace_tenant_id "
            "ON agent_trace (tenant_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_agent_trace_user_id "
            "ON agent_trace (user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_unresolved_case_tenant_id "
            "ON unresolved_case (tenant_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_unresolved_case_user_id "
            "ON unresolved_case (user_id)"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _migrate_audit_table(
    connection: sqlite3.Connection,
    table: str,
    tenant_id: int,
) -> None:
    _require_table(connection, table)
    _add_column(connection, table, "tenant_id", "INTEGER")
    _add_column(connection, table, "user_id", "INTEGER")
    connection.execute(
        f"UPDATE {table} SET tenant_id = ? WHERE tenant_id IS NULL",
        (tenant_id,),
    )
    connection.execute(
        f"UPDATE {table} SET user_id = 1 WHERE user_id IS NULL"
    )


def _require_table(connection: sqlite3.Connection, table: str) -> None:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"数据库缺少表: {table}")


def _add_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {
        row[1]
        for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if column not in columns:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def verify_database(database_path: Path) -> None:
    """验证认证所需列、管理员账号和密码哈希已经存在。"""
    connection = sqlite3.connect(database_path)
    try:
        expected = {
            "user": {"tenant_id", "password_hash", "role", "is_active"},
            "agent_trace": {"tenant_id", "user_id"},
            "unresolved_case": {"tenant_id", "user_id"},
        }
        for table, required_columns in expected.items():
            _require_table(connection, table)
            columns = {
                row[1]
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            missing = required_columns - columns
            if missing:
                raise RuntimeError(
                    f"{table} 缺少认证字段: {sorted(missing)}"
                )

        invalid_users = connection.execute(
            'SELECT count(*) FROM "user" WHERE tenant_id IS NULL '
            "OR password_hash = '' OR role NOT IN ('customer', 'admin') "
            "OR is_active IS NULL"
        ).fetchone()[0]
        admin_count = connection.execute(
            'SELECT count(*) FROM "user" '
            "WHERE role = 'admin' AND is_active = 1"
        ).fetchone()[0]
        if invalid_users:
            raise RuntimeError(f"存在 {invalid_users} 个未完成认证迁移的用户")
        if admin_count < 1:
            raise RuntimeError("没有可用的管理员账号")
        print("认证数据库结构验证通过。")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "data" / "fashion.db",
    )
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--customer-password")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password")
    parser.add_argument("--generate-passwords", action="store_true")
    parser.add_argument("--credentials-output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    if args.verify_only:
        verify_database(args.database)
        return

    customer_password = args.customer_password
    admin_password = args.admin_password
    if args.generate_passwords:
        customer_password = secrets.token_urlsafe(14)
        admin_password = secrets.token_urlsafe(14)

    if not customer_password or not admin_password:
        parser.error(
            "请提供 --customer-password 和 --admin-password，"
            "或使用 --generate-passwords"
        )

    migrate(
        args.database,
        tenant_id=args.tenant_id,
        customer_password=customer_password,
        admin_username=args.admin_username,
        admin_password=admin_password,
    )
    verify_database(args.database)

    if args.credentials_output:
        args.credentials_output.parent.mkdir(parents=True, exist_ok=True)
        args.credentials_output.write_text(
            "本地开发账号，请勿提交到版本库。\n"
            f"普通用户：张三 / {customer_password}\n"
            f"管理员：{args.admin_username} / {admin_password}\n",
            encoding="utf-8",
        )
        print(f"认证迁移完成，开发账号已写入: {args.credentials_output}")
    else:
        print("认证迁移完成。请妥善保存本次设置的账号密码。")


if __name__ == "__main__":
    main()
