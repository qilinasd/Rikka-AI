"""
RikkaAI - 记忆层升级包（Phase 1）

新增/叠加在既有 memory_vault 之上的能力，全部受 features 开关控制、可独立回滚：
  - markdown_store : Markdown 真源镜像 + git 版本化（可迁移/可 obsidian / 归你所有）
  - tags           : 正交多维标签（user/agent/app/project/session）
  - surprise       : surprise 加权遗忘（越意外越记得牢）
  - gap            : gap analysis（告诉契约者"我还不知道什么"）
  - wiki           : 知识 wiki（自动把高价值信息编成可编辑 Markdown 百科）

统一用 rikkai.db 的既有表（mf_fragments / mf_episodes / mf_entities）作为唯数据源，
不另起炉灶、不动主存储。
"""
import os
import sqlite3

import config as cfg


def db_path() -> str:
    return os.path.join(cfg.USER_CONFIG_DIR, "rikkai.db")


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def markdown_root() -> str:
    return os.path.join(cfg.USER_CONFIG_DIR, "memory_markdown")
