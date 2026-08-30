"""
RikkaAI - 六花语音引擎

管线：
    文字 → (本地 GPT-SoVITS HTTP 服务，直接用六花微调模型合成) → 播放 / 发QQ

- GPT-SoVITS 独占引擎：HTTP 调用本地 api_v2.py 服务（默认 127.0.0.1:9880），
  输出已是六花音色，无需其它变声处理，直接输出干净人声。
- speak() 是 fire-and-forget：返回后由后台线程完成合成，完成后通过 voice_ready 信号
  把成品 wav 交给主窗口（本地播放 / 发QQ语音），不阻塞 AI 流式回复。
"""
import os
import re
import hashlib
import logging
import threading

import requests

import config as cfg
from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger("Voice")


class VoiceSignals(QObject):
    """跨线程信号：后台合成线程只发信号，不碰 GUI。"""
    # path, to("local"/"qq"/"both"), qq_target(JSON字符串 或 "null"), text(实际念出的文字), translation(中文对照,可空)
    voice_ready = pyqtSignal(str, str, str, str, str)
    # 语音合成进度信号：status_text(状态描述), text(要合成的内容预览)
    voice_synthesizing = pyqtSignal(str, str)
    # 语音合成完成信号（用于移除进度气泡）
    voice_synthesis_done = pyqtSignal()


class VoiceEngine:
    """六花语音引擎：GPT-SoVITS 直接合成六花音色。"""

    def __init__(self):
        self.signals = VoiceSignals()
        self._lock = threading.Lock()   # 串行合成，避免 GPU 争用
        self._qq_context = None         # (user_id, group_id) 最近一次 QQ 会话
        self._gen = 0                   # 合成代次号：新的 speak / stop 会作废在途合成

    # ── 上下文 ─────────────────────────────────────────────

    def set_qq_context(self, user_id, group_id):
        """记录当前正在处理的 QQ 会话目标，供 speak(to='qq') 使用。"""
        self._qq_context = (user_id, group_id)

    # ── 文本清洗（TTS 读不了 markdown/表情/链接） ─────────────

    _EMOJI_RE = re.compile(
        "["
        "\U0001F000-\U0001F6FF"   # 表情符号、交通、工具
        "\U0001F900-\U0001F9FF"   # 补充符号
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000027BF"   # 杂项符号、dingbats
        "\U00002B00-\U00002BFF"   # 箭头等
        "\uFE00-\uFE0F"           # 变体选择符
        "\u2764\u2763\u2B50\U0001F1E6-\U0001F1FF"
        "]", flags=re.UNICODE)

    @staticmethod
    def _clean_text(text):
        """去掉 markdown/代码块/URL/表情，折叠空白，截断到 VOICE_MAX_CHARS。"""
        if not text:
            return ""
        t = text
        t = t.replace("・", "、")   # GPT-SoVITS 服务端 GBK 编码不认日文间隔号 U+30FB（会 HTTP 400）
        # 代码块（多行）
        t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)
        # 行内代码 → 保留内容
        t = re.sub(r"`([^`]*)`", r"\1", t)
        # 图片/链接 → 保留文字部分
        t = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", t)
        t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
        # URL
        t = re.sub(r"https?://\S+|www\.\S+", " ", t)
        # markdown 符号
        t = re.sub(r"[*_#>~]+", " ", t)
        # 表情
        t = VoiceEngine._EMOJI_RE.sub(" ", t)
        # 换行 → 空格，折叠连续空白
        t = re.sub(r"\s+", " ", t)
        t = t.strip().strip("，。！？,.;:：;!?")
        # 截断（按字符数）
        max_len = int(cfg.VOICE_MAX_CHARS or 80)
        if len(t) > max_len:
            t = t[:max_len]
        return t

    # ── GPT-SoVITS 定制音色（唯一合成方式） ────────────────

    def _gptsovits_synth(self, text, emotion="neutral"):
        """HTTP 调本地 GPT-SoVITS 服务，直接合成六花音色。
        emotion: neutral/happy/sad → 按情感参考音频合成音色。"""
        url = (cfg.GPT_SOVITS_URL or "http://127.0.0.1:9880").rstrip("/") + "/tts"
        # 情感参考（缺失回退链：指定情感 → neutral → 旧 ref）
        refs = cfg.get_gptsovits_emotion_refs()
        emo = emotion if emotion in refs else "neutral"
        ref = refs.get(emo) or {}
        ref_audio = ref.get("audio") or cfg.GPT_SOVITS_REF_AUDIO
        ref_text = ref.get("text") or cfg.GPT_SOVITS_REF_TEXT
        if not os.path.exists(ref_audio):
            ref_audio, ref_text = cfg.GPT_SOVITS_REF_AUDIO, cfg.GPT_SOVITS_REF_TEXT
        lang = "ja" if cfg.PERSONA_LANGUAGE == "ja" else "zh"
        temp = float(getattr(cfg, "GPT_SOVITS_TEMPERATURE", 1.0))
        top_k = int(getattr(cfg, "GPT_SOVITS_TOP_K", 5))
        top_p = float(getattr(cfg, "GPT_SOVITS_TOP_P", 1.0))
        steps = int(getattr(cfg, "GPT_SOVITS_SAMPLE_STEPS", 32))
        rp = float(getattr(cfg, "GPT_SOVITS_REPETITION_PENALTY", 1.35))
        split = str(getattr(cfg, "GPT_SOVITS_TEXT_SPLIT_METHOD", "cut5"))
        h = hashlib.md5((
            "gptsovits|" + text
            + "|ref=" + ref_audio
            + "|reft=" + ref_text
            + "|lang=" + lang
            + "|emo=" + emo
            + "|sf=" + str(getattr(cfg, "GPT_SOVITS_SPEED_FACTOR", 1.0))
            + "|temp=" + str(temp)
            + "|topk=" + str(top_k)
            + "|topp=" + str(top_p)
            + "|steps=" + str(steps)
            + "|rp=" + str(rp)
            + "|split=" + split
            + "|url=" + url
        ).encode("utf-8")).hexdigest()
        os.makedirs(cfg.VOICE_CACHE_DIR, exist_ok=True)
        out_path = os.path.join(cfg.VOICE_CACHE_DIR, f"{h}.wav")
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            return out_path

        params = {
            "text": text,
            "text_lang": lang,
            "ref_audio_path": ref_audio,
            "prompt_lang": cfg.GPT_SOVITS_PROMPT_LANG,
            "prompt_text": ref_text,
            "text_split_method": split,
            "batch_size": 1,
            "media_type": "wav",
            "streaming_mode": False,
            "speed_factor": float(getattr(cfg, "GPT_SOVITS_SPEED_FACTOR", 1.0)),
            "temperature": temp,
            "top_k": top_k,
            "top_p": top_p,
            "sample_steps": steps,
            "repetition_penalty": rp,
        }
        try:
            r = requests.get(url, params=params,
                             timeout=float(getattr(cfg, "GPT_SOVITS_TIMEOUT", 180)))
        except requests.RequestException as e:
            raise RuntimeError(f"GPT-SoVITS 服务不可达: {e}")
        if r.status_code != 200:
            raise RuntimeError(f"GPT-SoVITS 失败({r.status_code}): {r.text[:200]}")
        with open(out_path, "wb") as f:
            f.write(r.content)
        if os.path.getsize(out_path) == 0:
            raise RuntimeError("GPT-SoVITS 返回空音频")
        return out_path

    # ── 合成（带缓存） ───────────────────────────────────────

    def synthesize(self, text, emotion="neutral"):
        """文字 → 六花.wav 完整路径（GPT-SoVITS 直出六花语音）。"""
        text = self._clean_text(text)
        if not text:
            return None
        return self._gptsovits_synth(text, emotion)

    # ── 对外：说一句话 ───────────────────────────────────────

    @staticmethod
    def _setup_problem():
        """检查语音环境是否就绪；返回问题描述，就绪返回空串。"""
        if not getattr(cfg, "GPT_SOVITS_REF_AUDIO", "") or not os.path.exists(cfg.GPT_SOVITS_REF_AUDIO):
            return "未配置 GPT-SoVITS 六花参考音频 (GPT_SOVITS_REF_AUDIO)"
        if not getattr(cfg, "GPT_SOVITS_REF_TEXT", ""):
            return "未配置参考音频文字 (GPT_SOVITS_REF_TEXT)"
        from brain.voice_server import get_voice_server
        server = get_voice_server()
        # 先检查外部服务（重要：确保能检测到已运行的服务）
        server.ensure_adopt_external()
        status = server.status()
        # 检查服务状态：ready=正常运行，starting=启动中（稍等即可），其他=需要启动
        if status["state"] == "ready":
            return ""  # 服务就绪
        elif status["state"] == "starting":
            return "GPT-SoVITS 正在启动中，请稍候..."
        elif status["state"] == "error":
            return f"GPT-SoVITS 服务异常: {status.get('detail', '未知错误')}"
        else:
            return "GPT-SoVITS 语音服务未运行。\n请在输入框点击「🎙️语音服务」按钮启动（需等待30-60秒加载模型）"

    def speak(self, text, to="local", emotion="neutral", translation=None):
        """fire-and-forget：起后台线程合成，完成后 emit voice_ready。立即返回。
        emotion: neutral/happy/sad（影响 GPT-SoVITS 情感参考音色）；
        translation: 中文对照，语音条展示用（日语模式由 LLM 提供）。"""
        if not cfg.VOICE_ENABLED:
            return "语音开关是关着的，没有开口"
        problem = self._setup_problem()
        if problem:
            return f"语音不可用：{problem}"
        to = (to or "local").lower()
        if to not in ("local", "qq", "both"):
            to = "local"

        # 检查QQ发送目标
        if to in ("qq", "both"):
            if not self._qq_context or self._qq_context == (None, None):
                # 没有配置QQ桥接或没有QQ会话上下文，强制改为local
                to = "local"
                logger.warning(f"语音请求 to='{to}' 但无QQ上下文，已改为local")

        if emotion not in ("neutral", "happy", "sad"):
            emotion = "neutral"
        qq_target = self._qq_context
        self._gen += 1
        gen = self._gen
        threading.Thread(
            target=self._speak_worker,
            args=(text, to, qq_target, gen, emotion, translation),
            daemon=True, name="VoiceSpeak",
        ).start()
        return f"（已用语音说：{text[:24]}…）"

    def _speak_worker(self, text, to, qq_target, gen, emotion="neutral", translation=None):
        try:
            # 发送开始合成信号
            cleaned_text = self._clean_text(text)
            self.signals.voice_synthesizing.emit("🎙️ 六花正在为你合成语音...", cleaned_text)

            with self._lock:
                path = self.synthesize(text, emotion)

            # 发送合成完成信号（移除进度气泡）
            self.signals.voice_synthesis_done.emit()

            if gen != self._gen:
                return  # 已被更新的 speak 或叫停取代，作废在途合成
            if path:
                tgt = f"{qq_target[0]},{qq_target[1]}" if qq_target else ""
                spoken = self._clean_text(text)   # 实际念出的文字（无 markdown/emoji/・）
                self.signals.voice_ready.emit(path, to, tgt, spoken, translation or "")
        except Exception as e:
            logger.error(f"语音合成失败: {e}")
            # 合成失败也要移除进度气泡
            self.signals.voice_synthesis_done.emit()

    def stop_current(self):
        """作废在途合成（新的 speak 或叫停会取代它）。"""
        self._gen += 1


# 模块级单例
_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = VoiceEngine()
    return _engine
