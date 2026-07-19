import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.migrate_agent_trace_steps import migrate, verify


class AgentTraceMigrationTests(unittest.TestCase):
    def test_legacy_trace_table_gains_summary_and_step_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "legacy.db"
            connection = sqlite3.connect(database_path)
            connection.executescript(
                """
                CREATE TABLE agent_trace (
                    id INTEGER PRIMARY KEY,
                    tool_name VARCHAR(50),
                    tool_status VARCHAR(20)
                );
                INSERT INTO agent_trace (id, tool_name, tool_status)
                VALUES (1, 'order_workflow', 'success');
                """
            )
            connection.commit()
            connection.close()

            migrate(database_path)
            migrate(database_path)
            verify(database_path)

            connection = sqlite3.connect(database_path)
            row = connection.execute(
                "SELECT workflow_name, status FROM agent_trace WHERE id = 1"
            ).fetchone()
            step_table = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='agent_trace_step'"
            ).fetchone()
            connection.close()

            self.assertEqual(row, ("order_workflow", "succeeded"))
            self.assertIsNotNone(step_table)


if __name__ == "__main__":
    unittest.main()
