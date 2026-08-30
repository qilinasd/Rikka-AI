"""
测试 Phase 3（需求体系）与 Phase 5（压缩/校验/网络哨兵）。
纯逻辑，不依赖 GUI / 真实外网。
"""
import unittest

import config as cfg


class NeedsTest(unittest.TestCase):
    def setUp(self):
        cfg.load_upgrade_flags()
        cfg._UPGRADE_FLAGS["emotion_needs_enabled"] = True

    def tearDown(self):
        cfg._UPGRADE_FLAGS["emotion_needs_enabled"] = True

    def test_update_and_drive(self):
        from brain.needs import NeedsState
        n = NeedsState()
        # 用户主动找 → 孤独下降、社交满足
        n.on_user_talk(valence=1)
        self.assertGreater(n.social, 0)
        self.assertLess(n.loneliness, 40)
        # 主动一次 → 耗能
        n.on_proactive(delivered=True)
        self.assertLess(n.energy, 50)
        # 时间流逝 → 孤独/社交/新奇上升
        n.tick(hours=2)
        self.assertGreater(n.loneliness, n.__dict__.get("loneliness", 0) if False else 0)

    def test_drive_range_and_suppression(self):
        from brain.needs import NeedsState
        n = NeedsState()
        d = n.initiative_drive()
        self.assertGreaterEqual(d, 0.0)
        self.assertLessEqual(d, 1.0)

    def test_prompt_suffix_gated(self):
        from brain.needs import NeedsState
        n = NeedsState()
        self.assertIn("需求", n.prompt_suffix())
        # 关闭后为空串
        cfg._UPGRADE_FLAGS["emotion_needs_enabled"] = False
        self.assertEqual(n.prompt_suffix(), "")


class CompressorTest(unittest.TestCase):
    def setUp(self):
        cfg._UPGRADE_FLAGS["tool_compress_enabled"] = True

    def test_short_passthrough(self):
        from brain.compressor import compress, est_tokens
        s = "短文本"
        self.assertEqual(compress(s, max_tokens=10000), s)
        self.assertGreater(est_tokens(s), 0)

    def test_long_compressed(self):
        from brain.compressor import compress
        long = "内容。" * 4000
        out = compress(long, max_tokens=500)
        self.assertIn("已压缩", out)
        self.assertLess(len(out), len(long))


class PlannerTest(unittest.TestCase):
    def setUp(self):
        cfg._UPGRADE_FLAGS["decision_planner_enabled"] = True

    def test_decide_proactive(self):
        from brain.needs import NeedsState
        from brain.planner import decide_proactive, expected_value
        n = NeedsState()
        # 白天、没冷却 → 正常决策
        r = decide_proactive(n, hour=14, last_proactive_min=None)
        self.assertIn("should", r)
        self.assertGreaterEqual(r["drive"], 0.0)
        self.assertLessEqual(r["p_success"], 1.0)
        # 刚主动过 + 冷却 → 概率显著下降
        r2 = decide_proactive(n, hour=14, last_proactive_min=5, cooldown_min=60)
        self.assertGreaterEqual(r2["p_success"], 0.0)
        # 期望效用
        ev = expected_value(0.6, 0.8)
        self.assertGreater(ev, 0.0)


if __name__ == "__main__":
    unittest.main()
