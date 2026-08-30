"""Quick-start action cards."""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QToolButton, QWidget

from gui.home.assets import icon


class QuickActions(QWidget):
    focus_chat_requested = pyqtSignal()
    prompt_requested = pyqtSignal(str)
    summary_requested = pyqtSignal()
    tools_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeQuickActions")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)

        actions = (
            ("chat", "AI 聊天\n与六花开始对话", self.focus_chat_requested.emit),
            ("more", "更多功能\n探索工具能力", self.tools_requested.emit),
        )
        for icon_name, text, callback in actions:
            button = QToolButton()
            button.setObjectName("HomeActionCard")
            button.setText(text)
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(88)
            button.clicked.connect(callback)
            layout.addWidget(button, 1)
