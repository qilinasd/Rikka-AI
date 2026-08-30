"""
RikkaAI - 表达学习者（对标麦麦 expression_learner / jargon_learner 的轻量版）
==========================================================================
让六花"成为人类"的两件套：
  1. 风格模仿：低频抽样攒下契约者的原话样本（怎么说话、口头禅、句式），
     聊天时注入少量样本，让她偶尔自然借用 ta 的用词习惯——不生硬复读。
  2. 黑话学习：检测对话里 AI 可能不懂的新词/梗/圈内用语，让模型写一句话
     解释存档；之后她"听得懂"，合适时也能自然用。

存储：config.USER_CONFIG_DIR/learner.json（自包含，不占记忆库）。
触发：agent 每轮对话结束后调用 maybe_learn_from_chat（内部 30% 抽样，失败静默）。
注入：hooks 的 learner hook，每轮回复前返回风格样本 + 已学词条。
"""

import json
import os
import random
import re
import threading
import time

import config as cfg

_STYLE_CAP = 40        # 风格样本上限（FIFO）
_JARGON_CAP = 30       # 词条上限（按最近见到淘汰）
_JARGON_AGE_DAYS = 30  # 词条 30 天没再见到就淡忘
_SAMPLE_PROB = 0.3     # 每轮对话的抽样概率（控制 LLM 开销）


class LearnerStore:
    """风格样本 + 黑话词条的 JSON 存储（线程安全，坏档自愈）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._path = os.path.join(cfg.USER_CONFIG_DIR, "learner.json")
        self._data = self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data.setdefault("style_samples", [])
                    data.setdefault("jargon", [])
                    return data
        except Exception:
            pass
        return {"style_samples": [], "jargon": []}

    def _save(self):
        try:
            os.makedirs(cfg.USER_CONFIG_DIR, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    # ── 风格样本 ──────────────────────────────────────────────
    def add_style_sample(self, text):
        text = str(text or "").strip()
        if not text:
            return
        with self._lock:
            samples = self._data["style_samples"]
            if any(s.get("text") == text for s in samples[-5:]):
                return  # 连续重复的话不攒
            samples.append({"text": text[:120], "ts": time.time()})
            del samples[:-_STYLE_CAP]
            self._save()

    def recent_style_samples(self, limit=3):
        with self._lock:
            rows = list(self._data["style_samples"])[-limit:]
        return [r["text"] for r in rows]

    # ── 黑话词条 ──────────────────────────────────────────────
    def upsert_jargon(self, term, meaning):
        term = str(term or "").strip()[:24]
        meaning = str(meaning or "").strip()[:120]
        if not term or not meaning:
            return
        now = time.time()
        with self._lock:
            for row in self._data["jargon"]:
                if row["term"] == term:
                    row["meaning"] = meaning  # 语义变了就更新理解
                    row["seen"] = int(row.get("seen", 1)) + 1
                    row["last_seen"] = now
                    # 重排让"最近见过的"排前面（jargon_rows 注入按此取 top）
                    self._data["jargon"].sort(key=lambda r: r.get("last_seen", 0), reverse=True)
                    self._save()
                    return
            self._data["jargon"].append(
                {"term": term, "meaning": meaning, "seen": 1,
                 "ts": now, "last_seen": now})
            self._data["jargon"].sort(key=lambda r: r.get("last_seen", 0), reverse=True)
            del self._data["jargon"][_JARGON_CAP:]
            self._save()

    def forget_stale_jargon(self):
        cutoff = time.time() - _JARGON_AGE_DAYS * 86400
        with self._lock:
            kept = [r for r in self._data["jargon"]
                    if r.get("last_seen", 0) >= cutoff]
            if len(kept) != len(self._data["jargon"]):
                self._data["jargon"] = kept
                self._save()

    def jargon_rows(self, limit=5):
        self.forget_stale_jargon()
        with self._lock:
            return [dict(r) for r in self._data["jargon"][:limit]]


_learner = None
_learner_lock = threading.Lock()


def get_learner():
    global _learner
    if _learner is None:
        with _learner_lock:
            if _learner is None:
                _learner = LearnerStore()
    return _learner


# ── 学习触发（agent 每轮对话后调用）─────────────────────────────
def maybe_learn_from_chat(agent, user_text, reply_text):
    """抽样学习：攒原话样本（零成本）+ 低频让模型解释新词（一次小调用）。

    任何失败都静默——学习永远不影响对话本身。
    """
    user_text = str(user_text or "").strip()
    if not user_text or len(user_text) < 6 or len(user_text) > 150:
        return
    if user_text.startswith(("/", "【", "[", "http")):
        return  # 指令/引用/链接不是语言样本
    learner = get_learner()
    learner.add_style_sample(user_text)
    if random.random() > _SAMPLE_PROB:
        return
    term, meaning = _extract_jargon(user_text)
    if term and meaning:
        learner.upsert_jargon(term, meaning)


def _extract_jargon(user_text):
    """让小模型判断这句话里有没有值得记录的新词/梗。返回 (term, meaning) 或 (None, None)。"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
        resp = client.chat.completions.create(
            model=cfg.MODEL,
            messages=[{"role": "user", "content": (
                "下面是用户对AI说的一句话。判断里面有没有 AI 可能不懂的新词、网络梗、"
                "缩写或圈子里才懂的用语（不含专有名词人名地名）。\n"
                "有：只输出 JSON {\"term\": \"词\", \"meaning\": \"一句话通俗解释\"}\n"
                "没有：只输出 NONE\n\n"
                f"用户的话：{user_text[:150]}"
            )}],
            temperature=0.1, max_tokens=100, timeout=15,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if "NONE" in raw.upper():
            return None, None
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None, None
        data = json.loads(match.group())
        return data.get("term"), data.get("meaning")
    except Exception:
        return None, None


# ── prompt 注入（hooks 调用）────────────────────────────────────
def build_prompt_suffix():
    """返回【契约者的说话风格】+【你学会的词】注入块；没料时返回空串。"""
    learner = get_learner()
    parts = []
    samples = learner.recent_style_samples(limit=3)
    if samples:
        parts.append(
            "【契约者的说话风格】ta 平时是这么说话的：\n"
            + "\n".join(f"  · {s[:50]}" for s in samples)
            + "\n偶尔（不是每轮）自然借用 ta 的用词习惯和句式，让对话更像老朋友；别生硬复读。"
        )
    rows = learner.jargon_rows(limit=5)
    if rows:
        parts.append(
            "【你学会的词】这些是 ta 圈子里的说法，你已经懂了：\n"
            + "\n".join(f"  · {r['term']}＝{r['meaning']}" for r in rows)
            + "\n听到时自然明白意思；合适时你也可以自己用，但别硬凑。"
        )
    return "\n\n".join(parts)
