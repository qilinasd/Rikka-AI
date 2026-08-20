"""Native message timeline for RikkaAI."""

import os
import wave

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QPixmap
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import config
from gui.image_utils import circular_pixmap


class MessageBubble(QFrame):
    def __init__(self, text="", is_user=False, image_path=None, sender=None, parent=None):
        super().__init__(parent)
        self.setObjectName("MessageRow")
        self.text_label = None
        self._search_text = text or ""

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        card = QFrame()
        if is_user:
            card.setObjectName("UserBubble")
            meta_text = "你 · 刚刚"
            meta_obj, text_obj = "UserBubbleMeta", "UserBubbleText"
        elif sender:
            # QQ 等「对方」消息：左对齐、独立配色，元信息显示发送者
            card.setObjectName("ContactBubble")
            meta_text = f"{sender} · 刚刚"
            meta_obj, text_obj = "ContactBubbleMeta", "ContactBubbleText"
        else:
            card.setObjectName("AIBubble")
            meta_text = "RikkaAI · 刚刚"
            meta_obj, text_obj = "AIBubbleMeta", "AIBubbleText"
        card.setMaximumWidth(690)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 14)
        card_layout.setSpacing(7)

        meta = QLabel(meta_text)
        meta.setObjectName(meta_obj)
        card_layout.addWidget(meta)

        if text or image_path is None:
            self.text_label = QLabel(text)
            self.text_label.setObjectName(text_obj)
            self.text_label.setWordWrap(True)
            self.text_label.setTextFormat(Qt.PlainText)
            self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card_layout.addWidget(self.text_label)

        if image_path:
            image = QLabel()
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                image.setPixmap(pixmap.scaled(400, 330, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                image.setObjectName("BubbleImage")
                image.setCursor(Qt.PointingHandCursor)
                image.mousePressEvent = (
                    lambda event: os.startfile(image_path)
                    if hasattr(os, "startfile")
                    else None
                )
                card_layout.addWidget(image)
            elif not text:
                # 历史图片文件已丢失：显示占位，避免空白卡片
                missing = QLabel("[图片已丢失]")
                missing.setObjectName(text_obj)
                missing.setWordWrap(True)
                missing.setTextFormat(Qt.PlainText)
                card_layout.addWidget(missing)

        if is_user or sender:
            # 「你」和 QQ「对方」消息都靠最右边（对方消息用独立配色区分，不误当「你」）
            row.addStretch()
            row.addWidget(card)
        else:
            avatar = QLabel()
            avatar.setObjectName("BubbleAvatar")
            avatar.setFixedSize(38, 38)
            avatar.setPixmap(circular_pixmap(os.path.join(config.IMAGES_DIR, "avatar.png"), 38))
            row.addWidget(avatar, 0, Qt.AlignTop)
            row.addWidget(card)
            row.addStretch()

    def append_text(self, chunk):
        if self.text_label is not None:
            self._search_text += chunk
            try:
                self.text_label.setText(self.text_label.text() + chunk)
            except RuntimeError:
                pass

    def matches(self, query):
        return not query or query in self._search_text.lower()

    def stop_cursor(self):
        pass


class StreamingBubble(MessageBubble):
    def __init__(self, parent=None):
        super().__init__("", is_user=False, parent=parent)
        self._base_text = ""
        self._cursor_visible = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._toggle_cursor)
        self._cursor_timer.start(500)

    def _alive(self):
        """text_label 的 C++ 对象是否已被销毁（气泡被 clear/trim/deleteLater 后不能再碰）。
        Qt 已删对象抛 RuntimeError；这里统一兜住，避免流式 chunk 写入已删除的 QLabel。"""
        if self.text_label is None:
            return False
        try:
            from PyQt5 import sip
            if sip.isdeleted(self.text_label):
                return False
            return True
        except Exception:
            try:
                self.text_label.text()
                return True
            except RuntimeError:
                return False

    def _toggle_cursor(self):
        if not self._alive():
            self._cursor_timer.stop()
            return
        self._cursor_visible = not self._cursor_visible
        self.text_label.setText(self._base_text + ("|" if self._cursor_visible else ""))

    def append_text(self, chunk):
        if not self._alive():
            self._cursor_timer.stop()
            return
        self._base_text += chunk
        self._search_text = self._base_text
        self.text_label.setText(self._base_text + "|")

    def stop_cursor(self):
        self._cursor_timer.stop()
        if not self._alive():
            return
        self.text_label.setText(self._base_text)


class VoiceBubble(QFrame):
    """语音条气泡：点击播放/暂停，显示日语文本 + 中文翻译（QQ/微信样式）。

    每个气泡自持一个 QMediaPlayer（主线程创建）；类级 _active_player 保证同时只有
    一个气泡在响——播新的会先停掉上一个。
    """

    _active_player = None   # 当前正在播放的气泡播放器

    def __init__(self, text="", translation="", audio_path="", parent=None):
        super().__init__(parent)
        self.setObjectName("MessageRow")
        self.audio_path = audio_path
        self._search_text = (text or "") + " " + (translation or "")

        self._player = QMediaPlayer(self)
        self._player.setMedia(QMediaContent(QUrl.fromLocalFile(audio_path)))
        self._player.stateChanged.connect(self._on_state_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        card = QFrame()
        card.setObjectName("AIBubble")
        card.setMaximumWidth(690)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 14)
        card_layout.setSpacing(7)

        meta = QLabel("RikkaAI · 语音")
        meta.setObjectName("AIBubbleMeta")
        card_layout.addWidget(meta)

        # 控制行：播放/暂停 + 时长
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        self.play_btn = QPushButton("▶")
        self.play_btn.setObjectName("VoiceBubblePlay")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setFixedSize(34, 34)
        self.play_btn.setToolTip("播放/暂停")
        self.play_btn.clicked.connect(self.toggle)
        self.dur_label = QLabel(self._duration_str())
        self.dur_label.setObjectName("VoiceBubbleMeta")
        ctrl.addWidget(self.play_btn)
        ctrl.addWidget(self.dur_label)
        ctrl.addStretch()
        card_layout.addLayout(ctrl)

        if text:
            self.text_label = QLabel(text)
            self.text_label.setObjectName("AIBubbleText")
            self.text_label.setWordWrap(True)
            self.text_label.setTextFormat(Qt.PlainText)
            self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card_layout.addWidget(self.text_label)

        if translation:
            tl = QLabel(f"中文：{translation}")
            tl.setObjectName("VoiceBubbleTranslation")
            tl.setWordWrap(True)
            tl.setTextFormat(Qt.PlainText)
            card_layout.addWidget(tl)

        avatar = QLabel()
        avatar.setObjectName("BubbleAvatar")
        avatar.setFixedSize(38, 38)
        avatar.setPixmap(circular_pixmap(os.path.join(config.IMAGES_DIR, "avatar.png"), 38))
        row.addWidget(avatar, 0, Qt.AlignTop)
        row.addWidget(card)
        row.addStretch()

    def _duration_str(self):
        try:
            with wave.open(self.audio_path, "rb") as w:
                secs = w.getnframes() / max(w.getframerate(), 1)
            m, s = divmod(int(round(secs)), 60)
            return f"{m}:{s:02d}"
        except Exception:
            return ""

    def _on_state_changed(self, state):
        self.play_btn.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            if VoiceBubble._active_player is self._player:
                VoiceBubble._active_player = None

    def play(self):
        prev = VoiceBubble._active_player
        if prev is not None and prev is not self._player:
            try:
                prev.stop()
            except Exception:
                pass
        VoiceBubble._active_player = self._player
        self._player.play()

    def pause(self):
        self._player.pause()

    def toggle(self):
        if self._player.state() == QMediaPlayer.PlayingState:
            self.pause()
        else:
            self.play()

    def stop(self):
        try:
            self._player.stop()
        except Exception:
            pass
        if VoiceBubble._active_player is self._player:
            VoiceBubble._active_player = None

    def matches(self, query):
        return not query or query in self._search_text.lower()


class ServiceBanner(QFrame):
    """系统提示 + 进度条气泡（GPT-SoVITS 服务启动进度用）。"""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.setObjectName("MessageRow")

        card = QFrame()
        card.setObjectName("AIBubble")
        card.setMaximumWidth(690)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 13, 16, 14)
        cl.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("AIBubbleMeta")
        self.title_label.setWordWrap(True)
        cl.addWidget(self.title_label)

        self.bar = QProgressBar()
        self.bar.setObjectName("ServiceProgress")
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedHeight(18)
        cl.addWidget(self.bar)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        avatar = QLabel()
        avatar.setObjectName("BubbleAvatar")
        avatar.setFixedSize(38, 38)
        avatar.setPixmap(circular_pixmap(os.path.join(config.IMAGES_DIR, "avatar.png"), 38))
        row.addWidget(avatar, 0, Qt.AlignTop)
        row.addWidget(card)
        row.addStretch()

    def update_progress(self, percent, text=None):
        self.bar.setValue(max(0, min(100, int(percent))))
        if text:
            self.title_label.setText(text)


class ChatWidget(QWidget):
    MAX_MESSAGES = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatWidget")
        self._stream_bubbles = {}   # sid -> StreamingBubble（在流的气泡，含已 park 的）
        self._active_sid = None     # 当前挂在布局上的流式气泡所属会话
        self._current_sid = None    # 当前显示的会话
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("ChatScrollArea")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ChatScrollContent")
        self.message_layout = QVBoxLayout(self.scroll_content)
        self.message_layout.setContentsMargins(24, 22, 24, 24)
        self.message_layout.setSpacing(14)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll, 1)
        self._add_welcome()

    def _add_welcome(self):
        welcome = "邪王真眼，觉醒。\n\n我在这里。今天想先从哪件事聊起？"
        self.message_layout.insertWidget(
            self.message_layout.count() - 1,
            MessageBubble(welcome, is_user=False),
        )

    def add_message(self, text="", is_user=False, image_path=None, sender=None):
        self.message_layout.insertWidget(
            self.message_layout.count() - 1,
            MessageBubble(text, is_user=is_user, image_path=image_path, sender=sender),
        )
        self._scroll_to_bottom()
        self._trim_messages()

    def add_voice_message(self, text="", translation="", audio_path=""):
        bubble = VoiceBubble(text=text, translation=translation, audio_path=audio_path)
        self.message_layout.insertWidget(self.message_layout.count() - 1, bubble)
        self._scroll_to_bottom()
        self._trim_messages()
        return bubble

    def add_service_banner(self, title=""):
        banner = ServiceBanner(title)
        self.message_layout.insertWidget(self.message_layout.count() - 1, banner)
        self._scroll_to_bottom()
        return banner

    def stop_all_voice(self):
        for index in range(self.message_layout.count()):
            widget = self.message_layout.itemAt(index).widget()
            if isinstance(widget, VoiceBubble):
                widget.stop()

    # ── 流式气泡：按会话存活，切走时 park、切回时恢复 ────────────────

    def start_streaming(self, sid):
        """开始流式回复，sid = 该回复所属会话。
        若布局上挂着别的会话的气泡 → 先摘下来 park（保留对象，不销毁）；
        切回那个会话时会自动恢复。"""
        if self._active_sid is not None and self._active_sid != sid:
            self._detach_active_bubble()
        if sid in self._stream_bubbles:
            self._drop_bubble(sid)
        b = StreamingBubble()
        self._stream_bubbles[sid] = b
        self._attach_bubble(sid, b)

    def append_stream(self, sid, chunk):
        b = self._stream_bubbles.get(sid)
        if b is None:
            return
        try:
            b.append_text(chunk)
        except RuntimeError:
            self._drop_bubble(sid)
            return
        if sid == self._active_sid:
            self._scroll_to_bottom()

    def stop_streaming(self, sid=None):
        """结束流式。sid 缺省 = 结束当前正在显示的气泡。
        附加着 → 留在布局当最终回复；已 park → 删除（切回该会话时由历史重载显示完整回复）。"""
        if sid is None:
            sid = self._active_sid
        b = self._stream_bubbles.pop(sid, None)
        if b is None:
            return
        try:
            b.stop_cursor()
        except Exception:
            pass
        if sid == self._active_sid:
            self._active_sid = None
        else:
            b.hide()
            self._delete_bubble(b)

    def pop_streaming_bubble(self, sid=None):
        """取走流式气泡并删除，返回已流文字（有图路径用）。"""
        if sid is None:
            sid = self._active_sid
        b = self._stream_bubbles.pop(sid, None)
        if b is None:
            return ""
        text = b._base_text
        try:
            b.stop_cursor()
        except Exception:
            pass
        if sid == self._active_sid:
            for index in range(self.message_layout.count()):
                item = self.message_layout.itemAt(index)
                if item and item.widget() is b:
                    self.message_layout.takeAt(index)
                    b.hide()
                    break
            self._active_sid = None
        else:
            b.hide()
        self._delete_bubble(b)
        return text

    def set_current_session(self, sid):
        """主窗口切换会话后调用：记录当前显示的是哪个会话。"""
        self._current_sid = sid

    def reattach_stream(self, sid):
        """切回 sid 会话并重载完历史后调用：若该会话还有在流的气泡 → 重新挂回布局。"""
        b = self._stream_bubbles.get(sid)
        if b is not None and self._active_sid is None:
            self._attach_bubble(sid, b)

    def new_session(self):
        """清空当前显示（新会话/切会话）。正在流的气泡 → park 保留，切回时恢复。"""
        if self._active_sid is not None:
            self._detach_active_bubble()
        self._clear_messages()
        self.message_layout.addStretch()
        self._add_welcome()

    # ── 流式气泡内部工具 ─────────────────────────────────────────

    def _attach_bubble(self, sid, b):
        b.show()
        self.message_layout.insertWidget(self.message_layout.count() - 1, b)
        self._active_sid = sid
        self._scroll_to_bottom()

    def _detach_active_bubble(self):
        """把当前挂在布局上的流式气泡摘下来（park，保留对象）。
        摘离布局后必须 hide()：否则气泡仍是 scroll_content 的可见子控件，
        会以旧坐标浮在屏幕上，切到任何会话都「残留」。"""
        b = self._stream_bubbles.get(self._active_sid)
        if b is not None:
            for index in range(self.message_layout.count()):
                item = self.message_layout.itemAt(index)
                if item and item.widget() is b:
                    self.message_layout.takeAt(index)
                    b.hide()
                    break
        self._active_sid = None

    def _delete_bubble(self, b):
        try:
            b.deleteLater()
        except Exception:
            pass

    def _drop_bubble(self, sid):
        """从注册表移除并销毁 sid 的气泡（若正挂着则先从布局摘下）。"""
        b = self._stream_bubbles.pop(sid, None)
        if b is None:
            return
        if sid == self._active_sid:
            for index in range(self.message_layout.count()):
                item = self.message_layout.itemAt(index)
                if item and item.widget() is b:
                    self.message_layout.takeAt(index)
                    b.hide()
                    break
            self._active_sid = None
        else:
            b.hide()
        self._delete_bubble(b)

    def filter_messages(self, query):
        query = query.strip().lower()
        for index in range(self.message_layout.count()):
            widget = self.message_layout.itemAt(index).widget()
            if isinstance(widget, MessageBubble):
                widget.setVisible(widget.matches(query))

    def _clear_messages(self):
        # 只清布局里已附加的消息；已 park 的流式气泡不在布局里，不受影响
        while self.message_layout.count():
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _scroll_to_bottom(self):
        QTimer.singleShot(
            50,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ),
        )

    def _trim_messages(self):
        count = sum(
            1
            for index in range(self.message_layout.count())
            if self.message_layout.itemAt(index).widget()
        )
        while count > self.MAX_MESSAGES:
            item = self.message_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
                count -= 1
