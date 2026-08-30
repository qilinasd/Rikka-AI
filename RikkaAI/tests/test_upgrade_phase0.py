"""
测试 Phase 0 底座：features 开关 + costlog 成本核算 + config 升级开关框架。
纯逻辑测试，不依赖 GUI / 网络。
"""
import os
import uuid
import unittest

import config as cfg


class _TempDirMixin:
    # 工作区下建临时目录（Windows 沙箱对 AppData/temp 的写入有 ACL 限制，工作区可写）。
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
        try:
            if os.path.isdir(self._tmp):
                for root, dirs, files in os.walk(self._tmp, topdown=False):
                    for f in files:
                        os.remove(os.path.join(root, f))
                    for d in dirs:
                        os.rmdir(os.path.join(root, d))
                os.rmdir(self._tmp)
        except Exception:
            pass


class ConfigFlagsTest(unittest.TestCase):
    def test_defaults_exist_and_are_loadable(self):
        cfg.load_upgrade_flags()
        allf = cfg.get_all_upgrade_flags()
        self.assertIn("costlog_enabled", allf)
        self.assertIn("dream_enabled", allf)
        self.assertIn("mcp_enabled", allf)
        # 大部分默认开启（这些是我们打算默认启用的升级）
        self.assertTrue(cfg.get_upgrade_flag("costlog_enabled", True))

    def test_unknown_flag_defaults_to_false(self):
        self.assertIs(cfg.get_upgrade_flag("totally_unknown_xyz", False), False)

    def test_save_and_reload_override(self):
        cfg.load_upgrade_flags()
        # 临时改一个开关并持久化
        import brain.features as feats
        ok = feats.set_flags({"mcp_enabled": False})
        self.assertTrue(ok)
        self.assertFalse(feats.is_enabled("mcp_enabled"))
        # 恢复
        feats.set_flags({"mcp_enabled": True})


class CostlogTest(_TempDirMixin, unittest.TestCase):
    def test_record_and_aggregate(self):
        from brain import costlog
        costlog.reset()
        costlog.record_llm("deepseek-v4-flash", prompt_tokens=1000, completion_tokens=500, ms=20)
        costlog.record_tool("web_search", "success", ms=300)
        t = costlog.get_totals()
        self.assertEqual(t["llm_calls"], 1)
        self.assertEqual(t["tool_calls"], 1)
        self.assertEqual(t["total_tokens"], 1500)
        self.assertEqual(t["cost_usd"], 0.0)  # 单价表已移除：未提供真实账单时记 0
        # 按模型聚合
        self.assertIn("deepseek-v4-flash", t["by_model"])
        self.assertIn("web_search", t["by_tool"])

    def test_disabled_writes_nothing(self):
        from brain import costlog
        costlog.reset()
        old = bool(cfg.get_upgrade_flag("costlog_enabled", True))
        try:
            cfg._UPGRADE_FLAGS["costlog_enabled"] = False
            costlog.record_llm("deepseek-v4-flash", 10, 10)
            costlog.record_tool("x", "success")
            t = costlog.get_totals()
            self.assertEqual(t["calls"], 0)
        finally:
            cfg._UPGRADE_FLAGS["costlog_enabled"] = old


if __name__ == "__main__":
    unittest.main()
