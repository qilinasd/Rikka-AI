"""
RikkaAI - 输入面板组件（支持图片发送）
"""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QTextEdit, QFileDialog
from PyQt5.QtCore import Qt, pyqtSignal

class InputPanel(QWidget):
    send_message = pyqtSignal(str)
    send_image = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InputPanel")
        self.setFixedHeight(72)
        self._setup_ui()

    def _tool_btn_style(self):
        return "QPushButton{background:transparent;border:1px solid #2a1050;border-radius:16px;min-width:32px;min-height:32px;max-width:32px;max-height:32px;font-size:14px;color:#7a5aaa}QPushButton:hover{background:#2d1b4e;border-color:#9b59b6;color:#c084fc}"

    def _setup_ui(self):
        inp_layout = QHBoxLayout(self)
        inp_layout.setContentsMargins(12,8,12,8); inp_layout.setSpacing(8)

        self.btn_voice = QPushButton("🎤")
        self.btn_voice.setToolTip("语音输入（即将开放）")
        self.btn_voice.setEnabled(False)
        self.btn_voice.setStyleSheet(self._tool_btn_style())
        inp_layout.addWidget(self.btn_voice)

        self.btn_image = QPushButton("🖼️")
        self.btn_image.setToolTip("发送图片给六花")
        self.btn_image.setStyleSheet(self._tool_btn_style())
        self.btn_image.setCursor(Qt.PointingHandCursor)
        self.btn_image.clicked.connect(self._on_image)
        inp_layout.addWidget(self.btn_image)

        self.input_field = QTextEdit()
        self.input_field.setObjectName("InputField")
        self.input_field.setPlaceholderText("给六花发消息… (Enter发送, Shift+Enter换行)")
        self.input_field.setFixedHeight(36)
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_field.setAcceptRichText(False)
        inp_layout.addWidget(self.input_field, 1)

        self.btn_send = QPushButton("送信")
        self.btn_send.setObjectName("SendButton")
        self.btn_send.setToolTip("邪王真眼 · 释放！")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setFixedHeight(36)
        self.btn_send.setStyleSheet("QPushButton{background:#6a2aba;border:1px solid #8a4ada;border-radius:18px;min-width:80px;max-width:80px;font-size:13px;font-weight:bold;color:#ffd700;padding:4px 8px}QPushButton:hover{background:#8a4ada;border:1px solid #a06aee;color:#ffd700}QPushButton:pressed{background:#4a1a8a}")
        self.btn_send.clicked.connect(self._on_send)
        inp_layout.addWidget(self.btn_send)

        self.input_field.installEventFilter(self)

    def _on_send(self):
        text = self.input_field.toPlainText().strip()
        if not text: return
        self.send_message.emit(text)
        self.input_field.clear()

    def _on_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "图片 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            self.send_image.emit(path)

    def set_input_enabled(self, enabled):
        self.input_field.setEnabled(enabled)
        self.btn_send.setEnabled(enabled)
        if enabled:
            self.input_field.setPlaceholderText("给六花发消息… (Enter发送, Shift+Enter换行)")
            self.input_field.setStyleSheet("")  # 恢复QSS金色
        else:
            self.input_field.setPlaceholderText("六花正在思考中…")
            self.input_field.setStyleSheet("background:#0f0818;border:1px solid #1a0d2e;border-radius:16px;padding:8px 16px;color:#3a2a4a;font-size:13px;")

    def focus_input(self):
        self.input_field.setFocus()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if not (event.modifiers() & Qt.ShiftModifier):
                self._on_send(); event.accept(); return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.input_field and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (event.modifiers() & Qt.ShiftModifier):
                self._on_send(); return True
        return super().eventFilter(obj, event)
