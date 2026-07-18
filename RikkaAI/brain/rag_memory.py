"""
RikkaAI - RAG 长期记忆系统
基于 SQLite LIKE + FTS5 全文检索，让六花记住几周前的对话
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
        CREATE TABLE IF NOT EXISTS rag_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '对话',
            session_id INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def store(session_id: int, title: str, content: str, category: str = "对话"):
    """存储一条记忆"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO rag_memories (title, content, category, session_id, created_at) VALUES (?, ?, ?, ?, ?)",
            (title[:100], content[:500], category, session_id, now),
        )
        conn.commit()
    finally:
        conn.close()


def search(query: str, top_k: int = 5) -> list:
    """搜索相关记忆，返回最匹配的 top_k 条"""
    if not query or not query.strip():
        return []

    conn = _get_db()
    try:
        # 拆成关键词，用 LIKE 逐个匹配
        words = [w.strip() for w in query.strip().split() if w.strip()]
        if not words:
            return []

        # 构建 WHERE 条件：所有关键词都要匹配（AND）
        conditions = []
        params = []
        for w in words:
            conditions.append("(title LIKE ? OR content LIKE ?)")
            params.extend([f"%{w}%", f"%{w}%"])

        sql = f"""
            SELECT id, title, content, category, created_at
            FROM rag_memories
            WHERE {' AND '.join(conditions)}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(top_k)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_recent(limit: int = 20) -> list:
    """获取最近记忆"""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, content, category, created_at FROM rag_memories ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def format_for_prompt(memories: list) -> str:
    """将检索到的记忆格式化为 prompt 片段"""
    if not memories:
        return ""

    parts = ["【相关记忆】"]
    for i, m in enumerate(memories[:3], 1):
        title = m.get("title", "")
        content = m.get("content", "")
        time = m.get("created_at", "")
        parts.append(f"{i}. {title} ({time}): {content[:100]}")
    return "\n".join(parts)
