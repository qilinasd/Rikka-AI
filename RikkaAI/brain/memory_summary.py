"""
RikkaAI - 层级化记忆总结系统
日记 → 周记 → 月报 → 年鉴
自动编织个人史
"""
import os, sqlite3, json, re
from datetime import datetime, date, timedelta
from openai import OpenAI
import config as cfg

# 报告保存目录
SUMMARY_DIRS = {
    "daily": os.path.join(cfg.ROOT_DIR, "summaries", "daily"),
    "weekly": os.path.join(cfg.ROOT_DIR, "summaries", "weekly"),
    "monthly": os.path.join(cfg.ROOT_DIR, "summaries", "monthly"),
    "yearly": os.path.join(cfg.ROOT_DIR, "summaries", "yearly"),
}

def _ensure_dirs():
    for d in SUMMARY_DIRS.values():
        os.makedirs(d, exist_ok=True)

def _save_to_file(level, period_key, title, content, highlights, emotional_trend, period_range: str = ""):
    """保存报告到对应文件夹；period_range 可选，用于在报告中显示时间范围（如 2026-08-10 ~ 2026-08-16）"""
    _ensure_dirs()
    d = SUMMARY_DIRS.get(level, SUMMARY_DIRS["daily"])
    safe_key = str(period_key).replace(":", "-").replace("/", "-")
    fname = safe_key + ".md"
    fpath = os.path.join(d, fname)
    lines = []
    lines.append("# " + str(title))
    lines.append("")
    if period_range:
        lines.append("> 时间范围: " + str(period_range) + "  |  生成: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    else:
        lines.append("> 时段: " + str(period_key) + "  |  生成: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(str(content))
    lines.append("")
    if highlights:
        lines.append("## 亮点")
        lines.append("")
        for h in highlights:
            lines.append("- " + str(h))
        lines.append("")
    if emotional_trend:
        lines.append("## 情绪轨迹")
        lines.append("")
        for t in emotional_trend:
            lines.append("- " + str(t.get("period","")) + ": " + str(t.get("mood","")) + " (强度: " + str(t.get("intensity","")) + ")")
        lines.append("")
    lines.append("---")
    lines.append("*由 RikkaAI 记忆系统自动生成*")
    md = chr(10).join(lines)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(md)
    return fpath
    

def build_daily(date_str: str = None) -> dict:
    """生成日报"""
    if date_str is None:
        date_str = date.today().isoformat()
    conn = _get_db()
    try:
        diary = conn.execute("SELECT * FROM diary WHERE date=?", (date_str,)).fetchone()
        if not diary:
            return {"title": f"{date_str} 没有记录", "content": "", "highlights": [], "emotional_trend": []}
        diary = dict(diary)
        content = diary.get("summary", "") or diary.get("details", "")[:500] or diary.get("title", "")
        result = {
            "title": f"{date_str} 日报",
            "content": content[:500],
            "highlights": [content[:100]] if content else [],
            "emotional_trend": [{"period": date_str, "mood": diary.get("mood", "一般"), "intensity": 0.5}],
        }
        _save_to_file("daily", date_str, result["title"], result["content"], result["highlights"], result["emotional_trend"])
        return result
    finally:
        conn.close()



def _get_db():
    db_path = os.path.join(cfg.USER_CONFIG_DIR, "rikkai.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mf_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level TEXT NOT NULL CHECK(level IN ('weekly','monthly','yearly')),
            period_key TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            highlights TEXT NOT NULL DEFAULT '[]',
            emotional_trend TEXT NOT NULL DEFAULT '[]',
            event_count INTEGER DEFAULT 0,
            source_ids TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE(level, period_key)
        )
    """)
    conn.commit()
    conn.close()


_init()


# ═══════════════════════════════════════════════════════════
#  核心：用 LLM 生成总结
# ═══════════════════════════════════════════════════════════

def _generate_summary(materials: str, level_name: str) -> dict:
    """调用 LLM 生成总结（带健壮 JSON 解析 + 重试）"""
    fallback = {"title": f"{level_name}记录", "content": "", "highlights": [], "emotional_trend": []}

    def _parse_json(text: str) -> dict:
        """从 LLM 输出中尽力提取 JSON 对象：
        1) 直接整体解析；2) 剥离 markdown 代码块后解析；3) 提取最外层 { ... } 再解析"""
        if not text:
            return {}
        candidates = []
        t = text.strip()
        candidates.append(t)
        # 剥离 ```json ... ``` / ``` ... ``` 代码块
        m = re.search(r"```(?:json)?\s*(.*?)\s*```", t, re.DOTALL)
        if m:
            candidates.append(m.group(1).strip())
        # 提取最外层大括号（可能被前后文字包裹）
        start, end, depth = -1, -1, 0
        for i, ch in enumerate(t):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if start != -1 and end > start:
            candidates.append(t[start:end + 1])
        for c in candidates:
            try:
                obj = json.loads(c)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
        return {}

    def _normalize(data: dict) -> dict:
        """规整字段类型，缺省时给合理兜底"""
        highlights = data.get("highlights") or []
        if isinstance(highlights, str):
            highlights = [highlights]
        trend = data.get("emotional_trend") or []
        if isinstance(trend, dict):
            trend = [trend]
        norm_trend = []
        for item in trend:
            if isinstance(item, dict):
                norm_trend.append({
                    "period": str(item.get("period", "")),
                    "mood": str(item.get("mood", "")),
                    "intensity": float(item.get("intensity", 0.5)),
                })
        return {
            "title": str(data.get("title") or f"{level_name}记录"),
            "content": str(data.get("content") or "").strip(),
            "highlights": [str(h) for h in highlights if str(h).strip()],
            "emotional_trend": norm_trend,
        }

    for attempt in range(2):  # 最多重试 2 次
        try:
            client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
            resp = client.chat.completions.create(
                model=cfg.MODEL,
                messages=[{"role": "user", "content": (
                    f"你是一位温柔的书记官，正在为你的契约者整理{level_name}的记忆。\n\n"
                    f"以下是这段时间的原始记录（每条可能带情感权重 💖 和提及次数，如 ❤️×10）：\n{materials[:2000]}\n\n"
                    f"请生成以下 JSON 格式的总结（只输出 JSON，不要 markdown 代码块、不要额外文字）：\n"
                    f"{{\n"
                    f'  "title": "标题（一句话概括这一时期的主题）",\n'
                    f'  "content": "叙事性总结（3-5句话，像讲故事一样）",\n'
                    f'  "highlights": ["亮点事件1", "亮点事件2", ...],\n'
                    f'  "emotional_trend": [\n'
                    f'    {{"period": "时段", "mood": "开心/平静/低落等", "intensity": 0.0~1.0}}\n'
                    f'  ]\n'
                    f"}}\n"
                    f"\n【重要原则 — 拥抱冗余】\n"
                    f"回忆不是散落的碎片，而是一条流动的河。反复出现的、带着强情感（💖 高或 ❤️×多次）的内容，"
                    f"恰恰是最珍贵的羁绊——请务必保留它们的完整语境和情感，不要机械去重或合并。"
                    f"哪怕同一件事被记录了多次，每次的语境都可能不同，请在总结中如实呈现这种「厚度」。\n"
                    f"如果没有足够内容，highlights 和 emotional_trend 返回空数组。"
                )}],
                temperature=0.3, max_tokens=800,
            )
            result = resp.choices[0].message.content or ""
            data = _parse_json(result)
            if data:
                return _normalize(data)
        except Exception:
            if attempt == 1:
                break
    return fallback


# ═══════════════════════════════════════════════════════════
#  周记
# ═══════════════════════════════════════════════════════════

def _get_week_key(dt: date = None) -> str:
    """返回生成当天日期作为周记标识，如 2026-08-14（不再用 W 编号）"""
    if dt is None:
        dt = date.today()
    return dt.isoformat()


def _get_week_range(key: str) -> tuple:
    """根据标识获取周的范围 (start_date, end_date)：
    - 'YYYY-MM-DD'（新格式）→ 该日期所在 ISO 周（周一 ~ 周日）
    - 'YYYY-WNN'（旧格式兼容）→ ISO 周
    """
    if len(key) >= 10 and key[4] == "-" and key[7] == "-":
        d = date.fromisoformat(key[:10])
        iso = d.isocalendar()
        start = date.fromisocalendar(iso.year, iso.week, 1)
        end = start + timedelta(days=6)
        return start, end
    # 旧格式 2026-W33
    year = int(key[:4])
    week = int(key[6:])
    start = date.fromisocalendar(year, week, 1)
    end = start + timedelta(days=6)
    return start, end


def build_weekly(week_key: str = None) -> dict:
    """生成周记。week_key 默认取生成当天日期（如 2026-08-14），
    统计范围是该日期所在周（周一 ~ 周日）；也兼容旧格式 2026-W33。"""
    if week_key is None:
        week_key = _get_week_key()
    start, end = _get_week_range(week_key)
    start_str = start.isoformat()
    end_str = end.isoformat()
    period_range = f"{start_str} ~ {end_str}"

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM mf_summaries WHERE level='weekly' AND period_key=?", (week_key,)
        ).fetchone()
        if existing:
            return dict(existing)

        # 收集本周日记
        diaries = conn.execute(
            "SELECT date, title, summary, mood FROM diary WHERE date >= ? AND date <= ? ORDER BY date",
            (start_str, end_str),
        ).fetchall()

        # 收集本周记忆碎片
        fragments = conn.execute(
            "SELECT content, emotional_weight, created_at FROM mf_fragments WHERE created_at >= ? AND created_at <= ? ORDER BY created_at",
            (start_str, end_str + " 23:59"),
        ).fetchall()

        conn.close()

        raw_text = f"（本次周记覆盖时间范围：{period_range}）\n"
        if diaries:
            raw_text += "【日记】\n"
            for d in diaries:
                mood_str = f"（心情：{d['mood']}）" if d['mood'] else ""
                raw_text += f"{d['date']}: {d['summary'] or d['title']}{mood_str}\n"
        if fragments:
            raw_text += "\n【记忆碎片】\n"
            for f in fragments:
                ew = float(f['emotional_weight'] or 0.5)
                heart = "💖" if ew >= 0.7 else "💙" if ew >= 0.5 else "🤍"
                raw_text += f"  {heart} {f['content'][:100]}\n"

        if not diaries and not fragments:
            return {"title": f"{week_key} 没有记录", "content": "", "highlights": [], "emotional_trend": []}

        summary = _generate_summary(raw_text, "周记")

        # 生成失败（content 为空）时不入库：避免空记录被缓存，下次可重试
        if not summary.get("content"):
            return summary

        # 存储
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn2 = _get_db()
        try:
            conn2.execute(
                "INSERT OR REPLACE INTO mf_summaries (level, period_key, title, content, highlights, emotional_trend, event_count, source_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("weekly", week_key, summary.get("title", f"{week_key} 周记"),
                 summary.get("content", ""), json.dumps(summary.get("highlights", []), ensure_ascii=False),
                 json.dumps(summary.get("emotional_trend", []), ensure_ascii=False),
                 len(diaries) + len(fragments),
                 json.dumps([d["date"] for d in diaries], ensure_ascii=False), now),
            )
            conn2.commit()
            _save_to_file("weekly", week_key, summary.get("title", f"{week_key} 周记"), summary.get("content", ""), summary.get("highlights", []), summary.get("emotional_trend", []), period_range=period_range)
            row = conn2.execute("SELECT * FROM mf_summaries WHERE level='weekly' AND period_key=?", (week_key,)).fetchone()
            return dict(row) if row else summary
        finally:
            conn2.close()
    finally:
        try:
            conn.close()
        except:
            pass


# ═══════════════════════════════════════════════════════════
#  月报
# ═══════════════════════════════════════════════════════════

def _get_month_key(dt: date = None) -> str:
    if dt is None:
        dt = date.today()
    return dt.strftime("%Y-%m")


def build_monthly(month_key: str = None) -> dict:
    """生成月报"""
    if month_key is None:
        month_key = _get_month_key()

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM mf_summaries WHERE level='monthly' AND period_key=?", (month_key,)
        ).fetchone()
        if existing:
            return dict(existing)

        # 收集本月周记
        weeklies = conn.execute(
            "SELECT * FROM mf_summaries WHERE level='weekly' AND period_key LIKE ? ORDER BY period_key",
            (f"{month_key}%",),
        ).fetchall()

        conn.close()

        if not weeklies:
            return {"title": f"{month_key} 没有记录", "content": "", "highlights": [], "emotional_trend": []}

        raw_text = "【本月周记】\n"
        for w in weeklies:
            raw_text += f"\n{w['period_key']}: {w['title']}\n{w['content']}\n"

        summary = _generate_summary(raw_text, "月报")

        # 生成失败（content 为空）时不入库：避免空记录被缓存，下次可重试
        if not summary.get("content"):
            return summary

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn2 = _get_db()
        try:
            conn2.execute(
                "INSERT OR REPLACE INTO mf_summaries (level, period_key, title, content, highlights, emotional_trend, event_count, source_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("monthly", month_key, summary.get("title", f"{month_key} 月报"),
                 summary.get("content", ""), json.dumps(summary.get("highlights", []), ensure_ascii=False),
                 json.dumps(summary.get("emotional_trend", []), ensure_ascii=False),
                 len(weeklies),
                 json.dumps([w["period_key"] for w in weeklies], ensure_ascii=False), now),
            )
            conn2.commit()
            _save_to_file("monthly", month_key, summary.get("title", f"{month_key} 月报"), summary.get("content", ""), summary.get("highlights", []), summary.get("emotional_trend", []))
            row = conn2.execute("SELECT * FROM mf_summaries WHERE level='monthly' AND period_key=?", (month_key,)).fetchone()
            return dict(row) if row else summary
        finally:
            conn2.close()
    finally:
        try:
            conn.close()
        except:
            pass


# ═══════════════════════════════════════════════════════════
#  年鉴
# ═══════════════════════════════════════════════════════════

def build_yearly(year: str = None) -> dict:
    """生成年鉴"""
    if year is None:
        year = str(date.today().year)

    conn = _get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM mf_summaries WHERE level='yearly' AND period_key=?", (year,)
        ).fetchone()
        if existing:
            return dict(existing)

        monthlies = conn.execute(
            "SELECT * FROM mf_summaries WHERE level='monthly' AND period_key LIKE ? ORDER BY period_key",
            (f"{year}%",),
        ).fetchall()

        conn.close()

        if not monthlies:
            return {"title": f"{year} 年没有记录", "content": "", "highlights": [], "emotional_trend": []}

        raw_text = f"【{year} 年回顾】\n"
        for m in monthlies:
            raw_text += f"\n{m['period_key']}: {m['title']}\n{m['content']}\n"

        summary = _generate_summary(raw_text, "年鉴")

        # 生成失败（content 为空）时不入库：避免空记录被缓存，下次可重试
        if not summary.get("content"):
            return summary

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn2 = _get_db()
        try:
            conn2.execute(
                "INSERT OR REPLACE INTO mf_summaries (level, period_key, title, content, highlights, emotional_trend, event_count, source_ids, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("yearly", year, summary.get("title", f"{year} 年鉴"),
                 summary.get("content", ""), json.dumps(summary.get("highlights", []), ensure_ascii=False),
                 json.dumps(summary.get("emotional_trend", []), ensure_ascii=False),
                 len(monthlies),
                 json.dumps([m["period_key"] for m in monthlies], ensure_ascii=False), now),
            )
            conn2.commit()
            _save_to_file("yearly", year, summary.get("title", f"{year} 年鉴"), summary.get("content", ""), summary.get("highlights", []), summary.get("emotional_trend", []))
            row = conn2.execute("SELECT * FROM mf_summaries WHERE level='yearly' AND period_key=?", (year,)).fetchone()
            return dict(row) if row else summary
        finally:
            conn2.close()
    finally:
        try:
            conn.close()
        except:
            pass


# ═══════════════════════════════════════════════════════════
#  获取总结
# ═══════════════════════════════════════════════════════════

def get_latest(level: str = "weekly") -> dict:
    """获取最新的一条总结"""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM mf_summaries WHERE level=? ORDER BY period_key DESC LIMIT 1",
            (level,),
        ).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def format_for_prompt() -> str:
    """格式化最新总结供 prompt 使用"""
    parts = []
    for level, name in [("weekly", "本周"), ("monthly", "本月"), ("yearly", "今年")]:
        s = get_latest(level)
        if s and s.get("content"):
            parts.append(f"【📅 {name}记忆】{s['title']}: {s['content'][:200]}")
    return "\n".join(parts)
