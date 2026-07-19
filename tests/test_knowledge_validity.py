import unittest
from datetime import datetime, timedelta

from app.services.knowledge_validity import lifecycle_status


class KnowledgeValidityTests(unittest.TestCase):
    def test_lifecycle_status_boundaries(self):
        now = datetime(2026, 7, 19, 12, 0, 0)
        self.assertEqual(
            lifecycle_status(
                effective_at=now + timedelta(minutes=1),
                expires_at=None,
                now=now,
            ),
            "scheduled",
        )
        self.assertEqual(
            lifecycle_status(
                effective_at=None,
                expires_at=now,
                now=now,
            ),
            "expired",
        )
        self.assertEqual(
            lifecycle_status(
                effective_at=None,
                expires_at=now + timedelta(days=7),
                now=now,
            ),
            "expiring_soon",
        )
        self.assertEqual(
            lifecycle_status(
                effective_at=None,
                expires_at=now + timedelta(days=8),
                now=now,
            ),
            "active",
        )


if __name__ == "__main__":
    unittest.main()
