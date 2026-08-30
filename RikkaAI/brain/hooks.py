"""
RikkaAI - Hook 注入机制（对齐 Suzu Lives 的 Hook 自动注入）
===========================================================
把「每次对话前自动注入上下文」的逻辑从 agent.py 抽成可插拔的 hook 注册表。
新增注入项时，注册一个 hook 即可，不用改 agent.py 核心代码。

用法：
    from brain import hooks
    def my_hook(agent, text) -> str:
        return "【我的注入】...内容..."
    hooks.register("my_hook", my_hook)

hook 签名：fn(agent, text) -> str   （返回要注入的文本；返回空串则跳过）
agent 是 AgentCore 实例，text 是用户当前输入（可为空，如主动触发场景）。
"""
import config as cfg

# hook 注册表：name -> callable(agent, text) -> str
_HOOKS = {}
_ORDER = []  # 注册顺序


def register(name: str, fn):
    """注册一个注入 hook。同名覆盖并保持原顺序。"""
    if name not in _HOOKS:
        _ORDER.append(name)
    _HOOKS[name] = fn


def unregister(name: str):
    if name in _HOOKS:
        del _HOOKS[name]
        _ORDER.remove(name)


def get_registered() -> list:
    return list(_ORDER)


def build_dynamic_suffix(agent, text: str = "") -> str:
    """按注册顺序执行所有 hook，拼接注入文本。单个 hook 失败不影响其他。"""
    parts = []
    for name in _ORDER:
        fn = _HOOKS[name]
        try:
            out = fn(agent, text)
            if out:
                parts.append(str(out))
        except Exception:
            continue
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
#  内置 hooks（原 agent.py _build_dynamic_suffix 的注入项）
# ═══════════════════════════════════════════════════════════════

def _time_hook(agent, text):
    """当前时间 + 时段感知"""
    from datetime import datetime
    now = datetime.now()
    hour = now.hour
    if hour < 6:
        period = "凌晨"
    elif hour < 9:
        period = "早上"
    elif hour < 12:
        period = "上午"
    elif hour < 14:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    time_str = now.strftime(f"%Y-%m-%d %H:%M（%A），{period}，{hour}点")
    return f"【当前时间】{time_str}"


def _language_hook(agent, text):
    """六花语言（日语模式：文字中文，语音日语+翻译）"""
    if cfg.PERSONA_LANGUAGE == "ja":
        return (
            "【语言】你的文字回复一律用中文和契约者对话（不要写日语，契约者要看中文）。"
            "但用 speak 工具开口说话时，text 写日语口语（六花用日语出声），并同时提供 translation=对应的中文翻译。"
        )
    return (
        "【语言】你现在用中文和契约者对话。"
        "用 speak 工具说话时 text 也用中文，不需要 translation。"
    )


def _qq_hook(agent, text):
    """QQ 消息发送能力"""
    qq_users = cfg.get_qq_allowed_users()
    if not qq_users:
        return ""
    qq_list = "、".join(str(u) for u in qq_users)
    return (
        f"【QQ 消息能力】你可以使用 send_qq_message 工具给契约者的 QQ 发消息。"
        f"契约者的 QQ 号：{qq_list}。"
        "当契约者要求发送、转发或发给某人时，本轮必须发出真实 function call，"
        "绝不能在普通文本中写「[调用 send_qq_message 工具]」或声称已发送。"
        "若只提供联系人名称，先用 query_qq_contacts 查找，再根据结果发送或追问确认。"
    )


def _search_route_hook(agent, text):
    """搜索工具路由"""
    return (
        "【搜索路由】契约者提到特定平台搜索时，用对应专用工具，不要用 web_search："
        "B站搜视频→bilibili_search；YouTube视频/总结→youtube_transcript；GitHub仓库/文件→github_repo；"
        "维基百科/百科→search_wiki；新闻/时事→search_news；RSS/博客订阅→read_rss；"
        "Twitter/X→read_twitter；图片/壁纸→search_images。只有普通网页/综合信息搜索才用 web_search。"
    )


def _memory_summary_hook(agent, text):
    """上轮记忆总结（周记/月报/年鉴）"""
    # 注：memory_summary 模块已移除，此 hook 暂时禁用
    return ""


def _citations_hook(agent, text):
    """引用规则"""
    settings = cfg.get_chat_settings()
    if settings.get("chat_citations_enabled"):
        return "【引用规则】使用联网检索内容时，请在回答末尾列出清晰、可核对的来源链接。"
    return ""


def _drawing_hook(agent, text):
    """AI 画图目录"""
    return (
        "【AI 画图能力】你可以使用 generate_image 工具画图，图片保存在 images/generated/ 目录。"
        "契约者说「画一张/几张」就设 n=对应数量，严格按契约者要求的来，不要多画也不要少画。"
    )


def _voice_hook(agent, text):
    """语音能力"""
    if not cfg.VOICE_ENABLED:
        return ""
    return (
        "【语音能力】你拥有用自己声音开口说话的能力，用 speak 工具即可。"
        "契约者明确要求「发语音/用语音说/说句话/出个声」时，本轮必须立即发出真实 speak function call，"
        "绝不能把调用过程写进普通文本。你想用声音卖萌回应时、"
        "也可以调用 speak；"
        "你觉得某句话特别值得说出口时也可以调用。说话内容要简短口语化，几句话内，"
        "不要带表情符号、不要用 markdown 和换行。可用 emotion 表达这句话的情绪（happy/sad/neutral），"
        "会改变声音的语气；日语模式下务必附上 translation 中文对照。不要每条回复都开口，只在值得的时候说。"
    )


def _growth_hook(agent, text):
    """自我成长：每次对话结束时的轻量反思"""
    return (
        "【自我成长】每次你回复完契约者，想一想这轮对话："
        "有没有让你意识到自己新的性格特点、喜好，或学会的新能力？"
        "如果有，调用 append_self_discovery 记一条（每轮最多一条，第一人称、两三句话，描述具体一点）。"
        "如果这次没有，就跳过，不要为了凑数硬写。"
    )


def _emotion_hook(agent, text):
    """情感状态"""
    if hasattr(agent, "emotion"):
        return agent.emotion.get_prompt_suffix()
    return ""


def _inner_drive_hook(agent, text):
    """内驱引擎见闻注入：六花自己偷偷冲浪攒下的存货，
    在她回复契约者时自然带出（不相关时由 LLM 自行不提）。"""
    try:
        from brain.inner_drive import get_engine
        return get_engine().consume_stash_for_chat()
    except Exception:
        return ""


def _learner_hook(agent, text):
    """表达学习注入：契约者的说话风格样本 + 六花已学会的黑话词条。"""
    try:
        from brain import learner
        return learner.build_prompt_suffix()
    except Exception:
        return ""


def _register_builtins():
    register("time", _time_hook)
    register("language", _language_hook)
    register("qq", _qq_hook)
    register("search_route", _search_route_hook)
    register("memory_summary", _memory_summary_hook)
    register("citations", _citations_hook)
    register("drawing", _drawing_hook)
    register("voice", _voice_hook)
    register("growth", _growth_hook)
    register("emotion", _emotion_hook)
    register("inner_drive", _inner_drive_hook)
    register("learner", _learner_hook)


_register_builtins()
