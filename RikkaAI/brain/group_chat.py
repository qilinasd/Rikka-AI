"""
RikkaAI - QQ 群聊决策（对标麦麦 reply_necessity / turn_gates 的轻量版）
======================================================================
群聊里"要不要回这句话"由纯代码评分决定，模型无权参与：
- 被 @ → 必回；被点名（"六花"）→ 高分必回
- 其他消息按内容特征评分（提问/请求/征询加分，"哈哈""6"等短反应减分），
  乘随机抖动后过阈值 —— 大部分群聊闲聊她应该安静潜水
- 存在感惩罚：最近窗口内她自己发言占比越高扣分越多（防刷屏，麦麦同款）

模式（config.QQ_GROUP_MODE）：
- "smart"   智能插话：评分闸门
- "at_only" 仅 @我和点名才回
"""

import random
import re

AT_RE = re.compile(r"\[CQ:at,qq=(\d+)\]")
QUESTION_RE = re.compile(r"[?？]|吗[。？！?！~～]?$|呢[。？！?！~～]?$|怎么|为什么|什么|多少|几")
REQUEST_RE = re.compile(r"帮我|帮忙|能不能|可以吗|求助|来一份|给我")
OPINION_RE = re.compile(r"你觉得|你认为|怎么看|有什么建议|说说看法")
SHORT_REACTION_RE = re.compile(
    r"^(?:[哈嘿呵]{1,8}|[6九]{1,5}|[嗯哦噢哇啊呃欸]{1,3}|[?？!！.。~～…]{1,8}"
    r"|草|寄|乐|好|行|坏|芜湖|卧槽|牛|牛哇|ok|OK|OKK|666+)$"
)


def clean_cq(text: str, self_qq: int = 0, name_of=None) -> str:
    """把 OneBot CQ 码清洗成人类可读文本（喂给模型的群消息格式）。

    - @某人 → @昵称（@六花自己 → @我）
    - [CQ:reply] → （回复了一条消息）
    - [CQ:image] 保留原样（识图管线依赖它，后续由 describe 管线处理）
    - 其余 CQ 码丢弃
    """
    text = str(text or "")

    def _at(m):
        qq = m.group(1)
        if self_qq and qq == str(self_qq):
            return "@我"
        name = None
        try:
            name = name_of(int(qq)) if name_of else None
        except Exception:
            name = None
        return f"@{name or ('QQ' + qq)}"

    text = AT_RE.sub(_at, text)
    text = re.sub(r"\[CQ:reply,[^\]]*\]", "（回复了一条消息）", text)
    text = re.sub(r"\[CQ:(?!image)[a-zA-Z]+[^\]]*\]", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def score_group_message(text: str, *, at_me: bool, mention_me: bool,
                        my_recent: int = 0, window: int = 0) -> tuple:
    """麦麦式回复必要性评分（轻量版）。返回 (score, reasons)。

    text 应为清洗后的纯文本。my_recent/window = 最近窗口内她的发言数与群消息总数。"""
    text = str(text or "").strip()
    reasons = []
    score = 0

    if at_me:
        score += 100
        reasons.append("被@")
    if mention_me and not at_me:
        score += 60
        reasons.append("被点名")

    if QUESTION_RE.search(text):
        score += 15
        reasons.append("提问")
    if REQUEST_RE.search(text):
        score += 20
        reasons.append("请求")
    if OPINION_RE.search(text):
        score += 20
        reasons.append("征询")

    n = len(text)
    if n >= 120:
        score += 10
        reasons.append("长文本")
    elif n >= 40:
        score += 5
        reasons.append("中长文本")

    if text and SHORT_REACTION_RE.match(text):
        score -= 25
        reasons.append("短反应")

    if window > 0 and my_recent > 0:
        ratio = my_recent / window
        if ratio > 0.34:
            penalty = int(min(40, (ratio - 0.34) * 100))
            score -= penalty
            reasons.append(f"存在感-{penalty}")

    return score, reasons


def should_reply(text: str, *, at_me: bool, mention_me: bool, mode: str = "smart",
                 my_recent: int = 0, window: int = 0, threshold: int = 60) -> tuple:
    """群聊回复意愿闸门。返回 (should, score, reasons)。

    - 被 @ 永远回；被点名在两种模式下都回
    - "smart" 模式下按评分 × 随机抖动(0.75~1.15) 过阈值
    - "at_only" 模式下非 @/点名一律不回
    """
    score, reasons = score_group_message(
        text, at_me=at_me, mention_me=mention_me, my_recent=my_recent, window=window)
    if at_me:
        return True, score, reasons
    if mention_me:
        return True, score, reasons
    if str(mode) == "at_only":
        return False, score, reasons + ["仅@模式"]
    final = score * random.uniform(0.75, 1.15)
    return final >= threshold, int(final), reasons
