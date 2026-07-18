"""
RikkaAI - AI 对话核心（流式输出）
"""
import os
import json
from datetime import datetime
from openai import OpenAI
import config as cfg
from brain.tools import TOOL_DEFINITIONS, handle_tool_call
from brain.emotion import EmotionState
from brain import rag_memory
from brain import graph_memory

MAX_TOOL_ITERATIONS = 100

# 需要限制的电脑操作工具（对未授权QQ用户禁用）
RESTRICTED_TOOLS = {
    "screenshot", "send_image", "list_windows", "capture_window",
    "press_key", "click_mouse", "move_mouse", "type_text",
    "game_play", "game_guide", "open_app", "write_file", "edit_file",
    "download_image", "search_images", "search_images_smart",
}


class AgentCore:
    """六花的 AI 核心：对话、记忆、主动性"""

    def __init__(self, memory=None):
        self.memory = memory
        self._session_active = False
        self._history = []
        self.emotion = EmotionState()
        self._base_prompt = None  # 从 persona 文件缓存的基础 prompt
        self._restricted_mode = False  # QQ 未授权用户模式

    def set_restricted(self, restricted: bool):
        """设置受限模式 — 禁用所有电脑操作工具"""
        self._restricted_mode = restricted

    @property
    def tool_definitions(self):
        """获取工具定义列表，受限模式下过滤掉操作类工具"""
        if not self._restricted_mode:
            return TOOL_DEFINITIONS
        return [t for t in TOOL_DEFINITIONS
                if t.get("function", {}).get("name", "") not in RESTRICTED_TOOLS]

    # ------------------------------------------------------------------ #
    #   Prompt 构建（文件驱动 + 实时信息注入）                             #
    # ------------------------------------------------------------------ #

    def _build_base_prompt(self) -> str:
        """从 persona/ 三文件 + 上轮摘要 组装基础 prompt"""
        parts = []

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
        if os.path.exists(memo_path):
            with open(memo_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    parts.append(f"【你的备忘录】\n{content}")

        # 4. 上轮对话摘要
        prev = cfg.load_last_summary()
        if prev:
            parts.append(f"【上轮对话回顾】\n{prev}")

        return "\n\n---\n\n".join(parts)

    def _build_dynamic_suffix(self) -> str:
        """构建带实时信息的 prompt 后缀（每次对话时刷新）"""
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

        es = self.emotion.get_prompt_suffix()

        parts = [f"【当前时间】{time_str}"]

        # QQ 消息发送能力
        qq_users = cfg.get_qq_allowed_users()
        if qq_users:
            qq_list = "、".join(str(u) for u in qq_users)
            parts.append(
                f"【QQ 消息能力】你可以使用 send_qq_message 工具给契约者的 QQ 发消息。"
                f"契约者的 QQ 号：{qq_list}。"
                f"当契约者在本地对你说「发QQ消息」「告诉QQ上的我」之类的话时，直接用 send_qq_message 发过去就好。"
            )

        # AI 画图目录
        parts.append(
            f"【AI 画图能力】你可以使用 generate_image 工具画图，图片保存在 images/generated/ 目录。"
            f"契约者说「画一张/几张」就设 n=对应数量，严格按契约者要求的来，不要多画也不要少画。"
        )

        if es.strip():
            parts.append(es)
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

    def chat(self, text, on_stream=None):
        if not self._session_active:
            self.start_session()

        # 情感分析
        self.emotion.analyze(text)

        # 构建本次 system prompt（基础 + 实时信息 + 记忆检索）
        base = self._base_prompt or self._build_base_prompt()
        dyn = self._build_dynamic_suffix()

        prompt = f"{base}\n\n---\n\n{dyn}"

        # RAG 记忆检索（基于用户输入的关键词）
        r1 = rag_memory.search(text, 3)
        rs = rag_memory.format_for_prompt(r1)
        if rs.strip():
            prompt += "\n\n" + rs

        # 知识图谱检索
        gi = graph_memory.search(text)
        gs = graph_memory.format_for_prompt(gi)
        if gs.strip():
            prompt += "\n\n" + gs

        # 受限模式下注入安全限制说明
        if self._restricted_mode:
            prompt += (
                "\n\n【⚠️ 安全限制 — 当前对话来自未授权的 QQ 用户】\n"
                "你当前的对话对象没有操作电脑的权限。\n"
                "以下操作严禁执行：截图、按键、鼠标点击、打字、运行程序、文件读写、编辑文件、搜图下载。\n"
                "如果对方提出上述要求，请礼貌告知：「抱歉，你没有操作电脑的权限哦～需要找契约者授权才行 (｡•́︿•̀｡)」"
            )

        msgs = [{"role": "system", "content": prompt}]
        # 追加历史（跳过第一个 system）
        for m in self._history[1:]:
            msgs.append(m)
        msgs.append({"role": "user", "content": text})

        full_response = ""
        try:
            for it in range(MAX_TOOL_ITERATIONS):
                if on_stream:
                    stream = self._client.chat.completions.create(
                        model=cfg.MODEL, messages=msgs,
                        tools=self.tool_definitions, temperature=cfg.TEMPERATURE,
                        max_tokens=4096, stream=True,
                    )
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
                                idx = tc.index
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
                        tools=self.tool_definitions, temperature=cfg.TEMPERATURE,
                        max_tokens=4096,
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

            return full_response

        except Exception as e:
            em = f"力量波动了… {str(e)}"
            if on_stream:
                for ch in em:
                    on_stream(ch)
            return em

    @property
    def _client(self):
        return OpenAI(api_key=cfg.API_KEY, base_url=cfg.API_BASE)
