import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.core.passwords import verify_password
from scripts.migrate_auth import migrate, verify_database


class AuthMigrationTests(unittest.TestCase):
    def test_legacy_database_is_migrated_without_losing_user(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE tenant (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL
                );
                CREATE TABLE agent_trace (id INTEGER PRIMARY KEY);
                CREATE TABLE unresolved_case (id INTEGER PRIMARY KEY);
                INSERT INTO tenant (id, name) VALUES (1, '测试租户');
                INSERT INTO user (id, username) VALUES (1, '张三');
                """
            )
            connection.commit()
            connection.close()

            migrate(
                database_path,
                tenant_id=1,
                customer_password="CustomerPassword123!",
                admin_username="admin",
                admin_password="AdminPassword123!",
            )
            verify_database(database_path)

            connection = sqlite3.connect(database_path)
            users = connection.execute(
                'SELECT username, tenant_id, password_hash, role FROM "user" '
                "ORDER BY username"
            ).fetchall()
            connection.close()

            self.assertEqual([user[0] for user in users], ["admin", "张三"])
            admin = users[0]
            customer = users[1]
            self.assertEqual(admin[1:], (1, admin[2], "tenant_admin"))
            self.assertEqual(customer[1:], (1, customer[2], "customer"))
            self.assertTrue(verify_password("AdminPassword123!", admin[2]))
            self.assertTrue(
                verify_password("CustomerPassword123!", customer[2])
            )


if __name__ == "__main__":
    unittest.main()
