"""
RikkaAI - 知识 Wiki（Phase 1）

把高价值碎片自动整理成按实体/分类的可编辑 Markdown 百科页：
  memory_data/wiki/{分类}/{实体}.md
每页注明来源（source：chat/manual/archivist + 对应碎片 id），可回溯、可编辑、
可被六花当"知识库"检索。参考 CowAgent / EverOS 的 source-backed wiki。

gate: features.is_enabled("memory_wiki_enabled")
"""
import os
import re
from datetime import datetime

from brain.memory import conn, markdown_root
from brain import features

_TOP_MEM = 40       # 每个实体最多收多少条碎片
_MIN_WEIGHT = 0.35  # 低于此情感权重的碎片不进 wiki（保留精华）


def _slug(name: str) -> str:
    s = re.sub(r'[\\/:*?"<>|#\[\]]', "_", str(name or "").strip())
    return s[:64] or "uncategorized"


def _collect() -> list:
    """收集高价值碎片：按 (entity, category) 归组，取每条碎片。"""
    c = conn()
    try:
        rows = c.execute(
            "SELECT id, entity, content, category, emotional_weight, source, created_at "
            "FROM mf_fragments WHERE status='active' AND emotional_weight>=? "
            "ORDER BY emotional_weight DESC, created_at DESC LIMIT 2000",
            (_MIN_WEIGHT,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def build() -> dict:
    """重建 wiki。返回 {pages: n, files: [...]}。"""
    if not features.is_enabled("memory_wiki_enabled"):
        return {"pages": 0, "files": []}
    root = os.path.join(markdown_root(), "wiki")
    os.makedirs(root, exist_ok=True)
    # 清旧（只清 wiki 目录）
    for old in os.listdir(root):
        p = os.path.join(root, old)
        if os.path.isdir(p):
            import shutil
            shutil.rmtree(p, ignore_errors=True)
        else:
            os.remove(p)

    frags = _collect()
    # 按 entity 分组
    by_entity = {}
    for f in frags:
        ent = f["entity"] or "无主"
        by_entity.setdefault(ent, []).append(f)

    files = []
    for ent, items in by_entity.items():
        items = items[:_TOP_MEM]
        cat = items[0].get("category") or "日常"
        cat_dir = os.path.join(root, _slug(cat))
        os.makedirs(cat_dir, exist_ok=True)
        path = os.path.join(cat_dir, _slug(ent) + ".md")
        lines = [f"# {ent}", ""]
        if cat:
            lines.append(f"> 分类：{cat} ｜ 条数：{len(items)}")
            lines.append("")
        for it in items:
            src = it.get("source") or "chat"
            when = str(it.get("created_at") or "")[:16]
            lines.append(f"- [{it.get('id')}]（{src} · {when}） {str(it['content'])[:180]}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        files.append(path)

    return {"pages": len(files), "files": files}


def topic_search(query: str, top_k: int = 5) -> list:
    """在 wiki 里搜主题：返回命中的 md 路径列表（按内容关键词）。"""
    if not features.is_enabled("memory_wiki_enabled"):
        return []
    root = os.path.join(markdown_root(), "wiki")
    hits = []
    q = (query or "").strip()
    if not os.path.isdir(root) or not q:
        return hits
    for dirpath, _, names in os.walk(root):
        for name in names:
            if not name.endswith(".md"):
                continue
            p = os.path.join(dirpath, name)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                if q in content:
                    hits.append(p)
            except Exception:
                continue
            if len(hits) >= top_k:
                break
    return hits


def index() -> list:
    """wiki 文件清单（供 UI / 调试）。"""
    root = os.path.join(markdown_root(), "wiki")
    if not os.path.isdir(root):
        return []
    out = []
    for dirpath, _, names in os.walk(root):
        for name in names:
            if name.endswith(".md"):
                out.append(os.path.join(dirpath, name))
    return out
