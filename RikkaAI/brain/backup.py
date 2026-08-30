"""
RikkaAI - 数据备份（上线前新增）
启动时自动备份核心数据库 memory_data/rikkai.db（SQLite 在线安全备份 VACUUM INTO），
保留最近 N 份；同时备份 surf_records/history.json（冲浪记录）。

用法：
  from brain import backup
  backup.backup_all()      # 启动时调用，保留最近 10 份
  backup.list_backups()    # 查看备份列表
  backup.restore_latest()  # 手动恢复到最近一份（谨慎）
"""

import os
import shutil
import sqlite3
from datetime import datetime

import config

_BACKUP_DIR = os.path.join(config.MEMORY_DIR, "backups")
_KEEP = 10  # 保留最近 10 份


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _trim_backups():
    """删除超过保留份数的旧备份。"""
    try:
        entries = sorted(
            (d for d in os.listdir(_BACKUP_DIR) if d.startswith("rikkai_")),
            reverse=True,
        )
        for old in entries[_KEEP:]:
            shutil.rmtree(os.path.join(_BACKUP_DIR, old), ignore_errors=True)
    except Exception:
        pass


def backup_database() -> str:
    """SQLite 在线安全备份 rikkai.db（VACUUM INTO），返回备份目录路径。"""
    db_path = os.path.join(config.USER_CONFIG_DIR, "rikkai.db")
    if not os.path.exists(db_path):
        return ""
    try:
        os.makedirs(_BACKUP_DIR, exist_ok=True)
        stamp = _stamp()
        target_dir = os.path.join(_BACKUP_DIR, f"rikkai_{stamp}")
        os.makedirs(target_dir, exist_ok=True)
        target_db = os.path.join(target_dir, "rikkai.db")
        # SQLite 在线备份：无需关闭现有连接，一致性安全
        src = sqlite3.connect(db_path)
        try:
            dst = sqlite3.connect(target_db)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        # 附带备份冲浪记录（如有）
        history_json = os.path.join(config.SURF_DIR, "history.json")
        if os.path.exists(history_json):
            try:
                shutil.copy2(history_json, os.path.join(target_dir, "history.json"))
            except Exception:
                pass
        _trim_backups()
        return target_dir
    except Exception:
        return ""


def backup_all() -> str:
    """启动时调用：备份数据库 + 冲浪记录。返回备份目录（空串表示失败/无需备份）。"""
    return backup_database()


def list_backups() -> list:
    """列出所有备份（最新在前）。"""
    try:
        if not os.path.isdir(_BACKUP_DIR):
            return []
        return sorted(
            (d for d in os.listdir(_BACKUP_DIR) if d.startswith("rikkai_")),
            reverse=True,
        )
    except Exception:
        return []


def restore_latest() -> bool:
    """恢复到最近一份备份（覆盖当前数据库）。谨慎使用：先确认应用已停止。"""
    backups = list_backups()
    if not backups:
        return False
    latest = os.path.join(_BACKUP_DIR, backups[0])
    db_path = os.path.join(config.USER_CONFIG_DIR, "rikkai.db")
    src = os.path.join(latest, "rikkai.db")
    if not os.path.exists(src):
        return False
    try:
        shutil.copy2(src, db_path)
        return True
    except Exception:
        return False
