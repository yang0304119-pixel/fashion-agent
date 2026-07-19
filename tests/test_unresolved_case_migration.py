import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_unresolved_case_review import migrate, verify


class UnresolvedCaseMigrationTests(unittest.TestCase):
    def test_legacy_case_table_gains_review_fields_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE unresolved_case (
                    id INTEGER PRIMARY KEY,
                    user_message TEXT NOT NULL,
                    created_at DATETIME
                );
                INSERT INTO unresolved_case (id, user_message, created_at)
                VALUES (1, '原问题', '2026-07-18 10:00:00');
                """
            )
            connection.commit()
            connection.close()

            migrate(database_path)
            migrate(database_path)
            verify(database_path)

            connection = sqlite3.connect(database_path)
            row = connection.execute(
                "SELECT user_message, reviewed_by, reviewed_at, updated_at "
                "FROM unresolved_case WHERE id = 1"
            ).fetchone()
            connection.close()

            self.assertEqual(row[:3], ("原问题", None, None))
            self.assertEqual(row[3], "2026-07-18 10:00:00")


if __name__ == "__main__":
    unittest.main()
