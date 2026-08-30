"""
测试 Phase 1 记忆层：markdown_store / tags / surprise / gap / wiki。
纯逻辑：在临时工作区库上建表、插几条碎片，验证各模块行为。不污染真实数据库。
"""
import os
import uuid
import unittest

import config as cfg


class _MemTempMixin:
    def setUp(self):
        self._orig = cfg.USER_CONFIG_DIR
        self._orig_path = cfg.USER_CONFIG_PATH
        self._orig_user_config = cfg._USER_CONFIG
        self._tmp = os.path.join(cfg.ROOT_DIR, "_test_tmp_" + uuid.uuid4().hex[:8])
        os.makedirs(self._tmp, exist_ok=True)
        cfg.USER_CONFIG_DIR = self._tmp
        cfg.USER_CONFIG_PATH = os.path.join(self._tmp, "user_config.json")
        cfg._USER_CONFIG = {}
        # 在临时库上建表（memory_vault 在 import + _init 时执行）
        from brain import memory_vault
        memory_vault._init()

    def tearDown(self):
        cfg.USER_CONFIG_DIR = self._orig
        cfg.USER_CONFIG_PATH = self._orig_path
        cfg._USER_CONFIG = self._orig_user_config
        try:
            import shutil
            shutil.rmtree(self._tmp, ignore_errors=True)
        except Exception:
            pass


class MemoryPhase1Test(_MemTempMixin, unittest.TestCase):
    def test_store_fragments(self):
        from brain import memory_vault
        fid1 = memory_vault.store_fragment("契约者", "契约者喜欢吃辣，尤其是四川火锅", "喜好/喜欢", emotional_weight=0.7)
        fid2 = memory_vault.store_fragment("契约者", "下周五有个重要面试，记得提醒", "重要的事/承诺", emotional_weight=0.8)
        self.assertGreater(fid1, 0)
        self.assertGreater(fid2, 0)

    def test_surprise(self):
        from brain import memory_vault
        from brain.memory import surprise
        # 建一些"既有记忆"作为上下文
        for i in range(5):
            memory_vault.store_fragment("契约者", f"今天天气不错，去公园散步第{i}次", "日常/生活")
        # 一条"意外"的碎片
        fid = memory_vault.store_fragment("契约者", "契约者宣布要辞职去创业做宠物咖啡店", "重要的事/目标", emotional_weight=0.4)
        sc = surprise.surprise_score("契约者宣布要辞职去创业做宠物咖啡店", [])
        self.assertGreaterEqual(sc, 0.0)
        sc2 = surprise.surprise_score("今天天气不错，去公园散步", ["今天天气不错，去公园散步"])
        self.assertLess(sc2, sc + 0.0001)  # 与语境越像，surprise 越低
        # 打开开关后 boost 不应报错
        surprise.boost(fid)

    def test_gap(self):
        from brain import memory_vault
        from brain.memory import gap
        # 空白主题 → 提示无碎片
        notes = gap.analyze("量子力学")
        self.assertTrue(any("没有可回顾" in n for n in notes))
        # 有记录的 → 不应提示"没记过"
        memory_vault.store_fragment("契约者", "契约者下周要做手术，很紧张", "重要的事")
        notes2 = gap.format_for_prompt("下周手术")
        self.assertNotIn("没有可回顾", notes2)

    def test_markdown_snapshot(self):
        from brain import memory_vault
        from brain.memory import markdown_store
        memory_vault.store_fragment("契约者", "契约者喜欢猫，家里养了两只布偶", "喜好/喜欢", emotional_weight=0.7)
        snap = markdown_store.snapshot()
        self.assertGreaterEqual(snap["fragments"], 1)
        root = markdown_store.markdown_root()
        self.assertTrue(os.path.exists(os.path.join(root, "INDEX.md")))
        # git 提交不应抛异常（返回 dict）
        git = markdown_store.git_commit("test")
        self.assertIsInstance(git, dict)

    def test_wiki(self):
        from brain import memory_vault
        from brain.memory import wiki
        memory_vault.store_fragment("契约者", "契约者喜欢猫，家里养了两只布偶", "喜好/喜欢", emotional_weight=0.7)
        res = wiki.build()
        self.assertGreaterEqual(res["pages"], 1)
        self.assertTrue(wiki.topic_search("布偶"))  # 命中的文件列表非空
        self.assertIsInstance(wiki.index(), list)


if __name__ == "__main__":
    unittest.main()
