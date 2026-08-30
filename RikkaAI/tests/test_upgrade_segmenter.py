"""
测试 Phase: segmenter（分段发送/莲心式连发）。纯逻辑。
"""
import unittest

import config as cfg


class SegmenterTest(unittest.TestCase):
    def setUp(self):
        cfg.load_upgrade_flags()
        cfg._UPGRADE_FLAGS["split_reply_enabled"] = True

    def test_short_no_split(self):
        from brain.segmenter import split_reply
        self.assertEqual(split_reply("我在呢。"), ["我在呢。"])
        self.assertEqual(split_reply(""), [])

    def test_split_by_sentence(self):
        from brain.segmenter import split_reply
        out = split_reply("你好呀。今天天气不错哦。我们出去走走吧。")
        self.assertGreaterEqual(len(out), 3)
        self.assertTrue(all(s.strip() for s in out))

    def test_cap_max_segs(self):
        from brain.segmenter import split_reply
        many = "。".join([f"这是第{i}句" for i in range(12)]) + "。"
        out = split_reply(many, max_segs=5)
        self.assertLessEqual(len(out), 5)

    def test_delivery_plan_gaps(self):
        from brain.segmenter import delivery_plan
        plan = delivery_plan("你好啊。今天好吗。一起吃饭吧。")
        self.assertIsInstance(plan, list)
        self.assertGreaterEqual(len(plan), 2)
        for item in plan:
            self.assertGreaterEqual(item["gap_sec"], 1.0)
            self.assertLessEqual(item["gap_sec"], 3.0)

    def test_is_enabled(self):
        from brain import segmenter
        self.assertTrue(segmenter.is_enabled())
        cfg._UPGRADE_FLAGS["split_reply_enabled"] = False
        self.assertFalse(segmenter.is_enabled())


if __name__ == "__main__":
    unittest.main()
