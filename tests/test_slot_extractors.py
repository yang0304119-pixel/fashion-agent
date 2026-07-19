import unittest

from app.agent.slot_extractors import (
    collect_slots,
    extract_product_id,
    extract_size_slots,
    missing_slots_for_intent,
)


class SlotExtractorTests(unittest.TestCase):
    def test_product_id_from_number_and_name(self):
        self.assertEqual(extract_product_id("查询商品编号 3 的库存"), 3)
        self.assertEqual(extract_product_id("羊毛围巾还有货吗"), 7)
        self.assertIsNone(extract_product_id("这件衣服还有货吗"))

    def test_size_slots_support_common_units(self):
        metric = extract_size_slots("175cm 70kg，喜欢宽松")
        chinese = extract_size_slots("身高1米75，体重140斤，喜欢修身")
        self.assertEqual(
            (metric.height, metric.weight, metric.style),
            (175, 70, "宽松"),
        )
        self.assertEqual(
            (chinese.height, chinese.weight, chinese.style),
            (175, 70, "修身"),
        )

    def test_bare_order_id_fills_pending_order_slot(self):
        slots = collect_slots("order_query", "10001", {})
        self.assertEqual(slots, {"order_id": 10001})
        self.assertEqual(missing_slots_for_intent("order_query", slots), [])

    def test_size_slots_merge_across_turns_and_keep_style(self):
        first = collect_slots(
            "size_recommend",
            "身高175cm，喜欢宽松",
            {},
        )
        second = collect_slots("size_recommend", "70kg", first)
        self.assertEqual(
            second,
            {"height": 175, "weight": 70, "style": "宽松"},
        )

    def test_refund_reason_survives_until_order_id_arrives(self):
        first = collect_slots("refund_request", "衣服破损，申请退款", {})
        second = collect_slots("refund_request", "10001", first)
        self.assertEqual(second["reason"], "质量问题")
        self.assertEqual(second["order_id"], 10001)


if __name__ == "__main__":
    unittest.main()
