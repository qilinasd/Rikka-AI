"""Persistent navigation and conversation list for the desktop workspace.

The 190px navigation is owned by the main window.  Home and chat only swap
the content to its right, while chat adds its own session-list column.
"""

import os

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import config
from brain import history
from gui.image_utils import circular_pixmap
from gui.settings_assets import settings_asset_icon, tinted_settings_asset_icon


class SessionItemWidget(QWidget):
    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setObjectName("SessionItemCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 9, 8, 9)
        layout.setSpacing(9)

        avatar = QLabel()
        avatar.setObjectName("SessionAvatar")
        avatar.setFixedSize(36, 36)
        avatar.setPixmap(circular_pixmap(os.path.join(config.IMAGES_DIR, "avatar.png"), 36))
        layout.addWidget(avatar)

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)
        title = QLabel(session.get("title") or "新会话")
        title.setObjectName("SessionTitle")
        title.setToolTip(title.text())
        copy.addWidget(title)
        count = int(session.get("msg_count", 0))
        summary = QLabel(f"与六花的对话 · {count} 条消息")
        summary.setObjectName("SessionSummary")
        copy.addWidget(summary)
        layout.addLayout(copy, 1)

        updated = str(session.get("updated_at", ""))
        timestamp = QLabel(updated[5:10] if len(updated) >= 10 else "")
        timestamp.setObjectName("SessionTime")
        layout.addWidget(timestamp, 0, Qt.AlignTop)


class NavSidebar(QWidget):
    """统一尺寸的窄导航栏（190px），与首页侧栏保持一致。"""

    home_requested = pyqtSignal()
    chat_requested = pyqtSignal()
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    summary_requested = pyqtSignal()
    diary_requested = pyqtSignal()
    surf_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent=None, active_section="chat"):
        super().__init__(parent)
        self.setObjectName("ChatNavSidebar")
        self.setFixedWidth(190)
        self._active_section = active_section
        self._nav_buttons = {}
        self._appearance = None
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 16, 10, 14)
        root.setSpacing(4)

        brand = QHBoxLayout()
        brand.setSpacing(7)
        mark = QLabel()
        mark.setFixedSize(32, 32)
        logo_path = os.path.join(
            config.ASSETS_DIR, "images", "branding", "rikka_mark.png"
        )
        mark.setPixmap(QIcon(logo_path).pixmap(30, 30))
        brand.addWidget(mark)
        name = QLabel("RikkaAI")
        name.setObjectName("ChatBrand")
        brand.addWidget(name)
        brand.addStretch()
        root.addLayout(brand)
        root.addSpacing(14)

        nav_items = [
            ("home", "首页", self.home_requested),
            ("chat", "对话", self.chat_requested),
            ("knowledge", "知识库", self.summary_requested),
            ("music", "AI 音乐", self.tools_requested),
            ("diary", "日记", self.diary_requested),
            ("memory", "记忆", self.memo_requested),
            ("history", "历史记录", self.history_requested),
            ("workflow", "冲浪记录", self.surf_requested),
            ("settings", "设置", self.settings_requested),
        ]
        for icon_name, text, signal in nav_items:
            button = QPushButton(text)
            button.setObjectName("ChatNavButton")
            button.setProperty("active", icon_name == self._active_section)
            button.setIcon(settings_asset_icon(f"sidebar.{icon_name}"))
            button.setIconSize(QSize(17, 17))
            button.setFixedHeight(40)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, section=icon_name, target=signal:
                self._activate_and_emit(section, target)
            )
            self._nav_buttons[icon_name] = button
            root.addWidget(button)
        root.addStretch()

    def _activate_and_emit(self, section, signal):
        self.set_active_section(section)
        signal.emit()

    def set_active_section(self, section):
        self._active_section = section
        for name, button in self._nav_buttons.items():
            button.setProperty("active", name == section)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self._refresh_icons()

    def apply_appearance(self, appearance):
        self._appearance = appearance
        self._refresh_icons()

    def _refresh_icons(self):
        if self._appearance is None:
            return
        for name, button in self._nav_buttons.items():
            color = (
                self._appearance.accent_hover
                if name == self._active_section else self._appearance.accent
            )
            button.setIcon(tinted_settings_asset_icon(f"sidebar.{name}", color))


class SessionListPanel(QWidget):
    """独立的会话列表列。"""

    new_conversation_requested = pyqtSignal()
    session_selected = pyqtSignal(int)
    history_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatSessionPanel")
        self.setMinimumWidth(200)
        self._sessions = []
        self._active_session_id = 0
        self._setup_ui()
        self.refresh_sessions()

    def _setup_ui(self):
        session_layout = QVBoxLayout(self)
        session_layout.setContentsMargins(10, 14, 10, 12)
        session_layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setObjectName("SessionSearch")
        self._search.setPlaceholderText("搜索对话")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._render_sessions)
        session_layout.addWidget(self._search)

        outline = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")
        new_button = QPushButton("新建对话")
        new_button.setObjectName("NewSessionButton")
        new_button.setIcon(QIcon(os.path.join(outline, "plus.svg")))
        new_button.setIconSize(QSize(16, 16))
        new_button.setFixedHeight(38)
        new_button.setCursor(Qt.PointingHandCursor)
        new_button.clicked.connect(self.new_conversation_requested.emit)
        session_layout.addWidget(new_button)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        for index, text in enumerate(("全部", "置顶", "最近")):
            chip = QPushButton(text)
            chip.setObjectName("SessionFilter")
            chip.setProperty("active", index == 0)
            chip.setFixedHeight(27)
            filter_row.addWidget(chip)
        filter_row.addStretch()
        session_layout.addLayout(filter_row)

        self._list = QListWidget()
        self._list.setObjectName("SessionList")
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._select_session)
        session_layout.addWidget(self._list, 1)

    def refresh_sessions(self, active_session_id=None):
        if active_session_id is not None:
            self._active_session_id = int(active_session_id or 0)
        self._sessions = history.get_sessions(100)
        self._render_sessions()

    def _render_sessions(self):
        query = self._search.text().strip().lower()
        self._list.clear()
        for session in self._sessions:
            title = str(session.get("title") or "新会话")
            if query and query not in title.lower():
                continue
            item = QListWidgetItem()
            item.setData(Qt.UserRole, int(session["id"]))
            item.setSizeHint(QSize(0, 68))
            self._list.addItem(item)
            self._list.setItemWidget(item, SessionItemWidget(session))
            if int(session["id"]) == self._active_session_id:
                self._list.setCurrentItem(item)

    def _select_session(self, item):
        session_id = int(item.data(Qt.UserRole))
        if session_id > 0 and session_id != self._active_session_id:
            self._active_session_id = session_id
            self.session_selected.emit(session_id)


class CharacterWidget(QWidget):
    """兼容容器：导航 + 会话列表并排（旧版布局使用）。"""

    home_requested = pyqtSignal()
    chat_requested = pyqtSignal()
    new_conversation_requested = pyqtSignal()
    session_selected = pyqtSignal(int)
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    summary_requested = pyqtSignal()
    diary_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CharacterPanel")
        self.setFixedWidth(430)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 0, 8)
        layout.setSpacing(8)
        self.nav = NavSidebar(self)
        self.panel = SessionListPanel(self)
        layout.addWidget(self.nav)
        layout.addWidget(self.panel, 1)

        self.nav.home_requested.connect(self.home_requested.emit)
        self.nav.chat_requested.connect(self.chat_requested.emit)
        self.nav.history_requested.connect(self.history_requested.emit)
        self.nav.memo_requested.connect(self.memo_requested.emit)
        self.nav.summary_requested.connect(self.summary_requested.emit)
        self.nav.diary_requested.connect(self.diary_requested.emit)
        self.nav.tools_requested.connect(self.tools_requested.emit)
        self.nav.settings_requested.connect(self.settings_requested.emit)
        self.panel.new_conversation_requested.connect(self.new_conversation_requested.emit)
        self.panel.session_selected.connect(self.session_selected.emit)
        self.panel.history_requested.connect(self.history_requested.emit)

    def set_active_section(self, section):
        self.nav.set_active_section(section)

    def refresh_sessions(self, active_session_id=None):
        self.panel.refresh_sessions(active_session_id)
