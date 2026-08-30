"""
RikkaAI - 后台"做梦"引擎（Phase 2）

独立于 UI/对话线程的蒸馏循环：六花安静时，在后台把散乱的记忆合并、消解矛盾、
更新实体画像、给重要碎片做 surprise 加权、重建 Markdown 库与知识 wiki、生成叙事日记。
这正是 gbrain dream cycle / CowAgent Deep Dream / genesis DreamCycle 的共同精髓
——"越用越懂你"。

gate: features.is_enabled("dream_enabled") + dream_consolidate_enabled
"""
import threading
import time
from datetime import datetime

from brain import features
import config as cfg


def run_dream_cycle() -> dict:
    """执行一轮做梦（先只做最安全、同步回收的部分）。返回各子任务结果。"""
    res = {"ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "steps": {}}
    if not features.is_enabled("dream_enabled"):
        res["skipped"] = "dream_disabled"
        return res

    # 1) 记忆整合 + 归档（复用既有 archivist/memory_vault）
    if features.is_enabled("dream_consolidate_enabled"):
        try:
            from brain import memory_vault, archivist
            m1 = memory_vault.consolidate_fragments()
            m2 = archivist.light_tick()
            res["steps"]["consolidate"] = {"fragments": m1, "archivist": m2}
        except Exception as e:
            res["steps"]["consolidate"] = {"error": str(e)[:120]}

    # 2) 给近期高情感碎片做 surprise 加权
    if features.is_enabled("memory_surprise_weight_enabled"):
        try:
            from brain.memory import surprise
            c = __import__("brain.memory", fromlist=["conn"]).conn()
            try:
                ids = [r["id"] for r in c.execute(
                    "SELECT id FROM mf_fragments WHERE status='active' AND emotional_weight<0.9 "
                    "ORDER BY created_at DESC LIMIT 40").fetchall()]
            finally:
                c.close()
            boosted = surprise.score_many(ids)
            res["steps"]["surprise"] = {"boosted": len(boosted)}
        except Exception as e:
            res["steps"]["surprise"] = {"error": str(e)[:120]}

    # 3) 重建 Markdown 真源 + git
    if features.is_enabled("memory_markdown_enabled"):
        try:
            from brain.memory import markdown_store
            s = markdown_store.snapshot()
            g = markdown_store.git_commit("dream")
            res["steps"]["markdown"] = {**s, "git": g}
        except Exception as e:
            res["steps"]["markdown"] = {"error": str(e)[:120]}

    # 4) 重建知识 wiki
    if features.is_enabled("memory_wiki_enabled"):
        try:
            from brain.memory import wiki
            res["steps"]["wiki"] = wiki.build()
        except Exception as e:
            res["steps"]["wiki"] = {"error": str(e)[:120]}

    return res


class DreamEngine:
    """后台做梦循环：daemon 线程按间隔运行 run_dream_cycle。"""

    def __init__(self, interval_hours: float = None):
        self._interval_h = float(interval_hours or features.flag("dream_interval_hours", 6) or 6)
        self._thread = None
        self._stop = threading.Event()

    @property
    def interval_seconds(self) -> int:
        return max(60, int(self._interval_h * 3600))

    def _loop(self):
        # 先睡一小段再跑，避免与启动期其它任务抢资源
        if self._stop.wait(30):
            return
        run_dream_cycle()
        while not self._stop.wait(self.interval_seconds):
            run_dream_cycle()

    def start(self):
        if not features.is_enabled("dream_enabled"):
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="rikka-dream")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
