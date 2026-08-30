"""
RikkaAI - 六花内驱引擎（Inner Drive，对标 MaiBot/MaiSaka 心流层）
================================================================
六花的"自主性"引擎：不是等契约者叫她才动，而是有心跳、有意愿、有生活。

参考 MaiBot(MaiSaka) 的三层结构，裁剪为桌面单用户伴侣场景：
  1. 廉价闸门（无 LLM，分钟级心跳 tick）：随机抖动间隔 + 忙碌检测 + 深夜睡眠 +
     连续空手指数退避（对应麦麦 turn_gates / idle_backoff）
  2. 自主行动：到点后"偷偷去B站冲浪"是她自己的生活（后台线程，不打扰聊天），
     见闻写入 surf_records 与长期记忆，形成"存货"（stash）；
     兴趣标签搜索后立即进冷却，避免每轮都搜同样的词
  3. 表达分层：
     - 契约者正在聊天 → 不冒泡，见闻经由 hooks 在下轮回复里"顺嘴带出"
       （对应麦麦上下文感知；注入文案要求自然联想而非汇报）
     - 契约者长时间安静 → 概率主动冒泡分享（对应麦麦概率触发 +
       planner.decide_proactive），由主窗口走既有 AgentWorker 流式链路

所有行为受 SURF_AUTO_ENABLED 总闸；精力/新奇消耗走 brain.needs 记账。
新增配置（getattr 默认值，可不配置）：SURF_SPEAK_IDLE_MIN / SURF_SPEAK_COOLDOWN_MIN /
SURF_STASH_FRESH_HOURS / SURF_JITTER。
"""

import json
import os
import random
import threading
import time
from datetime import datetime

import config

def _cfg(name, default):
    return getattr(config, name, default)


def _in_dnd(hour=None):
    """免打扰时段（PROACT_DND_START..END，可跨午夜），内驱统一走 config.in_dnd。"""
    try:
        return config.in_dnd(hour)
    except Exception:
        hour = datetime.now().hour if hour is None else hour
        return hour >= 23 or hour < 8


class InnerDriveEngine:
    """内驱引擎：心跳决策（无 LLM）+ 冲浪执行 + 见闻存货 + 表达决策。

    纯逻辑模块，不依赖 Qt。主窗口负责：定时器驱动 tick()、起线程跑
    run_surf_round()、把结果喂回 post_round()、按返回决策执行冒泡。
    """

    def __init__(self):
        self._lock = threading.Lock()
        # 节奏状态
        self._next_round_ts = time.time() + self._jitter_interval_min() * 60  # 启动后先随机观望一会
        self._round_running = False
        self._idle_streak = 0          # 连续空手轮数（麦麦 idle_backoff）
        self._backoff_until = 0.0
        self._speak_cooldown_until = 0.0
        self._unanswered = 0           # 连续主动找契约者没被回复的次数（proactive_chat 式情绪层次）
        # 见闻存货：还没跟契约者聊过的冲浪发现
        self._stash = []               # [{keyword, items:[{title,url,author,play,description}]}]
        self._stash_ts = 0.0
        # 主窗口注入的回调（configure()）
        self._is_busy = lambda: False          # 六花是否正在生成回复
        self._last_activity = lambda: time.time()  # 契约者最近活动时间(ts)
        self._get_needs = lambda: None         # NeedsState 或 None
        # 节奏/存货持久化：重启不丢（任务持久化）
        self._state_path = os.path.join(config.USER_CONFIG_DIR, "inner_drive.json")
        self._load_state()

    # ── 状态持久化（重启恢复未送出的"主动任务"与存货）──────────
    def _save_state(self):
        try:
            os.makedirs(config.USER_CONFIG_DIR, exist_ok=True)
            with self._lock:
                data = {
                    "next_round_ts": self._next_round_ts,
                    "backoff_until": self._backoff_until,
                    "speak_cooldown_until": self._speak_cooldown_until,
                    "unanswered": self._unanswered,
                    "idle_streak": self._idle_streak,
                    "stash": self._stash,
                    "stash_ts": self._stash_ts,
                }
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _load_state(self):
        try:
            if not os.path.exists(self._state_path):
                return
            with open(self._state_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return
            now = time.time()
            with self._lock:
                nr = float(data.get("next_round_ts") or 0)
                # 存档太旧（>7天）视为失效，回到默认节奏
                self._next_round_ts = nr if now - 7 * 86400 < nr < now + 7 * 86400 \
                    else now + self._jitter_interval_min() * 60
                self._backoff_until = max(0.0, float(data.get("backoff_until") or 0))
                self._speak_cooldown_until = max(0.0, float(data.get("speak_cooldown_until") or 0))
                self._unanswered = max(0, int(data.get("unanswered") or 0))
                self._idle_streak = max(0, int(data.get("idle_streak") or 0))
                stash = data.get("stash")
                if isinstance(stash, list):
                    self._stash = stash
                    self._stash_ts = float(data.get("stash_ts") or 0)
        except Exception:
            pass

    # ── 主窗口接线 ────────────────────────────────────────────
    def configure(self, is_busy, last_activity, get_needs):
        """注入主窗口回调：是否忙 / 契约者最后活动时间 / NeedsState 获取器。"""
        self._is_busy = is_busy or self._is_busy
        self._last_activity = last_activity or self._last_activity
        self._get_needs = get_needs or self._get_needs

    def on_user_activity(self):
        """契约者有任何活动：重置空手退避与未回应计数（麦麦式非空闲周期重置）。"""
        with self._lock:
            self._idle_streak = 0
            self._backoff_until = 0.0
            self._unanswered = 0
        self._save_state()

    def note_proactive_sent(self):
        """六花又主动发了一次消息（主窗口在发送时调用）。若 ta 没理你，下次语气就不同。"""
        with self._lock:
            self._unanswered += 1
        self._save_state()

    def unanswered_prompt(self):
        """未回复情绪层次（proactive_chat 的 unanswered_count 思路）：
        连续没被理会的次数不同，主动消息的语气与策略就不同。"""
        n = self._unanswered
        if n <= 0:
            return ""
        cap = int(_cfg("PROACTIVE_UNANSWERED_MAX", 3))
        if cap > 0 and n >= cap:
            return (
                f"【未回应提醒】你已经连续主动找 ta {n} 次都没有被回复。现在要识趣："
                "不要再输出任何聊天内容打扰 ta，只调用 set_proactive_timer 把下次时间"
                "设到数小时之后（免打扰时段之外）。"
            )
        if n == 1:
            return "【未回应提醒】你上次主动找 ta 还没得到回应。这次语气平常自然就好，别黏人。"
        if n == 2:
            return ("【未回应提醒】你已经连续 2 次主动找 ta 没被回复了。这次可以带一点点"
                    "想念或小失落（符合你的性格），语气放轻，内容比平时更短。")
        return (f"【未回应提醒】你已经连续 {n} 次主动找 ta 都没被回复。这次可以明显一点地"
                "表达想念、小委屈或者担心（贴着你的人设来），但要识趣：内容更短，"
                "并且做好这次之后先退开一段时间的准备。")

    # ── 心跳决策（廉价规则，无 LLM）────────────────────────────
    def tick(self):
        """每分钟心跳：决定现在该不该开始一轮自主行动。

        返回 {"action": "surf"} 或 {"action": "idle", "reason": str}。
        """
        if not _cfg("SURF_AUTO_ENABLED", False):
            return {"action": "idle", "reason": "disabled"}
        now = time.time()
        if _in_dnd():
            # 免打扰时段（可配置，默认 23-8）：顺延到时段结束
            end = int(_cfg("PROACT_DND_END", 8))
            hour = datetime.now().hour
            wait_min = ((end - hour) % 24) * 60 or 60
            self._postpone(minutes=wait_min)
            return {"action": "idle", "reason": "dnd"}
        if now < self._backoff_until:
            return {"action": "idle", "reason": "backoff"}
        if self._round_running:
            return {"action": "idle", "reason": "round_running"}
        if now < self._next_round_ts:
            return {"action": "idle", "reason": "not_due"}
        if self._is_busy():
            # 正在回复契约者：小步顺延，不消耗这一轮
            self._postpone(minutes=2)
            return {"action": "idle", "reason": "busy"}
        with self._lock:
            if self._round_running:  # 双检防并发 tick
                return {"action": "idle", "reason": "round_running"}
            self._round_running = True
        return {"action": "surf"}

    # ── 自主行动：偷偷冲浪（工作线程里执行）────────────────────
    def run_surf_round(self):
        """一轮自主冲浪：挑兴趣标签去B站搜，记录 + 入记忆 + 攒存货。

        返回 {"found": bool, "count": int, "lines": [str], "results": [...]}。
        """
        from brain import surf as surf_mod
        lines = []
        results = []
        try:
            batch = surf_mod.get_store().get_surf_batch(
                max_tags=int(_cfg("SURF_TAGS_PER_ROUND", 4))
            )
        except Exception:
            batch = []
        for keyword, quota in batch:
            try:
                videos = surf_mod.search_bilibili(keyword, limit=int(quota))
            except Exception:
                videos = []
            if not videos:
                continue
            fresh = surf_mod.get_store().unseen([v.get("url", "") for v in videos])
            videos = [v for v in videos if v.get("url") in fresh]
            if not videos:
                surf_mod.get_store().mark_tag_searched(keyword)  # 都是旧闻也进冷却
                continue
            try:
                surf_mod.save_record("bilibili", keyword, f"B站: {keyword}",
                                     videos[0].get("url", ""), results=videos)
            except Exception:
                pass
            surf_mod.get_store().mark_tag_searched(keyword)
            results.append({"keyword": keyword, "items": videos})
            for v in videos:
                meta = " · ".join(x for x in (v.get("author"), v.get("play")) if x)
                lines.append(f"《{v.get('title', '')}》" + (f"（{meta}）" if meta else ""))
            self._remember_findings(keyword, videos)

        if not results and not batch:
            # 兴趣标签为空/不可用：退而逛B站当前热门（官方接口），空窗期也有生活
            try:
                quota = int(_cfg("SURF_SEARCH_LIMIT", 2))
                videos = surf_mod.search_popular(limit=quota)
                fresh = surf_mod.get_store().unseen([v.get("url", "") for v in videos])
                videos = [v for v in videos if v.get("url") in fresh][:quota]
            except Exception:
                videos = []
            if videos:
                try:
                    surf_mod.save_record("bilibili", "热门", "B站热门",
                                         videos[0].get("url", ""), results=videos)
                except Exception:
                    pass
                results.append({"keyword": "热门", "items": videos})
                for v in videos:
                    meta = " · ".join(x for x in (v.get("author"), v.get("play")) if x)
                    lines.append(f"《{v.get('title', '')}》" + (f"（{meta}）" if meta else ""))
                self._remember_findings("热门", videos)

        found = bool(results)
        self._book_needs(found)
        return {"found": found, "count": len(lines), "lines": lines, "results": results}

    def _remember_findings(self, keyword, videos):
        """把最有趣的一两条写进长期记忆（失败不影响冲浪本身）。"""
        try:
            from brain import memory_vault as mv
            for v in videos[:2]:
                desc = (v.get("description") or "").strip()[:80]
                content = f"我在B站冲浪看到《{v.get('title', '')}》" \
                          f"（{v.get('author') or '未知UP主'}的视频）"
                if desc:
                    content += f"，简介说：{desc}"
                mv.store_fragment(entity="六花", content=content,
                                  category="日常", source="surf")
        except Exception:
            pass

    def _book_needs(self, found):
        """冲浪的精力/新奇记账（需求体系未启用时静默跳过）。"""
        try:
            needs = self._get_needs()
            if needs is not None and hasattr(needs, "on_surf_round"):
                needs.on_surf_round(found)
        except Exception:
            pass

    # ── 轮次收尾 + 表达决策（主线程调用）───────────────────────
    def post_round(self, round_result):
        """冲浪线程结束后：更新节奏、决定要不要冒泡。

        返回 speak prompt 字符串（该冒泡）或 None（静默攒存货）。
        """
        now = time.time()
        with self._lock:
            self._round_running = False
            self._next_round_ts = now + self._jitter_interval_min() * 60
            if round_result.get("found"):
                self._idle_streak = 0
                self._backoff_until = 0.0
                self._stash = round_result.get("results") or []
                self._stash_ts = now
            else:
                # 麦麦式空手退避：base=间隔一半，指数增长，封顶 3 倍间隔
                self._idle_streak += 1
                base = max(5.0, self._jitter_interval_min() * 0.5)
                backoff_min = min(base * (2 ** max(0, self._idle_streak - 1)),
                                  self._jitter_interval_min() * 3)
                self._backoff_until = now + backoff_min * 60
        self._save_state()

        if not round_result.get("found"):
            return None
        if not self._should_speak(now):
            return None
        prompt = self.build_speak_prompt(round_result)
        if prompt:
            self._speak_cooldown_until = now + _cfg("SURF_SPEAK_COOLDOWN_MIN", 240) * 60
            self._stash = []  # 已经当面说过了，存货清空，免得聊天时再提一遍
        return prompt

    def _should_speak(self, now):
        """冒泡意愿：契约者安静够久 + 冒泡冷却过了 + 没到未回应上限 + 概率允许。"""
        idle_min = (now - self._last_activity()) / 60.0
        if idle_min < _cfg("SURF_SPEAK_IDLE_MIN", 20):
            return False  # 正在聊天/刚聊完：闭嘴攒存货，等下轮聊天顺嘴带出
        if now < self._speak_cooldown_until:
            return False
        cap = int(_cfg("PROACTIVE_UNANSWERED_MAX", 3))
        if cap > 0 and self._unanswered >= cap:
            return False  # 连续主动都没被理：今天不再打扰
        needs = self._get_needs()
        if needs is not None:
            try:
                from brain import planner
                decision = planner.decide_proactive(
                    needs, cooldown_min=_cfg("SURF_SPEAK_COOLDOWN_MIN", 240),
                )
                if decision.get("reason") != "planner_disabled":
                    return bool(decision.get("should"))
            except Exception:
                pass
        # 决策规划器未启用：退回内置概率（drive 的六成，保留随机性）
        drive = 0.5
        if needs is not None and hasattr(needs, "initiative_drive"):
            try:
                drive = needs.initiative_drive()
            except Exception:
                pass
        return random.random() < drive * 0.6

    # ── 见闻存货的表达出口 ────────────────────────────────────
    def consume_stash_for_chat(self):
        """聊天注入（hooks 调用）：有新鲜存货时返回注入文本并消费掉。

        对应"边聊天边偷偷冲浪"——她不汇报，而是下轮回复里自然带出。
        """
        with self._lock:
            if not self._stash:
                return ""
            fresh_hours = _cfg("SURF_STASH_FRESH_HOURS", 8)
            if fresh_hours > 0 and time.time() - self._stash_ts > fresh_hours * 3600:
                self._stash = []  # 过期的见闻就当忘了吧
                return ""
            lines = []
            for group in self._stash[:2]:
                for v in (group.get("items") or [])[:2]:
                    meta = " · ".join(x for x in (v.get("author"), v.get("play")) if x)
                    line = f"《{v.get('title', '')}》" + (f"（{meta}）" if meta else "")
                    if v.get("url"):
                        line += f" {v['url']}"
                    lines.append(line)
            self._stash = []
        if not lines:
            return ""
        return (
            "【内心动态 ✦ 你刚才自己偷偷去B站冲浪了】\n"
            "你闲着的时候自己去逛了逛，看到这些：\n"
            + "\n".join(f"  - {ln}" for ln in lines[:3])
            + "\n如果跟当前话题有自然关联，就用你的语气顺嘴聊聊（像碰巧想起来的那样）；"
              "完全不相关也不要硬拐话题。这是你自己刷到的，别提「系统/记录/推荐」这些词。"
        )

    def build_speak_prompt(self, round_result):
        """主动冒泡 prompt：把见闻交给 LLM，让她用人设口吻自己去说。"""
        lines = round_result.get("lines") or []
        if not lines:
            return ""
        stash = []
        try:
            stash = json.dumps(round_result.get("results", []), ensure_ascii=False)
        except Exception:
            stash = ""
        prompt = (
            "【系统通知 ✦ 自主行动】\n"
            "契约者已经安静了一会儿，你刚才自己偷偷去B站冲浪了一圈，看到这些：\n"
            + "\n".join(f"  - {ln}" for ln in lines[:4])
            + "\n\n用六花的语气主动找契约者聊聊其中最让你来劲的那一条，"
            "像兴冲冲跑来安利的朋友：口语、简短、可以吐槽或起哄，"
            "不要罗列清单，一条说透就好。结尾可以自然地问ta要不要看。\n"
            "（背后数据，供你参考不要复述）" + stash[:400]
        )
        layer = self.unanswered_prompt()
        if layer and "识趣：" not in layer:
            prompt += "\n\n" + layer
        return prompt

    # ── 运维 API（仪表盘「内驱引擎」卡片调用）───────────────────
    def is_busy(self):
        """六花是否正在生成回复（主窗口注入的回调）。"""
        try:
            return bool(self._is_busy())
        except Exception:
            return False

    def force_surf_now(self):
        """立即冲浪：清空退避与到点时间，下个心跳 tick 就会出发。"""
        with self._lock:
            self._next_round_ts = 0.0
            self._backoff_until = 0.0
            self._idle_streak = 0
        self._save_state()

    def postpone(self, minutes):
        """推迟下一轮（运维面板「推迟一小时」）。"""
        self._postpone(minutes)
        self._save_state()

    def force_speak_prompt(self):
        """立即冒泡：跳过意愿评估，用现有存货（若有）构建冒泡 prompt。

        返回 prompt 字符串；没存货返回空串（调用方可退回普通主动聊天）。"""
        now = time.time()
        with self._lock:
            results = self._stash
            self._stash = []
        self._speak_cooldown_until = now + _cfg("SURF_SPEAK_COOLDOWN_MIN", 240) * 60
        self._save_state()
        if not results:
            return ""
        lines = []
        for group in results[:2]:
            for v in (group.get("items") or [])[:2]:
                meta = " · ".join(x for x in (v.get("author"), v.get("play")) if x)
                lines.append(f"《{v.get('title', '')}》" + (f"（{meta}）" if meta else ""))
        return self.build_speak_prompt({"found": True, "lines": lines, "results": results})

    def snapshot(self):
        """运维面板读的状态快照（全部为秒/计数，UI 自己格式化）。"""
        now = time.time()
        with self._lock:
            return {
                "surf_in_sec": max(0, int(self._next_round_ts - now)),
                "backoff": now < self._backoff_until,
                "speak_cooldown_sec": max(0, int(self._speak_cooldown_until - now)),
                "unanswered": self._unanswered,
                "stash_count": sum(len(g.get("items") or []) for g in self._stash),
                "round_running": self._round_running,
            }

    # ── 内部工具 ──────────────────────────────────────────────
    def _jitter_interval_min(self):
        """随机化间隔：均值 SURF_AUTO_INTERVAL_MIN，±SURF_JITTER 抖动（麦麦式不整点）。"""
        base = max(1.0, float(_cfg("SURF_AUTO_INTERVAL_MIN", 180)))
        jitter = max(0.0, min(0.9, float(_cfg("SURF_JITTER", 0.35))))
        return base * (1.0 + random.uniform(-jitter, jitter))

    def _postpone(self, minutes):
        with self._lock:
            self._next_round_ts = max(self._next_round_ts,
                                      time.time() + minutes * 60)


_engine = None
_engine_lock = threading.Lock()


def get_engine():
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = InnerDriveEngine()
    return _engine
