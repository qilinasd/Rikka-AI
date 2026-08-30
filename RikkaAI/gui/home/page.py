"""Composes the modular RikkaAI home screen."""

from datetime import datetime

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QStackedLayout, QVBoxLayout, QWidget

from gui.home.assets import image_path
from gui.home.background import HomeBackground
from gui.home.composer import HomeComposer
from gui.home.quick_actions import QuickActions
from gui.home.recent_sessions import RecentSessionsPanel
from gui.home.right_rail import HomeRightRail


class HomeWidget(QWidget):
    start_chat = pyqtSignal(str)
    chat_requested = pyqtSignal()
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    summary_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    session_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeWidget")
        self._setup_ui()
        self.refresh_recent()

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        canvas = QFrame()
        canvas.setObjectName("HomeCanvas")
        canvas_stack = QStackedLayout(canvas)
        canvas_stack.setContentsMargins(0, 0, 0, 0)
        canvas_stack.setStackingMode(QStackedLayout.StackAll)

        self.background = HomeBackground(image_path("home_background.png"))
        canvas_stack.addWidget(self.background)
        shade = QFrame()
        shade.setObjectName("HomeBackdropShade")
        canvas_stack.addWidget(shade)

        foreground = QWidget()
        foreground.setObjectName("HomeForeground")
        foreground_layout = QHBoxLayout(foreground)
        foreground_layout.setContentsMargins(218, 20, 14, 18)
        foreground_layout.setSpacing(12)

        content = QWidget()
        content.setObjectName("HomeContent")
        content.setMaximumWidth(650)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        greeting = QLabel(self._greeting_text())
        greeting.setObjectName("HomeGreeting")
        content_layout.addWidget(greeting)
        subtitle = QLabel("今天想和我聊些什么呢？")
        subtitle.setObjectName("HomeSubtitle")
        content_layout.addWidget(subtitle)

        self.composer = HomeComposer()
        self.composer.submitted.connect(self.start_chat.emit)
        self.composer.tools_requested.connect(self.tools_requested.emit)
        content_layout.addWidget(self.composer)

        section = QLabel("快速开始")
        section.setObjectName("HomeSectionTitle")
        content_layout.addWidget(section)
        quick_actions = QuickActions()
        quick_actions.focus_chat_requested.connect(self.composer.focus_input)
        quick_actions.prompt_requested.connect(self.composer.prefill)
        quick_actions.summary_requested.connect(self.summary_requested.emit)
        quick_actions.tools_requested.connect(self.tools_requested.emit)
        content_layout.addWidget(quick_actions)

        self.recent_sessions = RecentSessionsPanel()
        self.recent_sessions.session_selected.connect(self.session_selected.emit)
        self.recent_sessions.history_requested.connect(self.history_requested.emit)
        content_layout.addWidget(self.recent_sessions, 1)
        foreground_layout.addWidget(content, 1)
        foreground_layout.addStretch(1)

        self.right_rail = HomeRightRail()
        self.right_rail.prompt_requested.connect(self.composer.prefill)
        self.right_rail.summary_requested.connect(self.summary_requested.emit)
        self.right_rail.memo_requested.connect(self.memo_requested.emit)
        self.right_rail.tools_requested.connect(self.tools_requested.emit)
        foreground_layout.addWidget(self.right_rail)

        canvas_stack.addWidget(foreground)
        canvas_stack.setCurrentWidget(foreground)
        root.addWidget(canvas, 1)

    def _greeting_text(self):
        hour = datetime.now().hour
        if hour < 6:
            return "夜深了，主人"
        if hour < 11:
            return "早安，主人"
        if hour < 14:
            return "午安，主人"
        if hour < 19:
            return "下午好，主人"
        return "晚上好，主人"

    def refresh_recent(self):
        self.recent_sessions.refresh()
        self.right_rail.refresh_stats()

    def set_appearance_background(self, pixmap, wash):
        home_wash = wash
        if wash is not None:
            from PyQt5.QtGui import QColor
            home_wash = QColor(wash)
            home_wash.setAlpha(min(92, home_wash.alpha()))
        self.background.set_background(pixmap, home_wash)

    def resizeEvent(self, event):
        self.right_rail.setVisible(self.width() >= 1120)
        super().resizeEvent(event)
