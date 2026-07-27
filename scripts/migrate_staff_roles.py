"""幂等迁移商家员工角色、租户内用户名唯一约束和人工审计表。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


USER_SCHEMA = '''
CREATE TABLE user_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    username VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'customer',
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_user_tenant_username UNIQUE (tenant_id, username),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id)
);
'''

AUDIT_SCHEMA = '''
CREATE TABLE IF NOT EXISTS admin_audit_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    actor_user_id INTEGER NOT NULL,
    actor_role VARCHAR(50) NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_id VARCHAR(100),
    before_data JSON,
    after_data JSON,
    reason VARCHAR(500),
    ip_address VARCHAR(64),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(actor_user_id) REFERENCES user(id)
);
CREATE INDEX IF NOT EXISTS ix_admin_audit_tenant_created
    ON admin_audit_event (tenant_id, created_at);
CREATE INDEX IF NOT EXISTS ix_admin_audit_actor
    ON admin_audit_event (tenant_id, actor_user_id);
CREATE INDEX IF NOT EXISTS ix_admin_audit_action
    ON admin_audit_event (action);
'''


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        user_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user'"
        ).fetchone()
        if not user_exists:
            return
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='user'"
        ).fetchone()[0] or ""
        if "uq_user_tenant_username" not in table_sql:
            connection.commit()
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.executescript(USER_SCHEMA)
            connection.execute('''
                INSERT INTO user_new (
                    id, tenant_id, username, password_hash, role, is_active, created_at
                )
                SELECT
                    id,
                    tenant_id,
                    username,
                    password_hash,
                    CASE WHEN role = 'admin' THEN 'tenant_admin' ELSE role END,
                    is_active,
                    created_at
                FROM "user"
            ''')
            connection.execute('DROP TABLE "user"')
            connection.execute('ALTER TABLE user_new RENAME TO "user"')
            connection.execute(
                'CREATE INDEX IF NOT EXISTS ix_user_tenant_id ON "user" (tenant_id)'
            )
            connection.execute("PRAGMA foreign_keys=ON")
        else:
            connection.execute(
                "UPDATE user SET role='tenant_admin' WHERE role='admin'"
            )
        connection.executescript(AUDIT_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def verify(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        audit = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_audit_event'"
        ).fetchone()
        user_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='user'"
        ).fetchone()
        if not audit or not user_sql or "uq_user_tenant_username" not in (user_sql[0] or ""):
            raise RuntimeError("商家员工角色数据库结构验证失败")
        legacy = connection.execute(
            "SELECT COUNT(*) FROM user WHERE role='admin'"
        ).fetchone()[0]
        if legacy:
            raise RuntimeError("仍存在未迁移的admin角色")
        tenants_without_admin = connection.execute('''
            SELECT tenant.id
            FROM tenant
            LEFT JOIN user
              ON user.tenant_id = tenant.id
             AND user.role = 'tenant_admin'
             AND user.is_active = 1
            GROUP BY tenant.id
            HAVING COUNT(user.id) = 0
            ORDER BY tenant.id
        ''').fetchall()
        if tenants_without_admin:
            tenant_ids = ", ".join(str(row[0]) for row in tenants_without_admin)
            raise RuntimeError(
                f"以下租户缺少启用的tenant_admin账号: {tenant_ids}"
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
    print("商家员工角色与审计数据库结构验证通过。")


if __name__ == "__main__":
    main()
