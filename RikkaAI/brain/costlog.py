"""
RikkaAI - 执行记录 & Token 用量核算（costlog）

记录每次 LLM 调用与工具调用的 token 用量与耗时，追加写入
memory_data/costlog.jsonl。用于：
  - 观察六花每轮/每天花了多少 token
  - 诊断哪些工具/模型调用最频繁

纯本地、线程安全、完全受 features.is_enabled("costlog_enabled") 控制。
开启前不写任何文件；关闭时 record_* 直接返回，零开销。
"""
import json
import os
import threading
import time
from datetime import datetime

import config as cfg

_lock = threading.Lock()


def _costlog_path() -> str:
    d = os.path.join(cfg.USER_CONFIG_DIR, "costlog")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "costlog.jsonl")


def _append(record: dict):
    with _lock:
        try:
            with open(_costlog_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass


def record_llm(model: str, prompt_tokens: int, completion_tokens: int,
               ms: int = 0, cost_usd: float | None = None, meta: dict | None = None):
    """记录一次 LLM 调用。cost_usd 只有在调用方拿到真实账单时才给；默认记 0（只记用量）。"""
    if not cfg.get_upgrade_flag("costlog_enabled", True):
        return
    _append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kind": "llm",
        "model": model,
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int((prompt_tokens or 0) + (completion_tokens or 0)),
        "cost_usd": round(float(cost_usd or 0), 6),
        "ms": int(ms or 0),
        "meta": meta or {},
    })


def record_tool(name: str, status: str, ms: int = 0, meta: dict | None = None):
    """记录一次工具调用（本身不耗 token，仅记耗时/状态，用于成本回放与诊断）。"""
    if not cfg.get_upgrade_flag("costlog_enabled", True):
        return
    _append({
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kind": "tool",
        "name": name,
        "status": status,
        "cost_usd": 0.0,
        "ms": int(ms or 0),
        "meta": meta or {},
    })


def reset():
    """清空成本记录。"""
    with _lock:
        try:
            p = _costlog_path()
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def get_totals() -> dict:
    """聚合当前成本记录：总 token、总成本、LLM/工具调用次数、按模型拆解。"""
    p = _costlog_path()
    if not os.path.exists(p):
        return {"calls": 0, "llm_calls": 0, "tool_calls": 0, "total_tokens": 0,
                "cost_usd": 0.0, "by_model": {}, "by_tool": {}}
    totals = {"calls": 0, "llm_calls": 0, "tool_calls": 0, "total_tokens": 0,
              "cost_usd": 0.0, "by_model": {}, "by_tool": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                totals["calls"] += 1
                totals["cost_usd"] += float(r.get("cost_usd", 0) or 0)
                if r.get("kind") == "llm":
                    totals["llm_calls"] += 1
                    totals["total_tokens"] += int(r.get("total_tokens", 0) or 0)
                    m = r.get("model", "?")
                    bm = totals["by_model"].setdefault(m, {"calls": 0, "tokens": 0, "cost_usd": 0.0})
                    bm["calls"] += 1
                    bm["tokens"] += int(r.get("total_tokens", 0) or 0)
                    bm["cost_usd"] += float(r.get("cost_usd", 0) or 0)
                elif r.get("kind") == "tool":
                    totals["tool_calls"] += 1
                    t = r.get("name", "?")
                    bt = totals["by_tool"].setdefault(t, {"calls": 0})
                    bt["calls"] += 1
    except Exception:
        pass
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return totals


def get_recent(n: int = 50) -> list:
    """最近 n 条记录（从后往前）。"""
    p = _costlog_path()
    if not os.path.exists(p):
        return []
    out = []
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = [l for l in f if l.strip()]
        for line in lines[-n:]:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out
