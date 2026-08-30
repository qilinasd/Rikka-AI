"""
测试 Phase 2（dream / scheduler / autofetch）与 Phase 4（mcp_client）。
纯逻辑 + 临时工作区库。
"""
import os
import uuid
import unittest

import config as cfg
from brain import features


class _TempMixin:
    def setUp(self):
        self._orig_dir = cfg.USER_CONFIG_DIR
        self._orig_path = cfg.USER_CONFIG_PATH
        self._orig_user_config = cfg._USER_CONFIG
        self._tmp = os.path.join(cfg.ROOT_DIR, "_test_tmp_" + uuid.uuid4().hex[:8])
        os.makedirs(self._tmp, exist_ok=True)
        cfg.USER_CONFIG_DIR = self._tmp
        # 沙箱必须同时重定向 USER_CONFIG_PATH（save_user_config 写的是它）：
        # 否则 set_route 等测试会把假方案追加进真实 user_config.json
        cfg.USER_CONFIG_PATH = os.path.join(self._tmp, "user_config.json")
        cfg._USER_CONFIG = {}
        from brain import memory_vault
        memory_vault._init()
        cfg.load_upgrade_flags()
        cfg._UPGRADE_FLAGS.update({
            "dream_enabled": True, "cron_enabled": True, "autofetch_enabled": True,
            "mcp_enabled": True,
            "memory_markdown_enabled": True, "memory_wiki_enabled": True,
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


class SchedulerTest(_TempMixin, unittest.TestCase):
    def test_parse_schedule(self):
        from brain import scheduler
        daily = scheduler.parse_schedule("每天 23:00 生成日报")
        self.assertEqual(daily["kind"], "daily")
        self.assertEqual(daily["at"], "23:00")
        weekly = scheduler.parse_schedule("每周日 21 点写周记")
        self.assertEqual(weekly["kind"], "weekly")
        self.assertEqual(weekly["weekday"], 6)

    def test_add_and_tick(self):
        from brain import scheduler
        r = scheduler.add_job("每天 23:00 生成日报", "diary")
        self.assertTrue(r["ok"])
        self.assertEqual(len(scheduler.list_jobs()), 1)
        # 把 next_run 设到过去，模拟到点
        jobs = scheduler.list_jobs()
        jobs[0]["next_run"] = "2000-01-01 00:00:00"
        fired = []
        scheduler._save(jobs)
        n = scheduler.tick(lambda j: fired.append(j["action"]))
        self.assertEqual(n, 1)
        self.assertEqual(fired, ["diary"])


class DreamTest(_TempMixin, unittest.TestCase):
    def test_engine_start_stop(self):
        from brain import dream
        eng = dream.DreamEngine(interval_hours=24)
        self.assertTrue(eng.start())
        eng.stop()
        # 关闭 dream 后 start 返回 False
        cfg._UPGRADE_FLAGS["dream_enabled"] = False
        self.assertFalse(dream.DreamEngine().start())

    def test_run_cycle(self):
        from brain import dream
        from brain import memory_vault
        memory_vault.store_fragment("契约者", "契约者喜欢猫，养了两只布偶", "喜好/喜欢", emotional_weight=0.7)
        res = dream.run_dream_cycle()
        self.assertIsInstance(res, dict)
        self.assertIn("steps", res)


class AutofetchTest(_TempMixin, unittest.TestCase):
    def test_run_and_dedup(self):
        from brain import autofetch
        inbox = autofetch._inbox()
        with open(os.path.join(inbox, "note.md"), "w", encoding="utf-8") as f:
            f.write("契约者下周要去上海出差三天。\n\n记得带护照和电脑。")
        r1 = autofetch.run_autofetch()
        self.assertGreaterEqual(r1["added"], 1)
        # 再次运行（文件未变）→ 去重，added 0
        r2 = autofetch.run_autofetch()
        self.assertEqual(r2["added"], 0)


class McpClientTest(_TempMixin, unittest.TestCase):
    def test_to_openai(self):
        from brain import mcp_client
        tools = [{"name": "weather", "description": "查天气",
                  "inputSchema": {"type": "object", "properties": {"city": {"type": "string"}}}}]
        out = mcp_client.to_openai_schemas(tools)
        self.assertEqual(out[0]["function"]["name"], "mcp_weather")

    def test_call_failure_graceful(self):
        from brain import mcp_client
        client = mcp_client.McpClient("x", "http://127.0.0.1:9/nope", timeout=1.0)
        # 无法连接的服务器 → 不应崩溃，返回 failure 结构
        self.assertTrue(client.initialize() is False)
        res = client.call_tool("t", {})
        self.assertEqual(res.get("status"), "failure")


if __name__ == "__main__":
    unittest.main()
