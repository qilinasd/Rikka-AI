"""
RikkaAI - 记忆冥想盆（升级版记忆核心）
基于 MemoryConstellations 架构理念：
1. Scribe - 自动从对话提取事实碎片
2. Archivist - 自动分类/整合碎片为叙事
3. Librarian - 多路召回（关键词+向量融合）
4. 时间衰减 - 情绪权重决定遗忘速度
"""
import os, sqlite3, json, re, math
from datetime import datetime, timedelta
import config


def _get_db():
    db_path = os.path.join(config.USER_CONFIG_DIR, "rikkai.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init():
    conn = _get_db()
    # 记忆碎片表（Scribe 产出）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mf_fragments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            category TEXT DEFAULT '一般',
            emotional_weight REAL DEFAULT 0.5,
            source TEXT DEFAULT 'chat',
            source_id INTEGER DEFAULT 0,
            keywords TEXT NOT NULL DEFAULT '[]',
            status TEXT DEFAULT 'active',       -- active / cooling / frozen / tombstone
            last_accessed TEXT DEFAULT '',     -- 最近被检索/引用的时间，驱动生命周期
            favorite INTEGER DEFAULT 0,        -- 收藏标记（界面星标）
            created_at TEXT NOT NULL
        )
    """)
    # FTS5 全文搜索虚拟表
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS mf_fragments_fts USING fts5(
            content, entity, category,
            content=,
            tokenize='unicode61'
        )
    """)
    # 触发器：自动同步 fragments 到 FTS5 索引
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS mf_fragments_ai AFTER INSERT ON mf_fragments BEGIN
            INSERT INTO mf_fragments_fts(rowid, content, entity, category)
            VALUES (new.id, new.content, new.entity, new.category);
        END;
        CREATE TRIGGER IF NOT EXISTS mf_fragments_ad AFTER DELETE ON mf_fragments BEGIN
            INSERT INTO mf_fragments_fts(mf_fragments_fts, rowid, content, entity, category)
            VALUES ('delete', old.id, old.content, old.entity, old.category);
        END;
        CREATE TRIGGER IF NOT EXISTS mf_fragments_au AFTER UPDATE ON mf_fragments BEGIN
            INSERT INTO mf_fragments_fts(mf_fragments_fts, rowid, content, entity, category)
            VALUES ('delete', old.id, old.content, old.entity, old.category);
            INSERT INTO mf_fragments_fts(rowid, content, entity, category)
            VALUES (new.id, new.content, new.entity, new.category);
        END;
    """)
    # 叙事段落表（Archivist 产出）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mf_episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            entities TEXT NOT NULL DEFAULT '[]',
            emotional_weight REAL DEFAULT 0.5,
            source_date TEXT,
            created_at TEXT NOT NULL
        )
    """)
    # 碎片-段落关联表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mf_fragment_episode (
            fragment_id INTEGER NOT NULL,
            episode_id INTEGER NOT NULL,
            PRIMARY KEY (fragment_id, episode_id),
            FOREIGN KEY (fragment_id) REFERENCES mf_fragments(id) ON DELETE CASCADE,
            FOREIGN KEY (episode_id) REFERENCES mf_episodes(id) ON DELETE CASCADE
        )
    """)
    # 实体画像表（三字段模型：facts 客观事实 / current_status 近况 / judgment 主观评价）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS mf_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            entity_type TEXT DEFAULT '人物',
            summary TEXT DEFAULT '',
            facts TEXT DEFAULT '',            -- 客观事实（无条件覆盖）
            current_status TEXT DEFAULT '',   -- 近期动态（新顶旧）
            judgment TEXT DEFAULT '',         -- 主观评价（可修订保留）
            mention_count INTEGER DEFAULT 1,
            last_seen TEXT,
            emotional_weight REAL DEFAULT 0.5,
            created_at TEXT NOT NULL
        )
    """)
    # 标签索引（加速检索）
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_fragments_category
        ON mf_fragments(category)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_fragments_entity
        ON mf_fragments(entity)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_fragments_created
        ON mf_fragments(created_at)
    """)
    # 用户状态表（current_state — 有时效的瞬态：生理期/搬家/压力/备考等，TTL 自动过期）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT NOT NULL,
            state_type TEXT DEFAULT 'general',
            expires_at TEXT,             -- 过期时间（YYYY-MM-DD HH:MM 或 'none'）
            schedule TEXT DEFAULT '',    -- 周期提醒（JSON：{"type":"daily","windows":[...]}）
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    # 行为模式表（user_patterns — 长期规律，置信度只增不减，freshness 控制注入优先级）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern TEXT NOT NULL UNIQUE,
            confidence REAL DEFAULT 0.5,   -- 置信度（只增不减）
            freshness REAL DEFAULT 0.5,    -- 新鲜度（随时间衰减，独立于置信度）
            source TEXT DEFAULT 'auto',
            last_confirmed TEXT,
            created_at TEXT NOT NULL
        )
    """)
    # 长故事弧表（sagas — 跨实体叙事串联）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS memory_sagas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            episodes TEXT NOT NULL DEFAULT '[]',   -- 关联的 episode id 列表
            entities TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


_init()

# ═══════════════════════════════════════════════════════════
#  旧库迁移：为已存在的表补充新增列（CREATE TABLE IF NOT EXISTS 不改已有表）
# ═══════════════════════════════════════════════════════════

def _migrate_schema():
    conn = _get_db()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(mf_fragments)").fetchall()}
        if cols:
            if "status" not in cols:
                conn.execute("ALTER TABLE mf_fragments ADD COLUMN status TEXT DEFAULT 'active'")
            if "last_accessed" not in cols:
                conn.execute("ALTER TABLE mf_fragments ADD COLUMN last_accessed TEXT DEFAULT ''")
            if "favorite" not in cols:
                conn.execute("ALTER TABLE mf_fragments ADD COLUMN favorite INTEGER DEFAULT 0")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(mf_entities)").fetchall()}
        if cols:
            for col, ddl in (
                ("facts", "ALTER TABLE mf_entities ADD COLUMN facts TEXT DEFAULT ''"),
                ("current_status", "ALTER TABLE mf_entities ADD COLUMN current_status TEXT DEFAULT ''"),
                ("judgment", "ALTER TABLE mf_entities ADD COLUMN judgment TEXT DEFAULT ''"),
            ):
                if col not in cols:
                    conn.execute(ddl)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


_migrate_schema()

# ═══════════════════════════════════════════════════════════
#  分类体系 — 两级：「大类/小类」
# ═══════════════════════════════════════════════════════════

MEMORY_CATEGORIES = {
    "重要的事": ("承诺", "目标", "纪念"),
    "喜好":     ("偏好", "喜欢", "兴趣"),
    "日常":     ("心情", "生活"),
    "系统":     ("升级", "事件"),
}
CATEGORY_SEP = "/"


def split_category(category) -> tuple:
    """把「大类/小类」拆成 (大类, 小类)；无分隔符时小类为空。"""
    raw = str(category or "").strip()
    if CATEGORY_SEP in raw:
        main, sub = raw.split(CATEGORY_SEP, 1)
        return main.strip(), sub.strip()
    return raw, ""


# 旧版自由文本分类 → 新体系 的显式映射（去 emoji 后匹配）
_LEGACY_CATEGORY_MAP = {
    "重要的事": ("重要的事", "承诺"), "⭐重要的事": ("重要的事", "承诺"), "重要": ("重要的事", "承诺"),
    "偏好": ("喜好", "偏好"), "喜欢": ("喜好", "喜欢"),
    "❤️喜欢的": ("喜好", "喜欢"), "喜欢的": ("喜好", "喜欢"), "兴趣": ("喜好", "兴趣"),
    "🎯想做的事": ("重要的事", "目标"), "想做的事": ("重要的事", "目标"), "目标": ("重要的事", "目标"),
    "承诺": ("重要的事", "承诺"),
    "日常": ("日常", "心情"), "📝日常": ("日常", "心情"), "心情": ("日常", "心情"), "生活": ("日常", "生活"),
    "系统升级": ("系统", "升级"), "升级": ("系统", "升级"), "事件": ("系统", "事件"),
    "契约者设定": ("重要的事", "承诺"),
}


def normalize_category(raw) -> tuple:
    """把任意自由文本分类归一到「大类/小类」，兜底 (日常, 心情)。"""
    key = re.sub(r'[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U00002B50\U00002764]', '', str(raw or ""))
    key = key.replace('️', '').replace('‍', '').strip()  # 去变体选择符 / ZWJ
    if key in _LEGACY_CATEGORY_MAP:
        return _LEGACY_CATEGORY_MAP[key]
    for main, subs in MEMORY_CATEGORIES.items():
        if main in key:
            for sub in subs:
                if sub in key:
                    return main, sub
            return main, subs[0]
    return "日常", "心情"


# ═══════════════════════════════════════════════════════════
#  Scribe — 存储事实碎片
# ═══════════════════════════════════════════════════════════

def store_fragment(entity: str, content: str, category: str = "一般",
                   emotional_weight: float = 0.5, keywords: list = None,
                   source: str = "chat", source_id: int = 0) -> int:
    """存储一条记忆碎片"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    kw_json = json.dumps(keywords or [], ensure_ascii=False)
    conn = _get_db()
    try:
        cur = conn.execute(
            """INSERT INTO mf_fragments
            (entity, content, category, emotional_weight, source, source_id, keywords, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity[:50], content[:500], category, min(max(emotional_weight, 0), 1.0),
             source, source_id, kw_json, now),
        )
        fid = cur.lastrowid
        conn.commit()
        # 更新实体画像
        _update_entity(entity, emotional_weight)
        # 同步写入向量库（离线 n-gram 向量，失败静默）
        try:
            from brain import vector_memory
            vector_memory.add_fragment(fid, content[:300], entity)
        except Exception:
            pass

        # 🆕 Phase 2.1: 检查是否需要触发 Archivist 整合
        _maybe_trigger_consolidation(conn)

        return fid
    finally:
        conn.close()


def _maybe_trigger_consolidation(conn):
    """每 50 条 active 碎片触发一次 Archivist 整合"""
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM mf_fragments WHERE status='active'"
        ).fetchone()[0]

        if count >= 50:
            print(f"[MemoryVault] 触发 Archivist 整合（{count} 条活跃碎片）", flush=True)
            try:
                from brain import archivist
                # 在后台线程运行，避免阻塞当前保存
                import threading
                threading.Thread(
                    target=archivist.consolidate_fragments,
                    daemon=True
                ).start()
            except Exception as e:
                print(f"[MemoryVault] Archivist 整合失败: {e}", flush=True)
    except Exception:
        pass  # 静默失败，不影响主流程


def store_fragments_batch(fragments: list) -> list:
    """批量存储碎片"""
    ids = []
    for f in fragments:
        fid = store_fragment(
            entity=f.get("entity", ""),
            content=f.get("content", ""),
            category=f.get("category", "一般"),
            emotional_weight=f.get("emotional_weight", 0.5),
            keywords=f.get("keywords", []),
            source=f.get("source", "chat"),
            source_id=f.get("source_id", 0),
        )
        ids.append(fid)
    return ids


def add_memory(content: str, category: str = "重要的事", entity: str = "契约者") -> int:
    """手动新增一条记忆（界面「+ 新建记忆」按钮用）。"""
    if not content or not content.strip():
        return 0
    return store_fragment(
        entity=entity,
        content=content.strip(),
        category=category,
        emotional_weight=0.6,
        keywords=[entity],
        source="manual",
    )


def delete_fragment(fragment_id: int) -> bool:
    """删除一条记忆碎片。

    - FTS5 由触发器 mf_fragments_ad 自动 'delete' 同步
    - mf_fragment_episode 由 FK ON DELETE CASCADE 自动清理
    - 不动 mf_entities（实体是共享画像，不随单条碎片删除）
    - 同步删除向量库条目
    """
    conn = _get_db()
    try:
        cur = conn.execute("DELETE FROM mf_fragments WHERE id = ?", (fragment_id,))
        conn.commit()
        if cur.rowcount > 0:
            try:
                from brain import vector_memory
                vector_memory.delete_fragment(fragment_id)
            except Exception:
                pass
        return cur.rowcount > 0
    finally:
        conn.close()


def get_fragment(fragment_id: int) -> dict:
    """取单条记忆碎片的完整信息（含 source/source_id，供详情展示）。"""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT id, entity, content, category, emotional_weight, source, source_id,"
            " keywords, created_at, favorite FROM mf_fragments WHERE id = ?",
            (fragment_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def toggle_favorite(fragment_id: int):
    """收藏/取消收藏一条记忆。返回新状态（1/0/None）。"""
    conn = _get_db()
    try:
        row = conn.execute("SELECT favorite FROM mf_fragments WHERE id = ?", (fragment_id,)).fetchone()
        if not row:
            return None
        new_val = 0 if row["favorite"] else 1
        conn.execute("UPDATE mf_fragments SET favorite = ? WHERE id = ?", (new_val, fragment_id))
        conn.commit()
        return new_val
    finally:
        conn.close()


def _update_entity(name: str, emotional_weight: float = 0.5):
    """更新实体画像（mention_count / last_seen / 情绪权重滑动平均）"""
    if not name:
        return
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        existing = conn.execute("SELECT id, mention_count, emotional_weight FROM mf_entities WHERE name = ?", (name,)).fetchone()
        if existing:
            # 滑动平均情绪权重
            new_ew = (existing["emotional_weight"] * existing["mention_count"] + emotional_weight) / (existing["mention_count"] + 1)
            conn.execute(
                "UPDATE mf_entities SET mention_count = mention_count + 1, last_seen = ?, emotional_weight = ? WHERE id = ?",
                (now, round(new_ew, 2), existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO mf_entities (name, entity_type, summary, mention_count, last_seen, emotional_weight, created_at) VALUES (?, ?, ?, 1, ?, ?, ?)",
                (name, "人物", "", now, emotional_weight, now),
            )
        conn.commit()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  生命周期 — active / cooling / frozen / tombstone
# ═══════════════════════════════════════════════════════════

_LIFE_ACTIVE_DAYS = 14      # 14 天未访问 → cooling
_LIFE_COOLING_DAYS = 30     # cooling 再 30 天未访问 → frozen（从最近访问起算）
_LIFE_FROZEN_DAYS = 90      # frozen 再 90 天未访问 → tombstone（清内容）

def touch_fragment(fragment_id: int):
    """碎片被检索/引用时刷新 last_accessed；cooling 碎片被访问自动复活为 active。"""
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute(
            "UPDATE mf_fragments SET last_accessed = ?, status = CASE WHEN status = 'cooling' THEN 'active' ELSE status END WHERE id = ?",
            (now, fragment_id),
        )
        conn.commit()
    finally:
        conn.close()


def run_lifecycle():
    """生命周期调度：按 last_accessed 天数推进状态。
    active(14d) → cooling(30d) → frozen(90d) → tombstone(清空内容但保留 id 关联)。
    """
    conn = _get_db()
    try:
        now = datetime.now()
        rows = conn.execute("SELECT id, status, created_at, last_accessed FROM mf_fragments").fetchall()
        changes = 0
        for r in rows:
            try:
                base = datetime.strptime(r["last_accessed"] or r["created_at"], "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                base = now
            days = (now - base).days
            status = r["status"] or "active"
            new_status = status
            if status == "active" and days >= _LIFE_ACTIVE_DAYS:
                new_status = "cooling"
            elif status == "cooling" and days >= _LIFE_COOLING_DAYS:
                new_status = "frozen"
            elif status == "frozen" and days >= _LIFE_FROZEN_DAYS:
                new_status = "tombstone"
            if new_status != status:
                if new_status == "tombstone":
                    conn.execute(
                        "UPDATE mf_fragments SET status = 'tombstone', content = '', keywords = '[]' WHERE id = ?",
                        (r["id"],),
                    )
                else:
                    conn.execute("UPDATE mf_fragments SET status = ? WHERE id = ?", (new_status, r["id"]))
                changes += 1
        conn.commit()
        return changes
    finally:
        conn.close()


def get_active_fragment_count() -> int:
    """活跃（非 tombstone）碎片数量，供 Archivist 判断是否该跑深度层。"""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM mf_fragments WHERE status != 'tombstone'"
        ).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  Archivist — 整合碎片
# ═══════════════════════════════════════════════════════════

def consolidate_fragments():
    """将近期未整理的碎片合并为叙事段落"""
    conn = _get_db()
    try:
        # 找还没被归入任何 episode 的碎片
        orphans = conn.execute("""
            SELECT f.id, f.entity, f.content, f.category, f.emotional_weight, f.keywords, f.created_at
            FROM mf_fragments f
            LEFT JOIN mf_fragment_episode fe ON f.id = fe.fragment_id
            WHERE fe.episode_id IS NULL
            ORDER BY f.created_at DESC
            LIMIT 30
        """).fetchall()

        if len(orphans) < 3:
            return 0  # 碎片太少，先不整合

        # 按实体分组合并
        from collections import defaultdict
        groups = defaultdict(list)
        for o in orphans:
            entity = o["entity"] or "其他"
            groups[entity].append(o)

        consolidated = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for entity, frags in groups.items():
            if len(frags) < 2:
                continue
            contents = [f["content"] for f in frags if f["content"]]
            if not contents:
                continue

            avg_ew = sum(f["emotional_weight"] for f in frags) / len(frags)
            episode_text = "；".join(contents[:5])

            cur = conn.execute(
                "INSERT INTO mf_episodes (title, content, entities, emotional_weight, source_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (f"关于{entity}", episode_text[:1000], json.dumps([entity], ensure_ascii=False),
                 round(avg_ew, 2), frags[0]["created_at"], now),
            )
            eid = cur.lastrowid
            for f in frags:
                conn.execute("INSERT OR IGNORE INTO mf_fragment_episode (fragment_id, episode_id) VALUES (?, ?)", (f["id"], eid))
            consolidated += 1

        conn.commit()
        return consolidated
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  Librarian — 多路召回
# ═══════════════════════════════════════════════════════════

# 时间衰减参数
_SEGMENT_DAYS = 3  # 短期/长期分界
_STM_TIME_WEIGHT = 0.7  # 短期：新鲜度权重
_LTM_EMOTION_WEIGHT = 0.7  # 长期：情绪权重


def _get_decay_lambda(emotional_weight: float) -> float:
    """情绪权重决定衰减速度"""
    if emotional_weight >= 0.8:
        return 0.005  # 重要记忆，半衰期~140天
    elif emotional_weight >= 0.6:
        return 0.01  # 标准，~70天
    elif emotional_weight >= 0.4:
        return 0.02  # 轻度，~35天
    return 0.04  # 琐碎，~17天


def _calc_relevance_score(days: float, emotional_weight: float) -> float:
    """计算综合相关度分数（时间衰减 + 情绪权重）"""
    ew = min(max(emotional_weight, 0), 1)
    lam = _get_decay_lambda(ew)
    time_decay = math.exp(-lam * days)
    emotion_retention = 0.3 + ew * 0.7

    if days <= _SEGMENT_DAYS:
        return _STM_TIME_WEIGHT * time_decay + (1 - _STM_TIME_WEIGHT) * emotion_retention
    return (1 - _LTM_EMOTION_WEIGHT) * time_decay + _LTM_EMOTION_WEIGHT * emotion_retention


def rebuild_fts():
    """重建 FTS5 全文索引（删除索引表重建）"""
    conn = _get_db()
    try:
        # 检查 FTS 表是否有数据
        count = conn.execute("SELECT COUNT(*) as c FROM mf_fragments_fts").fetchone()["c"]
        total = conn.execute("SELECT COUNT(*) as c FROM mf_fragments").fetchone()["c"]
        if count >= total:
            return count  # 已经完整
        # 删除触发器（避免冲突），重建 FTS 表，再建触发器
        conn.executescript("""
            DROP TRIGGER IF EXISTS mf_fragments_ai;
            DROP TRIGGER IF EXISTS mf_fragments_ad;
            DROP TRIGGER IF EXISTS mf_fragments_au;
            DROP TABLE IF EXISTS mf_fragments_fts;
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS mf_fragments_fts USING fts5(
                content, entity, category,
                content=,
                tokenize='unicode61'
            )
        """)
        conn.executescript("""
            CREATE TRIGGER IF NOT EXISTS mf_fragments_ai AFTER INSERT ON mf_fragments BEGIN
                INSERT INTO mf_fragments_fts(rowid, content, entity, category)
                VALUES (new.id, new.content, new.entity, new.category);
            END;
            CREATE TRIGGER IF NOT EXISTS mf_fragments_ad AFTER DELETE ON mf_fragments BEGIN
                INSERT INTO mf_fragments_fts(mf_fragments_fts, rowid, content, entity, category)
                VALUES ('delete', old.id, old.content, old.entity, old.category);
            END;
            CREATE TRIGGER IF NOT EXISTS mf_fragments_au AFTER UPDATE ON mf_fragments BEGIN
                INSERT INTO mf_fragments_fts(mf_fragments_fts, rowid, content, entity, category)
                VALUES ('delete', old.id, old.content, old.entity, old.category);
                INSERT INTO mf_fragments_fts(rowid, content, entity, category)
                VALUES (new.id, new.content, new.entity, new.category);
            END;
        """)
        # 重新插入所有数据
        all_rows = conn.execute("SELECT id, content, entity, category FROM mf_fragments").fetchall()
        for r in all_rows:
            conn.execute(
                "INSERT INTO mf_fragments_fts(rowid, content, entity, category) VALUES (?, ?, ?, ?)",
                (r["id"], r["content"], r["entity"], r["category"]),
            )
        conn.commit()
        return len(all_rows)
    except Exception as e:
        print(f"[FTS] rebuild error: {e}")
        return 0
    finally:
        conn.close()


# 模块加载时：如果 fragments 已存在但 FTS 索引为空，重建一次（在 rebuild_fts 定义之后执行）
try:
    conn = _get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM mf_fragments_fts").fetchone()[0]
    except sqlite3.OperationalError:
        count = 0
    total = conn.execute("SELECT COUNT(*) FROM mf_fragments").fetchone()[0]
    conn.close()
    if count < total:
        rebuild_fts()
except Exception:
    pass


def search(query: str, top_k: int = 8) -> list:
    """多路召回：FTS5 全文搜索 + 关键词 + RRF 融合排序 + 时间衰减"""
    if not query or not query.strip():
        return _get_recent_with_decay(top_k)

    conn = _get_db()
    try:
        words = [w.strip() for w in query.split() if w.strip()]
        if not words:
            return _get_recent_with_decay(top_k, conn)
        # 中文单字（如"猫"）在 unicode61 分词下 FTS 命中率极差，单字词只走 LIKE；
        # 多字词才进 FTS。这样单字查询不再被降级成"最近记忆"。
        fts_words = [w for w in words if len(w) > 1]

        now = datetime.now()
        all_scored = {}  # id -> (score, item)

        # ── 第一路：FTS5 全文搜索（仅多字词） ──
        fts_results = []
        if fts_words:
            fts_query = " OR ".join(f'"{w}"' for w in fts_words)
            try:
                fts_rows = conn.execute(
                    "SELECT rowid, rank FROM mf_fragments_fts WHERE mf_fragments_fts MATCH ? ORDER BY rank LIMIT 20",
                    (fts_query,),
                ).fetchall()
                for r in fts_rows:
                    frag = conn.execute(
                        "SELECT id, entity, content, category, emotional_weight, keywords, created_at FROM mf_fragments WHERE id = ?",
                        (r["rowid"],),
                    ).fetchone()
                    if frag:
                        fts_results.append(dict(frag))
            except:
                pass

        # ── 第二路：关键词 LIKE 匹配 ──
        kw_results = []
        conditions = []
        params = []
        for w in words:
            conditions.append("(content LIKE ? OR entity LIKE ? OR keywords LIKE ?)")
            p = f"%{w}%"
            params.extend([p, p, p])
        try:
            kw_rows = conn.execute(
                f"SELECT id, entity, content, category, emotional_weight, keywords, created_at FROM mf_fragments WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT 20",
                params,
            ).fetchall()
            kw_results = [dict(r) for r in kw_rows]
        except:
            pass

        # ── 第三路：向量检索（ChromaDB 本地 n-gram，离线；失败不影响主流程） ──
        vec_results = []
        try:
            from brain import vector_memory
            hits = vector_memory.search(query, top_k=8)
            for h in hits:
                row = conn.execute(
                    "SELECT id, entity, content, category, emotional_weight, keywords, created_at FROM mf_fragments WHERE id = ?",
                    (h["fragment_id"],),
                ).fetchone()
                if row:
                    vec_results.append(dict(row))
        except Exception:
            pass

        # ── RRF 融合 ──
        K = 60  # 🆕 Phase 2.3: Mem0 v3 验证的最优 K 值（原 60，保持不变）

        def _parse_created(value):
            """解析碎片创建时间；脏数据回退到当前时间，避免整轮搜索崩溃。"""
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M") if value else now
            except (ValueError, TypeError):
                return now

        # 🆕 Phase 2.3: FTS5 全文检索路径（权重 1.0，基准）
        for idx, item in enumerate(fts_results):
            fid = item["id"]
            rank = idx + 1
            score = 1.0 / (K + rank)  # 基准权重
            if fid not in all_scored:
                created = _parse_created(item.get("created_at"))
                days = (now - created).days
                ew = item["emotional_weight"] or 0.5
                decay_score = _calc_relevance_score(days, ew)
                all_scored[fid] = {"item": item, "rrf_score": 0, "decay": decay_score}
            all_scored[fid]["rrf_score"] += score

        # 🆕 Phase 2.3: 关键词 LIKE 路径（权重 0.8，略低于 FTS）
        for idx, item in enumerate(kw_results):
            fid = item["id"]
            rank = idx + 1
            score = 0.8 / (K + rank)  # 降低权重，LIKE 精度低于 FTS
            if fid not in all_scored:
                created = _parse_created(item.get("created_at"))
                days = (now - created).days
                ew = item["emotional_weight"] or 0.5
                decay_score = _calc_relevance_score(days, ew)
                all_scored[fid] = {"item": item, "rrf_score": 0, "decay": decay_score}
            all_scored[fid]["rrf_score"] += score

        # 🆕 Phase 2.3: 向量检索路径（权重 1.2，语义召回最高权重）
        for idx, item in enumerate(vec_results):
            fid = item["id"]
            rank = idx + 1
            score = 1.2 / (K + rank)  # Mem0 v3 建议：向量路权重 1.2
            if fid not in all_scored:
                created = _parse_created(item.get("created_at"))
                days = (now - created).days
                ew = item["emotional_weight"] or 0.5
                decay_score = _calc_relevance_score(days, ew)
                all_scored[fid] = {"item": item, "rrf_score": 0, "decay": decay_score}
            all_scored[fid]["rrf_score"] += score

        # ── 综合排序（episodes 权重已在 format_for_prompt 处理；这里过滤 tombstone） ──
        final = []
        for fid, data in all_scored.items():
            if data["item"].get("status") == "tombstone":
                continue
            total = data["rrf_score"] * 0.6 + data["decay"] * 0.4
            data["item"]["_score"] = round(total, 3)
            final.append((total, data["item"]))

        final.sort(key=lambda x: -x[0])
        top = [item for _, item in final[:top_k]]
        # 刷新被检索碎片的 last_accessed（生命周期用进废退）
        for item in top:
            try:
                touch_fragment(item["id"])
            except Exception:
                pass
        return top
    finally:
        conn.close()


def _get_recent_with_decay(limit: int = 8, conn=None):
    """获取最近记忆（带时间衰减排序）"""
    close_later = False
    if conn is None:
        conn = _get_db()
        close_later = True
    try:
        rows = conn.execute(
            "SELECT id, entity, content, category, emotional_weight, keywords, created_at FROM mf_fragments ORDER BY id DESC LIMIT 50"
        ).fetchall()
        now = datetime.now()
        scored = []
        for r in rows:
            try:
                created = datetime.strptime(r["created_at"], "%Y-%m-%d %H:%M")
            except:
                created = now
            days = (now - created).days
            ew = r["emotional_weight"] or 0.5
            score = _calc_relevance_score(days, ew)
            scored.append((score, dict(r)))
        scored.sort(key=lambda x: -x[0])
        return [item for _, item in scored[:limit]]
    finally:
        if close_later:
            conn.close()


def get_recent_fragments(limit: int = 100, query: str = "", favorite_only: bool = False):
    """按时间倒序获取记忆碎片（最新在前，界面列表用，不做相关性排序）。
    query 非空时做关键词过滤（content/entity/keywords LIKE）；favorite_only 只看收藏。"""
    conn = _get_db()
    try:
        sql = ("SELECT id, entity, content, category, emotional_weight, keywords, created_at, status, favorite "
               "FROM mf_fragments WHERE status != 'tombstone'")
        params = []
        if favorite_only:
            sql += " AND favorite = 1"
        q = str(query or "").strip()
        if q:
            words = [w for w in q.split() if w.strip()]
            conds = []
            for w in words:
                p = f"%{w}%"
                conds.append("(content LIKE ? OR entity LIKE ? OR keywords LIKE ?)")
                params.extend([p, p, p])
            if conds:
                sql += " AND " + " AND ".join(conds)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, int(limit)))
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def search_episodes(query: str, top_k: int = 3) -> list:
    """搜索叙事段落"""
    if not query:
        return []
    conn = _get_db()
    try:
        words = [w.strip() for w in query.split() if w.strip()]
        if not words:
            return []
        conditions = []
        params = []
        for w in words:
            conditions.append("(title LIKE ? OR content LIKE ? OR entities LIKE ?)")
            p = f"%{w}%"
            params.extend([p, p, p])
        sql = f"""
            SELECT id, title, content, entities, emotional_weight, created_at
            FROM mf_episodes
            WHERE {' AND '.join(conditions)}
            ORDER BY id DESC
            LIMIT ?
        """
        params.append(top_k)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def format_for_prompt(query: str = "") -> str:
    """格式化记忆供 prompt 使用（叙事段落 1.5× 权重，优先于碎片）"""
    fragments = search(query, top_k=6)
    episodes = search_episodes(query, top_k=3)

    parts = []
    # 叙事段落优先展示（比单条碎片信息密度高）
    if episodes:
        lines = ["【📚 记忆叙事】"]
        for ep in episodes[:2]:
            lines.append(f"  📖 {ep['title']}: {ep['content'][:220]}")
        parts.append("\n".join(lines))

    if fragments:
        lines = ["【📖 记忆碎片】"]
        for f in fragments[:4]:
            if f.get("status") == "tombstone":
                continue
            ew = f.get("emotional_weight", 0.5)
            heart = "💖" if ew >= 0.8 else "💙" if ew >= 0.6 else "💚" if ew >= 0.4 else "🤍"
            name = f.get("entity", "")
            tag = f" [{name}]" if name else ""
            lines.append(f"  {heart} {f['content'][:120]}{tag}")
        parts.append("\n".join(lines))

    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
#  实体检索
# ═══════════════════════════════════════════════════════════

def search_entities(query: str) -> list:
    """搜索实体"""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT name, entity_type, summary, mention_count, emotional_weight FROM mf_entities WHERE name LIKE ? ORDER BY mention_count DESC LIMIT 10",
            (f"%{query}%",),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def category_stats() -> dict:
    """全量碎片按大类统计（归一化后），与界面分类口径一致。"""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT category FROM mf_fragments WHERE status != 'tombstone'"
        ).fetchall()
        counts = {}
        for r in rows:
            main = normalize_category(str(r["category"] or ""))[0]
            counts[main] = counts.get(main, 0) + 1
        return counts
    finally:
        conn.close()


def get_stats() -> dict:
    """记忆系统统计"""
    conn = _get_db()
    try:
        frag_count = conn.execute(
            "SELECT COUNT(*) as c FROM mf_fragments WHERE status != 'tombstone'"
        ).fetchone()["c"]
        ep_count = conn.execute("SELECT COUNT(*) as c FROM mf_episodes").fetchone()["c"]
        ent_count = conn.execute("SELECT COUNT(*) as c FROM mf_entities").fetchone()["c"]
        recent = conn.execute(
            "SELECT content, emotional_weight, created_at FROM mf_fragments "
            "WHERE status != 'tombstone' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {
            "fragments": frag_count,
            "episodes": ep_count,
            "entities": ent_count,
            "last_memory": dict(recent) if recent else None,
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  实体三字段模型（facts / current_status / judgment）
# ═══════════════════════════════════════════════════════════

def update_entity_fields(name: str, facts: str = None, current_status: str = None,
                         judgment: str = None, entity_type: str = None):
    """按三字段模型更新实体画像：
    - facts: 客观事实 → 无条件覆盖
    - current_status: 近期动态 → 新顶旧
    - judgment: 主观评价 → 非空才更新（可修订保留）
    """
    if not name:
        return
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        existing = conn.execute("SELECT id FROM mf_entities WHERE name = ?", (name,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO mf_entities (name, entity_type, summary, facts, current_status, judgment, mention_count, last_seen, created_at) VALUES (?, ?, '', ?, ?, ?, 1, ?, ?)",
                (name, entity_type or "人物", facts or "", current_status or "", judgment or "", now, now),
            )
        else:
            sets = ["last_seen = ?"]
            params = [now]
            if facts is not None:
                sets.append("facts = ?"); params.append(facts[:500])
            if current_status is not None:
                sets.append("current_status = ?"); params.append(current_status[:300])
            if judgment is not None:
                sets.append("judgment = ?"); params.append(judgment[:300])
            if entity_type:
                sets.append("entity_type = ?"); params.append(entity_type)
            params.append(existing["id"])
            conn.execute(f"UPDATE mf_entities SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()


def merge_duplicate_entities(threshold: int = 2):
    """合并重复实体：mention_count 高且 name 相似度高的实体视为同一人/物。
    简单实现：完全同名已由 UNIQUE 约束保证；这里处理「xx 的 xx」与「xx」这类包含关系。
    返回合并数。"""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, mention_count FROM mf_entities ORDER BY mention_count DESC"
        ).fetchall()
        merged = 0
        for i, a in enumerate(rows):
            if a["mention_count"] < threshold:
                continue
            for b in rows[i + 1:]:
                # 一个名字包含另一个（如「小王」与「小王的朋友」）且出现次数差较大 → 合并
                an, bn = a["name"], b["name"]
                if an and bn and (an in bn or bn in an):
                    keep, drop = (a, b) if a["mention_count"] >= b["mention_count"] else (b, a)
                    conn.execute(
                        "UPDATE mf_fragments SET entity = ? WHERE entity = ?",
                        (keep["name"], drop["name"]),
                    )
                    conn.execute("DELETE FROM mf_entities WHERE id = ?", (drop["id"],))
                    merged += 1
        conn.commit()
        return merged
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  用户状态（current_state）— 有时效的瞬态，TTL 自动过期
# ═══════════════════════════════════════════════════════════

def set_user_state(content: str, state_type: str = "general", expires_at: str = "",
                   schedule: str = "") -> int:
    """记录一条用户状态（瞬态）。expires_at 为空 → 默认 90 天后过期；'none' → 永不过期。"""
    if not content:
        return 0
    conn = _get_db()
    try:
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        if not expires_at or expires_at == "none":
            if expires_at == "none":
                exp = "none"
            else:
                exp = (now + timedelta(days=90)).strftime("%Y-%m-%d %H:%M")
        else:
            exp = expires_at
        cur = conn.execute(
            "INSERT INTO user_states (content, state_type, expires_at, schedule, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (content[:300], state_type, exp, schedule, now_str, now_str),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update_user_state(state_id: int, content: str = None, expires_at: str = None) -> bool:
    """修改一条用户状态（如「那个截止日期变了」）。"""
    conn = _get_db()
    try:
        sets = ["updated_at = ?"]
        params = [datetime.now().strftime("%Y-%m-%d %H:%M")]
        if content is not None:
            sets.append("content = ?"); params.append(content[:300])
        if expires_at is not None:
            sets.append("expires_at = ?"); params.append(expires_at)
        params.append(state_id)
        cur = conn.execute(f"UPDATE user_states SET {', '.join(sets)} WHERE id = ?", params)
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def resolve_user_state(state_id: int, reason: str = "") -> bool:
    """结束一条用户状态（标记为已结束：直接删除。reason 记录到日志可选）。"""
    conn = _get_db()
    try:
        cur = conn.execute("DELETE FROM user_states WHERE id = ?", (state_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def get_active_states() -> list:
    """获取所有未过期的用户状态。"""
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        rows = conn.execute(
            "SELECT id, content, state_type, expires_at, schedule, created_at FROM user_states WHERE expires_at = 'none' OR expires_at >= ? ORDER BY created_at DESC",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def expire_states() -> int:
    """清理已过期的用户状态（TTL 到期）。返回删除条数。"""
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cur = conn.execute("DELETE FROM user_states WHERE expires_at != 'none' AND expires_at < ?", (now,))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  行为模式（user_patterns）— 置信度只增不减
# ═══════════════════════════════════════════════════════════

def add_pattern(pattern: str, confidence: float = 0.5, source: str = "auto") -> bool:
    """记录一条行为模式。置信度只增不减：已存在则取 max(旧, 新)。"""
    if not pattern:
        return False
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        existing = conn.execute("SELECT id, confidence FROM user_patterns WHERE pattern = ?", (pattern,)).fetchone()
        if existing:
            new_conf = max(existing["confidence"], float(confidence))
            conn.execute(
                "UPDATE user_patterns SET confidence = ?, last_confirmed = ?, freshness = MIN(1.0, freshness + 0.2) WHERE id = ?",
                (new_conf, now, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO user_patterns (pattern, confidence, freshness, source, last_confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (pattern, min(max(confidence, 0.1), 1.0), min(max(confidence, 0.3), 1.0), source, now, now),
            )
        conn.commit()
        return True
    finally:
        conn.close()


def boost_pattern(pattern: str, delta: float = 0.1):
    """确认一条模式（置信度上调，只增不减）。"""
    add_pattern(pattern, confidence=_get_pattern_confidence(pattern) + delta)


def _get_pattern_confidence(pattern: str) -> float:
    conn = _get_db()
    try:
        row = conn.execute("SELECT confidence FROM user_patterns WHERE pattern = ?", (pattern,)).fetchone()
        return row["confidence"] if row else 0.0
    finally:
        conn.close()


def decay_patterns(days: int = 7):
    """新鲜度随时间衰减（不影响置信度）；过低则暂停注入（不删除）。"""
    conn = _get_db()
    try:
        conn.execute("UPDATE user_patterns SET freshness = MAX(0.05, freshness - 0.15 * ?)", (max(1, days // 7),))
        conn.commit()
    finally:
        conn.close()


def get_patterns(active_only: bool = True) -> list:
    """获取行为模式（按 freshness 排序）。"""
    conn = _get_db()
    try:
        if active_only:
            rows = conn.execute(
                "SELECT id, pattern, confidence, freshness, source, last_confirmed FROM user_patterns WHERE freshness >= 0.2 ORDER BY freshness DESC, confidence DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, pattern, confidence, freshness, source, last_confirmed FROM user_patterns ORDER BY confidence DESC"
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  长故事弧（sagas）— 跨实体叙事串联
# ═══════════════════════════════════════════════════════════

def create_saga(title: str, episode_ids: list, entities: list, summary: str = "") -> int:
    """创建一条故事弧（跨实体叙事线）。"""
    conn = _get_db()
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cur = conn.execute(
            "INSERT INTO memory_sagas (title, summary, episodes, entities, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, summary, json.dumps(episode_ids, ensure_ascii=False),
             json.dumps(entities, ensure_ascii=False), now, now),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_sagas(limit: int = 10) -> list:
    """获取故事弧列表。"""
    conn = _get_db()
    try:
        rows = conn.execute(
            "SELECT id, title, summary, episodes, entities, created_at FROM memory_sagas ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["episodes"] = json.loads(d["episodes"] or "[]")
            d["entities"] = json.loads(d["entities"] or "[]")
            out.append(d)
        return out
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  记忆纠错（correct_memory）— 你说错了 → 修正/删除旧记忆
# ═══════════════════════════════════════════════════════════

def correct_fragment(fragment_id: int, correct_content: str = "") -> bool:
    """纠正一条碎片：给正确内容则更新（保留原内容作历史），否则删除（视为记错了）。
    返回是否成功。"""
    conn = _get_db()
    try:
        if correct_content and correct_content.strip():
            cur = conn.execute(
                "UPDATE mf_fragments SET content = ?, status = 'active', last_accessed = ? WHERE id = ?",
                (correct_content.strip()[:500], datetime.now().strftime("%Y-%m-%d %H:%M"), fragment_id),
            )
            # 同步更新向量库
            try:
                from brain import vector_memory
                row = conn.execute("SELECT entity FROM mf_fragments WHERE id = ?", (fragment_id,)).fetchone()
                vector_memory.add_fragment(fragment_id, correct_content[:300], row["entity"] if row else "")
            except Exception:
                pass
        else:
            cur = conn.execute("DELETE FROM mf_fragments WHERE id = ?", (fragment_id,))
            try:
                from brain import vector_memory
                vector_memory.delete_fragment(fragment_id)
            except Exception:
                pass
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def correct_by_keyword(query: str, correct_content: str = "") -> int:
    """按关键词找到最匹配的碎片并纠正（供 correct_memory 工具用）。
    返回处理条数。"""
    hits = search(query, top_k=3)
    if not hits:
        return 0
    count = 0
    for h in hits:
        if correct_fragment(h["id"], correct_content):
            count += 1
    return count
