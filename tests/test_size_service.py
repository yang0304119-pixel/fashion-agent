import unittest

from app.services.size_service import (
    InvalidSizeInputError,
    SizeNotFoundError,
    SizeService,
)
from app.tools.size_tool import size_recommend


class SizeServiceTests(unittest.TestCase):
    def test_standard_and_loose_recommendations(self):
        service = SizeService()
        standard = service.recommend(
            height=175,
            weight=70,
            style="标准",
        )
        loose = service.recommend(
            height=175,
            weight=70,
            style="宽松",
        )
        self.assertEqual(standard.base_size, "L")
        self.assertEqual(standard.size, "L")
        self.assertEqual(loose.size, "XL")

    def test_invalid_input_and_unmatched_size(self):
        service = SizeService()
        with self.assertRaises(InvalidSizeInputError):
            service.recommend(height=90, weight=70)
        with self.assertRaises(SizeNotFoundError):
            service.recommend(height=150, weight=35)

    def test_tool_is_only_an_adapter(self):
        result = size_recommend(175, 70, "标准")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["size"], "L")


if __name__ == "__main__":
    unittest.main()
