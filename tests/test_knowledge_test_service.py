import unittest

from app.rag.security import safe_relative_source


class KnowledgeTestSourceSafetyTests(unittest.TestCase):
    def test_absolute_and_parent_paths_are_removed(self):
        for source in (
            r"C:\\tenant\\processed\\rule.md",
            "/srv/fashionagent/rule.md",
            "../../tenant/rule.md",
            "documents/1/../../secret.md",
        ):
            with self.subTest(source=source):
                self.assertEqual(safe_relative_source(source), "")

    def test_safe_relative_source_is_normalized(self):
        self.assertEqual(
            safe_relative_source(r"documents\\1\\revisions\\2"),
            "documents/1/revisions/2",
        )


if __name__ == "__main__":
    unittest.main()
