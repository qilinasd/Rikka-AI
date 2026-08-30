"""
RikkaAI - 桌面感知（LingChat 式主动窥屏，替代旧"摸鱼偷看"链路）
================================================================
定期截屏 → 视觉模型分类桌面状态（工作/学习/游戏/娱乐/挂机/其他），
供主动聊天做差异化关心：什么时候该说话、该说什么、什么时候闭嘴。

安全边界（沿用旧偷屏链路并强化）：
- 判定只依据画面可见事实（窗口标题/内容/界面），不推断心情、意图、进度
- 六花对外表达时不得提"偷看/监控/截图/后台"这些词（约束写在注入文案里）

状态存档：config.USER_CONFIG_DIR/screen_sense.json（重启不丢）。
"""

import json
import os
import re
import threading
import time
from datetime import datetime

import config as cfg

_STATES = ("工作", "学习", "游戏", "娱乐", "挂机", "其他")
_MAX_AGE_MIN = 90  # 状态超过 90 分钟视为过期，不再注入

# 不同状态的差异化关心策略（注入给 LLM 的行为指引）
_GUIDANCE = {
    "工作": "ta 在忙正事：别长篇打扰，一句简短的加油或提醒休息就好，甚至可以只是安静陪着。",
    "学习": "ta 在学习：轻轻鼓励一句即可，不要抛新话题岔开注意力。",
    "游戏": "ta 在打游戏：别追问细节打断节奏，最多皮一句，等 ta 下线再好好聊。",
    "娱乐": "ta 在放松摸鱼：这是聊天的好时机，可以分享趣事或你冲浪看到的见闻。",
    "挂机": "ta 多半离开了：不要发需要回应的长内容，一两句话留个念想即可。",
    "其他": "状态不明确：按平常的方式自然搭话就好。",
}


class ScreenSense:
    """桌面状态的单例感知器：后台截屏分类 + 状态存档 + prompt 注入块。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = False
        self._path = os.path.join(cfg.USER_CONFIG_DIR, "screen_sense.json")
        self._state = {"state": "", "detail": "", "ts": 0.0}
        self._load()

    # ── 存档 ──────────────────────────────────────────────────
    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("state") in _STATES:
                    self._state = {
                        "state": data["state"],
                        "detail": str(data.get("detail") or "")[:80],
                        "ts": float(data.get("ts") or 0.0),
                    }
        except Exception:
            pass

    def _save(self):
        try:
            os.makedirs(cfg.USER_CONFIG_DIR, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False)
        except Exception:
            pass

    # ── 采集 ──────────────────────────────────────────────────
    def capture_async(self):
        """后台线程截屏分类。同一时间只跑一个；返回是否成功启动。"""
        with self._lock:
            if self._running:
                return False
            self._running = True
        threading.Thread(target=self._work, daemon=True).start()
        return True

    def _work(self):
        result = {"state": "", "detail": "", "ts": time.time()}
        try:
            result = self._capture_and_classify()
        except Exception:
            result = {"state": "", "detail": "", "ts": time.time()}
        with self._lock:
            self._running = False
            if result.get("state"):
                self._state = result
                self._save()

    def _capture_and_classify(self):
        from PIL import ImageGrab
        from brain.tools import _vision
        d = cfg.SCREENSHOTS_DIR
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, f"sense_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        ImageGrab.grab().save(p)
        raw = _vision(
            "这是契约者屏幕的截图。判断 ta 当前最可能在做什么，只依据画面可见内容"
            "（窗口标题、正在播放/编辑的内容、界面元素），不要猜测心情或进度。\n"
            '只输出 JSON：{"state": "工作|学习|游戏|娱乐|挂机|其他", "detail": "画面里明确可见的一句事实描述，30字内"}\n'
            "屏幕基本空白/锁屏/无操作痕迹 → state=挂机。",
            p, 0.2, 200,
        )
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        data = json.loads(m.group()) if m else {}
        state = data.get("state") if data.get("state") in _STATES else "其他"
        return {"state": state, "detail": str(data.get("detail") or "")[:60], "ts": time.time()}

    # ── 读取与注入 ────────────────────────────────────────────
    def current(self):
        with self._lock:
            return dict(self._state)

    def state_prompt(self, max_age_min=_MAX_AGE_MIN):
        """注入主动聊天的状态块；无状态或过期返回空串。"""
        st = self.current()
        if not st.get("state") or (time.time() - st.get("ts", 0.0)) > max_age_min * 60:
            return ""
        lines = [f"【契约者当前状态（你观察到的）】{st['state']}"]
        if st.get("detail"):
            lines.append(f"画面：{st['detail']}")
        guide = _GUIDANCE.get(st["state"], _GUIDANCE["其他"])
        lines.append(guide)
        lines.append("（不要提「偷看/监控/截图/后台」这些词，就像你恰好知道 ta 在干嘛一样自然。）")
        return "\n".join(lines)


_sense = None
_sense_lock = threading.Lock()


def get_sense():
    global _sense
    if _sense is None:
        with _sense_lock:
            if _sense is None:
                _sense = ScreenSense()
    return _sense
