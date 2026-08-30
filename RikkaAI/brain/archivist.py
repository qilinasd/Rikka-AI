"""
RikkaAI - Archivist 记忆档案员（对齐 MemoryConstellations 的叙事归并自动化）

两层调度：
- 轻量层（每 2 分钟 tick，不调 LLM）：
  1. 生命周期推进（active → cooling → frozen → tombstone）
  2. 合并重复实体
  3. 未归并碎片按实体挂载到 episodes（简单拼接，作为深度层的候选池）
- 深度层（闲置 ≥1 小时 或 新碎片 ≥10 条时触发，调 LLM）：
  1. 把同一实体/主题的孤儿碎片交给 LLM 重写成连贯叙事段落（带日期纠正、矛盾检测提示）
  2. 重新生成实体三字段画像（facts / current_status / judgment）
  3. 全部成功时把碎片标记归并，避免重复整合
"""

import json
import os
import re
import time
import sqlite3
from collections import defaultdict
from datetime import datetime

from openai import OpenAI

import config as cfg
from brain import memory_vault as mv

_DEEP_IDLE_MINUTES = 60      # 闲置超过 60 分钟触发深度层
_DEEP_MIN_NEW_FRAGMENTS = 10 # 新碎片积累超过 10 条也触发
_LIGHT_INTERVAL = 120        # 轻量层每 2 分钟跑一次（由 main_window 定时器驱动）

# 深度层运行锁：防止定时器并发触发重复归并
_deep_lock = False


def _get_db():
    db_path = os.path.join(cfg.USER_CONFIG_DIR, "rikkai.db")
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _get_orphan_fragments(limit=50):
    """取还没归入任何 episode 的碎片（按实体分组候选）。"""
    conn = _get_db()
    try:
        rows = conn.execute("""
            SELECT f.id, f.entity, f.content, f.category, f.emotional_weight, f.keywords, f.created_at
            FROM mf_fragments f
            LEFT JOIN mf_fragment_episode fe ON f.id = fe.fragment_id
            WHERE fe.episode_id IS NULL AND f.status != 'tombstone'
            ORDER BY f.created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _count_unmerged():
    conn = _get_db()
    try:
        row = conn.execute("""
            SELECT COUNT(*) AS c FROM mf_fragments f
            LEFT JOIN mf_fragment_episode fe ON f.id = fe.fragment_id
            WHERE fe.episode_id IS NULL AND f.status != 'tombstone'
        """).fetchone()
        return row["c"] if row else 0
    finally:
        conn.close()


def _last_activity_ts():
    """最近一次对话活动时间（从 sessions 表取最近消息时间；无则用当前时间避免误触发）。"""
    conn = _get_db()
    try:
        has = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        ).fetchone()
        if not has:
            return time.time()
        row = conn.execute(
            "SELECT MAX(created_at) AS t FROM messages"
        ).fetchone()
        t = row["t"] if row and row["t"] else None
        if not t:
            return time.time()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(t, fmt).timestamp()
            except (ValueError, TypeError):
                continue
        return time.time()
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════
#  轻量层 — 每 2 分钟（免费、无 LLM）
# ═══════════════════════════════════════════════════════════

def light_tick() -> dict:
    """轻量层（每 2 分钟，免费、无 LLM）：生命周期推进 + 实体合并 + 状态过期。
    叙事归并留给深度层（LLM 重写），轻量层不抢碎片，保证深度层有料可并。"""
    result = {"lifecycle": 0, "merged_entities": 0, "expired_states": 0, "unmerged": 0}
    try:
        result["lifecycle"] = mv.run_lifecycle()
    except Exception:
        pass
    try:
        result["merged_entities"] = mv.merge_duplicate_entities()
    except Exception:
        pass
    try:
        result["expired_states"] = mv.expire_states()  # 用户状态 TTL 自动过期
    except Exception:
        pass
    try:
        result["unmerged"] = _count_unmerged()
    except Exception:
        pass
    return result


# ═══════════════════════════════════════════════════════════
#  深度层 — 闲置 / 碎片积累时（LLM 重写叙事 + 实体画像）
# ═══════════════════════════════════════════════════════════

def _llm_write_narrative(entity: str, contents: list) -> str:
    """让 LLM 把一组碎片重写成连贯叙事段落（带日期纠正/矛盾检测提示）。
    含 2 次重试（API 偶发返回空 content 时重试）。"""
    for attempt in range(3):
        try:
            client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
            resp = client.chat.completions.create(
                model=cfg.MODEL,
                messages=[{"role": "user", "content": (
                    "把下面关于同一主题的记忆碎片，重写成一段连贯的第三人称叙事（150~250 字中文）。\n"
                    "要求：\n"
                    "1. 有前因后果和情绪脉络，读起来像一段完整的故事，不是列表拼接\n"
                    "2. 如果碎片间存在矛盾（比如一条说 A 一条说 B），挑更近时间的那条，并在结尾用「（注：…）」标出矛盾点\n"
                    "3. 如果碎片提到时间，尽量理顺先后顺序\n"
                    "4. 不要编造碎片里没有的信息\n\n"
                    "主题：{entity}\n碎片：\n{contents}"
                ).format(entity=entity, contents="\n".join(f"- {c}" for c in contents))}],
                temperature=0.5, max_tokens=600,
            )
            text = (resp.choices[0].message.content or "").strip()
            if len(text) > 30:
                return text[:800]
        except Exception as e:
            import sys as _s
            if attempt == 2:
                print(f"[archivist] narrative error: {e}", file=_s.stderr)
    return ""


def _extract_json(text: str):
    """从 LLM 回复中提取 JSON（兼容 ```json 代码块围栏 / 纯对象 / 数组）。"""
    if not text:
        return None
    t = text.strip()
    # 剥掉 markdown 代码块围栏
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            return None
    m2 = re.search(r"\[.*\]", t, re.DOTALL)
    if m2:
        try:
            return json.loads(m2.group())
        except Exception:
            return None
    return None


def _llm_entity_overview(entity: str, frags: list) -> dict:
    """让 LLM 重新生成实体三字段画像。返回 {facts, current_status, judgment, entity_type}。
    含 2 次重试（API 偶发返回空 content 时重试）。"""
    for attempt in range(3):
        try:
            client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
            contents = "\n".join(f"- {f['content']}" for f in frags[:12])
            resp = client.chat.completions.create(
                model=cfg.MODEL,
                messages=[{"role": "user", "content": (
                    "根据关于「" + entity + "」的记忆碎片，生成结构化画像，返回 JSON：\n"
                    '{"facts":"客观事实，稳定可验证的信息（新事实覆盖旧事实）",'
                    '"current_status":"最近的动态/变化，一句话",'
                    '"judgment":"六花对这个实体/人物的主观印象与感受",'
                    '"entity_type":"人物|地点|事物|概念|偏好|事件"}\n'
                    "碎片：\n" + contents
                )}],
                temperature=0.3, max_tokens=400,
            )
            data = _extract_json(resp.choices[0].message.content or "")
            if data and isinstance(data, dict):
                return {
                    "facts": str(data.get("facts") or ""),
                    "current_status": str(data.get("current_status") or ""),
                    "judgment": str(data.get("judgment") or ""),
                    "entity_type": str(data.get("entity_type") or ""),
                }
        except Exception as e:
            import sys as _sys
            if attempt == 2:
                print(f"[archivist] _llm_entity_overview error: {e}", file=_sys.stderr)
    return {}


def _upsert_entity_fields(conn, name: str, facts: str = None, current_status: str = None,
                          judgment: str = None, entity_type: str = None):
    """在给定连接的事务内更新实体三字段（供深度层复用同一 conn，避免跨连接写锁）。"""
    if not name:
        return
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


def _run_deep_cycle() -> dict:
    """深度层：LLM 叙事归并 + 实体画像再生。"""
    global _deep_lock
    if _deep_lock:
        return {"skipped": "already_running"}
    _deep_lock = True
    try:
        result = {"episodes": 0, "entities": 0}
        orphans = _get_orphan_fragments(limit=50)
        if len(orphans) < 3:
            return result

        groups = defaultdict(list)
        for o in orphans:
            groups[o["entity"] or "其他"].append(o)

        conn = _get_db()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            for entity, frags in groups.items():
                if len(frags) < 2:  # 2 条即可归并（碎片分布不均时也能成段）
                    continue
                contents = [f["content"] for f in frags if f["content"]]
                if len(contents) < 2:
                    continue

                # 1) LLM 重写叙事段落
                narrative = _llm_write_narrative(entity, contents[:10])
                if not narrative:
                    continue
                avg_ew = sum(f["emotional_weight"] for f in frags) / len(frags)
                cur = conn.execute(
                    "INSERT INTO mf_episodes (title, content, entities, emotional_weight, source_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (f"关于{entity}", narrative, json.dumps([entity], ensure_ascii=False),
                     round(avg_ew, 2), frags[0]["created_at"], now),
                )
                eid = cur.lastrowid
                for f in frags:
                    conn.execute("INSERT OR IGNORE INTO mf_fragment_episode (fragment_id, episode_id) VALUES (?, ?)",
                                 (f["id"], eid))
                result["episodes"] += 1

                # 2) 实体画像再生（用同一 conn，避免跨连接写锁）
                overview = _llm_entity_overview(entity, frags)
                if overview:
                    _upsert_entity_fields(
                        conn, entity,
                        facts=overview.get("facts") or None,
                        current_status=overview.get("current_status") or None,
                        judgment=overview.get("judgment") or None,
                        entity_type=overview.get("entity_type") or None,
                    )
                    result["entities"] += 1

            # 3) 行为模式聚类：从「偏好/喜欢/兴趣/习惯」类碎片提取长期规律（置信度只增不减）
            try:
                _extract_patterns(conn)
            except Exception as _e:
                import sys as _s
                print(f"[archivist] patterns error: {_e}", file=_s.stderr)

            conn.commit()
        finally:
            conn.close()

        # 4) 长故事弧：独立调度（每轮 deep 后都检查，episodes ≥2 即可串，不依赖本轮碎片量）
        try:
            _run_saga_tick()
        except Exception:
            pass

        return result
    finally:
        _deep_lock = False


def _run_saga_tick():
    """故事弧调度：只要 episodes ≥2 就尝试串联（跨实体/同实体叙事线）。"""
    conn = _get_db()
    try:
        _build_sagas(conn)
        conn.commit()
    finally:
        conn.close()


def _extract_patterns(conn):
    """从偏好类碎片提取行为模式（本地 bigram/关键词聚类，不调 LLM 也能跑）。"""
    try:
        rows = conn.execute(
            "SELECT id, content, entity FROM mf_fragments WHERE (category LIKE '%偏好%' OR category LIKE '%喜好%' OR category LIKE '%喜欢%' OR category LIKE '%兴趣%' OR content LIKE '%喜欢%' OR content LIKE '%习惯%' OR content LIKE '%偏好%') AND status != 'tombstone' ORDER BY id DESC LIMIT 30"
        ).fetchall()
        if len(rows) < 2:
            return
        # 简单聚类：相同实体 + 出现 ≥2 次的动词短语 → 模式
        from collections import Counter
        candidates = []
        for r in rows:
            content = str(r["content"] or "")
            # 提取「喜欢/偏好/习惯」后面的短语
            for kw in ("喜欢", "偏好", "最爱", "习惯"):
                if kw in content:
                    tail = content.split(kw, 1)[1].strip("，。、 ：:；;")
                    if 2 <= len(tail) <= 20:
                        candidates.append((str(r["entity"] or "契约者"), kw + tail))
                    break
        counts = Counter(candidates)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for (entity, phrase), cnt in counts.items():
            if cnt >= 1:  # 出现即记录（置信度按次数）
                confidence = min(0.9, 0.4 + 0.15 * cnt)
                pattern = f"{entity} {phrase}"
                existing = conn.execute("SELECT id, confidence FROM user_patterns WHERE pattern = ?", (pattern,)).fetchone()
                if existing:
                    new_conf = max(existing["confidence"], confidence)
                    conn.execute(
                        "UPDATE user_patterns SET confidence = ?, last_confirmed = ?, freshness = MIN(1.0, freshness + 0.2) WHERE id = ?",
                        (new_conf, now, existing["id"]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO user_patterns (pattern, confidence, freshness, source, last_confirmed, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (pattern, confidence, confidence, "auto", now, now),
                    )
    except Exception:
        pass


def _build_sagas(conn):
    """把实体相近的 episodes 串成故事弧（跨实体叙事线）。"""
    try:
        rows = conn.execute(
            "SELECT id, title, content, entities FROM mf_episodes ORDER BY id DESC LIMIT 20"
        ).fetchall()
        if len(rows) < 2:
            return
        # 简单串联：取最新 N 个 episodes，按共同实体聚合 → 生成一条总 saga（每轮最多 1 条，避免泛滥）
        latest = [dict(r) for r in rows[:8]]
        entities = set()
        for e in latest:
            try:
                ents = json.loads(e.get("entities") or "[]")
                entities.update(str(x) for x in ents if x)
            except Exception:
                pass
        if len(entities) < 1:
            return
        existing = conn.execute("SELECT COUNT(*) AS c FROM memory_sagas").fetchone()["c"]
        if existing > 3:  # 控制 saga 数量，不无限增长
            return
        title = "与「" + "、".join(list(entities)[:3]) + "」相关的故事"
        summary = "；".join(str(e["title"]) for e in latest[:3])
        eids = [int(e["id"]) for e in latest]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute(
            "INSERT INTO memory_sagas (title, summary, episodes, entities, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (title, summary[:400], json.dumps(eids, ensure_ascii=False),
             json.dumps(sorted(entities)[:8], ensure_ascii=False), now, now),
        )
    except Exception:
        pass


def should_run_deep() -> dict:
    """判断是否该跑深度层（不执行）。返回 {due: bool, reason: str, unmerged, idle_min}。"""
    try:
        unmerged = _count_unmerged()
        if unmerged >= _DEEP_MIN_NEW_FRAGMENTS:
            return {"due": True, "reason": "fragments", "unmerged": unmerged}
        idle_min = (time.time() - _last_activity_ts()) / 60.0
        if idle_min >= _DEEP_IDLE_MINUTES and unmerged >= 3:
            return {"due": True, "reason": "idle", "unmerged": unmerged, "idle_min": round(idle_min, 1)}
        return {"due": False, "reason": "not_due", "unmerged": unmerged, "idle_min": round(idle_min, 1)}
    except Exception:
        return {"due": False, "reason": "error"}


def get_archivist_stats() -> dict:
    """Archivist 状态（供调试/界面展示）。"""
    try:
        return {
            "unmerged": _count_unmerged(),
            "deep_idle_minutes": _DEEP_IDLE_MINUTES,
            "deep_min_new_fragments": _DEEP_MIN_NEW_FRAGMENTS,
            "light_interval_sec": _LIGHT_INTERVAL,
            "active_fragments": mv.get_active_fragment_count(),
            "active_states": len(mv.get_active_states()),
            "patterns": len(mv.get_patterns(active_only=False)),
            "sagas": len(mv.get_sagas(limit=50)),
        }
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════
#  🆕 Phase 4: Sleep-time Compute — 深度后台反思
# ═══════════════════════════════════════════════════════════

def _resolve_sleep_compute_llm():
    """解析 Sleep-time Compute 实际使用的模型配置。

    优先级：设置页选中的模型方案（model_preset）→ 旧版 settings.model → 全局 cfg。
    """
    model, api_key, api_base = cfg.MODEL, cfg.API_KEY, cfg.API_BASE
    try:
        settings = cfg.get_sleep_compute_settings()
    except Exception:
        settings = {}
    if isinstance(settings, dict):
        preset = settings.get("model_preset")
        if isinstance(preset, dict):
            model = preset.get("model") or model
            api_key = preset.get("api_key") or api_key
            api_base = preset.get("api_base") or api_base
        elif settings.get("model"):
            model = settings["model"]
    return model, api_key, api_base


def sleep_time_consolidation(lookback_days=7):
    """后台反思：每天 23 点运行，整合记忆

    使用设置页配置的模型（默认跟随主对话模型）进行深度反思：
    - 识别重复或矛盾的记忆
    - 提取长期行为模式
    - 生成连贯的叙事段落

    Args:
        lookback_days: 回溯天数（默认7天）
    """
    print(f"[Sleep-time Compute] 开始后台反思（回溯 {lookback_days} 天）", flush=True)

    conn = _get_db()
    try:
        # 1. 获取最近 N 天的所有 active/cooling 碎片
        fragments = conn.execute(
            """SELECT id, entity, content, category, emotional_weight, created_at
               FROM mf_fragments
               WHERE created_at >= datetime('now', '-' || ? || ' days')
               AND status IN ('active', 'cooling')
               ORDER BY created_at DESC""",
            (lookback_days,)
        ).fetchall()

        if len(fragments) < 10:
            print(f"[Sleep-time Compute] 碎片数量不足（{len(fragments)} < 10），跳过整合", flush=True)
            return

        print(f"[Sleep-time Compute] 找到 {len(fragments)} 条碎片，开始反思...", flush=True)

        # 2. 构造反思 prompt
        frag_summary = "\n".join(
            f"[{f['created_at']}] {f['entity']}: {f['content'][:100]}"
            for f in fragments[:50]  # 最多分析前 50 条
        )

        reflection_prompt = f"""你是六花的记忆整合 Agent。请分析最近 {lookback_days} 天的记忆碎片，提取：

【记忆碎片】
{frag_summary}

【任务】
1. **to_merge**: 识别重复或矛盾的记忆，标记待合并/删除
   - 格式: {{"id1": 123, "id2": 456, "reason": "内容重复"}}

2. **patterns**: 提取长期模式（用户习惯、行为规律）
   - 例如: "用户每周二开会", "用户喜欢简洁回复"

3. **episodes**: 生成 2-3 条叙事段落（episode），连贯描述重要事件
   - 格式: {{"title": "...", "content": "..."}}

输出严格的 JSON 格式：
{{
  "to_merge": [
    {{"id1": 123, "id2": 456, "reason": "内容重复"}}
  ],
  "patterns": [
    "用户每周二开会",
    "用户喜欢简洁回复"
  ],
  "episodes": [
    {{"title": "这周的学习计划", "content": "契约者这周在学习 Python..."}}
  ]
}}

如果某项为空，返回空数组。"""

        # 3. 调用记忆整合模型（设置页的模型方案优先，回退全局配置）
        model, api_key, api_base = _resolve_sleep_compute_llm()
        print(f"[Sleep-time Compute] 使用模型: {model}", flush=True)
        try:
            client = OpenAI(api_key=api_key, base_url=api_base)
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.3,
                max_tokens=2000,
            )

            result_text = response.choices[0].message.content or "{}"

            # 提取 JSON（可能被 markdown 包裹）
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if not json_match:
                print(f"[Sleep-time Compute] 无法解析 LLM 返回结果", flush=True)
                return

            result = json.loads(json_match.group())

            # 4. 应用整合结果
            _apply_consolidation_result(conn, result)

            print(f"[Sleep-time Compute] ✅ 完成反思：", flush=True)
            print(f"  - 合并 {len(result.get('to_merge', []))} 组重复记忆", flush=True)
            print(f"  - 提取 {len(result.get('patterns', []))} 个行为模式", flush=True)
            print(f"  - 生成 {len(result.get('episodes', []))} 条叙事", flush=True)

        except Exception as e:
            print(f"[Sleep-time Compute] LLM 调用失败: {e}", flush=True)

    finally:
        conn.close()


def _apply_consolidation_result(conn, result: dict):
    """应用整合结果"""
    # 1. 合并重复记忆（标记为 tombstone）
    for merge in result.get("to_merge", []):
        try:
            id1 = merge.get("id1")
            id2 = merge.get("id2")
            reason = merge.get("reason", "重复")

            if id1 and id2:
                # 保留较早的记忆，删除较晚的
                conn.execute(
                    "UPDATE mf_fragments SET status = 'tombstone' WHERE id = ?",
                    (max(id1, id2),)
                )
                print(f"  [Merge] 合并记忆 {id1}/{id2}: {reason}", flush=True)
        except Exception:
            pass

    # 2. 更新行为模式
    for pattern in result.get("patterns", []):
        try:
            if not pattern or len(pattern) < 5:
                continue

            # 检查是否已存在
            existing = conn.execute(
                "SELECT confidence FROM user_patterns WHERE pattern = ?",
                (pattern,)
            ).fetchone()

            if existing:
                # 提升置信度
                conn.execute(
                    "UPDATE user_patterns SET confidence = MIN(confidence + 0.1, 1.0), last_seen = CURRENT_TIMESTAMP WHERE pattern = ?",
                    (pattern,)
                )
            else:
                # 新建模式
                conn.execute(
                    "INSERT INTO user_patterns (pattern, confidence) VALUES (?, 0.7)",
                    (pattern,)
                )
            print(f"  [Pattern] 记录模式: {pattern}", flush=True)
        except Exception:
            pass

    # 3. 保存叙事段落
    for ep in result.get("episodes", []):
        try:
            title = ep.get("title", "")
            content = ep.get("content", "")

            if not content or len(content) < 10:
                continue

            conn.execute(
                """INSERT INTO mf_episodes (title, content, entities, emotional_weight, source_date, created_at)
                   VALUES (?, ?, '[]', 0.5, date('now'), datetime('now'))""",
                (title[:100], content[:2000])
            )
            print(f"  [Episode] 生成叙事: {title}", flush=True)
        except Exception:
            pass

    conn.commit()


def schedule_sleep_time_compute():
    """定时触发 Sleep-time Compute（每天 23 点）

    使用方式：
    1. 在 main.py 启动时调用此函数
    2. 会创建后台线程，定时检查并执行
    """
    import threading
    import time
    from datetime import datetime

    def _sleep_time_worker():
        """后台工作线程"""
        while True:
            try:
                # 读取配置
                settings = cfg.get_sleep_compute_settings()
                if not settings.get("enabled", True):
                    # 功能已禁用，休眠 30 分钟后再检查
                    time.sleep(1800)
                    continue

                now = datetime.now()
                exec_time = settings.get("execution_time", "23:00")
                try:
                    hour, minute = map(int, exec_time.split(":"))
                except:
                    hour, minute = 3, 0

                # 检查是否到达执行时间（±15分钟窗口）
                target_minutes = hour * 60 + minute
                current_minutes = now.hour * 60 + now.minute
                if abs(current_minutes - target_minutes) <= 15:
                    print(f"[Sleep-time Compute] 触发定时反思（{now.strftime('%Y-%m-%d %H:%M')}）", flush=True)

                    # 保存原始配置
                    original_model = cfg.MODEL
                    original_api_key = cfg.API_KEY
                    original_api_base = cfg.API_BASE

                    try:
                        # 应用方案配置
                        lookback = settings.get("lookback_days", 7)
                        model_preset = settings.get("model_preset")

                        if model_preset:
                            if model_preset.get("model"):
                                cfg.MODEL = model_preset["model"]
                            if model_preset.get("api_key"):
                                cfg.API_KEY = model_preset["api_key"]
                            if model_preset.get("api_base"):
                                cfg.API_BASE = model_preset["api_base"]
                        elif settings.get("model"):
                            # 兼容旧版只保存模型名的配置
                            cfg.MODEL = settings["model"]

                        sleep_time_consolidation(lookback_days=lookback)
                    finally:
                        # 恢复原始配置
                        cfg.MODEL = original_model
                        cfg.API_KEY = original_api_key
                        cfg.API_BASE = original_api_base

                    # 执行后休眠 2 小时，避免重复触发
                    time.sleep(7200)
                else:
                    # 非执行时段，每 30 分钟检查一次
                    time.sleep(1800)

            except Exception as e:
                print(f"[Sleep-time Compute] Worker 异常: {e}", flush=True)
                time.sleep(3600)  # 异常后休眠 1 小时

    # 启动后台线程
    worker = threading.Thread(target=_sleep_time_worker, daemon=True)
    worker.start()
    print("[Sleep-time Compute] 定时任务已启动（每天 23 点执行）", flush=True)

