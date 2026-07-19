import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_knowledge_lifecycle import migrate, verify


class KnowledgeLifecycleMigrationTests(unittest.TestCase):
    def test_knowledge_tables_are_created_idempotently(self):
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "legacy.db"
            connection = sqlite3.connect(database_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE tenant (id INTEGER PRIMARY KEY);
                    CREATE TABLE "user" (id INTEGER PRIMARY KEY);
                    """
                )
                connection.commit()
            finally:
                connection.close()

            migrate(database_path)
            migrate(database_path)
            verify(database_path)

            connection = sqlite3.connect(database_path)
            try:
                revision_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(knowledge_revision)"
                    )
                }
                self.assertIn("quality_report", revision_columns)
                self.assertIn("review_status", revision_columns)
                index_names = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA index_list(knowledge_document)"
                    )
                }
                self.assertIn(
                    "ix_knowledge_document_tenant_updated",
                    index_names,
                )
                build_columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(knowledge_index_build)"
                    )
                }
                self.assertIn("revision_snapshot", build_columns)
                self.assertIn("previous_active_build_id", build_columns)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
