"""
RikkaAI - Gap Analysis（Phase 1）

给一次查询/一个主题，主动指出"脑里还不知道什么"——这是 gbrain 最有特色的能力：
  检索找到页面只是第一步，告诉你有缺失/过期的信息才是活人感的关键。

输出几行"存疑"提示：
  1) 完全没记过该主题 / 实体
  2) 关于某实体/主题的碎片已经很久没更新（信息可能过期）
  3) 某高危分类（承诺/健康等）缺乏近期记录

gate: features.is_enabled("memory_gap_analysis_enabled")
"""
from datetime import datetime, timedelta

from brain.memory import conn
from brain import features

_STALE_DAYS = 30
# 关键分类：这些类目如果长期没更新，尤其值得提醒
_KEY_CATEGORIES = ("重要的事", "日常")


def _terms(query: str) -> set:
    """把查询拆成若干中文二元/英文词元，用于模糊命中判断。"""
    t = str(query or "")
    out = set()
    # 英文/数字词
    for m in re.findall(r"[a-zA-Z0-9]{2,}", t):
        out.add(m.lower())
    # 中文：按相邻二元（非重叠分块 + 滑窗各取一次，宁多勿漏）
    cjk = re.findall(r"[\u4e00-\u9fff]+", t)
    for block in cjk:
        if len(block) == 1:
            out.add(block)
        for i in range(len(block) - 1):
            out.add(block[i:i + 2])
    return out


def _hit(query: str, text: str) -> bool:
    q = (query or "").strip()
    hay = str(text or "")
    if not q or not hay:
        return False
    if q in hay or q.lower() in hay.lower():
        return True
    terms = _terms(q)
    low = hay.lower()
    return any(term in low for term in terms if term)


def analyze(query: str, top_k: int = 3) -> list:
    """返回存疑提示列表（字符串）。空列表表示无缺口。"""
    if not features.is_enabled("memory_gap_analysis_enabled"):
        return []
    query = (query or "").strip()
    if not query:
        return []
    notes = []
    c = conn()
    try:
        # 1) 该主题完全没记过？取近期碎片文本做词元命中
        rows = c.execute(
            "SELECT entity, content FROM mf_fragments WHERE status='active' "
            "ORDER BY created_at DESC LIMIT 400"
        ).fetchall()
        hit = any(_hit(query, (r["entity"] or "") + " " + (r["content"] or "")) for r in rows)
        if not hit:
            notes.append(f"关于「{query[:20]}」没有可回顾的碎片——你还没跟六花提过，或需要主动补充。")

        # 2) 相关实体是否过期
        since = (datetime.now() - timedelta(days=_STALE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        stale = c.execute(
            "SELECT name, last_seen FROM mf_entities WHERE last_seen IS NOT NULL AND last_seen < ? "
            "ORDER BY last_seen ASC LIMIT ?",
            (since, top_k),
        ).fetchall()
        for r in stale:
            notes.append(f"{r['name']} 的动态上次更新在 {str(r['last_seen'])[:10]}，可能已过期，建议确认近况。")

        # 3) 关键分类近期是否空白
        for cat in _KEY_CATEGORIES:
            recent = c.execute(
                "SELECT COUNT(*) n FROM mf_fragments WHERE category LIKE ? AND created_at>=?",
                (f"{cat}%", since),
            ).fetchone()["n"]
            if recent == 0:
                notes.append(f"「{cat}」类目最近 {_STALE_DAYS} 天没有新记录。")
    except Exception:
        return []
    finally:
        c.close()
    return notes[:top_k + 2]


def format_for_prompt(query: str, top_k: int = 3) -> str:
    """转成注入 prompt 的文本。没缺口返回空字符串。"""
    notes = analyze(query, top_k=top_k)
    if not notes:
        return ""
    lines = ["【🤔 脑内存疑】有些事六花还没把握："]
    for n in notes:
        lines.append(f"  · {n}")
    return "\n".join(lines)
