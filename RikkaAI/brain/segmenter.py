"""
RikkaAI - 分段发送（the Lianxin-style burst）

本质：一次 LLM 只跑了一轮，把最终回复**按句号/换行切成若干小段**，
段与段之间再隔随机 1~3 秒发送，看上去就像真人"一条条发消息"。

本模块只做"把一段文字切成适合连续发送的短段"的纯逻辑，不碰 GUI。
显示层（main_window）拿到 segments 后用定时器逐条 add_message 即可。

gate: features.is_enabled("split_reply_enabled")
"""
import re

from brain import features

# 句子结束符：中文/英文句号、问句、叹号、分号、空行
_SENT_END = re.compile(r"(?<=[。！？!?；;])\s*|\n\s*\n")
_MAX_SEG_CHARS = 64   # 每段目标长度（字符），避免太长
_MAX_SEGS = 5         # 最多拆成多少条，避免碎到离谱


def split_reply(text: str, max_chars: int = _MAX_SEG_CHARS, max_segs: int = _MAX_SEGS) -> list:
    """把回复按句号/问号/叹号逐句切成若干"短条"（莲心：按句号分段发送）。
    返回 list[str]（1 条以上；空/太短且无句读时返回 [原文]）。"""
    text = (text or "").strip()
    if not text:
        return []
    # 先按句子结束符切
    parts = [p.strip() for p in _SENT_END.split(text) if p.strip()]
    if not parts:
        return [text]
    # 逐句成段；单句过长硬切
    segs = []
    for p in parts:
        while len(p) > max_chars:
            segs.append(p[:max_chars])
            p = p[max_chars:]
        if p:
            segs.append(p)
    # 条数上限：超出则把多余并入最后一条（避免碎到离谱）
    if len(segs) > max_segs:
        segs = segs[: max_segs - 1] + ["".join(segs[max_segs - 1:])]
    # 去掉过短的碎片（<2字）并入上一条，避免 "嗯。" 单独成一气泡太碎
    clean = []
    for s in segs:
        if clean and len(s) < 2:
            clean[-1] += s
        else:
            clean.append(s)
    return [s for s in clean if s.strip()]


def delivery_plan(text: str, gap_min: float = 1.0, gap_max: float = 3.0) -> list:
    """返回 [{text, gap_sec}]：每条文本 + 发送前等待的随机秒数（1~3s）。"""
    import random
    segs = split_reply(text)
    return [{"text": s, "gap_sec": round(random.uniform(gap_min, gap_max), 1)} for s in segs]


def is_enabled() -> bool:
    return features.is_enabled("split_reply_enabled")
