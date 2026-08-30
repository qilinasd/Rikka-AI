"""
RikkaAI - 概率主动决策（Phase 3）

genesis 式 FormalPlanner 的轻量版：给定六花当前需求/活力状态，估算"该不该主动找
契约者"的概率，并给出决策 + 置信度。保留随机性（有概率主动、也有概率忍住），
但受需求驱动、冷却和时段约束，避免刷屏。

gate: features.is_enabled("decision_planner_enabled")
输入：needs（NeedsState），可选时段/冷却/上次主动距今/最近情感，输出决策摘要。
"""
import random
from datetime import datetime

from brain import features


def decide_proactive(needs, hour: int = None, cooldown_min: int = 60,
                     last_proactive_min: int = None, persistence: int = 3) -> dict:
    """返回 {should, drive, p_success, reason}。should 表示"现在主动找"是否可行。"""
    if not features.is_enabled("decision_planner_enabled"):
        return {"should": False, "drive": 0.0, "p_success": 0.0, "reason": "planner_disabled"}
    hour = datetime.now().hour if hour is None else int(hour)
    # 需求驱动的主动意愿 [0,1]
    drive = needs.initiative_drive()
    # 基础成功率：由 drive 决定，留一定不确定性
    p_success = max(0.05, min(0.95, drive * 0.9 + 0.05))
    reason = []
    # 冷却压制：刚主动过且未过冷却 → 大幅降概率
    if last_proactive_min is not None and last_proactive_min < cooldown_min:
        p_success *= 0.2
        reason.append(f"冷却中({last_proactive_min}min<{cooldown_min}min)")
    # 免打扰时段压制（PROACT_DND_START..END，可配置），减少打扰
    try:
        import config as _cfg
        in_dnd = _cfg.in_dnd(hour)
    except Exception:
        in_dnd = hour >= 23 or hour < 8
    if in_dnd:
        p_success *= 0.4
        reason.append("免打扰时段")
    # 精力极低压制
    if getattr(needs, "energy", 50) < 20:
        p_success *= 0.3
        reason.append("精力不足")
    p_success = max(0.0, min(1.0, p_success))
    # 用概率决定是否主动（保留随机；低概率多数时候忍住）
    should = random.random() < p_success
    reason.append(f"drive={drive:.2f}")
    return {"should": should, "drive": round(drive, 3), "p_success": round(p_success, 3),
            "reason": "；".join(reason)}


def expected_value(drive: float, p_success: float, reward_if_yes: float = 1.0,
                   cost_if_no: float = 0.2) -> float:
    """期望效用（供规划器比较分支）：主动的期望 = p*reward - (1-p)*cost。"""
    return round(p_success * reward_if_yes - (1 - p_success) * cost_if_no, 3)
