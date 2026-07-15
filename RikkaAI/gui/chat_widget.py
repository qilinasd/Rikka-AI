"""
RikkaAI - 聊天气泡（支持图片 + QQ式日期分隔）
"""
from datetime import datetime
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QLabel, QHBoxLayout, QFrame
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap

class MessageBubble(QFrame):
    BUBBLE_STYLE_USER = "background-color:#1e1040;border:1px solid #3a1a6e;border-radius:12px;border-top-right-radius:2px;padding:10px 14px;color:#ffd700;"
    BUBBLE_STYLE_AI = "background-color:#140a20;border:1px solid #2a1050;border-radius:12px;border-top-left-radius:2px;padding:10px 14px;color:#ffd700;"
    BUBBLE_STYLE_IMAGE = "background:transparent;border:none;"  # 纯图片不显示气泡框

    def __init__(self, text="", is_user=False, image_path=None, parent=None):
        super().__init__(parent)
        self._is_user = is_user
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12,4,12,4)
        container = QVBoxLayout()
        container.setSpacing(4)

        # 纯图片时：不创建文字标签，气泡透明无边框
        is_image_only = (not text and image_path)

        if not is_image_only:
            self.text_label = QLabel(text)
            self.text_label.setWordWrap(True)
            self.text_label.setStyleSheet(self.BUBBLE_STYLE_USER if is_user else self.BUBBLE_STYLE_AI)
            self.text_label.setTextFormat(Qt.PlainText)
            self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            container.addWidget(self.text_label)

        if image_path:
            self.image_label = QLabel()
            pixmap = QPixmap(image_path)
            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(320, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.image_label.setPixmap(scaled)
                self.image_label.setStyleSheet("border-radius:8px;margin:4px 0;")
                self.image_label.setCursor(Qt.PointingHandCursor)
                import os
                fp = image_path
                self.image_label.mousePressEvent = lambda e: os.startfile(fp) if hasattr(os,'startfile') else None
                container.addWidget(self.image_label)

        layout.addLayout(container)

        if is_image_only:
            self.setStyleSheet(self.BUBBLE_STYLE_IMAGE)
        elif is_user:
            self.setStyleSheet(self.BUBBLE_STYLE_USER)
        else:
            self.setStyleSheet(self.BUBBLE_STYLE_AI)

    def append_text(self, chunk):
        self.text_label.setText(self.text_label.text() + chunk)

    def stop_cursor(self):
        pass


class StreamingBubble(MessageBubble):
    def __init__(self, parent=None):
        super().__init__("", is_user=False, parent=parent)
        self._cursor_visible = True
        self._base_text = ""
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._toggle_cursor)
        self._cursor_timer.start(500)

    def _toggle_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.text_label.setText(self._base_text + ("|" if self._cursor_visible else ""))

    def append_text(self, chunk):
        self._base_text += chunk
        self.text_label.setText(self._base_text + "|")

    def stop_cursor(self):
        self._cursor_timer.stop()
        self.text_label.setText(self._base_text)


class DateSeparator(QWidget):
    """QQ 风格的日期分隔条"""
    def __init__(self, dt: datetime, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 8, 0, 8)
        l.setSpacing(8)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("border:none;border-top:1px solid #2a1050;")
        line.setFixedHeight(1)
        l.addWidget(line, 1)
        label = QLabel(self._format_date(dt))
        label.setStyleSheet(
            "color:#5a3a7a;font-size:11px;background:#0f0a18;"
            "padding:2px 12px;border:1px solid #2a1050;border-radius:10px;"
        )
        label.setAlignment(Qt.AlignCenter)
        l.addWidget(label)
        l.addWidget(QFrame(), 1)
        # 让 line 和 label 一样宽
        # 实际上左右两条线各占 1，label 自适应
        l.setStretch(0, 1)
        l.setStretch(2, 1)

    @staticmethod
    def _format_date(dt: datetime) -> str:
        return dt.strftime("%Y年%m月%d日 %H:%M")


class ChatWidget(QWidget):
    MAX_MESSAGES = 200

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatWidget")
        self._streaming_bubble = None
        self._last_msg_date = None  # 最近一条消息的日期
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{border:none;background:transparent}")
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background:transparent;")
        self.message_layout = QVBoxLayout(self.scroll_content)
        self.message_layout.setContentsMargins(12,12,12,12); self.message_layout.setSpacing(4)
        self.message_layout.addStretch()
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)
        self._add_welcome()

    def _add_welcome(self):
        w = "✨ 邪王真眼，觉醒！✨\n\n你好！我是小鸟游六花！\n…那个，请多指教！"
        b = MessageBubble(w, is_user=False)
        self.message_layout.insertWidget(self.message_layout.count()-1, b)

    def add_message(self, text="", is_user=False, image_path=None, created_at=None):
        """添加一条消息，自动插入日期分隔"""
        # 检查日期变化，插入分隔
        now = created_at if created_at else datetime.now()
        msg_date = now.date()
        if self._last_msg_date is not None and msg_date != self._last_msg_date:
            sep = DateSeparator(now)
            self.message_layout.insertWidget(self.message_layout.count()-1, sep)
        elif self._last_msg_date is None:
            sep = DateSeparator(now)
            self.message_layout.insertWidget(self.message_layout.count()-1, sep)
        self._last_msg_date = msg_date

        b = MessageBubble(text, is_user=is_user, image_path=image_path)
        self.message_layout.insertWidget(self.message_layout.count()-1, b)
        self._scroll_to_bottom()
        self._trim_messages()

    def start_streaming(self):
        self._streaming_bubble = StreamingBubble()
        self.message_layout.insertWidget(self.message_layout.count()-1, self._streaming_bubble)
        self._scroll_to_bottom()

    def append_stream(self, chunk):
        if self._streaming_bubble:
            self._streaming_bubble.append_text(chunk)
            self._scroll_to_bottom()

    def stop_streaming(self):
        if self._streaming_bubble:
            self._streaming_bubble.stop_cursor()
            self._streaming_bubble = None

    def pop_streaming_bubble(self):
        """获取流式文本并从布局中移除气泡（用于图片先于文字显示）"""
        text = ""
        if self._streaming_bubble:
            text = self._streaming_bubble._base_text
            self._streaming_bubble.stop_cursor()
            for i in range(self.message_layout.count()):
                item = self.message_layout.itemAt(i)
                if item and item.widget() is self._streaming_bubble:
                    self.message_layout.takeAt(i)
                    break
            self._streaming_bubble.deleteLater()
            self._streaming_bubble = None
        return text

    def new_session(self):
        self._clear_messages()
        self._last_msg_date = None
        self._add_welcome()

    def _clear_messages(self):
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def _scroll_to_bottom(self):
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def _trim_messages(self):
        count = self.message_layout.count() - 1
        while count > self.MAX_MESSAGES:
            item = self.message_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            count -= 1
