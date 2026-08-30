"""Usage summary and common tools shown on wide home screens."""

import os

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QGridLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from gui.chat_insights import ConversationOverviewPanel
from gui.home.assets import icon


class HomeRightRail(QWidget):
    prompt_requested = pyqtSignal(str)
    summary_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    tools_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeRightRail")
        self.setFixedWidth(268)
        self._setup_ui()
        self.refresh_stats()

    def _card(self, title):
        card = QFrame()
        card.setObjectName("HomeRailCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(11, 10, 11, 10)
        layout.setSpacing(8)
        heading = QLabel(title)
        heading.setObjectName("HomeRailTitle")
        layout.addWidget(heading)
        return card, layout

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.overview = ConversationOverviewPanel()
        layout.addWidget(self.overview)

        tools_card, tools_layout = self._card("常用工具")
        tools_grid = QGridLayout()
        tools_grid.setContentsMargins(0, 0, 0, 0)
        tools_grid.setSpacing(6)
        tools = (
            ("edit", "备忘记录", self.memo_requested.emit),
            ("voice", "语音转写", self.tools_requested.emit),
            ("more", "更多工具", self.tools_requested.emit),
        )
        for index, (icon_name, text, callback) in enumerate(tools):
            button = QToolButton()
            button.setObjectName("HomeRailTool")
            button.setText(text)
            button.setIcon(icon(icon_name))
            button.setIconSize(QSize(18, 18))
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setFixedHeight(55)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(callback)
            tools_grid.addWidget(button, index // 2, index % 2)
        tools_layout.addLayout(tools_grid)
        layout.addWidget(tools_card)

        status_card, status_layout = self._card("六花 AI Pro")
        status = QLabel("邪王真眼稳定运行中\n记忆与陪伴服务已连接")
        status.setObjectName("HomeRailBody")
        status.setWordWrap(True)
        status_layout.addWidget(status)
        layout.addWidget(status_card)
        layout.addStretch()

    def refresh_stats(self):
        self.overview.refresh_data()
