import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_conversation_state import migrate, verify


class ConversationStateMigrationTests(unittest.TestCase):
    def test_conversation_state_schema_and_owner_unique_constraint(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "conversation.db"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE tenant (id INTEGER PRIMARY KEY);
                CREATE TABLE "user" (id INTEGER PRIMARY KEY);
                INSERT INTO tenant (id) VALUES (1);
                INSERT INTO "user" (id) VALUES (1);
                """
            )
            connection.close()

            migrate(database)
            verify(database)

            connection = sqlite3.connect(database)
            try:
                values = (
                    1,
                    1,
                    "session-1",
                    "order_query",
                    '["order_id"]',
                    "{}",
                    "2026-07-18 10:00:00",
                    "2026-07-18 10:30:00",
                )
                connection.execute(
                    "INSERT INTO conversation_state "
                    "(tenant_id, user_id, session_id, pending_intent, "
                    "missing_slots, collected_slots, updated_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
                with self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(
                        "INSERT INTO conversation_state "
                        "(tenant_id, user_id, session_id, pending_intent, "
                        "missing_slots, collected_slots, updated_at, expires_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        values,
                    )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
