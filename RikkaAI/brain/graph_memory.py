"""
RikkaAI - 知识图谱记忆系统
实体-关系图记忆，比 RAG 更精准
"""
import os, sqlite3, json, re
from datetime import datetime
from openai import OpenAI
import config as cfg

NODE_TYPES = ["人物", "地点", "事物", "概念", "偏好", "事件", "时间"]
RELATION_TYPES = ["喜欢", "讨厌", "位于", "拥有", "属于", "相关", "发生于", "想要", "是"]


def _get_db():
    db_path = os.path.join(cfg.USER_CONFIG_DIR, "rikkai.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init():
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT NOT NULL DEFAULT '概念',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            relation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (source_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
            FOREIGN KEY (target_id) REFERENCES graph_nodes(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS graph_extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER DEFAULT 0,
            text TEXT NOT NULL,
            entities TEXT NOT NULL DEFAULT '[]',
            relations TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit(); conn.close()


_init()


def get_or_create_node(name: str, node_type: str = "概念") -> int:
    conn = _get_db()
    try:
        row = conn.execute("SELECT id FROM graph_nodes WHERE name = ?", (name,)).fetchone()
        if row:
            return row["id"]
        conn.execute("INSERT INTO graph_nodes (name, type, created_at) VALUES (?, ?, ?)",
                     (name, node_type, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    finally:
        conn.close()


def add_edge(source: str, relation: str, target: str):
    """添加一条关系：source --relation--> target"""
    sid = get_or_create_node(source)
    tid = get_or_create_node(target)
    conn = _get_db()
    try:
        exists = conn.execute(
            "SELECT id FROM graph_edges WHERE source_id=? AND target_id=? AND relation=?",
            (sid, tid, relation),
        ).fetchone()
        if not exists:
            conn.execute("INSERT INTO graph_edges (source_id, target_id, relation, created_at) VALUES (?, ?, ?, ?)",
                         (sid, tid, relation, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
    finally:
        conn.close()


def extract_entities(text: str) -> dict:
    """用 LLM 从文本中提取实体和关系"""
    try:
        client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
        resp = client.chat.completions.create(
            model=cfg.MODEL,
            messages=[{"role": "user", "content": (
                f"从以下文本中提取实体和关系，返回JSON格式：\n"
                f"{{\"entities\": [{{\"name\":\"...\",\"type\":\"人物|地点|事物|概念|偏好\"}}], "
                f"\"relations\": [{{\"source\":\"...\",\"relation\":\"喜欢|讨厌|位于|拥有|属于|想要\",\"target\":\"...\"}}]}}\n"
                f"如果没有则返回空数组。\n文本：{text[:500]}"
            )}],
            temperature=0.1, max_tokens=500,
        )
        result = resp.choices[0].message.content or "{}"
        # 提取 JSON
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"entities": [], "relations": []}
    except Exception:
        return {"entities": [], "relations": []}


def store_extraction(session_id: int, text: str):
    """从文本提取知识并存入图谱"""
    data = extract_entities(text)
    entities = data.get("entities", [])
    relations = data.get("relations", [])

    # 存节点
    for e in entities:
        get_or_create_node(e["name"], e.get("type", "概念"))

    # 存关系
    for r in relations:
        add_edge(r["source"], r["relation"], r["target"])

    # 存提取记录
    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO graph_extractions (session_id, text, entities, relations, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, text[:200], json.dumps(entities, ensure_ascii=False),
             json.dumps(relations, ensure_ascii=False), datetime.now().strftime("%Y-%m-%d %H:%M")),
        )
        conn.commit()
    finally:
        conn.close()


def search(query: str, depth: int = 2) -> str:
    """基于关键词搜索图谱，返回相关记忆"""
    conn = _get_db()
    try:
        # 找到匹配的节点
        nodes = conn.execute(
            "SELECT id, name, type FROM graph_nodes WHERE name LIKE ? LIMIT 5",
            (f"%{query}%",),
        ).fetchall()

        if not nodes:
            return ""

        related = set()
        for node in nodes:
            related.add((node["name"], node["type"], "self"))
            # 直接关系
            edges = conn.execute("""
                SELECT e.relation, n.name, n.type FROM graph_edges e
                JOIN graph_nodes n ON e.target_id = n.id
                WHERE e.source_id = ?
                UNION
                SELECT e.relation, n.name, n.type FROM graph_edges e
                JOIN graph_nodes n ON e.source_id = n.id
                WHERE e.target_id = ?
            """, (node["id"], node["id"])).fetchall()
            for rel, name, ntype in edges:
                related.add((name, ntype, rel))

        parts = []
        for name, ntype, rel in related:
            parts.append(f"{ntype}「{name}」({rel})")

        return "【知识图谱】\n" + "\n".join(parts)
    finally:
        conn.close()


def format_for_prompt(results: str) -> str:
    if not results:
        return ""
    return results[:500]
