"""为已有SQLite数据库创建确定性退款申请表。"""

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


REFUND_SCHEMA = """
CREATE TABLE IF NOT EXISTS refund_request (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    ticket_id INTEGER UNIQUE,
    reason TEXT NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    risk_level VARCHAR(20) NOT NULL,
    human_review BOOLEAN NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    gateway_mode VARCHAR(20) NOT NULL DEFAULT 'manual',
    provider_refund_id VARCHAR(100),
    failure_reason TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_refund_tenant_idempotency
        UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT uq_refund_tenant_order
        UNIQUE (tenant_id, order_id),
    CONSTRAINT ck_refund_risk_level
        CHECK (risk_level IN ('low', 'high')),
    CONSTRAINT ck_refund_status
        CHECK (status IN ('reviewing', 'approved', 'succeeded', 'rejected', 'failed')),
    FOREIGN KEY(tenant_id) REFERENCES tenant(id),
    FOREIGN KEY(order_id) REFERENCES "order"(id),
    FOREIGN KEY(user_id) REFERENCES "user"(id),
    FOREIGN KEY(ticket_id) REFERENCES ticket(id)
);
CREATE INDEX IF NOT EXISTS ix_refund_request_tenant_id
    ON refund_request (tenant_id);
CREATE INDEX IF NOT EXISTS ix_refund_request_order_id
    ON refund_request (order_id);
CREATE INDEX IF NOT EXISTS ix_refund_request_user_id
    ON refund_request (user_id);
CREATE INDEX IF NOT EXISTS ix_refund_order_status
    ON refund_request (tenant_id, order_id, status);
"""


def migrate(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(REFUND_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def verify(database_path: Path) -> None:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='refund_request'"
        ).fetchone()
        if row is None:
            raise RuntimeError("退款申请表不存在")

        expected = {
            "tenant_id",
            "order_id",
            "user_id",
            "ticket_id",
            "reason",
            "amount",
            "risk_level",
            "human_review",
            "status",
            "idempotency_key",
            "gateway_mode",
            "provider_refund_id",
            "failure_reason",
        }
        columns = {
            item[1]
            for item in connection.execute(
                "PRAGMA table_info(refund_request)"
            )
        }
        missing = expected - columns
        if missing:
            raise RuntimeError(f"退款申请表缺少字段: {sorted(missing)}")
        print("退款数据库结构验证通过。")
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


if __name__ == "__main__":
    main()
