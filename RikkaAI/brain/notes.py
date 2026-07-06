"""
RikkaAI - 备忘本系统
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
    return conn


def _init_db():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '一般',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def add(title: str, content: str, category: str = "一般"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO notes (title, content, category, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (title, content, category, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def update(note_id: int, title: str, content: str, category: str = None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _get_db()
    try:
        if category:
            conn.execute(
                "UPDATE notes SET title = ?, content = ?, category = ?, updated_at = ? WHERE id = ?",
                (title, content, category, now, note_id),
            )
        else:
            conn.execute(
                "UPDATE notes SET title = ?, content = ?, updated_at = ? WHERE id = ?",
                (title, content, now, note_id),
            )
        conn.commit()
    finally:
        conn.close()


def delete(note_id: int):
    conn = _get_db()
    try:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
    finally:
        conn.close()


def get_all(limit: int = 50) -> list:
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, content, category, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get(note_id: int) -> dict:
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


def search(query: str) -> list:
    conn = _get_db()
    try:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT id, title, content, category, created_at FROM notes WHERE title LIKE ? OR content LIKE ? ORDER BY updated_at DESC LIMIT 20",
            (like, like),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
