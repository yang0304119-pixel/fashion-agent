import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_staff_roles import migrate, verify


class StaffRoleMigrationTests(unittest.TestCase):
    def test_migrates_legacy_admin_and_allows_tenant_local_usernames(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "staff.db"
            connection = sqlite3.connect(path)
            connection.executescript('''
                CREATE TABLE tenant (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    industry TEXT NOT NULL
                );
                CREATE TABLE user (
                    id INTEGER PRIMARY KEY,
                    tenant_id INTEGER NOT NULL,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    role VARCHAR(20) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO tenant VALUES (1, '租户一', '服装');
                INSERT INTO tenant VALUES (2, '租户二', '服装');
                INSERT INTO user VALUES (1, 1, 'admin', 'x', 'admin', 1, CURRENT_TIMESTAMP);
            ''')
            connection.commit()
            connection.close()

            migrate(path)
            migrate(path)

            connection = sqlite3.connect(path)
            self.assertEqual(
                connection.execute("SELECT role FROM user WHERE id=1").fetchone()[0],
                "tenant_admin",
            )
            with self.assertRaises(RuntimeError):
                verify(path)
            connection.execute(
                "INSERT INTO user (id,tenant_id,username,password_hash,role,is_active) VALUES (2,2,'admin','x','tenant_admin',1)"
            )
            connection.commit()
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM admin_audit_event").fetchone()[0], 0)
            connection.close()
            verify(path)


if __name__ == "__main__":
    unittest.main()
