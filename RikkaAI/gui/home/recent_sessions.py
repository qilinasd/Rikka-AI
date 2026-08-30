"""Recent conversation list used by the home screen."""

import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

import config
import brain.history as history
from gui.image_utils import circular_pixmap


class SessionRow(QFrame):
    selected = pyqtSignal(int)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeRecentRow")
        self.setCursor(Qt.PointingHandCursor)
        self._session_id = session["id"]
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(9)

        avatar = QLabel()
        avatar.setPixmap(circular_pixmap(os.path.join(config.IMAGES_DIR, "avatar.png"), 30))
        layout.addWidget(avatar)

        text = QVBoxLayout()
        text.setSpacing(1)
        raw_title = session.get("title") or "和六花的新对话"
        title_text = " ".join(str(raw_title).split())
        if len(title_text) > 32:
            title_text = title_text[:32] + "..."
        title = QLabel(title_text)
        title.setObjectName("HomeRecentTitle")
        text.addWidget(title)
        meta = QLabel(f"{session.get('msg_count', 0)} 条消息  ·  继续上次的话题")
        meta.setObjectName("HomeRecentMeta")
        text.addWidget(meta)
        layout.addLayout(text, 1)

        tag = QLabel("AI 聊天")
        tag.setObjectName("HomeRecentTag")
        tag.setAlignment(Qt.AlignCenter)
        layout.addWidget(tag)

        updated = str(session.get("updated_at", ""))
        time_text = updated[11:16] if len(updated) >= 16 else updated
        time = QLabel(time_text)
        time.setObjectName("HomeRecentTime")
        layout.addWidget(time)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self._session_id)
        super().mousePressEvent(event)


class RecentSessionsPanel(QWidget):
    session_selected = pyqtSignal(int)
    history_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeRecentPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("最近对话")
        title.setObjectName("HomeSectionTitle")
        header.addWidget(title)
        header.addStretch()
        view_all = QPushButton("查看全部")
        view_all.setObjectName("HomeTextButton")
        view_all.clicked.connect(self.history_requested.emit)
        header.addWidget(view_all)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setObjectName("HomeRecentScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        self._rows = QVBoxLayout(content)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(5)
        self._rows.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def refresh(self):
        while self._rows.count() > 1:
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        sessions = history.get_sessions(5)
        if not sessions:
            empty = QLabel("还没有对话记录，先和六花说句话吧。")
            empty.setObjectName("HomeEmptyRecent")
            self._rows.insertWidget(0, empty)
            return
        for session in sessions:
            row = SessionRow(session)
            row.selected.connect(self.session_selected.emit)
            self._rows.insertWidget(self._rows.count() - 1, row)
