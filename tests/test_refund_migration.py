import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_refund import migrate, verify


class RefundMigrationTests(unittest.TestCase):
    def test_refund_table_and_unique_order_constraint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE tenant (id INTEGER PRIMARY KEY);
                CREATE TABLE "user" (id INTEGER PRIMARY KEY);
                CREATE TABLE "order" (id INTEGER PRIMARY KEY);
                CREATE TABLE ticket (id INTEGER PRIMARY KEY);
                INSERT INTO tenant VALUES (1);
                INSERT INTO "user" VALUES (1);
                INSERT INTO "order" VALUES (10001);
                """
            )
            connection.commit()
            connection.close()

            migrate(database_path)
            verify(database_path)

            connection = sqlite3.connect(database_path)
            values = (
                1,
                10001,
                1,
                "质量问题",
                89.0,
                "low",
                0,
                "approved",
                "idem-1",
                "manual",
            )
            connection.execute(
                "INSERT INTO refund_request "
                "(tenant_id, order_id, user_id, reason, amount, risk_level, "
                "human_review, status, idempotency_key, gateway_mode) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO refund_request "
                    "(tenant_id, order_id, user_id, reason, amount, risk_level, "
                    "human_review, status, idempotency_key, gateway_mode) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values[:-2] + ("idem-2", "manual"),
                )
            connection.close()


if __name__ == "__main__":
    unittest.main()
