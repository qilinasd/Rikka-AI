"""
RikkaAI - Markdown 真源记忆镜像 + git（Phase 1）

把 rikkai.db 里的记忆（碎片/段落/实体）导出成可读、可 diff、可 git、可迁移的
Markdown 文件夹：memory_data/memory_markdown/。
  - 归你所有：克隆/复制/删除即得或即失
  - 可直接用你习惯的编辑器/Obsidian 打开编辑
  - 支持 git init + commit（受控环境内），保留历史

gate: features.is_enabled("memory_markdown_enabled")
"""
import json
import os
import subprocess
from datetime import datetime

from brain.memory import conn, markdown_root
from brain import features

_MD_SUBDIRS = ["fragments", "episodes", "entities"]


def _safe(text: str) -> str:
    return str(text or "").replace("\n", " ")


def _write(path: str, lines: list):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def snapshot() -> dict:
    """导出一次快照。返回 {files, fragments, episodes, entities}。"""
    if not features.is_enabled("memory_markdown_enabled"):
        return {"files": 0, "fragments": 0, "episodes": 0, "entities": 0}
    root = markdown_root()
    for sub in _MD_SUBDIRS:
        os.makedirs(os.path.join(root, sub), exist_ok=True)

    c = conn()
    n = {"fragments": 0, "episodes": 0, "entities": 0}
    files = 0
    try:
        # 碎片
        fr = c.execute(
            "SELECT id, entity, content, category, emotional_weight, status, created_at "
            "FROM mf_fragments ORDER BY created_at DESC"
        ).fetchall()
        for r in fr:
            rec = dict(r)
            p = os.path.join(root, "fragments", f"fragment_{rec['id']:06d}.md")
            lines = [
                f"# 记忆碎片 #{rec['id']}",
                "",
                f"- 实体：{rec['entity']}",
                f"- 分类：{rec['category']}",
                f"- 情感权重：{rec['emotional_weight']}",
                f"- 状态：{rec['status']}",
                f"- 时间：{rec['created_at']}",
                "",
                _safe(rec["content"]),
            ]
            _write(p, lines)
            files += 1
        n["fragments"] = len(fr)

        # 叙事段落
        ep = c.execute("SELECT id, title, content, source_date, created_at FROM mf_episodes "
                       "ORDER BY created_at DESC").fetchall()
        for r in ep:
            rec = dict(r)
            p = os.path.join(root, "episodes", f"episode_{rec['id']:06d}.md")
            _write(p, [f"# {rec['title']}", "", f"- 时间：{rec['source_date'] or rec['created_at']}", "",
                       _safe(rec["content"])])
            files += 1
        n["episodes"] = len(ep)

        # 实体画像
        en = c.execute("SELECT name, entity_type, facts, current_status, judgment, mention_count, "
                       "last_seen, emotional_weight FROM mf_entities ORDER BY mention_count DESC").fetchall()
        for r in en:
            rec = dict(r)
            p = os.path.join(root, "entities", f"{_safe(rec['name'])}.md")
            _write(p, [
                f"# {rec['name']}（{rec['entity_type']}）",
                "",
                f"- 提及次数：{rec['mention_count']}",
                f"- 近况：{_safe(rec['current_status'])}",
                f"- 事实：{_safe(rec['facts'])}",
                f"- 评价：{_safe(rec['judgment'])}",
                f"- 情感权重：{rec['emotional_weight']}",
            ])
            files += 1
        n["entities"] = len(en)

        # 索引
        _write(os.path.join(root, "INDEX.md"), [
            "# RikkaAI 记忆仓库", "",
            f"- 导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- 碎片：{n['fragments']} ｜ 段落：{n['episodes']} ｜ 实体：{n['entities']}",
            "",
            "- fragments/ 记忆碎片（按 id）",
            "- episodes/  叙事段落",
            "- entities/  实体画像",
        ])
        files += 1
    finally:
        c.close()

    return {"files": files, **n}


def git_commit(message: str = "") -> dict:
    """在记忆仓库目录做 git init + commit（若未 init）。返回状态。"""
    if not features.is_enabled("memory_markdown_enabled"):
        return {"ok": False, "reason": "disabled"}
    root = markdown_root()
    if not os.path.isdir(root):
        return {"ok": False, "reason": "no snapshot"}
    try:
        if not os.path.isdir(os.path.join(root, ".git")):
            subprocess.run(["git", "init"], cwd=root, capture_output=True, timeout=20)
        subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True, timeout=20)
        msg = message or f"mem snapshot {datetime.now().strftime('%Y-%m-%d %H%M')}"
        r = subprocess.run(["git", "commit", "-m", msg], cwd=root,
                           capture_output=True, timeout=30, text=True)
        committed = (r.returncode == 0) or ("nothing to commit" in (r.stderr or ""))
        return {"ok": committed, "msg": (r.stderr or r.stdout or "").strip()[:200]}
    except Exception as e:
        return {"ok": False, "reason": str(e)[:120]}


def full_snapshot_and_commit() -> dict:
    """一步：导出 + git 提交。返回汇总。"""
    snap = snapshot()
    git = git_commit()
    return {**snap, "git": git}
