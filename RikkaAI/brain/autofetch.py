"""
RikkaAI - 个人数据自动拉取（Phase 2）

openhuman 的 auto-fetch 思路：六花定期把"你的生活数据"拉进记忆，做到
"它今天早上就知道你今天的安排"。这里提供一套**通用摄取管线**：
  - 本地摄入：扫描 memory_data/fetch_inbox/ 下的 .md/.txt，把内容抽取成记忆碎片
  - 可插拔连接器：预留 email/calendar/surveillance 的接口，未来接入具体账号
  - 去重（重复内容不重复入库）

gate: features.is_enabled("autofetch_enabled")
"""
import os
import re
import threading
from datetime import datetime

import config as cfg
from brain import features

_LOCK = threading.Lock()
_INBOX = "fetch_inbox"
_EXT = (".md", ".txt")
# 记录已摄取过的文件指纹，避免重复
_STATE = "_autofetch_state.json"


def _inbox():
    p = os.path.join(cfg.USER_CONFIG_DIR, _INBOX)
    os.makedirs(p, exist_ok=True)
    return p


def _state_path():
    return os.path.join(cfg.USER_CONFIG_DIR, _STATE)


def _load_state() -> set:
    try:
        import json
        with open(_state_path(), "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _save_state(state):
    try:
        import json
        with open(_state_path(), "w", encoding="utf-8") as f:
            json.dump(sorted(state), f, ensure_ascii=False)
    except Exception:
        pass


def _fingerprint(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ingest_file(path: str) -> int:
    """把一个本地文件抽取成记忆碎片。返回新增的碎片数。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return 0
        fp = _fingerprint(content)
        state = _load_state()
        if fp in state:
            return 0
        from brain import memory_vault
        # 切成合理大小的碎片；简单按段落/空行
        chunks = [c.strip() for c in re.split(r"\n\s*\n", content) if c.strip()]
        n = 0
        for ch in chunks[:20]:
            if len(ch) < 8:
                continue
            try:
                memory_vault.store_fragment(
                    entity=os.path.basename(path)[:50],
                    content=ch[:500],
                    category="系统/事件",
                    source="autofetch",
                )
                n += 1
            except Exception:
                pass
        state.add(fp)
        _save_state(state)
        return n
    except Exception:
        return 0


def run_autofetch() -> dict:
    """执行一轮自动拉取：扫描 inbox 目录导入。返回统计。"""
    if not features.is_enabled("autofetch_enabled"):
        return {"ok": False, "reason": "disabled"}
    inbox = _inbox()
    added = 0
    files = 0
    for name in os.listdir(inbox):
        p = os.path.join(inbox, name)
        if os.path.isfile(p) and name.lower().endswith(_EXT):
            files += 1
            added += _ingest_file(p)
    return {"ok": True, "files": files, "added": added}


class AutofetchEngine:
    """后台自动拉取循环（daemon 线程）。"""

    def __init__(self, interval_min: float = None):
        self._interval_min = float(interval_min or features.flag("autofetch_interval_min", 20) or 20)
        self._thread = None
        self._stop = threading.Event()

    @property
    def interval_seconds(self):
        return max(60, int(self._interval_min * 60))

    def _loop(self):
        if self._stop.wait(10):
            return
        run_autofetch()
        while not self._stop.wait(self.interval_seconds):
            run_autofetch()

    def start(self):
        if not features.is_enabled("autofetch_enabled"):
            return False
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="rikka-autofetch")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
