"""
RikkaAI - 主窗口
"""
import json
import os
import threading
import time
import random
import shutil
from datetime import date, datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QGridLayout,
    QLabel, QPushButton, QSplitter, QFrame, QStackedWidget,
    QGraphicsOpacityEffect,
)
from PyQt5.QtCore import (
    QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QTimer, QThread,
    pyqtSignal, QObject,
)
from PyQt5.QtGui import QColor, QPixmap, QIcon
import config
import gui.theme_manager as theme_manager
from brain.qq_bridge import get_bridge, set_message_handler, set_event_handlers
from gui.chat_widget import ChatWidget
from gui.input_panel import InputPanel
from gui.character_widget import CharacterWidget, NavSidebar, SessionListPanel
from gui.chat_page import ChatBackgroundPage
from gui.chat_top_bar import ChatTopBar
from gui.chat_insights import ChatInsightsPanel
from gui.knowledge_page import KnowledgePage
from gui.dashboard_pages import HistoryPage, MemoryPage, SettingsPage
from gui.home_widget import create_home_widget
from brain.agent import AgentCore
import brain.history as history
import brain.diary as diary_module


# ═══════════════════════════════════════════════════════════════════
#  定时器管理器 —— 替代旧的固定 QTimer
# ═══════════════════════════════════════════════════════════════════

class TimerManager(QObject):
    """链式主动 + 临时回访 的定时器管理器

    两种定时器类型:
    - proactive : 链式主动，AI 每次触发后重建
    - follow_up : 临时回访，一次性
    """
    timer_fired = pyqtSignal(str, dict)  # (type, context)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timers = []       # [(fire_epoch, timer_id, type, context)]
        self._next_id = 0
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._check)
        self._tick.start(2000)  # 每 2 秒检查一次

    def schedule(self, timer_type: str, delay_minutes: float, context: dict = None) -> int:
        """添加一个定时器，返回 timer_id"""
        fire_at = time.time() + delay_minutes * 60
        tid = self._next_id
        self._next_id += 1
        self._timers.append((fire_at, tid, timer_type, context or {}))
        return tid

    def cancel(self, timer_id: int):
        """按 ID 取消定时器"""
        self._timers = [t for t in self._timers if t[1] != timer_id]

    def cancel_by_type(self, timer_type: str):
        """按类型取消所有定时器"""
        self._timers = [t for t in self._timers if t[0] != timer_type]

    def list_pending(self) -> list:
        """列出待处理的定时器"""
        now = time.time()
        return [
            {"id": tid, "type": tp, "remaining_sec": max(0, int(fire - now)), "context": ctx}
            for fire, tid, tp, ctx in sorted(self._timers)
        ]

    def _check(self):
        now = time.time()
        fired = []
        remaining = []
        for entry in self._timers:
            fire_at, tid, tp, ctx = entry
            if now >= fire_at:
                fired.append(entry)
            else:
                remaining.append(entry)
        self._timers = remaining
        for _fire_at, _tid, tp, ctx in fired:  # noqa
            self.timer_fired.emit(tp, ctx)


# ═══════════════════════════════════════════════════════════════════
#  QQ 桥接信号桥（安全地从后台线程通知 UI）
# ═══════════════════════════════════════════════════════════════════

class QQBridgeSignals(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    got_message = pyqtSignal(object, object, str, str)  # user_id, group_id, message, msg_type
    got_error = pyqtSignal(str)


# ═══════════════════════════════════════════════════════════════════
#  工作线程
# ═══════════════════════════════════════════════════════════════════

class AgentWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    stream = pyqtSignal(str)

    def __init__(self, agent, text):
        super().__init__()
        self.agent = agent
        self._input = text

    def run(self):
        try:
            r = self.agent.chat(self._input, on_stream=lambda c: self.stream.emit(c))
            self.finished.emit(r)
        except Exception as e:
            self.error.emit(str(e))


class ImageWorker(QObject):
    done = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self._path = path

    def run(self):
        from brain.tools import handle_tool_call
        try:
            r = handle_tool_call("describe_image", {"path": self._path, "prompt": "请详细描述图片内容"})
            if r and not r.startswith("识图失败") and "执行出错" not in r:
                self.done.emit(r[:500])
            else:
                self.done.emit(f"[识图失败: {r}]")
        except Exception as e:
            self.done.emit(f"[识图失败: {e}]")


class ProactiveWorker(QObject):
    """独立观察（摸鱼偷看）：截图 → 视觉分析 → 返回结构化描述。
    分析只描述画面事实，不做情绪/意图推断（安全约束在 _on_proactive_peek 里进一步约束六花的表达）。"""
    done = pyqtSignal(str, str)

    def run(self):
        try:
            from PIL import ImageGrab
            from brain.tools import _vision
            d = config.SCREENSHOTS_DIR
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"proactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            ImageGrab.grab().save(p)
            # 中立描述：只报画面里明确可见的东西，不要推测用户情绪/意图/进度
            a = _vision(
                "这是契约者屏幕的截图。请客观、简短地描述画面中明确可见的内容"
                "（窗口标题、正在播放/编辑的内容、明显的界面元素等）。"
                "只描述看到的事实，不要猜测契约者在做什么、心情如何、进度如何。30字以内。",
                p, 0.2, 300,
            )
            self.done.emit(a, p)
        except Exception:
            self.done.emit("", "")


class MemoryCueWorker(QObject):
    """记忆唤起评估线程：把记忆冥想盆里的高权重碎片交给 LLM 判定
    （contact/check_in/remind/suppress/skip + 时间窗口 + 写作意图），写回 memory_proactive_cues。
    完全对齐莲心的 memory_cue_worker：模型做语义判断，代码强制执行时机。"""
    done = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, max_candidates=8, parent=None):
        super().__init__(parent)
        self.max_candidates = max_candidates

    def run(self):
        try:
            from brain import memory_proactive as mp
            candidates = mp.collect_candidates(self.max_candidates)
            if not candidates:
                mp.record_evaluation_batch("无新候选")
                self.done.emit({"evaluated": 0, "approved": 0})
                return

            from openai import OpenAI
            client = OpenAI(api_key=config.API_KEY, base_url=config.API_BASE, timeout=60)
            now = datetime.now()
            prompt = (
                f"当前本地时间：{now.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"下面是记忆库中六花记下的、关于契约者的重要事项（情感权重较高）。\n"
                f"请判断哪些适合在未来由六花主动关心、询问或提醒。\n\n"
                f"边界：\n"
                f"- 只有确实能带来帮助或自然关怀时才 contact/check_in/remind，否则 skip\n"
                f"- 生病、休息、情绪低落等更适合少打扰时可返回 suppress，并给出 window_end\n"
                f"- due_at/window_end 用 YYYY-MM-DD HH:MM:SS 格式，最早不早于 5 分钟后，最长不超过 30 天\n"
                f"- message_instruction 是给六花的写作意图（一两句话），不要直接冒充最终消息\n"
                f"- 每个 fingerprint 必须原样返回一次\n\n"
                f"仅返回 JSON：{{\"evaluations\":[{{\"fingerprint\":\"...\","
                f"\"action\":\"contact|check_in|remind|suppress|skip\",\"due_at\":\"...\","
                f"\"window_end\":\"...\",\"confidence\":0.0,\"rationale\":\"...\","
                f"\"message_instruction\":\"...\"}}]}}\n\n"
                f"候选：{json.dumps(candidates, ensure_ascii=False)}"
            )
            resp = client.chat.completions.create(
                model=config.MODEL,
                temperature=0.1,
                max_tokens=1800,
                messages=[
                    {"role": "system", "content": "你是谨慎的主动关怀决策器，只做判断，不直接聊天。"},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = (resp.choices[0].message.content or "{}").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            start, end = raw.find("{"), raw.rfind("}")
            data = json.loads(raw[start:end + 1] if start >= 0 and end >= start else "{}")

            by_fp = {c["fingerprint"]: c for c in candidates}
            valid = []
            for decision in data.get("evaluations", []):
                fp = decision.get("fingerprint")
                if fp in by_fp:
                    valid.append({"fingerprint": fp, "decision": decision})
            # 模型没返回的候选显式置 skip，防止无限重试
            seen = {v["fingerprint"] for v in valid}
            valid.extend(
                {"fingerprint": fp, "decision": {"action": "skip", "rationale": "模型未返回该候选"}}
                for fp in by_fp if fp not in seen
            )
            mp.apply_evaluations(valid)
            approved = sum(
                v["decision"].get("action") in ("contact", "check_in", "remind") for v in valid
            )
            mp.record_evaluation_batch(f"评估 {len(valid)} 条，通过 {approved} 条")
            self.done.emit({"evaluated": len(valid), "approved": approved})
        except Exception as exc:
            try:
                from brain import memory_proactive as mp
                mp.record_evaluation_batch(f"评估失败：{exc}")
            except Exception:
                pass
            self.error.emit(str(exc))


class QQAgentWorker(QObject):
    """QQ 消息处理线程（带流式 + 权限控制）"""
    stream = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, agent, text, restricted=False):
        super().__init__()
        self.agent = agent
        self._input = text
        self._restricted = restricted

    def run(self):
        try:
            print(f"[QQ] worker.run 开始 agent={id(self.agent)} restricted={self._restricted}", flush=True)
            self.agent.set_restricted(self._restricted)
            text = self._input
            # 消息里带 CQ 图片段 → 下载并识别，让六花真正"看到"QQ 发来的图
            try:
                from brain.tools import _describe_qq_images
                if "[CQ:image" in text:
                    text, _ = _describe_qq_images(text)
            except Exception:
                pass
            r = self.agent.chat(text, on_stream=lambda c: self.stream.emit(c))
            self.finished.emit(r)
        except Exception as e:
            print(f"[QQ] worker.run 异常: {e}", flush=True)
            self.error.emit(str(e))


class DraggableTitleBar(QFrame):
    """Chat-page title bar for the frameless desktop window."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self._drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self._window.move(event.globalPos() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._window._handle_window_action("maximize")
        super().mouseDoubleClickEvent(event)


# ═══════════════════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    # 日记自动收尾后台线程完成信号（worker 线程 emit，主线程槽刷新）
    _diary_summary_done = pyqtSignal(bool, str)
    # 周期总结（周记/月报/年鉴）后台线程完成信号
    _period_summary_done = pyqtSignal(str, str)
    # 敏感工具权限弹窗：后台线程 emit（Queued 到主线程），槽在主线程创建 QMessageBox
    _ask_dialog_signal = pyqtSignal(str, str)
    # 主动冲浪完成信号（后台线程 → 主线程聊天区推荐）
    _surf_result_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("RikkaAI - 六花AI")
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        # 核心模块
        self.agent = AgentCore()
        self.agent.start_session()

        # QQ 桥接（信号桥，保证线程安全）
        self._qq_bridge = get_bridge()
        from brain import tools as _tt
        _tt.set_qq_bridge(self._qq_bridge)
        self._qq_signals = QQBridgeSignals()
        self._qq_signals.connected.connect(self._on_qq_connected_modern)
        self._qq_signals.disconnected.connect(self._on_qq_disconnected_modern)
        self._qq_signals.got_message.connect(self._on_qq_message_threadsafe)
        self._qq_signals.got_error.connect(self._on_qq_error)
        set_message_handler(self._on_qq_message_bg)
        set_event_handlers(
            connected=lambda: self._qq_signals.connected.emit(),
            disconnected=lambda: self._qq_signals.disconnected.emit(),
        )

        # 语音引擎（六花自己决定何时开口）
        from brain.voice import get_engine as _get_voice_engine
        self._voice = _get_voice_engine()
        self._voice.signals.voice_ready.connect(self._on_voice_ready)
        self._audio_player = None  # QMediaPlayer，惰性创建

        # 本地 GPT-SoVITS 语音服务管理器（首页 AI 音乐卡片开关）
        from brain.voice_server import get_voice_server as _get_voice_server
        self._voice_server = _get_voice_server()
        self._voice_server.signals.status_changed.connect(self._on_voice_server_status)

        # 会话
        last_id = config.load_last_session()
        self._session_id = last_id if last_id else 0

        # 工作线程
        self._worker_thread = None
        self._worker = None
        self._img_thread = None
        self._img_worker = None
        self._proactive_thread = None
        self._proactive_worker = None
        self._save_btn = None
        # QQ worker 强引用仓库：防止局部变量 worker/thread 被 GC 吃掉导致
        # started.connect(worker.run) 连接失效、run() 永不执行（见 22:47 日志）
        self._qq_worker_refs = set()
        self._qq_busy = set()  # 正在回复中的 QQ user_id（同用户串行化，防止并发串扰）

        # ── 定时器管理器（替代旧 QTimer） ──
        self._timer_mgr = TimerManager(self)
        self._timer_mgr.timer_fired.connect(self._on_timer_fired)

        # ── ask 询问档：敏感工具调用前弹窗（allow/ask/deny 三档权限的 ask 档） ──
        try:
            from brain import tools as _tt
            _tt.register_ask_handler(self._ask_tool_permission)
        except Exception:
            pass

        # ── 记忆唤起评估（后台，每 30 分钟跑一次） ──
        self._memory_cue_thread = None
        self._memory_cue_worker = None
        self._memory_cue_timer = QTimer(self)
        self._memory_cue_timer.setInterval(30 * 60 * 1000)  # 30 分钟
        self._memory_cue_timer.timeout.connect(self._run_memory_cue_eval)
        if getattr(config, "MEMORY_CUE_ENABLED", False):
            self._memory_cue_timer.start()
            QTimer.singleShot(60 * 1000, self._run_memory_cue_eval)  # 启动 1 分钟后先评估一次

        # ── 自动周记（每周日固定时间生成本周周记；分钟级检查，到点才动作） ──
        self._weekly_timer = QTimer(self)
        self._weekly_timer.setInterval(60 * 1000)  # 每分钟检查一次（轻量）
        self._weekly_timer.timeout.connect(self._check_weekly_summary)
        if getattr(config, "WEEKLY_AUTO_ENABLED", False):
            self._weekly_timer.start()

        # ── 日记自动收尾（每天到点自动把当天流水提炼成六花视角的日记；启动时补写最近几天） ──
        self._diary_summary_thread = None
        self._diary_summary_timer = QTimer(self)
        self._diary_summary_timer.setInterval(60 * 1000)  # 每分钟检查一次（轻量）
        self._diary_summary_timer.timeout.connect(self._check_diary_auto_summary)
        self._diary_summary_done.connect(self._on_diary_auto_done)
        self._period_summary_done.connect(self._on_period_summary_done)
        self._period_thread = None
        # 权限弹窗跨线程桥
        self._ask_dialog_signal.connect(self._on_ask_dialog)
        self._ask_evt = threading.Event()
        self._ask_result = {}
        # 主动冲浪（定期去B站推荐视频）
        self._surf_result_signal.connect(self._on_surf_result)
        self._last_surf_ts = time.time()
        self._surf_thread = None
        self._surf_timer = QTimer(self)
        self._surf_timer.setInterval(60 * 1000)  # 每分钟检查一次（轻量）
        self._surf_timer.timeout.connect(self._check_auto_surf)
        if getattr(config, "SURF_AUTO_ENABLED", False):
            self._surf_timer.start()
        # ── Archivist 记忆档案员（每 2 分钟轻量层；闲置/碎片多时后台跑深度层叙事归并） ──
        self._archivist_thread = None
        self._archivist_timer = QTimer(self)
        self._archivist_timer.setInterval(2 * 60 * 1000)  # 每 2 分钟 tick
        self._archivist_timer.timeout.connect(self._archivist_tick)
        self._archivist_timer.start()
        QTimer.singleShot(30 * 1000, self._archivist_tick)  # 启动 30 秒后先跑一次
        if getattr(config, "DIARY_AUTO_SUMMARY_ENABLED", False):
            self._diary_summary_timer.start()
            QTimer.singleShot(45 * 1000, self._diary_auto_backfill)  # 启动 45 秒后补写最近几天

        # 旧的状态跟踪（保留，简化复位用）
        self._last_activity = datetime.now()
        self._proactive_enabled = config.PROACTIVE_ENABLED
        self._in_proactive = False

        # ⏹ 停止按钮状态：抑制迟到语音 + 作废在途屏幕偷看
        self._voice_suppressed = False  # 叫停后抑制迟到的 voice_ready
        self._response_suppressed = False  # 叫停后抑制迟到的 LLM 回复（停止纪元）
        self._action_epoch = 0          # 每次叫停 +1，作废在途的屏幕偷看结果
        self._peek_epoch = 0            # 屏幕偷看启动时的 epoch
        self._last_observe_ts = 0.0     # 上次观察（摸鱼偷看）时间戳，独立冷却用
        self._active_cue_id = None      # 当前主动回复消费的记忆唤起 cue id（回复完成后标记 delivered）
        self._active_appearance_key = None
        self._appearance_animation = None
        self._workspace_transition = None

        # 界面
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        ip = os.path.join(
            config.ASSETS_DIR, "images", "branding", "rikka_mark.png"
        )
        if os.path.exists(ip):
            self.setWindowIcon(QIcon(ip))
        self._setup_ui_modern()
        self._load_theme()
        self._apply_appearance(force=True)
        self._appearance_timer = QTimer(self)
        self._appearance_timer.setInterval(60 * 1000)
        self._appearance_timer.timeout.connect(self._check_seasonal_appearance)
        self._appearance_timer.start()

        # 加载历史会话
        loaded = False
        if self._session_id:
            loaded = self._load_session_messages(self._session_id)
        if not loaded:
            self._session_id = history.create_session()
            config.save_user_config({"last_session_id": self._session_id})

    # ── UI 构造 ────────────────────────────────────────────────

    def _setup_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        ml = QVBoxLayout(cw)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # 标题栏
        tb = QWidget()
        tb.setObjectName("TitleBar")
        tb.setFixedHeight(60)
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(16, 0, 16, 0)
        tt = QLabel("RikkaAI - 六花AI")
        tt.setObjectName("TitleText")
        tl.addWidget(tt)
        ts = QLabel("v" + config.APP_VERSION)
        ts.setObjectName("TitleSub")
        tl.addWidget(ts)
        tl.addStretch()
        for emoji, tooltip, slot in [
            ("➕", "新建", self._new_conversation),
            ("📜", "历史", self._open_history),
            ("📋", "备忘录", self._open_notes),
            ("🔧", "工具", self._open_tools),
            ("📚", "年鉴", self._open_summary),
            ("⚙", "设置", self._open_settings),
        ]:
            b = QPushButton(emoji)
            b.setFixedSize(32, 32)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setStyleSheet(
                "QPushButton{background:transparent;border:1px solid #F0E0F0;"
                "border-radius:16px;font-size:14px;color:#C8BBFF}"
                "QPushButton:hover{background:#FFF3EA;border-color:#E9C8FF;color:#FFB7D1}"
            )
            b.clicked.connect(slot)
            tl.addWidget(b)

        # 🛑 停止按钮（单独放，特殊样式）
        # 🛑 停止按钮（分开，特殊样式）
        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setFixedSize(28, 28)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setToolTip("停止")
        self._stop_btn.setStyleSheet(
            "QPushButton{background:#FFF0F0;border:1px solid #FFCCCC;"
            "border-radius:14px;font-size:12px;color:#FF8080}"
            "QPushButton:hover{background:#FFE0E0;border-color:#FFB7D1;color:#FF4444}"
        )
        self._stop_btn.clicked.connect(self._stop_everything)
        tl.addWidget(self._stop_btn)

        # 💬 QQ 开关按钮
        self._qq_btn = QPushButton("💬")
        self._qq_btn.setFixedSize(28, 28)
        self._qq_btn.setCursor(Qt.PointingHandCursor)
        self._qq_btn.setToolTip("QQ 离线")
        self._qq_btn.setStyleSheet(
            "QPushButton{background:transparent;border:1px solid #F0E0F0;"
            "border-radius:14px;font-size:12px;color:#C8BBFF}"
            "QPushButton:hover{background:#FFF3EA;border-color:#E9C8FF;color:#FFB7D1}"
        )
        self._qq_btn.clicked.connect(self._toggle_qq_bridge)
        tl.addWidget(self._qq_btn)
        ml.addWidget(tb)

        # 主区域
        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(1)
        self.character_widget = CharacterWidget()
        sp.addWidget(self.character_widget)
        rp = QWidget()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.chat_widget = ChatWidget()
        rl.addWidget(self.chat_widget, 1)
        self.input_panel = InputPanel()
        self.input_panel.send_message.connect(self._on_user_input)
        self.input_panel.send_image.connect(self._on_user_image)
        self.input_panel.open_tools.connect(self._open_tools)
        self.input_panel.open_knowledge.connect(self._show_knowledge)
        self.input_panel.qq_bridge_requested.connect(self._toggle_qq_bridge_modern)
        self.input_panel.voice_toggle_requested.connect(self._toggle_voice)
        self.input_panel.gptsovits_service_requested.connect(self._toggle_gptsovits_service)
        self.input_panel.stop_requested.connect(self._stop_everything)
        rl.addWidget(self.input_panel)
        sp.addWidget(rp)
        pw = config.CHARACTER_PANEL_WIDTH
        sp.setSizes([pw, config.WINDOW_WIDTH - pw])
        sp.setCollapsible(0, False)
        sp.setCollapsible(1, False)
        ml.addWidget(sp, 1)

        # 状态栏
        sb = QWidget()
        sb.setObjectName("StatusBar")
        sb.setFixedHeight(24)
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(16, 0, 16, 0)
        si = QLabel()
        sip = os.path.join(config.IMAGES_DIR, "avatar.png")
        spx = QPixmap(sip)
        if spx and not spx.isNull():
            spx = spx.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            si.setPixmap(spx)
            si.setFixedSize(18, 18)
        else:
            si.setObjectName("StatusActive")
        sl.addWidget(si)
        st = QLabel("邪王真眼 激活中")
        st.setStyleSheet("color:#7a5aaa;font-size:11px;")
        sl.addWidget(st)
        sl.addStretch()
        sm = QLabel(f"Model: {config.MODEL}")
        sm.setStyleSheet("color:#999;font-size:10px;")
        sl.addWidget(sm)
        ml.addWidget(sb)

    def _load_theme(self):
        styles = []
        for filename in (
            "theme.qss", "home.qss", "chat.qss", "knowledge.qss", "diary.qss",
            "dashboard_pages.qss", "memory.qss", "surf_history.qss",
        ):
            path = os.path.join(config.STYLES_DIR, filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    styles.append(f.read())
        self._base_stylesheet = "\n".join(styles)
        self.setStyleSheet(self._base_stylesheet)

    def _apply_appearance(self, force=False, day=None, animate=False):
        """Resolve and apply one effective appearance without rebuilding page state."""
        appearance = theme_manager.resolve_appearance(config, day)
        if not force and appearance.key == self._active_appearance_key:
            return False

        previous_key = self._active_appearance_key
        wash = appearance.wash_color()
        theme_manager.set_active_theme(appearance)
        if self._base_stylesheet:
            self.setStyleSheet(
                self._base_stylesheet + "\n" + theme_manager.theme_override(appearance)
            )

        page_specs = (
            (getattr(self, "home_widget", None), "home"),
            (getattr(self, "_chat_page", None), "chat"),
            (getattr(self, "knowledge_page", None), "knowledge"),
            (getattr(self, "diary_page", None), "diary"),
            (getattr(self, "history_page", None), "history"),
            (getattr(self, "surf_history_page", None), "surfing"),
            (getattr(self, "memory_page", None), "memory"),
            (getattr(self, "settings_page", None), "settings"),
        )
        for page, page_id in page_specs:
            if page is None:
                continue
            pixmap = theme_manager.load_theme_background(
                appearance, page_id=page_id
            )
            appearance_setter = getattr(page, "apply_appearance", None)
            if callable(appearance_setter):
                appearance_setter(appearance, pixmap, wash)
                continue
            setter = getattr(page, "set_appearance_background", None)
            if callable(setter):
                setter(pixmap, wash)
            else:
                page._background = QPixmap(pixmap)
                if hasattr(page, "_background_wash"):
                    page._background_wash = QColor(wash)
                page.update()
        if hasattr(self, "nav_sidebar"):
            self.nav_sidebar.apply_appearance(appearance)

        self._active_appearance_key = appearance.key
        if animate and previous_key is not None:
            self._fade_visible_page()
        return True

    def _check_seasonal_appearance(self):
        self._apply_appearance(animate=True)

    def _appearance_animations_enabled(self):
        if os.environ.get("RIKKAI_REDUCE_MOTION", "").strip().lower() in (
            "1", "true", "yes", "on"
        ):
            return False
        if os.name == "nt":
            try:
                import ctypes
                enabled = ctypes.c_int()
                if ctypes.windll.user32.SystemParametersInfoW(
                    0x1042, 0, ctypes.byref(enabled), 0
                ):
                    return bool(enabled.value)
            except Exception:
                pass
        return True

    def _fade_visible_page(self):
        if not self._appearance_animations_enabled():
            return
        page = self._workspace_stack.currentWidget()
        if page is None:
            return
        # Chromium-backed widgets do not reliably support QGraphicsEffect.
        if hasattr(page, "web_view"):
            return
        if self._appearance_animation is not None:
            animation, old_page, old_effect = self._appearance_animation
            animation.stop()
            if old_page.graphicsEffect() is old_effect:
                old_page.setGraphicsEffect(None)
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.62)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(220)
        animation.setStartValue(0.62)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def finish():
            if page.graphicsEffect() is effect:
                page.setGraphicsEffect(None)
            animation.deleteLater()
            if self._appearance_animation and self._appearance_animation[0] is animation:
                self._appearance_animation = None

        animation.finished.connect(finish)
        self._appearance_animation = (animation, page, effect)
        animation.start()

    def _setup_ui_modern(self):
        cw = QWidget()
        cw.setObjectName("WindowRoot")
        self.setCentralWidget(cw)

        ml = QVBoxLayout(cw)
        ml.setContentsMargins(14, 12, 14, 10)
        ml.setSpacing(10)
        self._root_layout = ml

        tb = DraggableTitleBar(self)
        tb.setObjectName("TitleBar")
        tb.setFixedHeight(64)
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(14, 10, 12, 10)
        tl.setSpacing(10)

        icon_label = QLabel()
        icon_label.setObjectName("TitleLogo")
        icon_label.setFixedSize(38, 38)
        icon_path = os.path.join(
            config.ASSETS_DIR, "images", "branding", "rikka_mark.png"
        )
        icon_pixmap = QPixmap(icon_path).scaled(
            38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        if icon_pixmap and not icon_pixmap.isNull():
            icon_label.setPixmap(icon_pixmap)
        tl.addWidget(icon_label)

        title_group = QVBoxLayout()
        title_group.setContentsMargins(0, 0, 0, 0)
        title_group.setSpacing(1)
        tt = QLabel("RikkaAI")
        tt.setObjectName("TitleText")
        title_group.addWidget(tt)
        title_caption = QLabel("Far East Magic, Noa Society")
        title_caption.setObjectName("TitleCaption")
        title_group.addWidget(title_caption)
        tl.addLayout(title_group)

        ts = QLabel("v" + config.APP_VERSION)
        ts.setObjectName("TitleSub")
        tl.addWidget(ts)
        tl.addStretch()

        icon_dir = os.path.join(config.ASSETS_DIR, "figma", "icons")
        outline_dir = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")
        for icon_path, tooltip, slot in [
            (os.path.join(outline_dir, "home.svg"), "首页", self._show_home),
            (os.path.join(icon_dir, "plus.svg"), "新建对话", self._new_conversation),
            (os.path.join(icon_dir, "history.svg"), "历史记录", self._open_history),
            (os.path.join(icon_dir, "memory.svg"), "备忘录", self._open_notes),
            (os.path.join(icon_dir, "ai.svg"), "工具", self._open_tools),
            (os.path.join(icon_dir, "quote.svg"), "摘要", self._open_summary),
            (os.path.join(icon_dir, "settings.svg"), "设置", self._open_settings),
        ]:
            button = QPushButton()
            button.setObjectName("TitleActionButton")
            button.setIcon(QIcon(icon_path))
            button.setIconSize(QSize(17, 17))
            button.setFixedSize(34, 34)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tooltip)
            button.clicked.connect(slot)
            tl.addWidget(button)

        self._stop_btn = QPushButton()
        self._stop_btn.setObjectName("StopButton")
        self._stop_btn.setIcon(QIcon(os.path.join(icon_dir, "stop.svg")))
        self._stop_btn.setIconSize(QSize(17, 17))
        self._stop_btn.setFixedSize(34, 34)
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setToolTip("停止")
        self._stop_btn.clicked.connect(self._stop_everything)
        tl.addWidget(self._stop_btn)

        self._qq_btn = QPushButton()
        self._qq_btn.setObjectName("QQButton")
        self._qq_btn.setIcon(QIcon(os.path.join(icon_dir, "chat.svg")))
        self._qq_btn.setIconSize(QSize(17, 17))
        self._qq_btn.setFixedSize(34, 34)
        self._qq_btn.setCursor(Qt.PointingHandCursor)
        self._qq_btn.clicked.connect(self._toggle_qq_bridge_modern)
        tl.addWidget(self._qq_btn)

        for text, tooltip, action in [
            ("−", "最小化", "minimize"),
            ("□", "最大化 / 还原", "maximize"),
            ("×", "关闭", "close"),
        ]:
            button = QPushButton(text)
            button.setObjectName("TitleWindowButton")
            button.setFixedSize(30, 34)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _checked=False, value=action: self._handle_window_action(value))
            tl.addWidget(button)
        ml.addWidget(tb)
        self._title_bar = tb

        shell = QFrame()
        shell.setObjectName("MainShell")
        shell_layout = QGridLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # One navigation instance is layered over the page stack. Switching
        # pages only replaces the artwork and content underneath it.
        self.nav_sidebar = NavSidebar(active_section="home")
        self.nav_sidebar.home_requested.connect(self._show_home)
        self.nav_sidebar.chat_requested.connect(self._show_chat)
        self.nav_sidebar.history_requested.connect(self._open_history)
        self.nav_sidebar.memo_requested.connect(self._open_notes)
        self.nav_sidebar.summary_requested.connect(self._show_knowledge)
        self.nav_sidebar.diary_requested.connect(self._open_diary)
        self.nav_sidebar.surf_requested.connect(self._open_surf_history)
        self.nav_sidebar.tools_requested.connect(self._open_tools)
        self.nav_sidebar.settings_requested.connect(self._open_settings)

        self._workspace_stack = QStackedWidget()
        self._workspace_stack.setObjectName("WorkspaceStack")

        self.home_widget = create_home_widget()
        self.home_widget.start_chat.connect(self._start_home_chat)
        self.home_widget.chat_requested.connect(self._show_chat)
        self.home_widget.history_requested.connect(self._open_history)
        self.home_widget.memo_requested.connect(self._open_notes)
        self.home_widget.summary_requested.connect(self._show_knowledge)
        self.home_widget.tools_requested.connect(self._open_tools)
        self.home_widget.settings_requested.connect(self._open_settings)
        self.home_widget.session_selected.connect(self._load_session)
        if hasattr(self.home_widget, "window_action"):
            self.home_widget.window_action.connect(self._handle_window_action)
            self.home_widget.window_drag.connect(self._handle_window_drag)
        if hasattr(self.home_widget, "voice_action"):
            self.home_widget.voice_action.connect(self._on_home_voice_action)
        self._workspace_stack.addWidget(self.home_widget)

        self.knowledge_page = KnowledgePage()
        self.knowledge_page.history_requested.connect(self._open_history)
        self.knowledge_page.memo_requested.connect(self._open_notes)
        self.knowledge_page.tools_requested.connect(self._open_tools)
        self.knowledge_page.settings_requested.connect(self._open_settings)
        self.knowledge_page.window_action.connect(self._handle_window_action)
        self.knowledge_page.window_drag.connect(self._handle_window_drag)
        self._workspace_stack.addWidget(self.knowledge_page)

        from gui.diary_page import DiaryPage
        self.diary_page = DiaryPage()
        self.diary_page.history_requested.connect(self._open_history)
        self.diary_page.memo_requested.connect(self._open_notes)
        self.diary_page.tools_requested.connect(self._open_tools)
        self.diary_page.settings_requested.connect(self._open_settings)
        self.diary_page.window_action.connect(self._handle_window_action)
        self.diary_page.window_drag.connect(self._handle_window_drag)
        self._workspace_stack.addWidget(self.diary_page)

        self.history_page = HistoryPage()
        self.history_page.session_selected.connect(self._load_session)
        self.history_page.history_cleared.connect(self._on_config_changed)
        self._connect_dashboard_page(self.history_page)
        self._workspace_stack.addWidget(self.history_page)

        from gui.surf_history_page import SurfHistoryPage
        self.surf_history_page = SurfHistoryPage()
        self._connect_dashboard_page(self.surf_history_page)
        self._workspace_stack.addWidget(self.surf_history_page)

        self.memory_page = MemoryPage()
        self.memory_page.advanced_requested.connect(lambda: self._open_settings_section("记忆与隐私"))
        self._connect_dashboard_page(self.memory_page)
        self._workspace_stack.addWidget(self.memory_page)

        self.settings_page = SettingsPage()
        self.settings_page.config_changed.connect(self._on_config_changed)
        self._connect_dashboard_page(self.settings_page)
        self._workspace_stack.addWidget(self.settings_page)

        chat_page = ChatBackgroundPage()
        chat_page_layout = QVBoxLayout(chat_page)
        chat_page_layout.setContentsMargins(190, 0, 0, 0)
        chat_page_layout.setSpacing(0)

        sp = QSplitter(Qt.Horizontal)
        sp.setObjectName("MainSplitter")
        sp.setHandleWidth(0)

        self.session_panel = SessionListPanel()
        self.session_panel.new_conversation_requested.connect(self._new_conversation)
        self.session_panel.session_selected.connect(self._load_session)
        self.session_panel.history_requested.connect(self._open_history)
        sp.addWidget(self.session_panel)

        chat_workspace = QFrame()
        chat_workspace.setObjectName("ChatWorkspace")
        workspace_layout = QVBoxLayout(chat_workspace)
        workspace_layout.setContentsMargins(0, 8, 8, 8)
        workspace_layout.setSpacing(0)

        chat_content = QFrame()
        chat_content.setObjectName("ChatContent")
        content_outer = QVBoxLayout(chat_content)
        content_outer.setContentsMargins(0, 0, 0, 0)
        content_outer.setSpacing(0)

        drag_strip = DraggableTitleBar(self)
        drag_strip.setObjectName("ChatDragRegion")
        drag_strip.setFixedHeight(54)
        content_outer.addWidget(drag_strip)

        content_row = QWidget()
        content_row_layout = QHBoxLayout(content_row)
        content_row_layout.setContentsMargins(0, 0, 0, 0)
        content_row_layout.setSpacing(9)

        rp = QFrame()
        rp.setObjectName("RightPanel")
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        self.chat_widget = ChatWidget()
        rl.addWidget(self.chat_widget, 1)
        self.input_panel = InputPanel()
        self.input_panel.send_message.connect(self._on_user_input)
        self.input_panel.send_image.connect(self._on_user_image)
        self.input_panel.open_tools.connect(self._open_tools)
        self.input_panel.open_knowledge.connect(self._show_knowledge)
        self.input_panel.qq_bridge_requested.connect(self._toggle_qq_bridge_modern)
        self.input_panel.voice_toggle_requested.connect(self._toggle_voice)
        self.input_panel.gptsovits_service_requested.connect(self._toggle_gptsovits_service)
        self.input_panel.stop_requested.connect(self._stop_everything)
        rl.addWidget(self.input_panel)
        content_row_layout.addWidget(rp, 1)

        self.chat_insights = ChatInsightsPanel()
        content_row_layout.addWidget(self.chat_insights)
        content_outer.addWidget(content_row, 1)

        self.chat_top_bar = ChatTopBar()
        self.chat_top_bar.history_requested.connect(self._open_history)
        self.chat_top_bar.memo_requested.connect(self._open_notes)
        self.chat_top_bar.tools_requested.connect(self._open_tools)
        self.chat_top_bar.settings_requested.connect(self._open_settings)
        self.chat_top_bar.window_action.connect(self._handle_window_action)
        self.chat_top_bar.window_drag.connect(self._handle_window_drag)
        self.chat_top_bar.search_changed.connect(self.chat_widget.filter_messages)

        overlay = QWidget()
        overlay.setObjectName("ChatOverlay")
        overlay_layout = QGridLayout(overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setSpacing(0)
        overlay_layout.addWidget(chat_content, 0, 0)
        overlay_layout.addWidget(self.chat_top_bar, 0, 0, Qt.AlignTop | Qt.AlignRight)
        overlay_layout.setRowStretch(0, 1)
        overlay_layout.setColumnStretch(0, 1)
        workspace_layout.addWidget(overlay, 1)
        sp.addWidget(chat_workspace)

        sp.setSizes([230, max(100, config.WINDOW_WIDTH - 420)])
        sp.setCollapsible(0, False)
        sp.setCollapsible(1, False)
        chat_page_layout.addWidget(sp)
        self._chat_page = chat_page
        self._workspace_stack.addWidget(chat_page)
        self._workspace_stack.setCurrentWidget(self.home_widget)
        # Both backgrounds span the full window.  The persistent navigation
        # is layered above them, which lets its translucent surface reveal
        # the current page artwork.
        shell_layout.addWidget(self._workspace_stack, 0, 0)
        shell_layout.addWidget(self.nav_sidebar, 0, 0, Qt.AlignLeft)
        self.nav_sidebar.raise_()
        ml.addWidget(shell, 1)

        sb = QFrame()
        sb.setObjectName("StatusBar")
        sb.setFixedHeight(24)
        sl = QHBoxLayout(sb)
        sl.setContentsMargins(12, 6, 12, 6)
        sl.setSpacing(10)

        self._status_dot = QLabel()
        self._status_dot.setObjectName("StatusDot")
        self._status_dot.setFixedSize(12, 12)
        self._status_dot.setVisible(False)
        sl.addWidget(self._status_dot)

        self._status_text = QLabel("邪王真眼已待命")
        self._status_text.setObjectName("StatusText")
        self._status_text.setVisible(False)
        sl.addWidget(self._status_text)
        sl.addStretch()

        self._status_meta = QLabel(f"Model: {config.MODEL}")
        self._status_meta.setObjectName("StatusMeta")
        self._status_meta.setVisible(False)
        sl.addWidget(self._status_meta)
        ml.addWidget(sb)
        self._status_bar = sb
        self._status_bar.setVisible(False)

        self._apply_home_chrome(True)

        self._set_qq_button_state("offline", "QQ 离线")

    def _refresh_widget_style(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _show_home(self):
        if hasattr(self, "home_widget"):
            self._switch_workspace(
                self.home_widget,
                "home",
                refresh=self.home_widget.refresh_recent,
                is_home=True,
            )

    def _show_chat(self):
        if hasattr(self, "_chat_page"):
            self._switch_workspace(
                self._chat_page,
                "chat",
                refresh=lambda: (
                    self.session_panel.refresh_sessions(self._session_id),
                    self._refresh_chat_insights(),
                ),
            )

    def _show_knowledge(self):
        if hasattr(self, "knowledge_page"):
            self._switch_workspace(
                self.knowledge_page,
                "knowledge",
                refresh=self.knowledge_page.refresh_data,
            )

    def _open_diary(self):
        """打开日记页面（日记/周记/月报/年鉴 分类浏览）"""
        if hasattr(self, "diary_page"):
            self._switch_workspace(
                self.diary_page,
                "diary",
                refresh=self.diary_page.refresh_data,
            )

    def _switch_workspace(self, page, section, refresh=None, is_home=False):
        """Switch pages with a lightweight screenshot crossfade.

        Taking the outgoing page snapshot keeps the transition smooth even for
        the Chromium-backed home page, where QGraphicsOpacityEffect is not
        reliable. Data refresh is deferred until the new page has painted its
        first frame, avoiding a synchronous blank or frozen transition.
        """
        if page is None or not hasattr(self, "_workspace_stack"):
            return
        current = self._workspace_stack.currentWidget()
        if current is page:
            if refresh is not None:
                QTimer.singleShot(30, refresh)
            return

        snapshot = QPixmap()
        if current is not None and current.isVisible() and current.width() > 0:
            try:
                snapshot = current.grab()
            except Exception:
                snapshot = QPixmap()

        self._workspace_stack.setCurrentWidget(page)
        self._apply_home_chrome(is_home)
        self.nav_sidebar.set_active_section(section)
        if refresh is not None:
            QTimer.singleShot(30, refresh)
        self._animate_workspace_transition(snapshot)

    def _animate_workspace_transition(self, snapshot):
        """Fade the outgoing screenshot away above the newly selected page."""
        if not self._appearance_animations_enabled() or snapshot.isNull():
            return
        previous = self._workspace_transition
        if previous is not None:
            previous[2].stop()
            previous[0].deleteLater()
            self._workspace_transition = None

        overlay = QLabel(self._workspace_stack)
        overlay.setObjectName("WorkspaceTransitionOverlay")
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        overlay.setPixmap(snapshot)
        overlay.setScaledContents(True)
        overlay.setGeometry(self._workspace_stack.rect())
        overlay.raise_()
        effect = QGraphicsOpacityEffect(overlay)
        effect.setOpacity(1.0)
        overlay.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(210)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)

        def finish():
            if overlay.graphicsEffect() is effect:
                overlay.setGraphicsEffect(None)
            overlay.deleteLater()
            animation.deleteLater()
            if self._workspace_transition and self._workspace_transition[0] is overlay:
                self._workspace_transition = None

        animation.finished.connect(finish)
        self._workspace_transition = (overlay, effect, animation)
        overlay.show()
        animation.start()

    def _connect_dashboard_page(self, page):
        page.history_requested.connect(self._open_history)
        page.memo_requested.connect(self._open_notes)
        page.tools_requested.connect(self._open_tools)
        page.settings_requested.connect(self._open_settings)
        page.window_action.connect(self._handle_window_action)
        page.window_drag.connect(self._handle_window_drag)

    def _apply_home_chrome(self, is_home):
        """Keep both workspaces edge-to-edge; each page owns its own chrome."""
        if not hasattr(self, "_title_bar"):
            return
        self._title_bar.setVisible(False)
        self._root_layout.setContentsMargins(0, 0, 0, 0)
        self._root_layout.setSpacing(0)

    def _handle_window_action(self, action):
        if action == "minimize":
            self.showMinimized()
        elif action == "maximize":
            self.showNormal() if self.isMaximized() else self.showMaximized()
        elif action == "close":
            self.close()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "chat_insights"):
            self.chat_insights.setVisible(self.width() >= 1160)

    def _handle_window_drag(self, screen_x, screen_y, phase):
        cursor = QPoint(screen_x, screen_y)
        if phase == "start":
            if self.isMaximized():
                self.showNormal()
            handle = self.windowHandle()
            if handle is not None and hasattr(handle, "startSystemMove"):
                try:
                    if handle.startSystemMove():
                        self._window_drag_offset = None
                        return
                except RuntimeError:
                    pass
            self._window_drag_offset = cursor - self.frameGeometry().topLeft()
        elif phase == "move" and getattr(self, "_window_drag_offset", None) is not None:
            self.move(cursor - self._window_drag_offset)
        elif phase == "end":
            self._window_drag_offset = None

    def _start_home_chat(self, text):
        self._new_conversation()
        self._on_user_input(text)

    def _set_qq_button_state(self, state: str, tooltip: str):
        self._qq_btn.setProperty("state", state)
        self._qq_btn.setToolTip(tooltip)
        self._refresh_widget_style(self._qq_btn)
        if hasattr(self, "input_panel"):
            self.input_panel.set_qq_state(state, tooltip)
        if hasattr(self, "chat_top_bar"):
            self.chat_top_bar.set_connection_state(state)

        if state == "online":
            self._status_dot.setProperty("state", "online")
            self._status_text.setText("QQ 通道已连接")
        elif state == "connecting":
            self._status_dot.setProperty("state", "away")
            self._status_text.setText("QQ 通道连接中")
        else:
            self._status_dot.setProperty("state", "offline")
            self._status_text.setText("邪王真眼已待命")
        self._refresh_widget_style(self._status_dot)

    def _toggle_qq_bridge_modern(self):
        if self._qq_bridge.is_running:
            msg = self._qq_bridge.stop()
            self._set_qq_button_state("offline", "QQ 离线")
            self.chat_widget.add_message(f"QQ {msg}", is_user=False)
        else:
            msg = self._qq_bridge.start()
            self._set_qq_button_state("connecting", "QQ 连接中")
            self.chat_widget.add_message(f"QQ {msg}\n等待 NapCat WebSocket 连接中...", is_user=False)

    def _on_qq_connected_modern(self):
        self._set_qq_button_state("online", "QQ 在线")
        self.chat_widget.add_message("QQ 已连接", is_user=False)

    def _on_qq_disconnected_modern(self):
        self._set_qq_button_state("offline", "QQ 断线")
        self.chat_widget.add_message("QQ 已断开", is_user=False)

    # ── 用户输入 ────────────────────────────────────────────────

    def _on_user_input(self, text):
        self._reset_activity()
        self._voice_suppressed = False  # 新消息到来，语音恢复
        self._response_suppressed = False  # 新消息到来，迟到回复恢复显示
        for attempt in range(3):
            try:
                history.add_message(self._session_id, "user", text)
                break
            except Exception:
                if attempt == 2:
                    break
                time.sleep(0.5)
                try:
                    self._session_id = history.create_session()
                    config.save_user_config({"last_session_id": self._session_id})
                except Exception:
                    time.sleep(1)
                    self._session_id = history.create_session()
                    config.save_user_config({"last_session_id": self._session_id})
        self.chat_widget.add_message(text, is_user=True)
        self._refresh_chat_insights()
        sid = self._session_id
        self.chat_widget.set_current_session(sid)
        self.chat_widget.start_streaming(sid)
        self.input_panel.set_input_enabled(False)
        thread = QThread(self)
        self._worker_thread = thread
        self._worker = AgentWorker(self.agent, text)
        self._worker.moveToThread(thread)
        thread.started.connect(self._worker.run)
        self._worker.stream.connect(lambda c, s=sid: self._on_stream(s, c))
        self._worker.finished.connect(lambda r, s=sid, t=thread: self._on_response_finished(s, r, t))
        self._worker.error.connect(lambda e, s=sid, t=thread: self._on_response_error(s, e, t))
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_user_image(self, path):
        self._reset_activity()
        os.makedirs(config.IMAGES_SENT_DIR, exist_ok=True)
        fn = f"img_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        dst = os.path.join(config.IMAGES_SENT_DIR, fn)
        try:
            shutil.copy2(path, dst)
        except Exception:
            dst = path
        self.chat_widget.add_message("", is_user=True, image_path=dst)
        history.add_message(self._session_id, "user", f"[图片]{dst}")
        self._refresh_chat_insights()
        self._img_thread = QThread(self)
        self._img_worker = ImageWorker(dst)
        self._img_worker.moveToThread(self._img_thread)
        self._img_worker.done.connect(self._on_image_analyzed)
        self._img_thread.started.connect(self._img_worker.run)
        self._img_thread.finished.connect(self._img_thread.deleteLater)
        self._img_thread.start()

    def _on_image_analyzed(self, vr):
        if self._img_thread:
            self._img_thread.quit()
            self._img_thread.wait()
            self._img_thread = None
        prompt = f"[系统提示] 契约者发了张图片：{vr}\n用六花的语气回应。"
        sid = self._session_id
        self.chat_widget.set_current_session(sid)
        self.chat_widget.start_streaming(sid)
        self.input_panel.set_input_enabled(False)
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, prompt)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(lambda c, s=sid: self._on_stream(s, c))
        self._worker.finished.connect(lambda r, s=sid: self._on_response_finished(s, r))
        self._worker.error.connect(lambda e, s=sid: self._on_response_error(s, e))
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _on_stream(self, sid, chunk):
        self.chat_widget.append_stream(sid, chunk)

    # ── 响应完成（核心：处理图片 + 定时器 + 历史） ─────────────

    def _on_response_finished(self, sid, response, thread=None):
        # 迟到的旧线程回复（已被新线程取代）→ 收尾它自己，不碰新线程
        if thread is not None and thread is not self._worker_thread:
            try:
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass
            return
        # 停止后被叫停的回复 → 丢弃，不显示
        if self._response_suppressed:
            self._finish_after_stop()
            return
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None

        # 检查是否有截图待发送——有的话先展示图片，再展示文字
        from brain import tools as _tt
        has_images = bool(_tt._PENDING_IMAGES)

        # 安全地拿下流式文字（异常时也不影响后续图片处理）
        text = ""
        try:
            if has_images:
                text = self.chat_widget.pop_streaming_bubble(sid)
            else:
                self.chat_widget.stop_streaming(sid)
        except Exception:
            if not has_images:
                self.chat_widget.stop_streaming(sid)

        # 1a. 处理 AI 主动发的截图（优先展示）
        try:
            while _tt._PENDING_IMAGES:
                p = _tt._PENDING_IMAGES.pop(0)
                if os.path.exists(p):
                    self.chat_widget.add_message("", is_user=False, image_path=p)
                    history.add_message(sid, "assistant", f"[图片]{p}")
        except Exception:
            pass

        # 1b. 有图时，文字放在图片后面
        if has_images and text:
            self.chat_widget.add_message(text, is_user=False)

        # 2. 处理 AI 设置的主动定时器（_PENDING_TIMERS）
        try:
            while _tt._PENDING_TIMERS:
                t = _tt._PENDING_TIMERS.pop(0)
                tp = t.get("type", "proactive")
                delay = t.get("delay", 30)
                reason = t.get("reason", "")
                self._timer_mgr.schedule(tp, delay, {"reason": reason})
        except Exception:
            pass

        # 2b. 本次主动回复消费了记忆唤起 → 标记已交付（防止反复唤起同一件事）
        if self._active_cue_id:
            try:
                from brain import memory_proactive as _mp
                _mp.mark_delivered(self._active_cue_id)
            except Exception:
                pass
            self._active_cue_id = None

        # 3. 存文字回复到历史（用实际显示的完整文本，不丢内容；sid 是发起本次回复的会话）
        text_to_store = text or response
        if text_to_store:
            try:
                history.add_message(sid, "assistant", text_to_store)
            except Exception:
                pass
        self._refresh_chat_insights()

        if self.agent.history and len(self.agent.history) == 3:
            title = (response[:30] + "…") if len(response) > 30 else response
            history.update_session_title(sid, title)

        self.input_panel.set_input_enabled(True)
        self.input_panel.focus_input()

        if self._in_proactive:
            self._in_proactive = False

    def _on_response_error(self, sid, em, thread=None):
        if thread is not None and thread is not self._worker_thread:
            try:
                thread.quit()
                thread.wait(1000)
            except Exception:
                pass
            return
        if self._response_suppressed:
            self._finish_after_stop()
            return
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None
        self.chat_widget.stop_streaming(sid)
        self.chat_widget.add_message(f"力量乱掉了…出错啦！\n{em}", is_user=False)
        self.input_panel.set_input_enabled(True)
        self.input_panel.focus_input()

    def _finish_after_stop(self):
        """停止后丢弃迟到回复时的收尾：清空待处理队列、恢复输入。"""
        from brain import tools as _tt
        try:
            _tt._PENDING_IMAGES.clear()
            _tt._PENDING_TIMERS.clear()
        except Exception:
            pass
        try:
            self.chat_widget.stop_streaming(self._session_id)
        except Exception:
            pass
        try:
            self.input_panel.set_input_enabled(True)
        except Exception:
            pass

    # ── ⏹ 停止按钮（中断一切操作） ───────────────────────────────

    def _stop_everything(self):
        """停止当前正在进行的任何操作（回复、游戏play、截图等）"""
        from brain import tools as _tt
        # 1. 发停止信号给 game_play 等后台操作
        _tt.request_stop()
        # 1.1 停止纪元：叫停后迟到的 LLM 回复直接丢弃；AI 待注册的定时器作废
        self._response_suppressed = True
        try:
            _tt._PENDING_TIMERS.clear()
        except Exception:
            pass
        # 1.5 中断正在进行的语音合成
        try:
            self._voice.stop_current()
        except Exception:
            pass
        # 1.6 停本地 GPT-SoVITS 语音服务（首页按钮同步变灰；嫌重载慢可注释此行）
        try:
            self._voice_server.stop()
        except Exception:
            pass
        # 1.7 停止正在播放的语音 + 抑制迟到的合成结果
        try:
            if self._audio_player is not None:
                self._audio_player.stop()
        except Exception:
            pass
        try:
            self.chat_widget.stop_all_voice()   # 停掉语音条气泡的播放
        except Exception:
            pass
        self._voice_suppressed = True
        # 2. 终止工作线程
        if self._worker_thread:
            try:
                self._worker_thread.requestInterruption()
                self._worker_thread.quit()
                self._worker_thread.wait(1000)
            except:
                pass
            self._worker_thread = None
            self._worker = None
        # 3. 终止截图线程
        if self._img_thread:
            try:
                self._img_thread.quit()
                self._img_thread.wait(500)
            except:
                pass
            self._img_thread = None
            self._img_worker = None
        # 3.5 终止屏幕偷看线程 + 作废在途结果（已排定的定时器保留）
        self._action_epoch += 1
        if self._proactive_thread:
            try:
                self._proactive_thread.quit()
                self._proactive_thread.wait(500)
            except:
                pass
            self._proactive_thread = None
            self._proactive_worker = None
        self._in_proactive = False
        # 4. 清理界面
        self.chat_widget.stop_streaming()
        self.chat_widget.add_message("⏹ 六花被契约者叫停了～", is_user=False)
        self.input_panel.set_input_enabled(True)
        self.input_panel.focus_input()

    # ── 🎙 本地 GPT-SoVITS 语音服务（首页 AI 音乐卡片） ──────────

    def _on_home_voice_action(self, action):
        if action == "start":
            self._voice_server.start()
        elif action == "stop":
            self._voice_server.stop()

    def _toggle_gptsovits_service(self):
        """输入区「语音服务」按钮：会话里弹系统消息 + 进度条，加载完变「正在运行」。"""
        sv = self._voice_server
        st = sv.status()["state"]
        if st == "ready":
            self.chat_widget.add_message("✅ GPT-SoVITS 语音服务正在运行", is_user=False)
            return
        if st == "starting":
            return  # 已在启动，避免重复
        if getattr(self, "_svc_timer", None) is not None:
            self._svc_timer.stop()
        self._svc_banner = self.chat_widget.add_service_banner(
            "🛠️ GPT-SoVITS 语音服务运行中…（加载模型约需数十秒）"
        )
        self._svc_timer = QTimer(self)
        self._svc_timer.setInterval(300)
        self._svc_timer.timeout.connect(self._poll_gptsovits_progress)
        self._svc_timer.start()
        sv.start()

    def _poll_gptsovits_progress(self):
        """轮询服务状态，刷新进度条；就绪/失败时收尾。"""
        sv = self._voice_server
        status = sv.status()
        st = status["state"]
        banner = getattr(self, "_svc_banner", None)
        if st == "ready":
            self._svc_timer.stop()
            if banner is not None:
                banner.update_progress(100, "✅ GPT-SoVITS 语音服务正在运行")
            self.chat_widget.add_message("✅ GPT-SoVITS 语音服务正在运行", is_user=False)
            self.input_panel.set_service_state("ready")
        elif st == "error":
            self._svc_timer.stop()
            detail = status.get("detail", "")
            if banner is not None:
                banner.update_progress(100, f"❌ GPT-SoVITS 启动失败：{detail}")
            self.input_panel.set_service_state("error")
        elif st == "starting":
            total = float(getattr(config, "GPT_SOVITS_START_TIMEOUT", 90))
            elapsed = float(status.get("elapsed", 0))
            pct = min(95, round(elapsed / total * 100))   # 留 5% 余量，就绪瞬间跳满
            if banner is not None:
                banner.update_progress(
                    pct,
                    f"🛠️ GPT-SoVITS 语音服务运行中…（{int(elapsed)}s / 预计 {int(total)}s）",
                )
            self.input_panel.set_service_state("starting")

    def _on_voice_server_status(self, status):
        hw = getattr(self, "home_widget", None)
        if hw is not None and hasattr(hw, "push_voice_status"):
            hw.push_voice_status(status)
        try:
            self.input_panel.set_service_state(status.get("state", "stopped"))
        except Exception:
            pass

    def closeEvent(self, event):
        # 退出时停掉本地 GPT-SoVITS 服务（杀进程树，异步短阻塞不卡窗）
        try:
            self._voice_server.stop()
        except Exception:
            pass
        timer = getattr(self, "_svc_timer", None)
        if timer is not None:
            timer.stop()
        # 退出时清理所有工作线程/定时器，避免挂起、崩溃或数据库残留
        try:
            getattr(self, "_timer_mgr", None) and self._timer_mgr._tick.stop()
        except Exception:
            pass
        for attr in ("_diary_summary_timer", "_weekly_timer", "_memory_cue_timer", "_archivist_timer"):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
        for attr, ms in (("_worker_thread", 1000), ("_img_thread", 500), ("_proactive_thread", 500), ("_archivist_thread", 500)):
            t = getattr(self, attr, None)
            if t is not None:
                try:
                    t.requestInterruption()
                    t.quit()
                    t.wait(ms)
                except Exception:
                    pass
        try:
            if self._qq_bridge is not None:
                self._qq_bridge.stop()
        except Exception:
            pass
        super().closeEvent(event)

    # ── 💬 QQ 桥接 ─────────────────────────────────────────────

    def _toggle_qq_bridge(self):
        """开关 QQ 桥接"""
        if self._qq_bridge.is_running:
            msg = self._qq_bridge.stop()
            self._qq_btn.setStyleSheet(
                "QPushButton{background:transparent;border:1px solid #3a1a6e;"
                "border-radius:14px;font-size:12px;color:#7a5aaa}"
                "QPushButton:hover{background:#2d1b4e;border-color:#9b59b6;color:#ffd700}"
            )
            self._qq_btn.setToolTip("QQ 离线")
            self.chat_widget.add_message(f"💬 {msg}", is_user=False)
        else:
            msg = self._qq_bridge.start()
            self.chat_widget.add_message(f"💬 {msg}\n等待 NapCat WebSocket 连接中...", is_user=False)
            # 样式变绿表示正在连接
            self._qq_btn.setStyleSheet(
                "QPushButton{background:transparent;border:1px solid #1a6a3a;"
                "border-radius:14px;font-size:12px;color:#44ff88}"
                "QPushButton:hover{background:#1a3a2a;border-color:#44ff88;color:#88ffbb}"
            )
            self._qq_btn.setToolTip("QQ 连接中...")

    def _on_qq_message_bg(self, user_id: int, group_id: int, message: str, msg_type: str):
        """后台线程收到 QQ 消息 → 通过信号桥发到主线程处理"""
        print(f"[QQ] 桥线程收到 user={user_id} type={msg_type} msg={message[:40]!r}", flush=True)
        self._qq_signals.got_message.emit(user_id, group_id, message, msg_type)
        return None

    def _on_qq_message_threadsafe(self, user_id, group_id, message, msg_type):
        """主线程：后台处理 QQ 消息，不阻塞 UI"""
        print(f"[QQ] 主线程收到 user={user_id} type={msg_type} msg={message[:40]!r}", flush=True)
        self._voice_suppressed = False  # QQ 新消息到来，语音恢复
        # 同用户串行化：上一条还在回复（含 3 秒思考延迟）时，丢弃新消息，避免共享 AgentCore 并发串扰
        if user_id in self._qq_busy:
            print(f"[QQ] user={user_id} 正在回复中，丢弃新消息", flush=True)
            return
        self._qq_busy.add(user_id)
        try:
            # 记录当前 QQ 会话目标，供六花 speak(to='qq') 使用
            try:
                self._voice.set_qq_context(user_id, group_id)
            except Exception:
                pass
            sender = f"QQ:{user_id}"
            if group_id:
                sender = f"QQ群{group_id}:{user_id}"
            # QQ 对方消息：用 sender 显示为「对方」气泡（靠右、独立配色），而不是渲染成「你」
            self.chat_widget.add_message(message, sender=sender)
            sid = self._session_id
            self.chat_widget.set_current_session(sid)
            self.chat_widget.start_streaming(sid)

            # 获取该 QQ 号独立的 AgentCore
            qq_agent = self._get_qq_agent(user_id)

            # 检查操作权限
            restricted = user_id not in config.QQ_ALLOWED_USERS if config.QQ_ALLOWED_USERS else True

            # 先「思考」几秒再开始回复（像真人那样），不阻塞主线程
            delay_ms = int(getattr(config, "QQ_REPLY_THINK_DELAY", 3) * 1000)
            QTimer.singleShot(delay_ms, lambda: self._start_qq_worker(
                qq_agent, message, user_id, group_id, msg_type, restricted, sid,
            ))
        except Exception as e:
            self.chat_widget.add_message(f"💬 QQ消息处理失败: {e}", is_user=False)

    def _start_qq_worker(self, qq_agent, message, user_id, group_id, msg_type, restricted, sid=None):
        """为一条 QQ 消息起独立线程回复（思考延迟结束后调用）。
        线程自回收，主线程绝不 wait()。
        settled 标记：看门狗兜底或正常完成，只允许一个生效，避免重复回复。"""
        print(f"[QQ] 思考延迟结束，起回复线程 user={user_id}", flush=True)
        try:
            thread = QThread(self)
            worker = QQAgentWorker(qq_agent, message, restricted=restricted)
            worker.moveToThread(thread)
            settled = threading.Event()
            worker.stream.connect(lambda c, s=sid: self._on_qq_stream(s, c))
            worker.finished.connect(
                lambda r, s=sid, u=user_id, g=group_id, mt=msg_type, st=settled:
                self._on_qq_done(s, r, u, g, mt, settled=st)
            )
            worker.error.connect(
                lambda e, s=sid, u=user_id, g=group_id, mt=msg_type, st=settled:
                self._on_qq_thread_error(s, e, u, g, mt, settled=st)
            )
            thread.started.connect(worker.run)
            # 自回收：worker 结束/出错 → 停事件循环 → 线程结束 → deleteLater
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            worker.error.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            # 关键：把 (thread, worker) 挂到 self 上持有强引用。
            # 否则函数一返回局部变量就被 GC，PyQt 连接随之失效，run() 永远不执行
            # （22:47 日志：QQ worker.run 从未打印，桌面端用 self._worker 所以没事）。
            ref_key = (thread, worker)
            self._qq_worker_refs.add(ref_key)

            def _drop_ref():
                self._qq_worker_refs.discard(ref_key)
            thread.finished.connect(_drop_ref)

            # 看门狗：超过 QQ_MAX_REPLY_TIME 还没回复 → 强制发兜底，绝不让对方干等
            watchdog_ms = int(getattr(config, "QQ_MAX_REPLY_TIME", 90) * 1000)
            QTimer.singleShot(
                watchdog_ms,
                lambda s=sid, u=user_id, g=group_id, mt=msg_type, st=settled:
                self._qq_watchdog_fire(s, u, g, mt, st),
            )

            thread.start()
        except Exception as e:
            print(f"[QQ] 起线程异常: {e}")
            self.chat_widget.add_message(f"💬 QQ消息处理失败: {e}", is_user=False)

    def _on_qq_stream(self, sid, chunk):
        """QQ 流式内容 → 聊天区（绑定方法，确保在 Qt 主线程执行）"""
        self.chat_widget.append_stream(sid, chunk)

    def _qq_watchdog_fire(self, sid, user_id, group_id, msg_type, settled):
        """QQ 回复看门狗：线程卡死超时后，强制发一条兜底（主线程执行）"""
        if settled is None or settled.is_set():
            return  # 已正常完成或已兜底过
        settled.set()
        self._qq_busy.discard(user_id)
        print(f"[QQ] 看门狗触发：回复超时，发兜底 user={user_id}", flush=True)
        try:
            self.chat_widget.stop_streaming(sid)
        except Exception:
            pass
        fallback = "……唔，我这边好像卡住了，稍等一下下，你可以再说一句话看看（´･ω･`）"
        self.chat_widget.add_message(f"💬 [六花→QQ] {fallback}", is_user=False)
        try:
            if msg_type == "group" and group_id:
                self._qq_bridge.send_group_msg(group_id, fallback)
            else:
                self._qq_bridge.send_private_msg(user_id, fallback)
        except Exception:
            pass

    def _get_qq_agent(self, user_id: int):
        """获取或创建某个 QQ 用户独立的 AgentCore 实例"""
        if not hasattr(self, '_qq_agents'):
            self._qq_agents = {}
        if user_id not in self._qq_agents:
            agent = AgentCore()
            agent.start_session()
            self._qq_agents[user_id] = agent
        return self._qq_agents[user_id]

    def _on_qq_done(self, sid, response, user_id, group_id, msg_type, settled=None):
        """QQ 回复完成 → 显示 + 发文字/图片到 QQ（线程已自回收，不阻塞主线程）"""
        # 看门狗兜底已经处理过 → 跳过，避免重复回复
        if settled is not None:
            if settled.is_set():
                print(f"[QQ] 已完成过（看门狗兜底），跳过重复发送 user={user_id}")
                return
            settled.set()
        self._qq_busy.discard(user_id)
        # 移除流式气泡，避免桌面残留一个看起来"卡死"的半截气泡
        try:
            self.chat_widget.pop_streaming_bubble(sid)
        except Exception:
            self.chat_widget.stop_streaming(sid)

        # 兜底：LLM 超时/空回复时也要让 QQ 那头有回应，不留死寂
        if not response or not response.strip():
            response = "……（唔，我这边好像卡了一下，那句话没组织好，你能再发一次吗？）"

        self.chat_widget.add_message(f"💬 [六花→QQ] {response}", is_user=False)

        # 发送文字到 QQ（失败重试一次，WS 可能短暂抖动）
        ok = False
        try:
            if msg_type == "group" and group_id:
                ok = self._qq_bridge.send_group_msg(group_id, response)
            else:
                ok = self._qq_bridge.send_private_msg(user_id, response)
            if not ok:
                if msg_type == "group" and group_id:
                    ok = self._qq_bridge.send_group_msg(group_id, response)
                else:
                    ok = self._qq_bridge.send_private_msg(user_id, response)
        except Exception as e:
            print(f"[QQ] 发送回复异常: {e}")
        print(f"[QQ] 回复完成 user={user_id} 发送{'成功' if ok else '失败'} resp={response[:40]!r}", flush=True)

        # 发送 AI 生成的图片到 QQ（截图、搜图、AI 画图等）
        from brain import tools as _tt
        while _tt._PENDING_IMAGES:
            img_path = _tt._PENDING_IMAGES.pop(0)
            if os.path.exists(img_path):
                self.chat_widget.add_message("", is_user=False, image_path=img_path)
                if msg_type == "group" and group_id:
                    self._qq_bridge.send_group_image(group_id, img_path)
                else:
                    self._qq_bridge.send_image(user_id, img_path)

    def _on_qq_thread_error(self, sid, err, user_id=None, group_id=None, msg_type=None, settled=None):
        """QQ 线程出错（线程已自回收，不阻塞主线程）"""
        print(f"[QQ] 回复线程出错: {err}  user={user_id}")
        # 看门狗兜底已处理过 → 跳过，避免重复回复
        if settled is not None:
            if settled.is_set():
                return
            settled.set()
        self._qq_busy.discard(user_id)
        try:
            self.chat_widget.stop_streaming(sid)
        except Exception:
            pass
        self.chat_widget.add_message(f"💬 QQ回复出错: {err}", is_user=False)
        # 出错也不让 QQ 那头死寂，发一条兜底
        if user_id or group_id:
            try:
                fallback = "……唔，我这边好像出故障了，你稍等一下下（´･ω･`）"
                if msg_type == "group" and group_id:
                    self._qq_bridge.send_group_msg(group_id, fallback)
                else:
                    self._qq_bridge.send_private_msg(user_id, fallback)
            except Exception:
                pass

    def _on_qq_connected(self):
        self._qq_btn.setStyleSheet(
            "QPushButton{background:transparent;border:1px solid #1a6a3a;"
            "border-radius:14px;font-size:12px;color:#44ff88}"
            "QPushButton:hover{background:#1a3a2a;border-color:#44ff88;color:#88ffbb}"
        )
        self._qq_btn.setToolTip("QQ 在线")
        self.chat_widget.add_message("💬 ✅ QQ 桥接已连接！", is_user=False)

    def _on_qq_disconnected(self):
        self._qq_btn.setStyleSheet(
            "QPushButton{background:transparent;border:1px solid #6a1a1a;"
            "border-radius:14px;font-size:12px;color:#ff4444}"
            "QPushButton:hover{background:#3a0a0a;border-color:#ff4444;color:#ff8888}"
        )
        self._qq_btn.setToolTip("QQ 断线")
        self.chat_widget.add_message("💬 ❌ QQ 桥接已断开", is_user=False)

    def _on_qq_error(self, err):
        self.chat_widget.add_message(f"💬 ⚠️ QQ 桥接错误: {err}", is_user=False)

    # ── 🔊 语音（六花 speak 工具触发） ────────────────────────

    def _toggle_voice(self):
        """静音开关：切换语音总开关"""
        enabled = not config.VOICE_ENABLED
        config.set_voice_enabled(enabled)
        try:
            self.input_panel.set_voice_state(enabled)
        except Exception:
            pass
        self.chat_widget.add_message(
            f"🔊 六花的语音已{'开启' if enabled else '关闭'}", is_user=False
        )

    def _on_voice_ready(self, path, to, qq_target, text="", translation=""):
        """语音合成完成：本地显示语音条并播放 / 发QQ语音"""
        # ⏹ 叫停后迟到的语音不再播放
        if self._voice_suppressed:
            return
        to = to or "local"
        if "local" in to:
            try:
                # 语音条：点击可播放/暂停，日语文本 + 中文翻译（QQ/微信样式）
                bubble = self.chat_widget.add_voice_message(text, translation, path)
                bubble.play()
            except Exception as e:
                print("语音条失败，退回旧播放:", e)
                self._play_audio(path)   # 兜底：退回共享播放器
        if "qq" in to:
            self._send_voice_qq(path, qq_target)

    def _play_audio(self, path):
        """用 QMediaPlayer 本地播放语音"""
        try:
            from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
            from PyQt5.QtCore import QUrl
            if self._audio_player is None:
                self._audio_player = QMediaPlayer()
            self._audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self._audio_player.play()
        except Exception as e:
            print("播放语音失败:", e)

    def _send_voice_qq(self, path, qq_target):
        """把语音发到QQ（优先当前QQ会话，其次契约者默认QQ）"""
        user_id = group_id = None
        try:
            parts = (qq_target or "").split(",")
            if len(parts) == 2 and parts[0]:
                user_id = int(parts[0])
                group_id = int(parts[1]) if parts[1] else None
        except Exception:
            pass
        if not user_id and not group_id:
            allowed = config.QQ_ALLOWED_USERS
            if allowed:
                user_id = int(allowed[0])
        try:
            if group_id:
                ok = self._qq_bridge.send_group_voice(group_id, path)
            elif user_id:
                ok = self._qq_bridge.send_voice(user_id, path)
            else:
                ok = False
            if ok:
                self.chat_widget.add_message("💬 [六花→QQ] 🔊 语音已发送", is_user=False)
        except Exception as e:
            print("发送QQ语音失败:", e)

    # ── 定时器触发（链式主动 + 临时回访） ─────────────────────

    def _on_timer_fired(self, timer_type: str, context: dict):
        """定时器到期时调用——构建 prompt 发给 AI"""
        if self._worker_thread or self._proactive_thread:
            # 正在回复中：把到期定时器顺延 5 分钟，而不是丢弃（链式主动/回访承诺不能消失）
            try:
                self._timer_mgr.schedule(timer_type, 5, context)
            except Exception:
                pass
            return

        # 如果用户关闭了主动聊天，跳过链式主动（临时回访不受影响）
        if timer_type == "proactive" and not config.PROACTIVE_ENABLED:
            return

        if timer_type == "proactive":
            self._in_proactive = True
            # 独立观察（摸鱼彩蛋）：开关 + 独立冷却 + 配置概率；命中则偷看屏幕，否则普通主动聊天
            observe_ok = (
                config.PROACTIVE_SLACK_ENABLED
                and (time.time() - self._last_observe_ts) >= config.PROACTIVE_SLACK_COOLDOWN * 60
            )
            if observe_ok and random.randint(1, 100) <= int(config.PROACTIVE_SLACK_PROB):
                self._last_observe_ts = time.time()
                self._peek_epoch = self._action_epoch
                self._proactive_thread = QThread(self)
                self._proactive_worker = ProactiveWorker()
                self._proactive_worker.moveToThread(self._proactive_thread)
                self._proactive_worker.done.connect(self._on_proactive_peek)
                self._proactive_thread.started.connect(self._proactive_worker.run)
                self._proactive_thread.finished.connect(self._proactive_thread.deleteLater)
                self._proactive_thread.start()
            else:
                self._do_proactive_chat()
        elif timer_type == "follow_up":
            self._in_proactive = True
            reason = context.get("reason", "想契约者了")
            prompt = (
                "【系统通知 ✦ 临时回访】\n"
                f"你之前说过要回访契约者，原因：{reason}\n"
                "现在去看看ta吧。自然一点，不要刻意提「回访」这个词。"
            )
            sid = self._session_id
            self.chat_widget.set_current_session(sid)
            self.chat_widget.start_streaming(sid)
            self._worker_thread = QThread(self)
            self._worker = AgentWorker(self.agent, prompt)
            self._worker.moveToThread(self._worker_thread)
            self._worker_thread.started.connect(self._worker.run)
            self._worker.stream.connect(lambda c, s=sid: self._on_stream(s, c))
            self._worker.finished.connect(lambda r, s=sid: self._on_response_finished(s, r))
            self._worker.error.connect(lambda e, s=sid: self._on_response_error(s, e))
            self._worker_thread.finished.connect(self._worker_thread.deleteLater)
            self._worker_thread.start()

    def _do_proactive_chat(self):
        """执行链式主动对话"""
        prompt = self._build_proactive_prompt()
        sid = self._session_id
        self.chat_widget.set_current_session(sid)
        self.chat_widget.start_streaming(sid)
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, prompt)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(lambda c, s=sid: self._on_stream(s, c))
        self._worker.finished.connect(lambda r, s=sid: self._on_response_finished(s, r))
        self._worker.error.connect(lambda e, s=sid: self._on_response_error(s, e))
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _on_proactive_peek(self, analysis, img_path):
        """屏幕偷看结果 → 发给 AI"""
        # ⏹ 已被叫停：偷看结果作废，不再 new 回复线程
        if self._action_epoch != self._peek_epoch:
            self._proactive_thread = None
            self._proactive_worker = None
            return
        if self._proactive_thread:
            self._proactive_thread.quit()
            self._proactive_thread.wait()
            self._proactive_thread = None
            self._proactive_worker = None
        if analysis:
            prompt = (
                f"【系统通知 ✦ 链式主动（观察）】\n"
                f"你刚刚看到契约者的屏幕画面：{analysis}\n"
                f"用六花的语气自然地聊聊这个画面。\n\n"
                f"【观察安全约束】\n"
                f"1. 只能引用画面中明确可见的事实；不确定的信息不要补全\n"
                f"2. 不要推断契约者的情绪、意图或工作进度，不要有\"被监控/被抓到\"的感觉\n"
                f"3. 可以轻微吐槽画面里明确可见的东西，但先保证事实准确\n"
                f"4. 不要提\"截图/屏幕/视觉模型/后台机制\"这些词，像朋友聊日常一样自然\n\n"
                f"注意：无论是否发消息，都要用 set_proactive_timer 设下一次！"
            )
        else:
            prompt = self._build_proactive_prompt()
        sid = self._session_id
        self.chat_widget.set_current_session(sid)
        self.chat_widget.start_streaming(sid)
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, prompt)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(lambda c, s=sid: self._on_stream(s, c))
        self._worker.finished.connect(lambda r, s=sid: self._on_response_finished(s, r))
        self._worker.error.connect(lambda e, s=sid: self._on_response_error(s, e))
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _run_memory_cue_eval(self):
        """后台评估记忆唤起候选（防重入：同一时间只跑一个）"""
        if not getattr(config, "MEMORY_CUE_ENABLED", False):
            return
        if self._memory_cue_thread and self._memory_cue_thread.isRunning():
            return
        try:
            self._memory_cue_thread = QThread(self)
            self._memory_cue_worker = MemoryCueWorker(
                max_candidates=int(getattr(config, "MEMORY_CUE_MAX_CANDIDATES", 8))
            )
            self._memory_cue_worker.moveToThread(self._memory_cue_thread)
            self._memory_cue_worker.done.connect(self._on_memory_cue_done)
            self._memory_cue_worker.error.connect(self._on_memory_cue_error)
            self._memory_cue_thread.started.connect(self._memory_cue_worker.run)
            self._memory_cue_thread.finished.connect(self._memory_cue_thread.deleteLater)
            self._memory_cue_thread.start()
        except Exception:
            self._memory_cue_thread = None
            self._memory_cue_worker = None

    def _on_memory_cue_done(self, result):
        if self._memory_cue_thread:
            self._memory_cue_thread.quit()
            self._memory_cue_thread.wait(500)
            self._memory_cue_thread = None
            self._memory_cue_worker = None

    def _on_memory_cue_error(self, err):
        self._on_memory_cue_done(None)

    # ── 自动周期总结（周记/月报/年鉴，固定时间触发） ──────────────────

    def _check_diary_auto_summary(self):
        """分钟级检查：到设定小时，当天有流水但还没有日记 → 自动生成（写入 summary 后条件自然失效，天然防重复）。"""
        if not getattr(config, "DIARY_AUTO_SUMMARY_ENABLED", False):
            return
        try:
            now = datetime.now()
            if now.hour != int(getattr(config, "DIARY_AUTO_SUMMARY_HOUR", 23)):
                return
            from brain import diary as _diary
            today = _diary.get_or_create_today()
            if (today.get("details") or "").strip() and not (today.get("summary") or "").strip():
                self._run_diary_auto_summary([today["date"]])
        except Exception:
            pass  # 任何异常都不影响主程序

    def _diary_auto_backfill(self):
        """启动后补写：最近 3 天有流水但没日记的，放入同一个后台 worker 串行生成。"""
        if not getattr(config, "DIARY_AUTO_SUMMARY_ENABLED", False):
            return
        try:
            from datetime import timedelta as _td
            from brain import diary as _diary
            pending = []
            for offset in range(1, 4):  # 昨天 → 前天 → 大前天
                day = (date.today() - _td(days=offset)).isoformat()
                row = _diary.get_diary(day)
                if row and (row.get("details") or "").strip() and not (row.get("summary") or "").strip():
                    pending.append(day)
            if pending:
                self._run_diary_auto_summary(pending)
        except Exception:
            pass

    def _run_diary_auto_summary(self, date_strs):
        """后台线程串行生成若干天日记（防重入），完成后通过信号回到主线程刷新。"""
        if isinstance(date_strs, str):
            date_strs = [date_strs]
        if getattr(self, "_diary_summary_thread", None) is not None and self._diary_summary_thread.is_alive():
            return

        def worker():
            ok_any = False
            try:
                from brain import diary as _diary
                for ds in date_strs:
                    result = _diary.write_diary_summary(ds)
                    if result.get("ok"):
                        ok_any = True
            except Exception:
                pass
            self._diary_summary_done.emit(ok_any, ",".join(date_strs))

        self._diary_summary_thread = threading.Thread(target=worker, daemon=True)
        self._diary_summary_thread.start()

    def _on_diary_auto_done(self, ok, date_strs):
        self._diary_summary_thread = None
        try:
            if hasattr(self, "diary_page"):
                self.diary_page.refresh_data()
        except Exception:
            pass

    # ── 主动冲浪：定期挑兴趣标签去B站搜视频，推荐给契约者 ────────

    def _check_auto_surf(self):
        """分钟级检查：距上次主动冲浪超过间隔 → 挑一批兴趣标签去冲浪。"""
        if not getattr(config, "SURF_AUTO_ENABLED", False):
            return
        try:
            interval = float(getattr(config, "SURF_AUTO_INTERVAL_MIN", 180)) * 60
            if time.time() - self._last_surf_ts < interval:
                return
            if self._surf_thread is not None and self._surf_thread.is_alive():
                return
            from brain import surf as _surf
            batch = _surf.get_store().get_surf_batch(
                max_tags=int(getattr(config, "SURF_TAGS_PER_ROUND", 4))
            )
            if not batch:
                self._last_surf_ts = time.time()  # 没有可用标签也顺延，避免每分钟空转
                return
            self._last_surf_ts = time.time()
            self._surf_thread = threading.Thread(
                target=self._surf_worker, args=(batch,), daemon=True
            )
            self._surf_thread.start()
        except Exception:
            pass

    def _surf_worker(self, batch):
        """遍历一批 (标签, 配额) 去B站搜索，聚合推荐消息。"""
        message = ""
        try:
            from brain import surf as _surf
            lines = []
            for keyword, quota in batch:
                videos = _surf.search_bilibili(keyword, limit=quota)
                if not videos:
                    continue
                _surf.save_record("bilibili", keyword, f"B站: {keyword}",
                                  videos[0]["url"], results=videos)
                lines.append(f"🏷️ {keyword}：")
                for v in videos[:quota]:
                    author = v.get("author") or ""
                    play = v.get("play") or ""
                    meta = " · ".join(x for x in (author, play) if x)
                    lines.append(f"  · {v.get('title', '')}" + (f"（{meta}）" if meta else ""))
                    desc = (v.get("description") or "").strip()
                    if desc:
                        lines.append(f"    {desc[:60]}")
                    lines.append(f"    {v['url']}")
            if lines:
                message = "🌊 我刚刚偷偷去B站冲浪啦～ 按你的兴趣挑了几条：\n" + "\n".join(lines)
                message += "\n（去「冲浪记录」页点 👍/👎，我会记住你的口味～）"
            else:
                message = "🌊 我刚去B站冲浪了一圈，这次没找到新视频呢～"
        except Exception:
            message = ""
        if message:
            self._surf_result_signal.emit(message)

    def _on_surf_result(self, message):
        self._surf_thread = None
        if not message:
            return
        try:
            self.chat_widget.add_message(message, is_user=False)
            from brain import history as _hist
            _hist.add_message(self._session_id, "assistant", message)
        except Exception:
            pass

    # ── Archivist 记忆档案员：每 2 分钟轻量层，闲置/碎片多时后台深度叙事归并 ──

    def _archivist_tick(self):
        """轻量层每 2 分钟跑（免费）；深度层条件满足时放后台线程跑（LLM 重写叙事）。"""
        try:
            from brain import archivist
            archivist.light_tick()  # 生命周期 + 实体合并 + 简单挂载（无 LLM）
            if self._archivist_thread is not None and self._archivist_thread.is_alive():
                return
            verdict = archivist.should_run_deep()
            if not verdict.get("due"):
                return
            self._archivist_thread = threading.Thread(
                target=self._archivist_deep_worker, daemon=True
            )
            self._archivist_thread.start()
        except Exception:
            pass

    def _archivist_deep_worker(self):
        try:
            from brain import archivist
            archivist._run_deep_cycle()
        except Exception:
            pass
        finally:
            self._archivist_thread = None

    def _check_weekly_summary(self):
        """分钟级检查：周日到点 → 自动周记；月末到点 → 自动月报；年末到点 → 自动年鉴。
        防重复：本期已有对应记录则跳过。失败重试：到点后每整点重试，最多 N 次，跨期作废。"""
        if not getattr(config, "WEEKLY_AUTO_ENABLED", False):
            return
        try:
            from datetime import date as _date
            today = _date.today()
            hour = datetime.now().hour
            target_hour = int(getattr(config, "WEEKLY_AUTO_HOUR", 21))
            retries = int(getattr(config, "WEEKLY_AUTO_RETRIES", 3))
            if hour < target_hour or hour >= target_hour + max(1, retries):
                return  # 未到触发窗口

            from brain import memory_summary as _ms

            # ── 年鉴：12 月 31 日（先于月报判断，因为当天也是月末，否则永远走不到） ──
            if today.month == 12 and today.day == 31:
                year_key = str(today.year)
                if not self._period_exists("yearly", year_key + "-01-01", year_key + "-12-31"):
                    self._run_period_summary("yearly", year_key, "今年年鉴")

            # ── 周记：周日 ──
            if today.weekday() == 6:
                period_key = today.isoformat()
                start, end = _ms._get_week_range(period_key)
                if not self._period_exists("weekly", start.isoformat(), end.isoformat()):
                    # 统一用「周一日期」作周标识：同一 ISO 周内无论哪天生成都是同一个 key，避免重复周记
                    self._run_period_summary("weekly", start.isoformat(), "本周周记")
                return

            # ── 月报：本月最后一天 ──
            if today.month != (today.replace(day=28) + __import__("datetime").timedelta(days=4)).month:
                month_key = today.strftime("%Y-%m")
                if not self._period_exists("monthly", month_key, month_key + "-31"):
                    self._run_period_summary("monthly", month_key, "本月月报")
                return
        except Exception:
            pass  # 任何异常都不影响主程序

    def _period_exists(self, level, start_key, end_key) -> bool:
        """本期（level）是否已有记录（period_key 落在 [start_key, end_key] 内）"""
        try:
            from brain import memory_summary as _ms
            conn = _ms._get_db()
            try:
                return bool(conn.execute(
                    "SELECT 1 FROM mf_summaries WHERE level=? "
                    "AND period_key >= ? AND period_key <= ? LIMIT 1",
                    (level, start_key, end_key),
                ).fetchone())
            finally:
                conn.close()
        except Exception:
            return False

    def _run_period_summary(self, level, period_key, label):
        """后台线程执行周期总结（防重入），完成后通过信号回主线程告知"""
        if getattr(self, "_period_running", False):
            return
        self._period_running = True
        self._period_thread = threading.Thread(
            target=self._period_summary_worker,
            args=(level, period_key, label),
            daemon=True,
        )
        self._period_thread.start()

    def _period_summary_worker(self, level, period_key, label):
        message = ""
        try:
            from brain import memory_summary as _ms
            if level == "weekly":
                result = _ms.build_weekly(period_key)
            elif level == "monthly":
                result = _ms.build_monthly(period_key)
            else:
                result = _ms.build_yearly(period_key)
            if result.get("content"):
                message = f"📅 {label}自动写好啦：{result.get('title', '')}\n（可在记忆-总结中查看）"
        except Exception:
            message = ""
        self._period_summary_done.emit(label, message)

    def _on_period_summary_done(self, label, message):
        self._period_running = False
        self._period_thread = None
        if not message:
            return
        try:
            self.chat_widget.add_message(message, is_user=False)
            from brain import history as _hist
            _hist.add_message(self._session_id, "assistant", message)
        except Exception:
            pass

    # ── ask 询问档实现（allow/ask/deny 的 ask） ───────────────────────
    # 敏感工具在后台线程调用，这里把弹窗调度回 GUI 主线程，并同步等待用户选择。
    _TOOL_NAME_CN = {
        "write_file": "写入文件", "edit_file": "编辑文件", "open_app": "打开程序",
        "browser_task": "浏览器操作", "download_image": "下载图片",
    }

    def _on_ask_dialog(self, cn, display):
        """主线程槽：创建权限确认弹窗（必须在主线程，后台线程建 QMessageBox 会跨线程崩溃）。"""
        try:
            from PyQt5.QtWidgets import QMessageBox
            box = QMessageBox(self)
            box.setWindowTitle("六花想执行操作 ✋")
            box.setText(f"六花想执行：{cn}")
            box.setInformativeText(f"{display}\n\n是否允许？（允许一次）")
            allow_btn = box.addButton("✅ 允许", QMessageBox.AcceptRole)
            deny_btn = box.addButton("⛔ 拒绝", QMessageBox.RejectRole)
            box.setDefaultButton(deny_btn)
            box.exec_()
            self._ask_result["allowed"] = box.clickedButton() is allow_btn
        except Exception:
            self._ask_result["allowed"] = False
        finally:
            self._ask_evt.set()

    def _ask_tool_permission(self, name, args):
        """返回 True=允许 / False=拒绝。由 tools.handle_tool_call 在后台线程调用。

        弹窗通过信号桥跨线程调度到主线程（QueuedConnection），后台线程只等待结果，
        避免在后台线程创建 QMessageBox 导致 Qt 跨线程 setParent 崩溃。"""
        display = {
            "write_file": str(args.get("path", "")),
            "edit_file": str(args.get("path", "")),
            "open_app": str(args.get("target", "")),
            "browser_task": str(args.get("task", ""))[:60],
            "download_image": str(args.get("url", "")),
        }.get(name, "")
        cn = self._TOOL_NAME_CN.get(name, name)

        # 已在主线程：直接弹窗
        if QThread.currentThread() is self.thread():
            self._ask_evt.clear()
            self._ask_result.clear()
            self._on_ask_dialog(cn, display)
            return bool(self._ask_result.get("allowed"))

        # 后台线程：发信号到主线程，等待结果（最多 5 分钟防卡死）
        try:
            self._ask_evt.clear()
            self._ask_result.clear()
            self._ask_dialog_signal.emit(cn, display)
            self._ask_evt.wait(5 * 60)
            return bool(self._ask_result.get("allowed"))
        except Exception:
            return True  # 调度失败时保守放行（与旧行为一致）

    def _build_proactive_prompt(self) -> str:
        """构建链式主动触发的系统提示"""
        parts = []
        try:
            t = diary_module.get_or_create_today()
            if t.get("details"):
                parts.append(f"今日日记: {t['details'][:100]}")
        except Exception:
            pass
        try:
            import os as _os
            memo_path = _os.path.join(config.ROOT_DIR, "persona", "memo.md")
            if _os.path.exists(memo_path):
                with open(memo_path, "r", encoding="utf-8") as _f:
                    memo_content = _f.read()[:200]
                parts.append("备忘录: " + memo_content)
        except Exception:
            pass
        try:
            from brain import memory_vault as _mv
            for m in _mv.search("", top_k=3):
                parts.append(f"近期: {m['title'][:30]}")
        except Exception:
            pass
        try:
            p = config.load_last_summary()
            if p:
                parts.append(f"上轮摘要: {p[:100]}")
        except Exception:
            pass
        try:
            parts.append(f"好感度: {self.agent.emotion.affection}%")
        except Exception:
            pass

        # 待处理的定时器
        pending = self._timer_mgr.list_pending()
        if pending:
            info = "; ".join(
                f"{t['type']}({t['remaining_sec']}s后)" for t in pending[:3]
            )
            parts.append(f"待处理定时器: {info}")

        # 记忆唤起：到期的 approved 候选（完整版——LLM 评估过该关心什么、何时关心）
        memory_cue = None
        if getattr(config, "MEMORY_CUE_ENABLED", False):
            try:
                from brain import memory_proactive as _mp
                memory_cue = _mp.get_due_cue()
            except Exception:
                memory_cue = None
        if memory_cue:
            cue_content = (memory_cue.get("content") or "")[:150]
            cue_msg = (memory_cue.get("suggested_message") or "")[:200]
            cue_action = memory_cue.get("action", "contact")
            self._active_cue_id = memory_cue.get("id")
            parts.append(
                f"【📌 记忆唤起】你想起一件关于契约者的重要事情：{cue_content}"
                f"（这是你之前记下的，值得主动关心）\n"
                f"建议时机：{cue_action}；写作意图：{cue_msg or '自然地关心一下'}"
            )

        ctx = "\n".join(parts) if parts else "暂无"

        now = datetime.now()
        hour = now.hour
        period = (
            "凌晨" if hour < 6 else "早上" if hour < 9 else
            "上午" if hour < 12 else "中午" if hour < 14 else
            "下午" if hour < 18 else "晚上"
        )

        # 主动消息同步 QQ（莲心式多通道交付）：契约者不在电脑前也能收到关心
        qq_sync = ""
        if getattr(config, "PROACTIVE_QQ_ENABLED", False):
            qq_users = config.get_qq_allowed_users()
            if qq_users:
                qq_sync = (
                    f"\n【QQ 同步】如果你决定主动发消息，把这条消息也用 send_qq_message 发给契约者"
                    f"（QQ号：{qq_users[0]}）。用 send_qq_message 发的内容和你在窗口里说的话保持一致，"
                    f"不要重复编两条不同的。\n"
                    f"注意：这只是把消息同步给契约者，不影响你设置下一次 set_proactive_timer。"
                )

        return (
            f"【系统通知 ✦ 链式主动关心触发】\n"
            f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}（{period}，{hour}点）\n"
            f"以下是你当前的上下文：\n{ctx}\n\n"
            f"请按你的行为规范判断：\n"
            f"1. 现在是否该主动找契约者？\n"
            f"2. 如果要发消息，直接回复即可\n"
            f"3. **无论发不发，都必须调用 set_proactive_timer 设置下一次**（这是链条不中断的关键！）\n"
            f"4. 白天(8-23点)设10-60分钟，深夜(23-8点)设2-7小时"
            f"{qq_sync}"
        )

    # ── 活动跟踪 ─────────────────────────────────────────────

    def _reset_activity(self):
        """用户活动时调用——更新最后活动时间，清除防打扰"""
        self._last_activity = datetime.now()

    # ── 会话管理 ─────────────────────────────────────────────

    def _new_conversation(self):
        self._show_chat()
        self.agent.start_session()
        self._session_id = history.create_session()
        config.save_user_config({"last_session_id": self._session_id})
        self.chat_widget.new_session()
        self.chat_widget.set_current_session(self._session_id)
        self.chat_top_bar.clear_search()
        self.session_panel.refresh_sessions(self._session_id)
        self._refresh_chat_insights()
        self.input_panel.input_field.clear()
        self.input_panel.focus_input()
        self._reset_activity()

    def _open_history(self):
        if hasattr(self, "history_page"):
            self._switch_workspace(
                self.history_page,
                "history",
                refresh=self.history_page.refresh_data,
            )
            return
        from gui.history_dialog import HistoryDialog
        dialog = HistoryDialog(self)
        dialog.session_selected.connect(self._load_session)
        dialog.exec_()

    def _open_surf_history(self):
        """打开六花的冲浪记录页（侧边栏「历史记录」下方）。"""
        if hasattr(self, "surf_history_page"):
            self._switch_workspace(
                self.surf_history_page,
                "workflow",
                refresh=self.surf_history_page.refresh_data,
            )
            return
        from gui.surf_history_dialog import SurfHistoryDialog
        SurfHistoryDialog(self).exec_()

    def _load_session(self, sid):
        self._show_chat()
        self.chat_top_bar.clear_search()
        loaded = self._load_session_messages(sid)
        if not loaded:
            # 空会话：同样要重置 agent 上下文和聊天显示，
            # 否则上一条会话的内容（含流式气泡）会残留在屏幕上，像"气泡跟着会话跑"
            self.agent.start_session()
            self.chat_widget.new_session()
        self._session_id = sid
        self.chat_widget.set_current_session(sid)
        config.save_user_config({"last_session_id": self._session_id})
        self.session_panel.refresh_sessions(self._session_id)
        self._refresh_chat_insights()
        self._reset_activity()

    def _refresh_chat_insights(self):
        if hasattr(self, "chat_insights"):
            self.chat_insights.refresh_data()

    def _load_session_messages(self, sid) -> bool:
        msgs = history.get_messages(sid)
        if not msgs:
            return False
        self.agent.start_session()
        self._session_id = sid
        # 会话恢复：只注入最近 N 轮，避免旧历史撑爆上下文（Suzu Lives 连续性思想）
        RECENT_ROUNDS = 20
        hist_msgs = [m for m in msgs if m["role"] in ("user", "assistant")]
        recent = hist_msgs[-RECENT_ROUNDS * 2:]
        for m in recent:
            self.agent._history.append({"role": m["role"], "content": m["content"]})
        self.chat_widget.new_session()
        # 界面仍展示完整历史（聊天窗口显示全部，上下文只取最近 N 轮）
        for m in msgs:
            if m["role"] == "user":
                if m["content"].startswith("[图片]"):
                    p = m["content"].replace("[图片]", "", 1).strip()
                    self.chat_widget.add_message(
                        "", is_user=True,
                        image_path=p if os.path.exists(p) else None,
                    )
                else:
                    self.chat_widget.add_message(m["content"], is_user=True)
            elif m["role"] == "assistant":
                if m["content"].startswith("[图片]"):
                    p = m["content"].replace("[图片]", "", 1).strip()
                    self.chat_widget.add_message(
                        "", is_user=False,
                        image_path=p if os.path.exists(p) else None,
                    )
                else:
                    self.chat_widget.add_message(m["content"], is_user=False)
        config.save_user_config({"last_session_id": self._session_id})
        # 切回本会话：若它还有在流的回复气泡 → 重新挂回布局，让它继续显示
        self.chat_widget.set_current_session(sid)
        self.chat_widget.reattach_stream(sid)
        # 跳到会话最后一条消息（底部），而不是停在顶部要手动往下滑
        QTimer.singleShot(120, self.chat_widget._scroll_to_bottom)
        return True

    # ── 对话框 ────────────────────────────────────────────────

    def _open_notes(self):
        if hasattr(self, "memory_page"):
            self._switch_workspace(
                self.memory_page,
                "memory",
                refresh=self.memory_page.refresh_data,
            )
            return
        from gui.memo_dialog import MemoDialog
        MemoDialog(self).exec_()

    def _open_tools(self):
        from gui.tools_dialog import ToolsDialog
        ToolsDialog(self).exec_()

    def _open_summary(self):
        from gui.summary_dialog import SummaryDialog
        SummaryDialog(self).exec_()

    def _open_settings(self):
        self._switch_workspace(
            self.settings_page,
            "settings",
            refresh=self.settings_page.load_settings,
        )

    def _open_settings_section(self, category):
        """打开设置页并跳到指定分类。"""
        self._open_settings()
        self.settings_page.select_category(category)

    def _on_config_changed(self):
        """设置保存后重新加载配置"""
        config.reload_from_file()
        self._apply_appearance(animate=True)
        # 按新配置启停自动定时器（记忆唤起 / 自动周记 / 日记自动收尾 / 主动冲浪）
        for timer, flag in (
            (getattr(self, "_memory_cue_timer", None), "MEMORY_CUE_ENABLED"),
            (getattr(self, "_weekly_timer", None), "WEEKLY_AUTO_ENABLED"),
            (getattr(self, "_diary_summary_timer", None), "DIARY_AUTO_SUMMARY_ENABLED"),
            (getattr(self, "_surf_timer", None), "SURF_AUTO_ENABLED"),
        ):
            try:
                if timer is None:
                    continue
                if getattr(config, flag, False):
                    if not timer.isActive():
                        timer.start()
                else:
                    timer.stop()
            except Exception:
                pass
        if getattr(config, "DIARY_AUTO_SUMMARY_ENABLED", False):
            QTimer.singleShot(45 * 1000, self._diary_auto_backfill)
        if hasattr(self, "history_page"):
            self.history_page.refresh_data()
        if hasattr(self, "memory_page"):
            self.memory_page.refresh_data()
        if hasattr(self, "surf_history_page"):
            self.surf_history_page.refresh_data()
        session_ids = {item["id"] for item in history.get_sessions(1000)}
        if self._session_id not in session_ids:
            self._new_conversation()
