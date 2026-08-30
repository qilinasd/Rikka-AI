"""Compact status and window controls for the native chat workspace."""

import os

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton

import config
from gui.image_utils import circular_pixmap


class ChatTopBar(QFrame):
    # Shared compact chrome used by chat and all dashboard pages.
    BAR_HEIGHT = 46
    SEARCH_WIDTH = 176
    RIGHT_MARGIN = 8
    TOP_MARGIN = 8

    search_changed = pyqtSignal(str)
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    window_action = pyqtSignal(str)
    window_drag = pyqtSignal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatTopBar")
        self.setFixedHeight(self.BAR_HEIGHT)
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 6, 4)
        layout.setSpacing(4)

        figma = os.path.join(config.ASSETS_DIR, "figma", "icons")

        self.search = QLineEdit()
        self.search.setObjectName("ChatGlobalSearch")
        self.search.setPlaceholderText("搜索")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(QIcon(os.path.join(figma, "search.svg")), QLineEdit.LeadingPosition)
        self.search.setFixedWidth(self.SEARCH_WIDTH)
        self.search.textChanged.connect(self.search_changed.emit)
        layout.addWidget(self.search)

        for icon_name, tooltip, signal in (
            ("top_notification.svg", "备忘录", self.memo_requested),
            ("ai.svg", "工具", self.tools_requested),
            ("top_settings.svg", "设置", self.settings_requested),
        ):
            button = self._icon_button(os.path.join(figma, icon_name), tooltip)
            button.clicked.connect(signal.emit)
            layout.addWidget(button)

        divider = QFrame()
        divider.setObjectName("ChatToolbarDivider")
        divider.setFixedSize(1, 18)
        layout.addWidget(divider)

        for icon_name, tooltip, action in (
            ("top_minimize.svg", "最小化", "minimize"),
            ("top_maximize.svg", "最大化 / 还原", "maximize"),
            ("top_close.svg", "关闭", "close"),
        ):
            button = QPushButton()
            button.setObjectName("ChatWindowButton")
            button.setProperty("danger", action == "close")
            button.setIcon(QIcon(os.path.join(figma, icon_name)))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(26, 30)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(tooltip)
            button.clicked.connect(
                lambda _checked=False, value=action: self.window_action.emit(value)
            )
            layout.addWidget(button)

        self.avatar = QLabel()
        self.avatar.setObjectName("ChatTopAvatar")
        self.avatar.setFixedSize(28, 28)
        self.avatar.setPixmap(circular_pixmap(os.path.join(config.IMAGES_DIR, "avatar.png"), 28))
        layout.addWidget(self.avatar)

        self.status = QLabel("六花")
        self.status.setObjectName("ChatTopStatus")
        layout.addWidget(self.status)

    def set_identity_visible(self, visible):
        """Show or hide the optional avatar/name cluster in the title bar."""
        visible = bool(visible)
        self.avatar.setVisible(visible)
        self.status.setVisible(visible)

    def _icon_button(self, icon_path, tooltip):
        button = QPushButton()
        button.setObjectName("ChatTopAction")
        button.setIcon(QIcon(icon_path))
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(32, 32)
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        return button

    def clear_search(self):
        self.search.clear()

    def set_connection_state(self, state):
        if state == "online":
            self.status.setToolTip("QQ 桥接已连接")
        elif state == "connecting":
            self.status.setToolTip("QQ 桥接连接中")
        else:
            self.status.setToolTip("QQ 桥接未连接")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window_drag.emit(event.globalX(), event.globalY(), "start")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.window_drag.emit(event.globalX(), event.globalY(), "move")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window_drag.emit(event.globalX(), event.globalY(), "end")
        super().mouseReleaseEvent(event)
