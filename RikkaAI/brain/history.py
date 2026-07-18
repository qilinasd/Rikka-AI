"""
RikkaAI - 对话历史系统（SQLite 持久化）
"""
import os
import sqlite3
from datetime import datetime

import config


def _get_db():
    db_dir = config.USER_CONFIG_DIR
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "rikkai.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '新会话',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        )
    """)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


# 初始化
_init_db()


def create_session() -> int:
    """创建新会话，返回 session_id"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _get_db()
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.execute(
        "INSERT INTO sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
        ("新会话", now, now),
    )
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    return session_id


def update_session_title(session_id: int, title: str):
    conn = _get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute(
        "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
        (title[:50], now, session_id),
    )
    conn.commit()
    conn.close()


def delete_session(session_id: int):
    conn = _get_db()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def add_message(session_id: int, role: str, content: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _get_db()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, role, content, now),
    )
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (now, session_id),
    )
    conn.commit()
    conn.close()


def get_sessions(limit: int = 50) -> list:
    conn = _get_db()
    rows = conn.execute(
        """SELECT id, title, created_at, updated_at,
           (SELECT COUNT(*) FROM messages WHERE session_id = sessions.id) as msg_count
           FROM sessions ORDER BY updated_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_messages(session_id: int) -> list:
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, role, content, created_at FROM messages WHERE session_id = ? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
