"""
RikkaAI - 记忆唤起（Memory-to-Proactive bridge）
完整版设计，对齐莲心的 memory_proactive：
  模型评估语义，代码强制执行时机。

流水线：
  1) collect_candidates : 从记忆冥想盆挑「高情感权重 + 仍有效」的碎片作为候选
  2) LLM 语义评估        : 每条候选判定 contact / check_in / remind / suppress / skip
                           带 due_at(何时主动)、window_end(过期作废)、message_instruction(给六花的写作意图)
  3) get_due_cue        : 到点且未过窗口的 approved 候选 → 交给链式主动聊天
  4) 状态机             : candidate → approved/suppressed/dismissed → delivered
"""
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta

import config as cfg

_lock = threading.RLock()
_schema_ready = False

# 候选来源：只挑情感权重 >= 0.6 的记忆碎片（天然的高优先级关怀候选）
MIN_EMOTIONAL_WEIGHT = 0.6
# 候选时间范围：只看最近 90 天的碎片，太久远的不主动唤起
CANDIDATE_MAX_DAYS = 90


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_db():
    db_path = cfg.USER_CONFIG_DIR + "/rikkai.db"
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure():
    global _schema_ready
    if _schema_ready:
        return
    with _lock:
        if _schema_ready:
            return
        conn = _get_db()
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS memory_proactive_cues (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_kind TEXT NOT NULL,
          source_id INTEGER NOT NULL,
          fingerprint TEXT NOT NULL UNIQUE,
          content TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'candidate',
          due_at TEXT DEFAULT '',
          window_end TEXT DEFAULT '',
          action TEXT DEFAULT 'contact',
          suggested_message TEXT DEFAULT '',
          rationale TEXT DEFAULT '',
          confidence REAL DEFAULT 0,
          attempts INTEGER DEFAULT 0,
          last_error TEXT DEFAULT '',
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          delivered_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_memcues_due ON memory_proactive_cues(status, due_at);
        CREATE TABLE IF NOT EXISTS memory_proactive_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cue_id INTEGER,
          action TEXT NOT NULL,
          detail TEXT DEFAULT '',
          created_at TEXT NOT NULL
        );
        """)
        conn.commit()
        conn.close()
        _schema_ready = True


def _fingerprint(kind: str, source_id, content: str) -> str:
    return hashlib.sha256(f"{kind}:{source_id}:{content}".encode("utf-8")).hexdigest()


def _record_event(conn, cue_id, action, detail=""):
    conn.execute(
        "INSERT INTO memory_proactive_events(cue_id, action, detail, created_at) VALUES (?,?,?,?)",
        (cue_id, action, detail, _now()),
    )


def collect_candidates(limit: int = 8) -> list:
    """从记忆冥想盆收集候选：高情感权重 + 近期碎片，尚未被评估过的（status=candidate）"""
    _ensure()
    conn = _get_db()
    try:
        # 只取最近 CANDIDATE_MAX_DAYS 天内、情感权重达标的碎片
        since = (datetime.now() - timedelta(days=CANDIDATE_MAX_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT id, entity, content, category, emotional_weight, created_at "
            "FROM mf_fragments WHERE emotional_weight >= ? AND created_at >= ? "
            "ORDER BY emotional_weight DESC, created_at DESC LIMIT ?",
            (MIN_EMOTIONAL_WEIGHT, since, max(1, int(limit) * 3)),
        ).fetchall()

        out = []
        with _lock:
            for r in rows:
                d = dict(r)
                content = (d.get("content") or "").strip()
                if not content:
                    continue
                fp = _fingerprint("fragment", d["id"], content)
                # 已存在（任何状态）→ 跳过，避免重复收集
                exists = conn.execute(
                    "SELECT status FROM memory_proactive_cues WHERE fingerprint=?", (fp,)
                ).fetchone()
                if exists:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO memory_proactive_cues"
                    "(source_kind, source_id, fingerprint, content, created_at, updated_at) "
                    "VALUES ('fragment',?,?,?,?,?)",
                    (d["id"], fp, content[:300], _now(), _now()),
                )
                out.append({
                    "source_kind": "fragment",
                    "source_id": d["id"],
                    "content": content[:300],
                    "entity": d.get("entity", ""),
                    "category": d.get("category", "一般"),
                    "emotional_weight": d.get("emotional_weight", 0.5),
                    "created_at": d.get("created_at", ""),
                    "fingerprint": fp,
                })
            conn.commit()
        return out[: max(1, int(limit))]
    finally:
        conn.close()


def apply_evaluations(items: list):
    """把 LLM 的评估结果写回：approved/suppressed/dismissed + 时间窗口"""
    _ensure()
    conn = _get_db()
    try:
        now = _now()
        for item in items or []:
            fp = item.get("fingerprint")
            if not fp:
                continue
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else item
            action = str(decision.get("action", "skip")).lower()
            status = (
                "approved" if action in ("contact", "check_in", "remind")
                else "suppressed" if action == "suppress" else "dismissed"
            )
            due = decision.get("due_at") or ""
            end = decision.get("window_end") or ""
            # 时间归一化：解析失败/过早/过晚都兜底
            due, end = _clamp_time(due, end, now)
            conn.execute(
                "UPDATE memory_proactive_cues SET status=?, due_at=?, window_end=?, action=?,"
                " suggested_message=?, rationale=?, confidence=?, updated_at=? WHERE fingerprint=?",
                (
                    status, due, end, action,
                    str(decision.get("message_instruction", ""))[:500],
                    str(decision.get("rationale", ""))[:500],
                    float(decision.get("confidence", 0) or 0), now, fp,
                ),
            )
            row = conn.execute(
                "SELECT id FROM memory_proactive_cues WHERE fingerprint=?", (fp,)
            ).fetchone()
            _record_event(conn, row["id"] if row else None, "evaluated", status)
        conn.commit()
    finally:
        conn.close()


def _clamp_time(due: str, end: str, now_str: str) -> tuple:
    """归一化 due_at / window_end：解析 ISO 或本地时间串，限 5 分钟 ~ 30 天"""
    now = datetime.now()
    parsed_due, parsed_end = now, None
    for s in (due, end):
        if not s:
            continue
        try:
            d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
            if d.tzinfo is not None:
                d = d.astimezone().replace(tzinfo=None)
            if s == due:
                parsed_due = d
            else:
                parsed_end = d
        except Exception:
            pass
    if parsed_due < now + timedelta(minutes=5):
        parsed_due = now + timedelta(minutes=5)
    if parsed_due > now + timedelta(days=30):
        parsed_due = now + timedelta(days=30)
    due_s = parsed_due.strftime("%Y-%m-%d %H:%M:%S")
    end_s = ""
    if parsed_end is not None:
        if parsed_end < parsed_due:
            parsed_end = parsed_due + timedelta(hours=6)
        if parsed_end > parsed_due + timedelta(days=30):
            parsed_end = parsed_due + timedelta(days=30)
        end_s = parsed_end.strftime("%Y-%m-%d %H:%M:%S")
    return due_s, end_s


def get_due_cue():
    """取一条到期的 approved 候选（未过 window_end、未交付）"""
    _ensure()
    conn = _get_db()
    try:
        now = _now()
        row = conn.execute(
            "SELECT * FROM memory_proactive_cues WHERE status='approved' AND due_at<=? "
            "AND (window_end='' OR window_end>=?) ORDER BY confidence DESC, due_at LIMIT 1",
            (now, now),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def mark_delivered(cue_id: int):
    _ensure()
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE memory_proactive_cues SET status='delivered', delivered_at=?, updated_at=? WHERE id=?",
            (_now(), _now(), cue_id),
        )
        _record_event(conn, cue_id, "delivered")
        conn.commit()
    finally:
        conn.close()


def record_evaluation_batch(detail: str):
    _ensure()
    conn = _get_db()
    try:
        _record_event(conn, None, "batch", detail[:300])
        conn.commit()
    finally:
        conn.close()


def get_stats() -> dict:
    _ensure()
    conn = _get_db()
    try:
        counts = {r["status"]: r["c"] for r in conn.execute(
            "SELECT status, COUNT(*) c FROM memory_proactive_cues GROUP BY status"
        ).fetchall()}
        pending = conn.execute(
            "SELECT COUNT(*) c FROM memory_proactive_cues WHERE status='approved' AND due_at<=? "
            "AND (window_end='' OR window_end>=?)", (_now(), _now())
        ).fetchone()["c"]
        return {"counts": counts, "due_now": pending}
    finally:
        conn.close()
