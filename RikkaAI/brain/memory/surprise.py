"""
RikkaAI - Surprise 加权遗忘（Phase 1）

信息论式 surprise：一条记忆内容与既有记忆库越"不同/意外"，其信息量越大，
越该在后续被记住、被主动唤起。给定一个碎片，计算它与整体记忆库的差异度，
据此给出一个可叠加到 emotional_weight 的增量。

参考 genesis-agent 的 surprise-weighted retention（越意外 → 保留度 ×N）。

gate: features.is_enabled("memory_surprise_weight_enabled")
"""
import math
import re
from datetime import datetime, timedelta

from brain.memory import conn
from brain import features


def _tokens(text: str) -> set:
    t = str(text or "")
    return set(re.findall(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+", t.lower()))


def _recent_context(limit: int = 60, days: int = 30) -> list:
    """取最近 days 天内的碎片文本作为"既有记忆"基准。"""
    c = conn()
    try:
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        rows = c.execute(
            "SELECT content FROM mf_fragments WHERE created_at>=? ORDER BY created_at DESC LIMIT ?",
            (since, limit),
        ).fetchall()
        return [r["content"] for r in rows]
    finally:
        c.close()


def surprise_score(content: str, context: list) -> float:
    """计算一条内容的 surprise 值 [0,1]。

    依据：与新近记忆库的平均 token 重叠度（重叠越低越意外）+ 情感词密度（情绪越强越重要）。
    """
    tokens = _tokens(content)
    if not tokens:
        return 0.0
    if not context:
        # 无既有记忆可比较 → 视为中等意外（全新但无从判断）
        return 0.5
    # 平均 Jaccard 差异：1 - overlap_rate
    total_overlap = 0.0
    for ctx in context:
        ct = _tokens(ctx)
        if not ct:
            continue
        overlap = len(tokens & ct) / max(1, len(tokens | ct))
        total_overlap += overlap
    avg_overlap = total_overlap / max(1, len(context))
    novelty = 1.0 - min(1.0, avg_overlap)
    # 情感词（情绪信号）作为额外权重
    strong = ("喜欢", "讨厌", "难过", "开心", "重要", "承诺", "生日",
              "发烧", "分手", "加班", "辞职", "出国", "结婚")
    emo = sum(1 for w in strong if w in str(content))
    emotional = min(1.0, emo / 3.0)
    return round(max(0.0, min(1.0, 0.6 * novelty + 0.4 * emotional)), 3)


def boost(fragment_id: int) -> float:
    """给一条碎片叠加 surprise 增量到 emotional_weight，返回新权重。
    若 surprise 不高则不叠加。失败静默（增强不能阻断主流程）。"""
    if not features.is_enabled("memory_surprise_weight_enabled"):
        return 0.0
    c = conn()
    try:
        row = c.execute(
            "SELECT content, emotional_weight FROM mf_fragments WHERE id=?", (fragment_id,)
        ).fetchone()
        if not row:
            return 0.0
        ctx = _recent_context()
        s = surprise_score(row["content"], ctx)
        if s < 0.35:
            return 0.0  # 不够意外，不强留
        base = float(row["emotional_weight"] or 0.5)
        added = round(0.5 * s, 2)  # 最多 +0.5
        new_w = min(1.0, base + added)
        c.execute("UPDATE mf_fragments SET emotional_weight=? WHERE id=?", (new_w, fragment_id))
        c.commit()
        return added
    except Exception:
        return 0.0
    finally:
        c.close()


def score_many(fragment_ids) -> list:
    """批量给多条碎片打分并更新，返回 [(id, 增量)]。"""
    out = []
    for fid in fragment_ids or []:
        inc = boost(int(fid))
        if inc:
            out.append((int(fid), inc))
    return out
