"""
RikkaAI - 自然语言定时自动化（Phase 2）

用一句话给六花安排长期任务（如"每晚23点生成日报""每周日21点写周记"）。
脚本引擎解析规则的 cron 描述，到点触发注册的动作。数据存 memory_data/scheduler.json。

gate: features.is_enabled("cron_enabled")
"""
import json
import os
import re
import threading
from datetime import datetime, timedelta

import config as cfg
from brain import features

_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
_LOCK = threading.Lock()


def _path():
    return os.path.join(cfg.USER_CONFIG_DIR, "scheduler.json")


def _load() -> list:
    if not os.path.exists(_path()):
        return []
    try:
        with open(_path(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(jobs):
    os.makedirs(cfg.USER_CONFIG_DIR, exist_ok=True)
    with open(_path(), "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=2)


def _normalize_hhmm(s):
    m = re.search(r"(\d{1,2})[:点时](\d{0,2})", str(s or ""))
    if not m:
        return "21:00"
    hh = int(m.group(1)) % 24
    mm = int(m.group(2) or 0)
    return f"{hh:02d}:{mm:02d}"


def parse_schedule(desc: str) -> dict:
    """解析一句话 → {kind, at, weekday}。kind ∈ daily / weekly / hourly。"""
    desc = (desc or "").strip()
    if not desc:
        return {"kind": "daily", "at": "21:00", "weekday": None}
    if re.search(r"每\s*\d+\s*小\s*时|every\s*\d+\s*hour", desc, re.I):
        m = re.search(r"每\s*(\d+)\s*小时", desc)
        return {"kind": "hourly", "hours": int(m.group(1)) if m else 1, "at": "", "weekday": None}
    weekday = next((w for w in _WEEKDAYS if w in desc), None)
    if "周" in desc and weekday:
        return {"kind": "weekly", "at": _normalize_hhmm(desc), "weekday": _WEEKDAYS.index(weekday)}
    if re.search(r"每天|每日|every\s+day", desc, re.I) or ("点" in desc and not weekday):
        return {"kind": "daily", "at": _normalize_hhmm(desc), "weekday": None}
    return {"kind": "daily", "at": _normalize_hhmm(desc), "weekday": None}


def add_job(desc: str, action: str, payload: dict = None) -> dict:
    if not features.is_enabled("cron_enabled"):
        return {"ok": False, "reason": "disabled"}
    sched = parse_schedule(desc)
    job = {
        "id": f"job_{int(datetime.now().timestamp() * 1000)}",
        "desc": desc,
        "action": action,
        "payload": payload or {},
        "enabled": True,
        "last_run": "",
        "next_run": "",
        **sched,
    }
    job["next_run"] = _compute_next(job).strftime("%Y-%m-%d %H:%M:%S")
    with _LOCK:
        jobs = _load()
        jobs.append(job)
        _save(jobs)
    return {"ok": True, "job": job}


def _compute_next(job) -> datetime:
    now = datetime.now()
    kind = job.get("kind", "daily")
    if kind == "hourly":
        hours = int(job.get("hours", 1) or 1)
        return now + timedelta(hours=hours)
    at = job.get("at") or "21:00"
    hh, mm = (int(x) for x in at.split(":"))
    base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if base <= now:
        base += timedelta(days=1)
    if kind == "weekly" and job.get("weekday") is not None:
        delta = (job["weekday"] - now.weekday()) % 7
        if delta == 0 and base <= now + timedelta(seconds=1):
            delta = 7
        # 找到下一个周X
        cand = datetime.combine(base.date(), base.time()) + timedelta(days=delta)
        if cand <= now:
            cand += timedelta(days=7)
        base = cand
    return base


def tick(handler) -> int:
    """到点但未运行的 job → 调 handler(job)。返回本次触发的数量。"""
    if not features.is_enabled("cron_enabled"):
        return 0
    now = datetime.now()
    fired = 0
    with _LOCK:
        jobs = _load()
        for j in jobs:
            if not j.get("enabled"):
                continue
            nxt = j.get("next_run", "")
            if not nxt:
                j["next_run"] = _compute_next(j).strftime("%Y-%m-%d %H:%M:%S")
                continue
            if nxt <= now.strftime("%Y-%m-%d %H:%M:%S"):
                try:
                    handler(j)
                    fired += 1
                except Exception:
                    pass
                j["last_run"] = now.strftime("%Y-%m-%d %H:%M:%S")
                j["next_run"] = _compute_next(j).strftime("%Y-%m-%d %H:%M:%S")
        _save(jobs)
    return fired


def list_jobs() -> list:
    return _load()
