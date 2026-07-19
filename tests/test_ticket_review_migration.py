import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_ticket_review import migrate, verify


class TicketReviewMigrationTests(unittest.TestCase):
    def test_legacy_ticket_table_gains_review_fields_without_data_loss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE ticket (
                    id INTEGER PRIMARY KEY,
                    status VARCHAR(20) NOT NULL
                );
                INSERT INTO ticket (id, status) VALUES (1, 'pending');
                """
            )
            connection.commit()
            connection.close()

            migrate(database_path)
            migrate(database_path)
            verify(database_path)

            connection = sqlite3.connect(database_path)
            row = connection.execute(
                "SELECT id, status, reviewed_by, reviewed_at, review_reason "
                "FROM ticket WHERE id = 1"
            ).fetchone()
            index = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' "
                "AND name='ix_ticket_reviewed_by'"
            ).fetchone()
            connection.close()

            self.assertEqual(row, (1, "pending", None, None, None))
            self.assertIsNotNone(index)


if __name__ == "__main__":
    unittest.main()
