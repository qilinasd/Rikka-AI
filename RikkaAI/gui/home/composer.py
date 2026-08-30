"""Greeting composer and mode shortcuts."""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout

from gui.home.assets import icon


class HomeComposer(QFrame):
    submitted = pyqtSignal(str)
    tools_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeComposer")
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.input_field = QTextEdit()
        self.input_field.setObjectName("HomeInput")
        self.input_field.setPlaceholderText("输入消息...")
        self.input_field.setAcceptRichText(False)
        self.input_field.setFixedHeight(52)
        self.input_field.installEventFilter(self)
        input_row.addWidget(self.input_field, 1)

        send = QPushButton()
        send.setObjectName("HomeSendButton")
        send.setIcon(icon("send", figma=True))
        send.setIconSize(QSize(19, 19))
        send.setFixedSize(44, 44)
        send.setToolTip("开始对话")
        send.setCursor(Qt.PointingHandCursor)
        send.clicked.connect(self.submit)
        input_row.addWidget(send, 0, Qt.AlignBottom)
        layout.addLayout(input_row)

        modes = QHBoxLayout()
        modes.setSpacing(6)
        mode_items = (
            ("chat", "AI 聊天", self.focus_input),
            ("more", "更多", self.tools_requested.emit),
        )
        for icon_name, text, callback in mode_items:
            button = QPushButton(text)
            button.setObjectName("HomeModeButton")
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(14, 14))
            button.setFixedHeight(28)
            button.clicked.connect(callback)
            modes.addWidget(button)
        modes.addStretch()
        layout.addLayout(modes)

    def focus_input(self):
        self.input_field.setFocus()

    def prefill(self, prefix):
        if not self.input_field.toPlainText().strip():
            self.input_field.setPlainText(prefix)
        self.input_field.moveCursor(QTextCursor.End)
        self.input_field.setFocus()

    def submit(self):
        text = self.input_field.toPlainText().strip()
        if not text:
            self.focus_input()
            return
        self.input_field.clear()
        self.submitted.emit(text)

    def eventFilter(self, obj, event):
        if obj is self.input_field and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
                self.submit()
                return True
        return super().eventFilter(obj, event)
