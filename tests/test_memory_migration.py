import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_memory_system import TABLES, migrate, verify


class MemoryMigrationTests(unittest.TestCase):
    def test_memory_schema_is_created_idempotently(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                'CREATE TABLE tenant (id INTEGER PRIMARY KEY);'
                'CREATE TABLE "user" (id INTEGER PRIMARY KEY);'
            )
            connection.close()
            migrate(path)
            migrate(path)
            verify(path)
            connection = sqlite3.connect(path)
            existing = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            connection.close()
            self.assertTrue(TABLES.issubset(existing))


if __name__ == "__main__":
    unittest.main()
