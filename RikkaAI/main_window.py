"""
RikkaAI - 主窗口
"""
import os
import time
import random
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QSplitter, QMessageBox,
)
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QIcon
import config
from brain.qq_bridge import get_bridge, set_message_handler, set_event_handlers
from gui.chat_widget import ChatWidget
from gui.input_panel import InputPanel
from gui.character_widget import CharacterWidget
from brain.agent import AgentCore
from brain.memory import MemorySystem
import brain.history as history
import brain.diary as diary_module
from brain import notes as notes_module


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
            self.done.emit(r[:500])
        except Exception:
            self.done.emit("")


class ProactiveWorker(QObject):
    """屏幕偷看（30%概率的彩蛋）"""
    done = pyqtSignal(str, str)

    def run(self):
        try:
            from PIL import ImageGrab
            from brain.tools import _vision
            d = config.SCREENSHOTS_DIR
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, f"proactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            ImageGrab.grab().save(p)
            a = _vision("你偷偷看了一眼契约者的屏幕，看到了什么？简短口语描述", p, 0.2, 300)
            self.done.emit(a, p)
        except Exception:
            self.done.emit("", "")


class SummaryWorker(QObject):
    done = pyqtSignal(str)

    def __init__(self, msgs):
        super().__init__()
        self._messages = msgs

    def run(self):
        from brain.context_compressor import _generate_summary
        try:
            self.done.emit(_generate_summary(self._messages))
        except Exception:
            self.done.emit("摘要生成失败")


# ═══════════════════════════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RikkaAI - 六花AI")
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)
        self.resize(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)

        # 核心模块
        self.memory = MemorySystem()
        self.agent = AgentCore(memory=self.memory)
        self.agent.start_session()

        # QQ 桥接（信号桥，保证线程安全）
        self._qq_bridge = get_bridge()
        self._qq_signals = QQBridgeSignals()
        self._qq_signals.connected.connect(self._on_qq_connected)
        self._qq_signals.disconnected.connect(self._on_qq_disconnected)
        self._qq_signals.got_message.connect(self._on_qq_message_threadsafe)
        self._qq_signals.got_error.connect(self._on_qq_error)
        set_message_handler(self._on_qq_message_bg)
        set_event_handlers(
            connected=lambda: self._qq_signals.connected.emit(),
            disconnected=lambda: self._qq_signals.disconnected.emit(),
        )

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
        self._summary_thread = None
        self._summary_worker = None
        self._save_btn = None

        # ── 定时器管理器（替代旧 QTimer） ──
        self._timer_mgr = TimerManager(self)
        self._timer_mgr.timer_fired.connect(self._on_timer_fired)

        # 旧的状态跟踪（保留，简化复位用）
        self._last_activity = datetime.now()
        self._proactive_enabled = config.PROACTIVE_ENABLED
        self._in_proactive = False

        # 界面
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        ip = os.path.join(config.IMAGES_DIR, "avatar.png")
        if os.path.exists(ip):
            self.setWindowIcon(QIcon(ip))
        self._setup_ui()
        self._load_theme()

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
        tb.setFixedHeight(40)
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
            ("🧠", "记忆", self._open_memory),
            ("📖", "日记", self._open_diary),
            ("📝", "备忘", self._open_notes),
            ("🔧", "工具", self._open_tools),
            ("💾", "保存", self._save_context),
            ("⚙", "设置", self._open_settings),
        ]:
            b = QPushButton(emoji)
            b.setFixedSize(32, 32)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tooltip)
            b.setStyleSheet(
                "QPushButton{background:transparent;border:1px solid #3a1a6e;"
                "border-radius:16px;font-size:14px;color:#7a5aaa}"
                "QPushButton:hover{background:#2d1b4e;border-color:#9b59b6;color:#ffd700}"
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
            "QPushButton{background:#3a0a0a;border:1px solid #6a1a1a;"
            "border-radius:14px;font-size:12px;color:#ff4444}"
            "QPushButton:hover{background:#5a0a0a;border-color:#ff4444;color:#ff8888}"
        )
        self._stop_btn.clicked.connect(self._stop_everything)
        tl.addWidget(self._stop_btn)

        # 💬 QQ 开关按钮
        self._qq_btn = QPushButton("💬")
        self._qq_btn.setFixedSize(28, 28)
        self._qq_btn.setCursor(Qt.PointingHandCursor)
        self._qq_btn.setToolTip("QQ 离线")
        self._qq_btn.setStyleSheet(
            "QPushButton{background:transparent;border:1px solid #3a1a6e;"
            "border-radius:14px;font-size:12px;color:#7a5aaa}"
            "QPushButton:hover{background:#2d1b4e;border-color:#9b59b6;color:#ffd700}"
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
        sm.setStyleSheet("color:#5a3a7a;font-size:10px;")
        sl.addWidget(sm)
        ml.addWidget(sb)

    def _load_theme(self):
        p = os.path.join(config.STYLES_DIR, "theme.qss")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    # ── 用户输入 ────────────────────────────────────────────────

    def _on_user_input(self, text):
        self._reset_activity()
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
        self.chat_widget.start_streaming()
        self.input_panel.set_input_enabled(False)
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, text)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(self._on_stream)
        self._worker.finished.connect(self._on_response_finished)
        self._worker.error.connect(self._on_response_error)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

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
        self.chat_widget.start_streaming()
        self.input_panel.set_input_enabled(False)
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, prompt)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(self._on_stream)
        self._worker.finished.connect(self._on_response_finished)
        self._worker.error.connect(self._on_response_error)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _on_stream(self, chunk):
        self.chat_widget.append_stream(chunk)

    # ── 响应完成（核心：处理图片 + 定时器 + 历史） ─────────────

    def _on_response_finished(self, response):
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
                text = self.chat_widget.pop_streaming_bubble()
            else:
                self.chat_widget.stop_streaming()
        except Exception:
            if not has_images:
                self.chat_widget.stop_streaming()

        # 1a. 处理 AI 主动发的截图（优先展示）
        try:
            while _tt._PENDING_IMAGES:
                p = _tt._PENDING_IMAGES.pop(0)
                if os.path.exists(p):
                    self.chat_widget.add_message("", is_user=False, image_path=p)
                    history.add_message(self._session_id, "assistant", f"[图片]{p}")
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

        # 3. 存文字回复到历史（用实际显示的完整文本，不丢内容）
        text_to_store = text or response
        if text_to_store:
            try:
                history.add_message(self._session_id, "assistant", text_to_store)
            except Exception:
                pass

        if self.agent.history and len(self.agent.history) == 3:
            title = (response[:30] + "…") if len(response) > 30 else response
            history.update_session_title(self._session_id, title)

        self.input_panel.set_input_enabled(True)
        self.input_panel.focus_input()

        if self._in_proactive:
            self._in_proactive = False

    def _on_response_error(self, em):
        if self._worker_thread:
            self._worker_thread.quit()
            self._worker_thread.wait()
            self._worker_thread = None
            self._worker = None
        self.chat_widget.stop_streaming()
        self.chat_widget.add_message(f"力量乱掉了…出错啦！\n{em}", is_user=False)
        self.input_panel.set_input_enabled(True)
        self.input_panel.focus_input()

    # ── ⏹ 停止按钮（中断一切操作） ───────────────────────────────

    def _stop_everything(self):
        """停止当前正在进行的任何操作（回复、游戏play、截图等）"""
        from brain import tools as _tt
        # 1. 发停止信号给 game_play 等后台操作
        _tt.request_stop()
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
        # 4. 清理界面
        self.chat_widget.stop_streaming()
        self.chat_widget.add_message("⏹ 六花被契约者叫停了～", is_user=False)
        self.input_panel.set_input_enabled(True)
        self.input_panel.focus_input()

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
        self._qq_signals.got_message.emit(user_id, group_id, message, msg_type)
        return None

    def _on_qq_message_threadsafe(self, user_id, group_id, message, msg_type):
        """主线程：处理 QQ 消息（在主线程运行，可以直接调 UI）"""
        try:
            sender = f"QQ:{user_id}"
            if group_id:
                sender = f"QQ群{group_id}:{user_id}"
            self.chat_widget.add_message(f"💬 [{sender}] {message}", is_user=True)

            # 直接在主线程调六花（会阻塞但QQ消息不多，问题不大）
            response = self.agent.chat(message)
            if response:
                self.chat_widget.add_message(f"💬 [六花→QQ] {response}", is_user=False)
                if msg_type == "group" and group_id:
                    self._qq_bridge.send_group_msg(group_id, response)
                else:
                    self._qq_bridge.send_private_msg(user_id, response)
        except Exception as e:
            self.chat_widget.add_message(f"💬 QQ消息处理失败: {e}", is_user=False)

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

    # ── 定时器触发（链式主动 + 临时回访） ─────────────────────

    def _on_timer_fired(self, timer_type: str, context: dict):
        """定时器到期时调用——构建 prompt 发给 AI"""
        if self._worker_thread or self._proactive_thread:
            return  # 正在回复中，跳过

        # 如果用户关闭了主动聊天，跳过链式主动（临时回访不受影响）
        if timer_type == "proactive" and not config.PROACTIVE_ENABLED:
            return

        now = datetime.now()
        hour = now.hour

        if timer_type == "proactive":
            self._in_proactive = True
            # 30% 概率偷看屏幕（保留原有彩蛋）
            if random.randint(1, 100) <= 30:
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
            self.chat_widget.start_streaming()
            self._worker_thread = QThread(self)
            self._worker = AgentWorker(self.agent, prompt)
            self._worker.moveToThread(self._worker_thread)
            self._worker_thread.started.connect(self._worker.run)
            self._worker.stream.connect(self._on_stream)
            self._worker.finished.connect(self._on_response_finished)
            self._worker.error.connect(self._on_response_error)
            self._worker_thread.finished.connect(self._worker_thread.deleteLater)
            self._worker_thread.start()

    def _do_proactive_chat(self):
        """执行链式主动对话"""
        prompt = self._build_proactive_prompt()
        self.chat_widget.start_streaming()
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, prompt)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(self._on_stream)
        self._worker.finished.connect(self._on_response_finished)
        self._worker.error.connect(self._on_response_error)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

    def _on_proactive_peek(self, analysis, img_path):
        """屏幕偷看结果 → 发给 AI"""
        if self._proactive_thread:
            self._proactive_thread.quit()
            self._proactive_thread.wait()
            self._proactive_thread = None
            self._proactive_worker = None
        if analysis:
            prompt = (
                f"【系统通知 ✦ 链式主动（屏幕偷看）】\n"
                f"你偷偷看了一眼契约者的屏幕：{analysis}\n"
                f"用六花的语气自然地聊聊ta看的东西。\n\n"
                f"注意：无论是否发消息，都要用 set_proactive_timer 设下一次！"
            )
        else:
            prompt = self._build_proactive_prompt()
        self.chat_widget.start_streaming()
        self._worker_thread = QThread(self)
        self._worker = AgentWorker(self.agent, prompt)
        self._worker.moveToThread(self._worker_thread)
        self._worker_thread.started.connect(self._worker.run)
        self._worker.stream.connect(self._on_stream)
        self._worker.finished.connect(self._on_response_finished)
        self._worker.error.connect(self._on_response_error)
        self._worker_thread.finished.connect(self._worker_thread.deleteLater)
        self._worker_thread.start()

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
            n = notes_module.get_all(3)
            if n:
                parts.append("备忘: " + " | ".join(
                    f"{x['title']}: {x['content'][:40]}" for x in n
                ))
        except Exception:
            pass
        try:
            from brain import rag_memory
            for m in rag_memory.get_recent(3):
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

        ctx = "\n".join(parts) if parts else "暂无"

        now = datetime.now()
        hour = now.hour
        period = (
            "凌晨" if hour < 6 else "早上" if hour < 9 else
            "上午" if hour < 12 else "中午" if hour < 14 else
            "下午" if hour < 18 else "晚上"
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
        )

    # ── 活动跟踪 ─────────────────────────────────────────────

    def _reset_activity(self):
        """用户活动时调用——更新最后活动时间，清除防打扰"""
        self._last_activity = datetime.now()

    # ── 会话管理 ─────────────────────────────────────────────

    def _new_conversation(self):
        self.agent.start_session()
        self._session_id = history.create_session()
        config.save_user_config({"last_session_id": self._session_id})
        self.chat_widget.new_session()
        self.input_panel.input_field.clear()
        self.input_panel.focus_input()
        self._reset_activity()

    def _save_context(self):
        msgs = [m for m in self.agent._history if m.get("role") in ("user", "assistant")]
        if len(msgs) < 2:
            QMessageBox.information(self, "提示", "对话太短")
            return
        self._summary_thread = QThread(self)
        self._summary_worker = SummaryWorker(msgs)
        self._summary_worker.moveToThread(self._summary_thread)
        self._summary_worker.done.connect(self._on_summary_done)
        self._summary_thread.started.connect(self._summary_worker.run)
        self._summary_thread.finished.connect(self._summary_thread.deleteLater)
        self._summary_thread.start()
        sb = self.sender()
        if sb:
            sb.setEnabled(False)
            sb.setText("⏳")

    def _on_summary_done(self, s):
        if self._summary_thread:
            self._summary_thread.quit()
            self._summary_thread.wait()
            self._summary_thread = None
        config.save_last_summary(s)
        QMessageBox.information(self, "已保存", "上下文已保存")
        for b in self.findChildren(QPushButton):
            if b.text() == "⏳":
                b.setEnabled(True)
                b.setText("💾")
                break

    def _open_history(self):
        from gui.history_dialog import HistoryDialog
        d = HistoryDialog(self)
        d.session_selected.connect(self._load_session)
        d.exec_()

    def _load_session(self, sid):
        self._load_session_messages(sid)
        self._session_id = sid
        config.save_user_config({"last_session_id": self._session_id})
        self._reset_activity()

    def _load_session_messages(self, sid) -> bool:
        msgs = history.get_messages(sid)
        if not msgs:
            return False
        self.agent.start_session()
        self._session_id = sid
        for m in msgs:
            if m["role"] in ("user", "assistant"):
                self.agent._history.append({"role": m["role"], "content": m["content"]})
        self.chat_widget.new_session()
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
        return True

    # ── 对话框 ────────────────────────────────────────────────

    def _open_memory(self):
        from gui.memory_dialog import MemoryDialog
        MemoryDialog(self).exec_()

    def _open_diary(self):
        from gui.diary_dialog import DiaryDialog
        DiaryDialog(self).exec_()

    def _open_notes(self):
        from gui.notes_dialog import NotesDialog
        NotesDialog(self).exec_()

    def _open_tools(self):
        from gui.tools_dialog import ToolsDialog
        ToolsDialog(self).exec_()

    def _open_settings(self):
        from gui.settings_dialog import SettingsDialog
        d = SettingsDialog(self)
        d.config_changed.connect(self._on_config_changed)
        d.exec_()

    def _on_config_changed(self):
        """设置保存后重新加载配置"""
        config.reload_from_file()
