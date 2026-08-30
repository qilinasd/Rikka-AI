"""情感/需求字段锁定：锁定的数值不被日常互动自动更新，且持久化。"""
import os
import sys
import unittest
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config as cfg


class _SandboxMixin:
    def setUp(self):
        self._orig_dir = cfg.USER_CONFIG_DIR
        self._orig_path = cfg.USER_CONFIG_PATH
        self._orig_user_config = cfg._USER_CONFIG
        self._tmp = os.path.join(cfg.ROOT_DIR, "_test_tmp_" + uuid.uuid4().hex[:8])
        os.makedirs(self._tmp, exist_ok=True)
        cfg.USER_CONFIG_DIR = self._tmp
        cfg.USER_CONFIG_PATH = os.path.join(self._tmp, "user_config.json")
        cfg._USER_CONFIG = {}

    def tearDown(self):
        cfg.USER_CONFIG_DIR = self._orig_dir
        cfg.USER_CONFIG_PATH = self._orig_path
        cfg._USER_CONFIG = self._orig_user_config
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


class EmotionLockTests(unittest.TestCase):
    def test_locked_mood_stays(self):
        from brain.emotion import EmotionState
        e = EmotionState()
        e.locked = {"mood"}
        e.analyze("太好了哈哈真棒")  # score>=2 本应变开心
        self.assertEqual(e.mood, "neutral")  # 锁定 → 不变

    def test_locked_affection_and_energy(self):
        from brain.emotion import EmotionState
        e = EmotionState()
        e.locked = {"affection", "emotion_energy"}
        e.analyze("太好了哈哈真棒")
        self.assertEqual(e.affection, 30)
        self.assertEqual(e.energy, 50)
        self.assertEqual(e.mood, "happy")  # 未锁定的 mood 正常变化

    def test_unlocked_still_updates(self):
        from brain.emotion import EmotionState
        e = EmotionState()
        e.analyze("太好了哈哈真棒")
        self.assertEqual(e.mood, "happy")
        self.assertGreater(e.affection, 30)

    def test_needs_locked_fields_skip_updates(self):
        from brain.needs import NeedsState
        n = NeedsState()
        n.locked = {"social", "loneliness"}
        n.on_user_talk(1)
        self.assertEqual(n.social, 40)   # 锁定 → 不降
        self.assertEqual(n.loneliness, 30)
        self.assertEqual(n.rest, 78)     # 未锁定 → 正常变化
        n.tick(2)
        self.assertEqual(n.social, 40)   # tick 也不动锁定字段
        self.assertEqual(n.novelty, 40)  # 未锁定：36（user_talk+1）+ 4（tick 2h）

    def test_needs_unlocked_normal(self):
        from brain.needs import NeedsState
        n = NeedsState()
        n.on_user_talk(1)
        self.assertEqual(n.social, 34)
        self.assertEqual(n.loneliness, 16)


class EmotionLockPersistenceTests(_SandboxMixin, unittest.TestCase):
    def test_set_locks_persists_and_reloads(self):
        from brain.agent import AgentCore
        core = AgentCore()
        core.set_emotion_locks({"mood", "affection", "bogus-key"})
        self.assertEqual(core._emotion_locks, {"mood", "affection"})  # 非法键被过滤
        self.assertEqual(core.emotion.locked, {"mood", "affection"})

        raw = json_load(cfg.USER_CONFIG_PATH)
        self.assertEqual(raw.get("emotion_locks"), ["affection", "mood"])

        # 新实例从配置恢复锁
        core2 = AgentCore()
        self.assertEqual(core2._emotion_locks, {"mood", "affection"})
        self.assertEqual(core2.emotion.locked, {"mood", "affection"})

    def test_locks_apply_to_lazy_needs(self):
        from brain.agent import AgentCore
        core = AgentCore()
        core.set_emotion_locks({"social", "rest"})
        snap = core.get_emotion_snapshot()  # 触发 _needs 懒建
        self.assertEqual(core._needs.locked, {"social", "rest"})
        core.apply_emotion_values({"social": 90})  # 设置弹窗手动改 → 锁不拦截手动值
        self.assertEqual(core._needs.social, 90)
        core.emotion.analyze("哈哈") or core._needs.on_user_talk(1)
        core._needs.on_user_talk(1)
        self.assertEqual(core._needs.social, 90)  # 锁定 → 互动不再改动
        self.assertTrue(snap)


def json_load(path):
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    unittest.main()
