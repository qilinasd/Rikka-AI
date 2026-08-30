"""
RikkaAI - 六花冲浪系统
搜索/浏览记录保存到 surf_records/（结构化 JSON + 兼容旧 md 文件）
"""

import json
import os
import re
import time
from datetime import datetime

import config

_HISTORY_LIMIT = 500
_SEEN_LIMIT = 1000


def _tag_cooldown_hours():
    return int(getattr(config, "SURF_TAG_COOLDOWN_HOURS", 48))


def _tag_decay_per_7_days():
    return int(getattr(config, "SURF_TAG_DECAY_PER_7_DAYS", 3))


class SurfStore:
    """六花的网上冲浪记录：结构化 JSON 存储，含历史记录、兴趣标签、去重与统计。

    参考莲心 BilibiliHistoryManager 的设计，做成通用冲浪记录：
    - history: 每次搜索/浏览一条记录（含可选 results 结果详情 + 用户反馈）
    - tags: 兴趣标签（基础分 + 加成 + 时间衰减 + 冷却 + 暂停）
    - seen: 已出现过的 url 去重
    """

    def __init__(self):
        self._path = os.path.join(config.SURF_DIR, "history.json")
        self._structured_available = False
        self._data = self._load()

    def _load(self):
        try:
            if os.path.exists(self._path):
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("history"), list):
                    if not isinstance(data.get("tags"), list):
                        data["tags"] = []
                    if not isinstance(data.get("seen"), list):
                        data["seen"] = []
                    self._structured_available = True
                    return data
        except Exception:
            pass
        return {"history": [], "seen": [], "tags": []}

    def _save(self):
        try:
            os.makedirs(config.SURF_DIR, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=1)
            self._structured_available = True
            return True
        except Exception:
            return False

    # ── 记录 ────────────────────────────────────────────────

    def add(self, source, tag, title, url="", detail="", results=None):
        """新增一条冲浪记录；results 为可选的搜索结果详情列表。"""
        record = {
            "id": f"surf_{int(time.time() * 1000)}",
            "time": datetime.now().isoformat(timespec="seconds"),
            "source": str(source),
            "tag": str(tag),
            "title": str(title),
            "url": str(url),
            "detail": str(detail),
            "results": [dict(r) for r in (results or [])],
            "reaction": "",
            "reaction_score": 0,
            "favorite": False,  # 收藏标记（设计稿「收藏记录」筛选 / 最近收藏面板）
        }
        self._data["history"].insert(0, record)
        if len(self._data["history"]) > _HISTORY_LIMIT:
            self._data["history"] = self._data["history"][:_HISTORY_LIMIT]
        seen_urls = [url]
        seen_urls.extend(item.get("url", "") for item in record["results"])
        for seen_url in seen_urls:
            seen_url = str(seen_url or "").strip()
            if seen_url and seen_url not in self._data["seen"]:
                self._data["seen"].append(seen_url)
        if len(self._data["seen"]) > _SEEN_LIMIT:
            self._data["seen"] = self._data["seen"][-_SEEN_LIMIT:]
        self._save()
        return record["id"]

    def records(self, limit=50, source=None, query=None, favorite_only=False):
        """读取冲浪记录：可按来源过滤、按关键词（标题/标签/详情/结果标题）搜索、只看收藏。"""
        rows = self._data["history"]
        if source:
            rows = [r for r in rows if r.get("source") == source]
        if favorite_only:
            rows = [r for r in rows if r.get("favorite")]
        if query:
            q = str(query).lower()
            matched = []
            for r in rows:
                haystack = " ".join(str(r.get(k) or "") for k in ("title", "tag", "detail"))
                if q in haystack.lower():
                    matched.append(r)
                    continue
                if any(q in str(x.get("title", "")).lower() for x in r.get("results", [])):
                    matched.append(r)
            rows = matched
        return rows[:limit]

    def toggle_favorite(self, record_id):
        """收藏/取消收藏一条记录。返回新状态。"""
        for rec in self._data["history"]:
            if rec.get("id") == record_id:
                rec["favorite"] = not rec.get("favorite", False)
                self._save()
                return rec["favorite"]
        return None

    def react_record(self, record_id, reaction):
        """更新一条记录的反馈；重复点击当前反馈会取消，并回滚标签分数。"""
        requested = reaction if reaction in ("liked", "disliked") else ""
        for rec in self._data["history"]:
            if rec.get("id") == record_id:
                previous = rec.get("reaction", "")
                if previous not in ("liked", "disliked"):
                    previous = ""
                reaction = "" if requested and requested == previous else requested

                liked = int(getattr(config, "SURF_REACTION_LIKED", 10))
                disliked = int(getattr(config, "SURF_REACTION_DISLIKED", 5))
                scores = {"": 0, "liked": liked, "disliked": -disliked}
                tag = rec.get("tag", "")
                tag_row = next(
                    (row for row in self._data.get("tags", []) if row.get("keyword") == tag),
                    None,
                )
                applied_score = 0
                if tag_row is not None:
                    try:
                        previous_score = int(rec["reaction_score"])
                    except (KeyError, TypeError, ValueError):
                        previous_score = scores[previous]
                    applied_score = scores[reaction]
                    tag_row["boost_score"] = (
                        int(tag_row.get("boost_score", 0))
                        + applied_score
                        - previous_score
                    )

                rec["reaction"] = reaction
                rec["reaction_score"] = applied_score
                self._save()
                return True
        return False

    def stats(self):
        from collections import Counter
        counter = Counter(r.get("source", "") for r in self._data["history"])
        return {
            "total": len(self._data["history"]),
            "by_source": dict(counter),
            "seen": len(self._data["seen"]),
            "tags": len(self._data.get("tags", [])),
            "favorites": sum(1 for r in self._data["history"] if r.get("favorite")),
        }

    def sources(self):
        return sorted({r.get("source", "") for r in self._data["history"]})

    def clear(self):
        self._data["history"] = []
        self._save()

    # ── 兴趣标签（参考莲心：分数 + 衰减 + 冷却 + 暂停） ────────

    def add_tag(self, keyword, base_score=50, source="auto"):
        keyword = str(keyword or "").strip()
        if not keyword:
            return
        for t in self._data["tags"]:
            if t["keyword"] == keyword:
                if t.get("status") == "paused":
                    t["status"] = "active"
                return
        self._data["tags"].append({
            "keyword": keyword,
            "base_score": int(base_score),
            "boost_score": 0,
            "status": "active",
            "source": source,
            "added_at": time.time(),
            "last_searched": 0,
        })
        self._save()

    def remove_tag(self, keyword):
        self._data["tags"] = [t for t in self._data["tags"] if t["keyword"] != keyword]
        self._save()

    def pause_tag(self, keyword):
        for t in self._data["tags"]:
            if t["keyword"] == keyword:
                t["status"] = "paused"
                self._save()
                return

    def resume_tag(self, keyword):
        for t in self._data["tags"]:
            if t["keyword"] == keyword:
                t["status"] = "active"
                self._save()
                return

    def update_tag_score(self, keyword, delta):
        for t in self._data["tags"]:
            if t["keyword"] == keyword:
                t["boost_score"] = t.get("boost_score", 0) + int(delta)
                self._save()
                return

    def get_tags(self, status=None):
        rows = self._data.get("tags", [])
        if status:
            rows = [t for t in rows if t.get("status", "active") == status]
        return rows

    def get_weighted_tags(self, limit=5):
        """按分数（含衰减）取权重最高的兴趣标签；冷却期内的跳过。"""
        now = time.time()
        cooldown_hours = _tag_cooldown_hours()
        decay_per_7_days = _tag_decay_per_7_days()
        scored = []
        for t in self._data.get("tags", []):
            if t.get("status") != "active":
                continue
            last = t.get("last_searched", 0)
            if last > 0 and (now - last) < cooldown_hours * 3600:
                continue
            base = t.get("base_score", 50)
            boost = t.get("boost_score", 0)
            added = t.get("added_at", now)
            decay = ((now - added) / 86400.0 / 7.0) * decay_per_7_days
            final = max(0, base + boost - decay)
            scored.append((t["keyword"], final))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in scored[:limit]]

    def get_surf_batch(self, max_tags=4):
        """挑一批本次冲浪要搜的标签：加权随机（分数越高越可能被挑中），
        并给每个标签分配视频条数配额——星级越高分到的越多（3★及以上 2 条，其余 1 条）。

        返回 [(keyword, quota), ...]；无可用标签时返回 []。
        """
        import random
        now = time.time()
        cooldown_hours = _tag_cooldown_hours()
        decay_per_7_days = _tag_decay_per_7_days()
        candidates = []
        for t in self._data.get("tags", []):
            if t.get("status") != "active":
                continue
            last = t.get("last_searched", 0)
            if last > 0 and (now - last) < cooldown_hours * 3600:
                continue
            base = t.get("base_score", 50)
            boost = t.get("boost_score", 0)
            added = t.get("added_at", now)
            decay = ((now - added) / 86400.0 / 7.0) * decay_per_7_days
            final = max(0, base + boost - decay)
            if final > 0:
                candidates.append((t["keyword"], final))
        if not candidates:
            return []
        # 加权随机抽 max_tags 个（不重复）
        picked = []
        pool = list(candidates)
        total_weight = sum(w for _, w in pool)
        for _ in range(min(max_tags, len(pool))):
            if total_weight <= 0:
                break
            r = random.uniform(0, total_weight)
            acc = 0
            for idx, (kw, w) in enumerate(pool):
                acc += w
                if r <= acc:
                    picked.append((kw, w))
                    total_weight -= w
                    pool.pop(idx)
                    break
        # 配额：星级 = 分数 // 20；>=3 星给 2 条，其余 1 条；再受 SURF_SEARCH_LIMIT 上限约束
        cap = int(getattr(config, "SURF_SEARCH_LIMIT", 2)) or 1
        result = []
        for kw, score in picked:
            stars = score // 20
            quota = 2 if stars >= 3 else 1
            result.append((kw, max(1, min(quota, cap))))
        return result

    def mark_tag_searched(self, keyword):
        for t in self._data.get("tags", []):
            if t["keyword"] == keyword:
                t["last_searched"] = time.time()
                self._save()
                return

    def unseen(self, urls):
        """过滤掉已经出现过的 url（主动冲浪的新鲜感去重）。"""
        seen = set(self._data.get("seen", []))
        return [u for u in (str(x or "").strip() for x in urls) if u and u not in seen]


_store = None


def get_store():
    global _store
    if _store is None:
        _store = SurfStore()
    return _store


def _format_play(play):
    """把播放量数字格式化成人类可读（26560 → 2.7万）。"""
    try:
        n = int(play)
    except (TypeError, ValueError):
        return str(play or "")
    if n >= 100000000:
        return f"{n / 100000000:.1f}亿"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


def _clean_html(text):
    import re as _re
    return _re.sub(r"<[^>]+>", "", text or "").strip()


def search_bilibili(keyword: str, limit: int = 5) -> list:
    """搜索B站视频 — 官方搜索接口优先，被风控时解析搜索页 HTML 兜底。

    返回结构：{bvid, title, url, author, play, description}（play 为格式化后的
    播放量字符串，如 "2.7万"）。
    """
    limit = int(limit) if limit else 5
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://search.bilibili.com/",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    # 官方搜索接口：返回干净 JSON（bvid/title/author/play/description）
    try:
        import requests
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={"search_type": "video", "keyword": keyword, "page": 1},
            headers=headers, timeout=15,
        )
        if resp.ok:
            data = resp.json()
            if data.get("code") == 0 and data.get("data", {}).get("result"):
                videos = []
                seen = set()
                for item in data["data"]["result"]:
                    bv = str(item.get("bvid") or "")
                    if not bv or bv in seen:
                        continue
                    seen.add(bv)
                    title = _clean_html(item.get("title"))
                    desc = _clean_html(item.get("description"))
                    if desc in ("", "-", "None", "null"):
                        desc = ""
                    videos.append({
                        "bvid": bv,
                        "title": title or f"B站: {keyword}",
                        "url": f"https://www.bilibili.com/video/{bv}",
                        "author": str(item.get("author") or ""),
                        "play": _format_play(item.get("play")),
                        "description": desc[:200],
                    })
                    if len(videos) >= limit:
                        break
                if videos:
                    return videos
    except Exception:
        pass

    # 兜底：解析搜索页 HTML（bili-video-card 卡片结构）
    html = ""
    try:
        import requests
        quoted = requests.utils.quote(keyword)
        resp = requests.get(
            f"https://search.bilibili.com/all?keyword={quoted}",
            headers=headers, timeout=15,
        )
        if resp.ok and resp.text:
            html = resp.text
    except Exception:
        pass

    if not html:
        try:
            import requests
            quoted = requests.utils.quote(keyword)
            resp = requests.get(
                f"https://r.jina.ai/https://search.bilibili.com/all?keyword={quoted}",
                headers={"User-Agent": "Mozilla/5.0"}, timeout=20,
            )
            if resp.ok:
                html = resp.text
        except Exception:
            pass

    videos = []
    seen = set()
    for blk in re.split(r'<div class="bili-video-card"', html or ""):
        if "/video/BV" not in blk:
            continue
        m = re.search(r"/video/(BV[0-9A-Za-z]+)", blk)
        if not m:
            continue
        bv = m.group(1)
        if bv in seen:
            continue
        seen.add(bv)
        tm = re.search(r'info--tit" title="([^"]*)"', blk)
        am = re.search(r'info--author"[^>]*>([^<]+)<', blk)
        pm = re.search(r'stats--item"[^>]*>.*?<span[^>]*>([0-9.,万亿]+)</span>', blk, re.S)
        videos.append({
            "bvid": bv,
            "title": _clean_html(tm.group(1)) if tm else f"B站: {keyword}",
            "url": f"https://www.bilibili.com/video/{bv}",
            "author": am.group(1).strip() if am else "",
            "play": pm.group(1).strip() if pm else "",
            "description": "",
        })
        if len(videos) >= limit:
            break
    return videos


def search_popular(limit: int = 3) -> list:
    """抓B站当前热门视频（官方 popular 接口，无需登录）。

    用途：兴趣标签为空/全在冷却时，主动冲浪的兜底话题源——
    六花没标签也能"逛热门"，而不是空手而归。
    返回结构与 search_bilibili 一致：{bvid, title, url, author, play, description}。"""
    limit = int(limit) if limit else 3
    headers = {
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Referer": "https://www.bilibili.com/",
    }
    try:
        import requests
        resp = requests.get(
            "https://api.bilibili.com/x/web-interface/popular",
            params={"ps": min(20, max(1, limit * 4))},
            headers=headers, timeout=15,
        )
        if resp.ok:
            data = resp.json()
            if data.get("code") == 0:
                videos = []
                seen = set()
                for item in (data.get("data", {}).get("list") or []):
                    bv = str(item.get("bvid") or "")
                    if not bv or bv in seen:
                        continue
                    seen.add(bv)
                    owner = item.get("owner") or {}
                    stat = item.get("stat") or {}
                    desc = _clean_html(item.get("desc") or "")
                    videos.append({
                        "bvid": bv,
                        "title": _clean_html(item.get("title")) or "B站热门视频",
                        "url": f"https://www.bilibili.com/video/{bv}",
                        "author": str(owner.get("name") or ""),
                        "play": _format_play(stat.get("view")),
                        "description": desc[:200],
                    })
                    if len(videos) >= limit:
                        break
                return videos
    except Exception:
        pass
    return []


def save_record(source: str, tag: str, title: str, url: str = "", detail: str = "", results=None):
    """保存冲浪记录：只写结构化 JSON（UI / 统计用）。
    纯 JSON 已是主数据源，不再双写旧 md 文件（已清理历史 md）。"""
    # 结构化记录（UI / 统计用）
    rec_id = get_store().add(source, tag, title, url, detail, results)
    return rec_id


def get_records(limit: int = 50, source: str = "", query: str = "", favorite_only: bool = False):
    """读取冲浪记录（仅结构化 JSON）。"""
    try:
        store = get_store()
        rows = store.records(limit=limit, source=source or None, query=query or None,
                             favorite_only=favorite_only)
        if store._structured_available:
            return rows
    except Exception:
        pass
    # 结构化 JSON 是唯一数据源，不再读取旧 md 文件（已清理历史 md）
    return []


def get_surf_stats() -> dict:
    """冲浪记录统计：总数 / 按来源分布 / 去重数。"""
    try:
        return get_store().stats()
    except Exception:
        return {"total": 0, "by_source": {}, "seen": 0}


def clear_records():
    """清空冲浪记录。"""
    try:
        get_store().clear()
        return True
    except Exception:
        return False


def react_record(record_id: str, reaction: str):
    """对一条冲浪记录反馈 👍/👎（liked/disliked），分数计入对应兴趣标签。"""
    try:
        return get_store().react_record(record_id, reaction)
    except Exception:
        return False


def toggle_favorite(record_id: str):
    """收藏/取消收藏一条冲浪记录。返回新状态（True/False/None）。"""
    try:
        return get_store().toggle_favorite(record_id)
    except Exception:
        return None
