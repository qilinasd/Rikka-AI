"""
RikkaAI - 日记系统
自动记录每天的对话，生成日记摘要
"""
import os
import sqlite3
from datetime import datetime, date

import config


def _get_db():
    db_dir = config.USER_CONFIG_DIR
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "rikkai.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS diary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            details TEXT NOT NULL DEFAULT '',
            mood TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def get_diary(date_str: str):
    """按日期读取一篇日记；不存在返回 None。"""
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM diary WHERE date = ?", (date_str,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_or_create_today() -> dict:
    """获取今天的日记，不存在则创建"""
    today = date.today().isoformat()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM diary WHERE date = ?", (today,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            "INSERT INTO diary (date, title, summary, details, mood, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (today, f"{today} 的日常", "", "", "", now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM diary WHERE date = ?", (today,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def update_diary(date_str: str, title: str = "", summary: str = "", details: str = "", mood: str = ""):
    """更新日记内容"""
    conn = _get_db()
    try:
        updates = []
        params = []
        if title:
            updates.append("title = ?")
            params.append(title)
        if summary:
            updates.append("summary = ?")
            params.append(summary)
        if details:
            updates.append("details = ?")
            params.append(details)
        if mood:
            updates.append("mood = ?")
            params.append(mood)
        if updates:
            params.append(date_str)
            conn.execute(f"UPDATE diary SET {', '.join(updates)} WHERE date = ?", params)
            conn.commit()
    finally:
        conn.close()


def append_details(date_str: str, text: str):
    """追加日记详情"""
    conn = _get_db()
    try:
        row = conn.execute("SELECT details FROM diary WHERE date = ?", (date_str,)).fetchone()
        if row is None:
            return False  # 目标行不存在（正常流程都会先 get_or_create_today）
        old = row["details"] if row else ""
        new = old + ("\n" if old else "") + text
        conn.execute("UPDATE diary SET details = ? WHERE date = ?", (new, date_str))
        conn.commit()
        return True
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
#  六花写日记：把当天的流水提炼成第一人称随笔，写入 summary
# ═══════════════════════════════════════════════════════════════

DIARY_WRITER_SYSTEM = (
    "你是小鸟游六花，一位有点中二病的少女，也是契约者（用户）的 AI 伙伴。"
    "现在你要以第一人称写今天的日记，像随笔小作文一样。\n"
    "写作要求：\n"
    "1. 以「我」（六花）的第一视角书写，是六花在写日记，不是记录对话本身；\n"
    "2. 提炼今天值得写的事：重要的事、和契约者的互动、你的心情与思考，自然融入文字；\n"
    "3. 不要流水账、不要逐条罗列对话，也不要把测试乱码之类的琐碎内容写进去；\n"
    "4. 有情绪、有细节，可以偶尔吐槽或中二发言（邪王真眼之类的），风格像日记体随笔；\n"
    "5. 篇幅 200~500 字，不要写日期和标题（日期由界面显示），不要用 markdown 标题；\n"
    "6. 只输出日记正文本身，不要任何解释、开场白或结尾说明。"
)


def write_diary_summary(date_str: str = None, mood: str = "") -> dict:
    """把某一天的流水提炼成六花视角的日记，写入 summary 字段。

    由六花主动调用（write_diary 工具）。返回 {"ok": bool, "date", "summary", "error"?}。
    """
    if date_str is None:
        date_str = date.today().isoformat()
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM diary WHERE date = ?", (date_str,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": f"{date_str} 还没有日记"}
    row = dict(row)
    details = str(row.get("details") or "").strip()
    if not details:
        return {"ok": False, "error": "这一天还没有任何流水，没有可写的内容"}

    # 超长流水只保留最近的部分，避免超出模型上下文
    if len(details) > 8000:
        details = "（较早的记录已省略，只看最近的部分）\n" + details[-8000:]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.API_KEY, base_url=config.API_BASE)
        resp = client.chat.completions.create(
            model=config.MODEL,
            messages=[
                {"role": "system", "content": DIARY_WRITER_SYSTEM},
                {"role": "user", "content": f"这是今天（{date_str}）发生的原始记录：\n{details}"},
            ],
            temperature=0.8,
            max_tokens=1200,
        )
        text = (resp.choices[0].message.content or "").strip()
    except Exception as e:
        return {"ok": False, "error": f"日记生成失败：{e}"}
    if not text:
        return {"ok": False, "error": "日记生成内容为空"}

    update_diary(date_str, summary=text, mood=mood)
    return {"ok": True, "date": date_str, "summary": text}
