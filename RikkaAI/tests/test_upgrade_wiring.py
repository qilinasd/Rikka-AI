"""
测试接线：background（后台服务聚合）、mcp 缓存、agent tool_definitions / 压缩。
纯逻辑 + 临时工作区库。
"""
import os
import uuid
import unittest

import config as cfg


class _TempMixin:
    def setUp(self):
        self._orig_dir = cfg.USER_CONFIG_DIR
        self._orig_path = cfg.USER_CONFIG_PATH
        self._orig_user_config = cfg._USER_CONFIG
        self._tmp = os.path.join(cfg.ROOT_DIR, "_test_tmp_" + uuid.uuid4().hex[:8])
        os.makedirs(self._tmp, exist_ok=True)
        cfg.USER_CONFIG_DIR = self._tmp
        # 沙箱同时重定向 USER_CONFIG_PATH / _USER_CONFIG，防止测试写入真实配置
        cfg.USER_CONFIG_PATH = os.path.join(self._tmp, "user_config.json")
        cfg._USER_CONFIG = {}
        from brain import memory_vault
        memory_vault._init()
        cfg.load_upgrade_flags()
        cfg._UPGRADE_FLAGS.update({
            "dream_enabled": True, "cron_enabled": True, "autofetch_enabled": True,
            "mcp_enabled": True, "tool_compress_enabled": True,
        })

    def tearDown(self):
        cfg.USER_CONFIG_DIR = self._orig_dir
        cfg.USER_CONFIG_PATH = self._orig_path
        cfg._USER_CONFIG = self._orig_user_config
        try:
            import shutil
            shutil.rmtree(self._tmp, ignore_errors=True)
        except Exception:
            pass


class BackgroundTest(_TempMixin, unittest.TestCase):
    def test_start_stop_status(self):
        from brain import background
        started = background.start_background_services()
        self.assertIn("dream", started)
        self.assertIn("autofetch", started)
        self.assertIn("scheduler", started)
        st = background.status()
        self.assertIsInstance(st, dict)
        background.stop_background_services()
        # 停止后不应抛异常
        background.stop_background_services()

    def test_disabled_only(self):
        from brain import background
        cfg._UPGRADE_FLAGS["dream_enabled"] = False
        started = background.start_background_services()
        self.assertFalse(started.get("dream", True))
        background.stop_background_services()


class McpCacheTest(_TempMixin, unittest.TestCase):
    def test_cache_empty_when_no_servers(self):
        from brain import mcp_client
        tools = mcp_client.get_cached_openai_tools(max_tools=10, force=True)
        self.assertIsInstance(tools, list)

    def test_cache_handles_bad_server(self):
        from brain import mcp_client
        cfg._USER_CONFIG = cfg._USER_CONFIG or {}
        cfg._USER_CONFIG["mcp_servers"] = [{"name": "bad", "url": "http://127.0.0.1:9", "enabled": True}]
        tools = mcp_client.get_cached_openai_tools(max_tools=10, force=True)
        self.assertIsInstance(tools, list)  # 连不上也要优雅返回


class AgentToolTest(_TempMixin, unittest.TestCase):
    def test_tool_definitions_no_crash(self):
        from brain.agent import AgentCore
        core = AgentCore()
        defs = core.tool_definitions("")
        self.assertIsInstance(defs, list)
        self.assertTrue(any(d.get("function", {}).get("name") == "read_file" for d in defs))

    def test_compressor_in_agent_path(self):
        from brain import compressor
        long = "x" * 5000
        out = compressor.compress_for_prompt(long, max_tokens=100)
        self.assertLess(len(out), len(long))


if __name__ == "__main__":
    unittest.main()
