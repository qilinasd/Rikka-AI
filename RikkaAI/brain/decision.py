"""
RikkaAI - DecisionEngine 决策层（对齐 EchoBot 三层架构的 Decision Layer）

责任：判断本轮用户输入该走「纯角色聊天 (chat)」还是「带工具的 Agent 流程 (agent)」。
核心：双层判断，先便宜后贵——
  1) 规则白名单（复用 agent.TOOL_GROUPS 的全部关键词 + AGENT_PATTERNS 正则）：
     命中任何「需要查/改/执行/记忆」的迹象 → 直接 agent，零 LLM 成本、毫秒级。
  2) 规则未命中 → 轻量 LLM（temperature=0，只回 {"route": ...}）兜底模糊意图。

这样纯闲聊不用背着工具列表，人设不稀释、响应更快；明确的工具请求仍走完整 Agent。
"""

import re

from openai import OpenAI

import config as cfg

# ── Agent 趋向的正则白名单（中英文，命中即走 agent） ──────────────
_ENG_PREFIX = r"^\s*(?:(?:please|kindly)\s+)?(?:(?:can|could|would)\s+you\s+)?(?:help\s+me\s+)?"
_CN_PREFIX = r"^\s*(?:请|请帮我|帮我|麻烦你|麻烦帮我)?\s*"

AGENT_PATTERNS = (
    # 记忆 / 搜索 / 网络
    rf"(记住|记下来|保存到记忆|存到记忆|查一下记忆|查记忆|搜索记忆|回忆|还记得|记不记得|你还记得|想想之前|以前.*(说|聊|做|喜欢))",
    rf"{_ENG_PREFIX}(remember|recall|look up|search).*(memor|history|recall)",
    # 记忆 / 日记 / 摘要 / 回顾：需要读取记忆库/日记/摘要等外部状态，必须走 agent（保留工具）
    rf"(日记|周记|日报|月报|纪要|备忘录|记忆碎片|记忆库|知识库|摘要|总结|回顾|翻阅|翻一下|翻翻|想想之前|看看之前)",
    rf"{_CN_PREFIX}(写|记|整理|看|查|翻|补|更新).*(日记|周记|日报|月报|纪要|备忘录|记忆|摘要|总结|回顾)",
    rf"{_CN_PREFIX}(查|搜|搜索|百度|谷歌|找一下|帮我找|查询|查查).*",
    rf"{_ENG_PREFIX}(search|look up|find|browse).*",
    # 文件 / 代码 / 系统操作
    rf"{_CN_PREFIX}(打开|查看|读取|检查|搜索|查找).*(文件|代码|项目|仓库|目录|工作区|资料)",
    rf"{_CN_PREFIX}(修改|编辑|删除|移除|重命名|移动|创建|新建|生成|写|运行|执行).*(文件|脚本|代码|命令|程序|项目|测试)",
    rf"{_ENG_PREFIX}(open|read|edit|create|write|run|execute|delete|move)\s+\S+",
    # 定时 / 提醒
    rf"{_CN_PREFIX}(设置|创建|添加|安排).*(提醒|定时|计划|任务|闹钟)",
    rf"{_CN_PREFIX}(提醒我.*(后|在|每|去|做)|设置提醒|定时提醒|计划任务|后台执行)",
    rf"{_ENG_PREFIX}(remind|schedule|cron|timer).*",
    # 语音是明确的副作用请求，必须进入带工具的流程。
    r"(发语音|发送语音|用语音说|语音说|说句话|出个声|开口说|朗读|读出来)",
    # QQ / 指定对象发送是外部动作，必须由工具执行，不能在文本中声称完成。
    r"(QQ|qq|发给|发送给|发消息|发送消息|发送信息|转发|私信)",
    r"^\s*\d{5,12}\s*$",  # 上一轮要求 QQ 联系人时，单独发来的 QQ 号
    # 主动调用工具类
    rf"{_CN_PREFIX}(帮我|给我|请).*(查|搜|算|分析|总结|翻译|写|做|生成|下载|截图|录音|播放|画)",
    # 特定平台动作（包含式，不锚定开头）。⚠️ 不能用 \b：中文后无词边界，"天气怎"无法匹配。
    rf"(B站|bilibili|YouTube|GitHub|github|天气|气温|温度|股价|行情|维基|百科|新闻|代码|仓库|项目)",
    # 通用"帮我做X"（包含式）
    rf"(帮我|给我|请帮我|麻烦).*(查|搜|算|分析|总结|翻译|写|做|生成|下载|截图|录音|播放|画|找|看)",
)

# 明确「纯聊天式」的关键词（命中则不依赖规则，直接 chat）
CHAT_HINTS = (
    "你好", "嗨", "早安", "晚安", "在吗", "哈哈", "谢谢",
    "我爱你", "想你", "喜欢你", "心情", "今天", "累", "饿", "困",
    "觉得", "感觉", "怎么样", "好不好", "好看", "可爱", "晚安",
)


def _rule_based_route(text: str):
    """规则白名单：命中 agent 特征 → 'agent'；命中性纯聊天特征 → 'chat'；否则 None（交给 LLM）。"""
    if not text or not text.strip():
        return "chat"
    cleaned = text.strip()
    for pat in AGENT_PATTERNS:
        if re.search(pat, cleaned, flags=re.IGNORECASE):
            return "agent"
    for hint in CHAT_HINTS:
        if hint in cleaned:
            return "chat"
    return None


_DECISION_PROMPT = """你是三层助手架构的「决策层」。判断这轮用户输入走哪条路：

- "chat"：纯对话答复即可。用于闲聊、情感陪伴、观点、头脑风暴、改写、翻译、情绪支持，以及凭当前消息+近期对话就能回答的问题。
- "agent"：助手必须查看/修改/搜索/核实/排程/执行任何超出当前可见对话的东西。包括：任何工具使用、项目或文件查看、代码审查或修改、shell 命令、技能使用、后台工作；任何记忆查询（含"你还记得..."）；任何排程/提醒/cron/心跳/定时器；任何依赖外部状态（工作区文件、已存记忆、排程状态、先前工具输出、后台任务状态）的请求；任何对先前可执行任务的修改/继续/重试/追问（如"继续""再试一次""改成明天9点""结果如何"）。

仅在确实不需要查外部状态、工具调用、记忆搜索、排程动作时才选 "chat"。模糊时若用户很可能在指先前工作或已存状态则选 "agent"，否则选 "chat"。

只返回 JSON：{"route":"chat"|"agent","reason":"简短原因"}"""


def _llm_decide(text: str) -> str:
    """轻量 LLM 决策：只问 route，temperature=0，成本低。失败时保守走 agent（宁多勿漏）。"""
    try:
        client = OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
        resp = client.chat.completions.create(
            model=cfg.MODEL,
            messages=[
                {"role": "system", "content": _DECISION_PROMPT},
                {"role": "user", "content": text[:2000]},
            ],
            temperature=0, max_tokens=100,
        )
        content = (resp.choices[0].message.content or "").strip()
        m = re.search(r'"route"\s*:\s*"(chat|agent)"', content)
        if m:
            return m.group(1)
        if "agent" in content.lower():
            return "agent"
        return "chat"
    except Exception:
        return "agent"  # 决策失败保守走 agent


def should_use_agent(text: str) -> bool:
    """是否应走带工具的 Agent 流程。双层：规则 → 轻量 LLM。"""
    rule = _rule_based_route(text)
    if rule is not None:
        return rule == "agent"
    return _llm_decide(text) == "agent"


def is_pure_chat(text: str) -> bool:
    """是否纯角色聊天（反向：非 agent）。供 Roleplay 纯净链路用。"""
    return not should_use_agent(text)
