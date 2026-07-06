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
        old = row["details"] if row else ""
        new = old + ("\n" if old else "") + text
        conn.execute("UPDATE diary SET details = ? WHERE date = ?", (new, date_str))
        conn.commit()
    finally:
        conn.close()


def get_diary(date_str: str = None) -> dict:
    """获取某天的日记，默认今天"""
    if date_str is None:
        date_str = date.today().isoformat()
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM diary WHERE date = ?", (date_str,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def get_all_diaries(limit: int = 30) -> list:
    """获取日记列表"""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, title, summary, mood FROM diary ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
