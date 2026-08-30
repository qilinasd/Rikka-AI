"""
RikkaAI - 后台服务聚合启动（Phase 2 接入主链路的入口）

把三件后台循环统一启动：
  - DreamEngine     : 后台做梦/蒸馏（合并记忆、消解矛盾、更新画像、重建 markdown/wiki）
  - AutofetchEngine : 个人数据自动拉取（inbox 摄入）
  - scheduler 线程  : 定时自动化（"每天23点..."到点触发）

全部受特性开关控制；用 daemon 线程，随应用退出，不阻塞 Qt 主循环。
"""
import threading
import time
from datetime import datetime

from brain import features
from brain.dream import DreamEngine
from brain.autofetch import AutofetchEngine
from brain import scheduler
import config as cfg

_engines = {}
_lock = threading.Lock()
_scheduler_stop = threading.Event()
_sched_thread = None


def _default_dispatcher(job: dict):
    """定时任务分发：把已知 action 映射到既有能力（失败静默）。未知 action 只记录。
    如你希望不同 action 走不同逻辑，可在这里扩展或由 main_window 注册替代。"""
    action = str(job.get("action", "")).lower()
    now = datetime.now().strftime("%H:%M")
    try:
        if action in ("diary", "diary_summary", "日记", "总结"):
            # 日记自动收尾：通读当天流水 → LLM 写第一人称日记
            from brain import diary
            if hasattr(diary, "write_diary_summary"):
                diary.write_diary_summary()
        elif action in ("weekly", "周记", "周报"):
            from brain import memory_summary
            if hasattr(memory_summary, "build_weekly"):
                memory_summary.build_weekly()
        else:
            # surf/冲浪等动作依赖主窗口上下文（agent prompt），
            # 由 main_window 的 QTimer 驱动，cron 侧无对应处理器
            print(f"[Scheduler] 自动任务「{action}」@ {now}（无对应处理器，请注册）", flush=True)
    except Exception:
        pass


def _scheduler_loop():
    while not _scheduler_stop.wait(60):
        try:
            scheduler.tick(_default_dispatcher)
        except Exception:
            pass


def start_background_services() -> dict:
    """启动所有升级后台服务（各自受开关控制）。返回启动状态。"""
    started = {}
    with _lock:
        # 做梦
        if features.is_enabled("dream_enabled"):
            e = _engines.setdefault("dream", DreamEngine())
            started["dream"] = e.start()
        else:
            _engines.pop("dream", None)
            started["dream"] = False
        # 自动拉取
        if features.is_enabled("autofetch_enabled"):
            e = _engines.setdefault("autofetch", AutofetchEngine())
            started["autofetch"] = e.start()
        else:
            _engines.pop("autofetch", None)
            started["autofetch"] = False
        # 定时自动化
        if features.is_enabled("cron_enabled"):
            global _sched_thread
            if _sched_thread is None or not _sched_thread.is_alive():
                _scheduler_stop.clear()
                _sched_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="rikka-scheduler")
                _sched_thread.start()
                started["scheduler"] = True
            else:
                started["scheduler"] = True
        else:
            _scheduler_stop.set()
            started["scheduler"] = False
    return started


def stop_background_services():
    """停止所有后台服务（用于退出/测试）。"""
    _scheduler_stop.set()
    with _lock:
        for name, e in list(_engines.items()):
            try:
                e.stop()
            except Exception:
                pass
        _engines.clear()


def status() -> dict:
    """后台服务运行状态（调试/设置页）。"""
    out = {}
    with _lock:
        for name, e in _engines.items():
            th = getattr(e, "_thread", None)
            out[name] = bool(th is not None and th.is_alive())
        if _sched_thread is not None:
            out["scheduler"] = _sched_thread.is_alive()
    return out
