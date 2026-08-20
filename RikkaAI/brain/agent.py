"""
RikkaAI - AI 对话核心（流式输出）
"""
import os
import json
import threading
import time
from datetime import datetime
from openai import OpenAI
import config as cfg
from brain.tools import TOOL_DEFINITIONS, handle_tool_call
from brain.emotion import EmotionState
from brain import graph_memory

MAX_TOOL_ITERATIONS = 100

# 需要限制的电脑操作工具（对未授权QQ用户禁用）
RESTRICTED_TOOLS = {
    "screenshot", "send_image",
    "game_guide", "open_app", "write_file", "edit_file",
    "download_image", "search_images", "search_images_smart",
    "query_qq_contacts",  # 未授权 QQ 用户不能枚举联系人
}

WEB_SEARCH_TOOLS = {
    "web_search",
    "argo_search",
    "search_images",
    "search_images_smart",
    "download_image",
}

# ── 按需加载工具分组（对齐 Suzu Lives / 莲心的渐进注入）─────────────────
# 基础工具：每次对话都注入（对话必需、安全、高频）
BASE_TOOL_NAMES = {
    "read_file", "write_file", "edit_file", "list_directory", "search_files", "grep_file",
    "open_app",
    "get_current_time", "get_system_info", "get_network_status",
    "read_summaries", "save_memory", "read_memories", "manage_user_state", "correct_memory",
    "set_proactive_timer", "set_follow_up", "cancel_follow_up",
    "write_to_memo", "append_self_discovery", "update_diary", "write_diary",
}

# 分组工具：按用户消息关键词动态注入（省 token、聚焦能力）
TOOL_GROUPS = {
    "visual": {
        "names": ["screenshot", "send_image", "describe_image", "ocr_image", "game_guide"],
        "keywords": ["截图", "屏幕", "看看", "图片", "画面", "识别", "OCR", "攻略", "游戏"],
    },
    "image_search": {
        "names": ["search_images", "search_images_smart", "download_image", "generate_image"],
        "keywords": ["搜图", "找图", "壁纸", "画", "生成图", "图片", "照片", "头像", "表情包"],
    },
    "web_platform": {
        "names": ["web_search", "argo_search", "bilibili_search", "read_url", "get_weather",
                  "search_news", "search_wiki", "read_rss", "youtube_transcript",
                  "github_repo", "read_twitter", "browser_task"],
        "keywords": ["搜索", "查一下", "查查", "新闻", "天气", "百科", "维基", "B站", "bilibili",
                     "YouTube", "油管", "GitHub", "仓库", "RSS", "Twitter", "推特", "网站", "网页", "浏览器",
                     "股价", "行情", "基金", "股票", "油价", "金价", "学术", "论文", "调研", "综述", "股价"],
    },
    "qq": {
        "names": ["send_qq_message", "send_qq_image", "query_qq_contacts"],
        "keywords": ["QQ", "qq", "发消息", "好友", "联系人", "群"],
    },
    "voice": {
        "names": ["speak"],
        "keywords": ["语音", "说话", "出个声", "说句话", "声音", "用嘴"],
    },
    "summary": {
        "names": ["build_summary"],
        "keywords": ["总结", "日报", "周记", "月报", "年鉴", "回顾"],
    },
}

# 受限 QQ 用户额外禁用的工具
RESTRICTED_QQ_ONLY = {"send_qq_message", "send_qq_image"}


def _select_tools(text: str) -> list:
    """按用户消息关键词选择工具子集（按需加载）。text 为空时给全量（proactive/回访等系统触发场景）。
    关键词匹配大小写不敏感（URL 如 github.com 小写也能触发 GitHub 工具）。"""
    if not text:
        return list(TOOL_DEFINITIONS)

    lowered = text.lower()
    selected = set(BASE_TOOL_NAMES)
    for group in TOOL_GROUPS.values():
        if any(kw.lower() in lowered for kw in group["keywords"]):
            selected.update(group["names"])
    return [t for t in TOOL_DEFINITIONS if t.get("function", {}).get("name", "") in selected]


class AgentCore:
    """六花的 AI 核心：对话、记忆、主动性"""

    def __init__(self, memory=None):
        self.memory = memory
        self._session_active = False
        self._history = []
        self.emotion = EmotionState()
        self._base_prompt = None  # 从 persona 文件缓存的基础 prompt
        self._restricted_mode = False  # QQ 未授权用户模式
        self._chat_lock = threading.Lock()  # 串行化同一 AgentCore 的并发 chat 调用，防 _history 竞态

    def set_restricted(self, restricted: bool):
        """设置受限模式 — 禁用所有电脑操作工具"""
        self._restricted_mode = restricted

    def tool_definitions(self, text: str = ""):
        """获取工具定义列表：按需加载（基础工具 + 关键词匹配分组）。
        text 为空（系统触发，如 proactive/回访）→ 全量工具。
        受限模式下再过滤掉操作类工具。"""
        definitions = _select_tools(text)
        settings = cfg.get_chat_settings()
        if not settings["chat_web_search_enabled"]:
            definitions = [
                tool for tool in definitions
                if tool.get("function", {}).get("name", "") not in WEB_SEARCH_TOOLS
            ]
        if self._restricted_mode:
            definitions = [
                tool for tool in definitions
                if tool.get("function", {}).get("name", "") not in RESTRICTED_TOOLS
                and tool.get("function", {}).get("name", "") not in RESTRICTED_QQ_ONLY
            ]
        return definitions

    # ------------------------------------------------------------------ #
    #   Prompt 构建（文件驱动 + 实时信息注入）                             #
    # ------------------------------------------------------------------ #

    def _build_base_prompt(self) -> str:
        """从 persona/ 三文件 + 上轮摘要 组装基础 prompt"""
        parts = []
        memory_enabled = cfg.get_chat_settings()["chat_memory_enabled"]

        # 1. 人设文件
        char_path = os.path.join(cfg.ROOT_DIR, "persona", "character.md")
        if os.path.exists(char_path):
            with open(char_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    parts.append(content)

        # 2. 行为规范
        rules_path = os.path.join(cfg.ROOT_DIR, "persona", "system_rules.md")
        if os.path.exists(rules_path):
            with open(rules_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    parts.append(content)

        # 3. 备忘录
        memo_path = os.path.join(cfg.ROOT_DIR, "persona", "memo.md")
        if memory_enabled and os.path.exists(memo_path):
            with open(memo_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    parts.append(f"【你的备忘录】\n{content}")

        # 4. 上轮对话摘要
        prev = cfg.load_last_summary() if memory_enabled else ""
        if prev:
            parts.append(f"【上轮对话回顾】\n{prev}")

        return "\n\n---\n\n".join(parts)

    def _build_dynamic_suffix(self, text: str = "") -> str:
        """构建带实时信息的 prompt 后缀（每次对话时刷新）。
        静态注入项由 brain/hooks.py 的 hook 注册表提供（可插拔，外部可注册新 hook）；
        这里只保留需要当前输入数据的动态检索（记忆碎片 + 知识图谱）。"""
        from brain import hooks

        parts = []
        # 1. 可插拔 hooks（时间/语言/QQ/搜索路由/记忆摘要/引用/画图/语音/成长/情感）
        hooked = hooks.build_dynamic_suffix(self, text)
        if hooked.strip():
            parts.append(hooked)

        # 2. 动态记忆检索（需要当前输入 text，不适合做成静态 hook）
        settings = cfg.get_chat_settings()
        if settings["chat_memory_enabled"]:
            try:
                from brain import memory_vault as _mv
                vs = _mv.format_for_prompt(text)
                if vs.strip():
                    parts.append(vs)
            except Exception:
                pass

            try:
                gi = graph_memory.search(text)
                gs = graph_memory.format_for_prompt(gi)
                if gs.strip():
                    parts.append(gs)
            except Exception:
                pass

            # 3. 用户状态（有时效的当下处境）+ 行为模式（长期规律）注入
            try:
                from brain import memory_vault as _mv
                states = _mv.get_active_states()
                if states:
                    sl = ["【📌 契约者当前状态】"]
                    for s in states[:5]:
                        exp = s.get("expires_at") or ""
                        exp_txt = f"（~{exp[:10]}）" if exp and exp != "none" else ""
                        sl.append(f"  · {s['content'][:80]}{exp_txt}")
                    parts.append("\n".join(sl))
                patterns = _mv.get_patterns(active_only=True)
                if patterns:
                    pl = ["【🧬 行为模式】"]
                    for p in patterns[:5]:
                        pl.append(f"  · {p['pattern'][:60]}（置信度 {p['confidence']:.0%}）")
                    parts.append("\n".join(pl))
            except Exception:
                pass

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  会话管理                                                           #
    # ------------------------------------------------------------------ #

    def start_session(self):
        """启动新会话：加载人设文件、读取备忘录、注入时间"""
        self._session_active = True
        self._base_prompt = self._build_base_prompt()
        base = self._base_prompt
        dyn = self._build_dynamic_suffix()
        prompt = f"{base}\n\n---\n\n{dyn}"
        self._history = [{"role": "system", "content": prompt}]

    def end_session(self):
        self._session_active = False

    @property
    def history(self):
        return self._history

    # ------------------------------------------------------------------ #
    #  对话核心                                                           #
    # ------------------------------------------------------------------ #

    def _chat_impl(self, text, on_stream=None):
        _t0 = time.time()
        print(f"[CHAT] 进入 _chat_impl (agent={id(self)})", flush=True)
        if not self._session_active:
            self.start_session()

        # 情感分析
        self.emotion.analyze(text)

        settings = cfg.get_chat_settings()

        # 构建本次 system prompt（基础 + 实时信息 + 记忆检索，均来自 _build_dynamic_suffix）
        base = self._base_prompt or self._build_base_prompt()
        dyn = self._build_dynamic_suffix(text)

        prompt = f"{base}\n\n---\n\n{dyn}"

        # 受限模式下注入安全限制说明
        if self._restricted_mode:
            prompt += (
                "\n\n【⚠️ 安全限制 — 当前对话来自未授权的 QQ 用户】\n"
                "你当前的对话对象没有操作电脑的权限。\n"
                "以下操作严禁执行：截图、按键、鼠标点击、打字、运行程序、文件读写、编辑文件、搜图下载。\n"
                "如果对方提出上述要求，请礼貌告知：「抱歉，你没有操作电脑的权限哦～需要找契约者授权才行 (｡•́︿•̀｡)」"
            )

        print(f"[CHAT] prompt 构建完成，耗时 {time.time() - _t0:.1f}s，准备调用 LLM (agent={id(self)})", flush=True)

        msgs = [{"role": "system", "content": prompt}]
        # 追加历史（跳过第一个 system）
        for m in self._history[1:]:
            msgs.append(m)
        msgs.append({"role": "user", "content": text})

        full_response = ""
        try:
            for it in range(MAX_TOOL_ITERATIONS):
                if on_stream:
                    print(f"[CHAT] LLM 请求 it={it} 开始 (agent={id(self)})", flush=True)
                    stream = self._client.chat.completions.create(
                        model=cfg.MODEL, messages=msgs,
                        tools=self.tool_definitions(text), temperature=cfg.TEMPERATURE,
                        max_tokens=settings["chat_max_tokens"], stream=True,
                    )
                    print(f"[CHAT] LLM 流 it={it} 已返回，开始消费 (agent={id(self)})", flush=True)
                    content_chunks = []
                    tool_call_acc = {}
                    for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if not delta:
                            continue
                        if delta.content:
                            content_chunks.append(delta.content)
                            on_stream(delta.content)
                        if delta.tool_calls:
                            for tc in delta.tool_calls:
                                idx = tc.index if tc.index is not None else len(tool_call_acc)
                                if idx not in tool_call_acc:
                                    tool_call_acc[idx] = {"id": "", "name": "", "args": ""}
                                if tc.id:
                                    tool_call_acc[idx]["id"] = tc.id
                                if tc.function:
                                    if tc.function.name:
                                        tool_call_acc[idx]["name"] += tc.function.name
                                    if tc.function.arguments:
                                        tool_call_acc[idx]["args"] += tc.function.arguments

                    full_response = "".join(content_chunks)
                    print(f"[CHAT] LLM it={it} 流消费完毕，耗时 {time.time() - _t0:.1f}s，{len(full_response)} 字 (agent={id(self)})", flush=True)

                    if tool_call_acc:
                        # 有工具调用 → 追加到 messages 继续
                        am = {"role": "assistant", "content": full_response}
                        am["tool_calls"] = []
                        for idx in sorted(tool_call_acc):
                            tc = tool_call_acc[idx]
                            am["tool_calls"].append({
                                "id": tc["id"], "type": "function",
                                "function": {"name": tc["name"], "arguments": tc["args"]},
                            })
                        msgs.append(am)
                        for idx in sorted(tool_call_acc):
                            tc = tool_call_acc[idx]
                            try:
                                fa = json.loads(tc["args"])
                            except json.JSONDecodeError:
                                fa = {}
                            result = handle_tool_call(tc["name"], fa, memory=self.memory)
                            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                        full_response = ""
                        continue
                    break
                else:
                    resp = self._client.chat.completions.create(
                        model=cfg.MODEL, messages=msgs,
                        tools=self.tool_definitions(text), temperature=cfg.TEMPERATURE,
                        max_tokens=settings["chat_max_tokens"],
                    )
                    msg = resp.choices[0].message
                    if msg.tool_calls:
                        am = {"role": "assistant", "content": msg.content or ""}
                        am["tool_calls"] = []
                        for tc in msg.tool_calls:
                            am["tool_calls"].append({
                                "id": tc.id, "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            })
                        msgs.append(am)
                        for tc in msg.tool_calls:
                            try:
                                fa = json.loads(tc.function.arguments)
                            except json.JSONDecodeError:
                                fa = {}
                            result = handle_tool_call(tc.function.name, fa, memory=self.memory)
                            msgs.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                    else:
                        full_response = msg.content or ""
                        break
            else:
                full_response = full_response or "工具调用次数过多"

            # 保存到历史
            self._history.append({"role": "user", "content": text})
            self._history.append({"role": "assistant", "content": full_response})

            # 自动轮换（长对话压缩）
            try:
                msgs_hist = [m for m in self._history if m["role"] in ("user", "assistant")]
                if len(msgs_hist) >= cfg.ROTATION_THRESHOLD * 2:
                    from brain.context_compressor import _generate_summary
                    su = _generate_summary(msgs_hist)
                    os.makedirs(cfg.CONVERSATIONS_DIR, exist_ok=True)
                    fn = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    with open(os.path.join(cfg.CONVERSATIONS_DIR, fn), "w", encoding="utf-8") as f:
                        f.write("会话存档\n")
                        for x in msgs_hist:
                            f.write(f"[{x['role']}] {x['content'][:200]}\n")
                        f.write(f"\n摘要:\n{su}")
                    cfg.save_last_summary(su)
                    self.start_session()
            except Exception:
                pass

            # 自动提取记忆（Scribe）
            try:
                if text and len(text) > 5 and full_response:
                    from brain.scribe import extract_from_chat
                    extract_from_chat(text, full_response)
            except Exception:
                pass

            # 实时流水日记：每轮对话结束自动追加到当天日记（一点点记录，不等定时）
            try:
                if getattr(cfg, "DIARY_AUTO_FLOW_ENABLED", False) and text and full_response:
                    from brain import diary as _diary
                    today = _diary.get_or_create_today()
                    now_hm = datetime.now().strftime("%H:%M")
                    flow_max = int(getattr(cfg, "DIARY_AUTO_FLOW_MAX", 120))
                    user_part = text.replace("\n", " ")[:flow_max]
                    rikka_part = full_response.replace("\n", " ")[:flow_max]
                    entry = f"[{now_hm}] 契约者：{user_part}｜六花：{rikka_part}"
                    _diary.append_details(today.get("date", ""), entry)
            except Exception:
                pass

            return full_response

        except Exception as e:
            em = f"力量波动了… {str(e)}"
            if on_stream:
                for ch in em:
                    on_stream(ch)
            return em

    def chat(self, text, on_stream=None):
        """对话入口：同一 AgentCore 的并发调用（如同一 QQ 用户连发消息）被串行化，
        避免多条消息同时读写 _history / emotion 造成竞态。

        用带超时的 try-acquire 而不是无条件 with：一旦某次调用卡住没释放锁
        （日志显示 QQ worker 曾死锁在锁上，对方永远收不到回复），后续调用最多等
        15 秒就返回兜底，绝不让 QQ 链路永久阻塞。"""
        if not getattr(cfg, "API_KEY", ""):
            msg = "还没有配置 API Key 哦～ 请先在「设置 → AI 能力设置」里添加模型预设。"
            if on_stream:
                for ch in msg:
                    on_stream(ch)
            return msg
        if not self._chat_lock.acquire(timeout=15):
            print(f"[CHAT] 锁等待超时，跳过本轮（上一调用未释放锁？）agent={id(self)}", flush=True)
            return "……唔，我这边好像卡住了，你稍等一下再和我说好不好（´･ω･`）"
        try:
            print(f"[CHAT] 获得锁 agent={id(self)}", flush=True)
            return self._chat_impl(text, on_stream)
        finally:
            self._chat_lock.release()

    @property
    def _client(self):
        """OpenAI 客户端。必须带超时：流式生成如果卡住（网络抖动/服务端停发 chunk），
        默认 600s 超时会让人等十分钟；这里用较短的 read 超时尽快中止，避免六花卡死在「回复中」"""
        stall = float(getattr(cfg, "LLM_STREAM_STALL_TIMEOUT", 30))
        timeout = stall
        try:
            import httpx
            timeout = httpx.Timeout(connect=10.0, read=stall, write=15.0, pool=10.0)
        except Exception:
            pass
        return OpenAI(
            api_key=cfg.API_KEY, base_url=cfg.API_BASE,
            timeout=timeout, max_retries=1,
        )
