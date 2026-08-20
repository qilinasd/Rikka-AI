"""Floating message composer for the desktop chat workspace."""

import os

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config


class InputPanel(QWidget):
    send_message = pyqtSignal(str)
    send_image = pyqtSignal(str)
    open_tools = pyqtSignal()
    open_knowledge = pyqtSignal()
    qq_bridge_requested = pyqtSignal()
    voice_toggle_requested = pyqtSignal()
    gptsovits_service_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("InputPanel")
        self.setFixedHeight(204)
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 0, 16, 16)
        root.setSpacing(0)

        composer = QFrame()
        composer.setObjectName("InputComposer")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(18, 16, 18, 16)
        composer_layout.setSpacing(12)

        self.input_field = QTextEdit()
        self.input_field.setObjectName("InputField")
        self.input_field.setPlaceholderText("输入消息，按回车发送，按 Shift+回车换行")
        self.input_field.setFixedHeight(88)
        self.input_field.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input_field.setAcceptRichText(False)
        composer_layout.addWidget(self.input_field)

        tool_tray = QFrame(composer)
        tool_tray.setObjectName("InputToolTray")
        toolbar = QHBoxLayout(tool_tray)
        toolbar.setContentsMargins(10, 7, 10, 7)
        toolbar.setSpacing(7)

        figma_icons = os.path.join(config.ASSETS_DIR, "figma", "icons")
        outline_icons = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")

        self.btn_image = self._make_tool_button(
            "图片",
            os.path.join(figma_icons, "image.svg"),
            "发送图片给六花",
        )
        self.btn_image.clicked.connect(self._on_image)
        toolbar.addWidget(self.btn_image)

        self.btn_attachment = self._make_tool_button(
            "附件",
            os.path.join(outline_icons, "upload.svg"),
            "添加附件",
        )
        self.btn_attachment.setObjectName("AttachmentToolButton")
        self.btn_attachment.clicked.connect(self._on_attachment)
        toolbar.addWidget(self.btn_attachment)

        knowledge_button = self._make_tool_button(
            "知识库", os.path.join(outline_icons, "knowledge.svg"), "打开知识库"
        )
        knowledge_button.clicked.connect(self.open_knowledge.emit)
        toolbar.addWidget(knowledge_button)

        self.btn_qq = self._make_tool_button(
            "QQ 桥接",
            os.path.join(outline_icons, "message.svg"),
            "连接 QQ 桥接",
        )
        self.btn_qq.setObjectName("QQBridgeToolButton")
        self.btn_qq.setProperty("state", "offline")
        self.btn_qq.clicked.connect(self.qq_bridge_requested.emit)
        toolbar.addWidget(self.btn_qq)

        self.btn_voice = self._make_tool_button(
            "语音",
            os.path.join(outline_icons, "voice.svg"),
            "开启/关闭六花语音（由六花自己决定何时开口）",
        )
        self.btn_voice.setObjectName("VoiceToolButton")
        self.btn_voice.setProperty("state", "on" if config.VOICE_ENABLED else "off")
        self.btn_voice.clicked.connect(self.voice_toggle_requested.emit)
        toolbar.addWidget(self.btn_voice)

        self.btn_svc = self._make_tool_button(
            "语音服务",
            os.path.join(outline_icons, "music.svg"),
            "启动 GPT-SoVITS 语音服务（六花音色合成，首次加载需数十秒）",
        )
        self.btn_svc.setObjectName("VoiceSvcButton")
        self.btn_svc.setProperty("state", "stopped")
        self.btn_svc.clicked.connect(self.gptsovits_service_requested.emit)
        toolbar.addWidget(self.btn_svc)

        stop_button = self._make_tool_button(
            "停止",
            os.path.join(outline_icons, "stop.svg"),
            "叫停六花当前动作（回复/语音/偷看）",
        )
        stop_button.clicked.connect(self.stop_requested.emit)
        toolbar.addWidget(stop_button)

        toolbar.addStretch()
        self.btn_send = QPushButton()
        self.btn_send.setObjectName("SendButton")
        self.btn_send.setIcon(QIcon(os.path.join(figma_icons, "send.svg")))
        self.btn_send.setIconSize(QSize(23, 23))
        self.btn_send.setToolTip("发送给六花")
        self.btn_send.setCursor(Qt.PointingHandCursor)
        self.btn_send.setFixedSize(58, 52)
        self.btn_send.clicked.connect(self._on_send)
        toolbar.addWidget(self.btn_send)
        composer_layout.addWidget(tool_tray)
        root.addWidget(composer)

        self.input_field.installEventFilter(self)

    def _make_tool_button(self, text, icon_path, tooltip):
        button = QPushButton(text)
        button.setObjectName("InputToolButton")
        button.setIcon(QIcon(icon_path))
        button.setIconSize(QSize(16, 16))
        button.setToolTip(tooltip)
        button.setCursor(Qt.PointingHandCursor)
        button.setFixedHeight(38)
        # Keep the icon-plus-Chinese-label treatment legible at compact widths.
        min_widths = {
            "图片": 70,
            "附件": 70,
            "知识库": 82,
            "QQ 桥接": 96,
            "语音": 70,
            "语音服务": 92,
            "停止": 70,
        }
        width = min_widths.get(text, 66)
        button.setProperty("composerWidth", str(width))
        button.setFixedWidth(width)
        if text == "语音服务":
            button.setProperty("composerWidth", "92")
        return button

    def _on_send(self):
        text = self.input_field.toPlainText().strip()
        if not text:
            return
        self.send_message.emit(text)
        self.input_field.clear()

    def _on_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif)",
        )
        if path:
            self.send_image.emit(path)

    def _on_attachment(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择附件",
            "",
            "所有文件 (*.*)",
        )
        if not path:
            return
        if os.path.splitext(path)[1].lower() in {
            ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"
        }:
            self.send_image.emit(path)
            return
        # 非图片附件先填入编辑区，用户确认内容后仍可按回车发送。
        self.input_field.setPlainText(f"附件：{os.path.basename(path)}\n路径：{path}")
        self.focus_input()

    def set_input_enabled(self, enabled):
        self.input_field.setEnabled(enabled)
        self.btn_send.setEnabled(enabled)
        self.btn_image.setEnabled(enabled)
        self.btn_attachment.setEnabled(enabled)
        self.input_field.setPlaceholderText(
            "输入消息，按回车发送，按 Shift+回车换行"
            if enabled
            else "六花正在思考中..."
        )

    def set_qq_state(self, state, tooltip):
        self.btn_qq.setProperty("state", state)
        self.btn_qq.setToolTip(tooltip)
        self.btn_qq.style().unpolish(self.btn_qq)
        self.btn_qq.style().polish(self.btn_qq)
        self.btn_qq.update()

    def set_voice_state(self, enabled, tooltip=None):
        self.btn_voice.setProperty("state", "on" if enabled else "off")
        self.btn_voice.setToolTip(tooltip or ("关闭六花语音" if enabled else "开启六花语音"))
        self.btn_voice.style().unpolish(self.btn_voice)
        self.btn_voice.style().polish(self.btn_voice)
        self.btn_voice.update()

    def set_service_state(self, state, tooltip=None):
        """GPT-SoVITS 服务按钮状态：stopped/starting/ready/error。"""
        self.btn_svc.setProperty("state", state)
        tips = {
            "stopped": "启动 GPT-SoVITS 语音服务",
            "starting": "GPT-SoVITS 语音服务加载中…",
            "ready": "GPT-SoVITS 语音服务正在运行",
            "error": "GPT-SoVITS 启动失败，点击重试",
        }
        self.btn_svc.setToolTip(tooltip or tips.get(state, ""))
        self.btn_svc.style().unpolish(self.btn_svc)
        self.btn_svc.style().polish(self.btn_svc)
        self.btn_svc.update()

    def focus_input(self):
        self.input_field.setFocus()

    def eventFilter(self, obj, event):
        if obj is self.input_field and event.type() == event.KeyPress:
            if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not (
                event.modifiers() & Qt.ShiftModifier
            ):
                self._on_send()
                return True
        return super().eventFilter(obj, event)
