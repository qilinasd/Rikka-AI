"""Local WebEngine home page and its QWebChannel bridge."""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import (
    QBuffer, QByteArray, QIODevice, QObject, Qt, QThread, QTimer, QUrl,
    pyqtSignal, pyqtSlot,
)
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView
from PyQt5.QtWidgets import QGridLayout, QWidget

import brain.history as history
import config
import gui.theme_manager as theme_manager


class _VoiceProbeThread(QThread):
    """后台探活语音服务，避免 HTTP 探针（最长 2s）阻塞 GUI 线程。

    完成后再把最新状态推给 JS；失败静默，前端保留上一次缓存状态。
    """

    result_ready = pyqtSignal(object)

    def __init__(self, server, parent=None):
        super().__init__(parent)
        self._server = server

    def run(self):
        try:
            self._server.ensure_adopt_external()
            self.result_ready.emit(self._server.status())
        except Exception:
            pass


class WebHomeBridge(QObject):
    """Expose home data and route Web UI actions back to native PyQt."""

    start_chat_requested = pyqtSignal(str)
    chat_requested = pyqtSignal()
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    summary_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    session_selected = pyqtSignal(int)
    window_action_requested = pyqtSignal(str)
    window_drag_requested = pyqtSignal(int, int, str)
    voice_action_requested = pyqtSignal(str)
    voice_probe_requested = pyqtSignal()

    def _greeting(self):
        hour = datetime.now().hour
        if hour < 6:
            return "夜深了，主人", "别太辛苦，六花会安静地陪着你。"
        if hour < 11:
            return "早安，主人", "新的一天，要和六花一起做点什么呢？"
        if hour < 14:
            return "午安，主人", "休息一下吧，也可以把今天的想法告诉我。"
        if hour < 19:
            return "下午好，主人", "灵感正在盛开，今天想和我聊些什么呢？"
        return "晚上好，主人", "辛苦一天了，六花一直在这里等你。"

    @staticmethod
    def _count_files(folder, suffixes):
        if not os.path.isdir(folder):
            return 0
        return sum(
            1
            for _, _, filenames in os.walk(folder)
            for filename in filenames
            if filename.lower().endswith(suffixes)
        )

    @pyqtSlot(result=str)
    def getHomeData(self):
        try:
            sessions = history.get_sessions(1000)
            recent = sessions[:5]
            greeting, subtitle = self._greeting()
            generated_dir = os.path.join(config.ROOT_DIR, "images", "generated")
            summary_dir = os.path.join(config.ROOT_DIR, "summaries")
            overview = history.get_chat_analytics(7)
            payload = {
                "greeting": greeting,
                "subtitle": subtitle,
                "model": config.MODEL,
                "sessions": recent,
                "stats": {
                    "messages": sum(int(item.get("msg_count", 0)) for item in sessions),
                    "images": self._count_files(generated_dir, (".png", ".jpg", ".jpeg", ".webp")),
                    "sessions": len(sessions),
                    "summaries": self._count_files(summary_dir, (".md", ".txt")),
                },
                "overview": overview,
            }
        except Exception as exc:
            payload = {
                "greeting": "欢迎回来，主人",
                "subtitle": "首页数据读取遇到了一点问题，但仍然可以开始对话。",
                "sessions": [],
                "stats": {},
                "overview": {},
                "error": str(exc),
            }
        return json.dumps(payload, ensure_ascii=False)

    @pyqtSlot(str)
    def startChat(self, text):
        cleaned = " ".join(text.split())
        if cleaned:
            self.start_chat_requested.emit(cleaned)

    @pyqtSlot(str)
    def openSection(self, section):
        routes = {
            "chat": self.chat_requested,
            "history": self.history_requested,
            "memo": self.memo_requested,
            "memory": self.memo_requested,
            "summary": self.summary_requested,
            "knowledge": self.summary_requested,
            "tools": self.tools_requested,
            "workflow": self.tools_requested,
            "plugin": self.tools_requested,
            "settings": self.settings_requested,
        }
        signal = routes.get(section)
        if signal is not None:
            signal.emit()

    @pyqtSlot(int)
    def openSession(self, session_id):
        if session_id > 0:
            self.session_selected.emit(session_id)

    @pyqtSlot(str)
    def windowAction(self, action):
        if action in {"minimize", "maximize", "close"}:
            self.window_action_requested.emit(action)

    @pyqtSlot(int, int, str)
    def windowDrag(self, screen_x, screen_y, phase):
        if phase in {"start", "move", "end"}:
            self.window_drag_requested.emit(screen_x, screen_y, phase)

    @pyqtSlot(result=str)
    def getVoiceStatus(self):
        """立即返回当前缓存状态（同步快照，不做网络探活），随后后台线程探活校正。

        ensure_adopt_external 内部用 requests 探端口，最长阻塞 2s，绝不能跑在 GUI 线程，
        否则每次进首页 JS 刷新都会卡死一两秒。
        """
        from brain.voice_server import get_voice_server   # 懒加载，create_home_widget 签名不变
        try:
            if not getattr(config, "VOICE_ENABLED", False):
                # 语音功能已下线：不再探活本地 9880 端口
                return json.dumps({"state": "stopped", "detail": "语音功能未启用"}, ensure_ascii=False)
            server = get_voice_server()
            self.voice_probe_requested.emit()   # 后台线程再探活，完成时推送校正
            return json.dumps(server.status(), ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"state": "error", "detail": str(exc)}, ensure_ascii=False)

    @pyqtSlot(str)
    def voiceAction(self, action):
        if action in ("start", "stop"):
            self.voice_action_requested.emit(action)


class _ThemeBackdrop(QWidget):
    """Paint the active artwork while the WebEngine page switches themes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._pixmap = None
        self._wash = QColor(247, 244, 251, 255)

    def set_background(self, pixmap, wash):
        self._pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self._wash = QColor(wash)
        if self._pixmap is None:
            self._wash.setAlpha(255)
        self.update()

    def paintEvent(self, event):  # noqa: N802 - Qt API name
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.fillRect(self.rect(), self._wash)
        if self._pixmap is not None and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
            painter.fillRect(self.rect(), self._wash)


class WebHomeWidget(QWidget):
    """Desktop widget hosting the local HTML/CSS/JavaScript home screen."""

    start_chat = pyqtSignal(str)
    chat_requested = pyqtSignal()
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    summary_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    session_selected = pyqtSignal(int)
    window_action = pyqtSignal(str)
    window_drag = pyqtSignal(int, int, str)
    voice_action = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WebHomeWidget")
        self._loaded = False
        self._pending_appearance = None
        self._appearance_serial = 0

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.web_view = QWebEngineView(self)
        self.web_view.setContextMenuPolicy(Qt.NoContextMenu)
        self.web_view.page().setBackgroundColor(QColor(247, 244, 251))
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)

        self.bridge = WebHomeBridge(self)
        self.bridge.start_chat_requested.connect(self.start_chat.emit)
        self.bridge.chat_requested.connect(self.chat_requested.emit)
        self.bridge.history_requested.connect(self.history_requested.emit)
        self.bridge.memo_requested.connect(self.memo_requested.emit)
        self.bridge.summary_requested.connect(self.summary_requested.emit)
        self.bridge.tools_requested.connect(self.tools_requested.emit)
        self.bridge.settings_requested.connect(self.settings_requested.emit)
        self.bridge.session_selected.connect(self.session_selected.emit)
        self.bridge.window_action_requested.connect(self.window_action.emit)
        self.bridge.window_drag_requested.connect(self.window_drag.emit)
        self.bridge.voice_action_requested.connect(self.voice_action.emit)
        self.bridge.voice_probe_requested.connect(self._start_voice_probe)
        self._voice_probe_thread = None
        self._voice_probe_at = 0.0

        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("rikkaBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        self.web_view.loadFinished.connect(self._on_load_finished)
        layout.addWidget(self.web_view, 0, 0)

        # The HTML page initially contains only legacy fallback tokens. Keep it
        # covered until the active theme artwork has been decoded and committed
        # by the WebEngine compositor, so no stale background can flash at boot.
        self._backdrop = _ThemeBackdrop(self)
        layout.addWidget(self._backdrop, 0, 0)
        self._backdrop.show()
        self._prime_initial_appearance()

        page_path = Path(config.ROOT_DIR, "ui", "home", "index.html").resolve()
        if not page_path.is_file():
            raise FileNotFoundError(f"Web home page not found: {page_path}")
        self.web_view.load(QUrl.fromLocalFile(str(page_path)))

    def _prime_initial_appearance(self):
        """Seed the first frame from persisted settings before HTML can paint."""
        try:
            appearance = theme_manager.resolve_appearance(config)
            pixmap = theme_manager.load_theme_background(appearance, page_id="home")
            self.apply_appearance(appearance, pixmap, appearance.wash_color())
        except Exception:
            self._backdrop.set_background(None, QColor(247, 244, 251, 255))

    def _on_load_finished(self, loaded):
        self._loaded = bool(loaded)
        if self._loaded:
            self._push_appearance()
            self.refresh_recent()
            self._wait_for_appearance_ready(self._appearance_serial)
        else:
            self.web_view.setHtml(
                "<meta charset='utf-8'><style>body{font-family:sans-serif;padding:40px;color:#4b405c}</style>"
                "<h2>六花的首页暂时没有加载成功</h2><p>请检查本地 UI 文件是否完整。</p>"
            )
            # Reveal the diagnostic page after the cover has had a chance to
            # replace the failed document; the cover itself still uses the
            # active theme and never exposes the legacy artwork.
            QTimer.singleShot(260, self._backdrop.hide)

    def refresh_recent(self):
        if self._loaded:
            self.web_view.page().runJavaScript("window.rikkaHome && window.rikkaHome.refresh();")

    def apply_appearance(self, appearance, pixmap, wash):
        self._appearance_serial += 1
        self._backdrop.set_background(pixmap, wash)
        self._backdrop.show()
        self._backdrop.raise_()
        # Keep the compositor's base color aligned with the active wash while
        # the image is loading (the overlay still covers the complete viewport).
        page_color = QColor(wash)
        page_color.setAlpha(255)
        self.web_view.page().setBackgroundColor(page_color)
        background = ""
        source_path = ""
        if appearance.theme_id in theme_manager.SEASONAL_THEMES:
            source_path = theme_manager.seasonal_background_path(
                appearance.theme_id, "home"
            )
        if source_path and os.path.isfile(source_path):
            background = QUrl.fromLocalFile(os.path.abspath(source_path)).toString()
        elif not background:
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.WriteOnly)
            saved = pixmap.save(buffer, "PNG")
            buffer.close()
            if saved:
                background = "data:image/png;base64," + bytes(data.toBase64()).decode("ascii")
        self._pending_appearance = {
            "themeId": appearance.theme_id,
            "accent": appearance.accent,
            "accentHover": appearance.accent_hover,
            "accentSoft": appearance.accent_soft,
            "accentForeground": appearance.accent_text,
            "text": appearance.text,
            "card": appearance.card,
            "tokens": theme_manager.appearance_tokens(appearance),
            "wash": "rgba(%d,%d,%d,%.3f)" % (
                wash.red(), wash.green(), wash.blue(), min(92, wash.alpha()) / 255.0,
            ),
            "background": background,
        }
        self._push_appearance()
        if self._loaded:
            self._wait_for_appearance_ready(self._appearance_serial)

    def _wait_for_appearance_ready(self, serial, attempt=0):
        """Hide the first-frame cover only after JS has decoded the new image."""
        if not self._loaded or serial != self._appearance_serial:
            return

        def _checked(value):
            if serial != self._appearance_serial:
                return
            state = str(value or "")
            if state == "1":
                QTimer.singleShot(140, lambda: self._hide_backdrop(serial))
            elif state == "error":
                # JS removes the legacy image on decode failure; reveal the
                # usable solid wash rather than exposing stale artwork.
                QTimer.singleShot(220, lambda: self._hide_backdrop(serial))
            elif attempt >= 75:
                # The legacy CSS image is disabled, so revealing after a slow
                # or broken JS bootstrap remains safe and restores interaction.
                self._hide_backdrop(serial)
            else:
                QTimer.singleShot(
                    40, lambda: self._wait_for_appearance_ready(serial, attempt + 1)
                )

        self.web_view.page().runJavaScript(
            "document.documentElement.dataset.appearanceReady || ''", _checked
        )

    def _hide_backdrop(self, serial):
        if serial == self._appearance_serial:
            self._backdrop.hide()

    def _push_appearance(self):
        if not self._loaded or not self._pending_appearance:
            return
        payload = json.dumps(self._pending_appearance, ensure_ascii=True)
        self.web_view.page().runJavaScript(
            "window.rikkaHome && window.rikkaHome.setAppearance(%s);" % payload
        )

    def push_voice_status(self, status):
        """Python 侧状态变更 → 推送给 JS。status 为 dict。"""
        if self._loaded:
            payload = json.dumps(status, ensure_ascii=False)
            self.web_view.page().runJavaScript(
                "window.rikkaHome && window.rikkaHome.setVoiceStatus(%s);" % payload)

    # ── 语音探活（后台线程，避免阻塞 GUI） ──

    def _start_voice_probe(self):
        """后台探活语音服务；运行中或 5 秒内探过则跳过，防止反复进首页重复探活。"""
        from brain.voice_server import get_voice_server
        if self._voice_probe_thread and self._voice_probe_thread.isRunning():
            return
        if time.time() - self._voice_probe_at < 5:
            return
        self._voice_probe_at = time.time()
        thread = _VoiceProbeThread(get_voice_server(), self)
        self._voice_probe_thread = thread
        thread.result_ready.connect(self._on_voice_probe_result)
        thread.finished.connect(self._voice_probe_done)
        thread.start()

    def _on_voice_probe_result(self, status):
        self.push_voice_status(status)

    def _voice_probe_done(self):
        self._voice_probe_thread = None

    def closeEvent(self, event):
        # 探活线程最长 2s，关窗时若仍在跑则等待收尾，避免 QThread destroyed while running
        if self._voice_probe_thread is not None and self._voice_probe_thread.isRunning():
            self._voice_probe_thread.wait(3000)
            self._voice_probe_thread = None
        super().closeEvent(event)
