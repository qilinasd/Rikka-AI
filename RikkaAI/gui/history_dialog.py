"""
RikkaAI - 历史记录弹窗（会话列表 + 加载 + 删除）
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

import brain.history as history


class HistoryDialog(QDialog):
    """查看所有历史会话，可加载或删除"""

    session_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.resize(480, 480)
        self.setMinimumSize(360, 300)
        self.setStyleSheet("""
            QDialog { background-color: #0f0a18; }
        """)
        self._setup_ui()
        self._load_sessions()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 顶栏 ──
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #120b1a; border-bottom: 1px solid #2a1050;")
        hd = QHBoxLayout(header)
        hd.setContentsMargins(20, 0, 16, 0)

        title = QLabel("📜 历史会话")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        hd.addWidget(title)
        hd.addStretch()

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(60, 26)
        close_btn.setStyleSheet("""
            QPushButton { background-color: transparent; border: 1px solid #2a1050;
                border-radius: 13px; font-size: 11px; color: #7a5aaa; }
            QPushButton:hover { border-color: #5a2a9e; color: #c084fc; }
        """)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        hd.addWidget(close_btn)

        outer.addWidget(header)

        # ── 会话列表 ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background-color: transparent; }
            QScrollBar:vertical { background: #0d0a14; width: 5px; border: none; }
            QScrollBar::handle:vertical { background: #2a1050; border-radius: 2px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: #4a2080; }
        """)

        content = QWidget()
        content.setStyleSheet("background-color: transparent;")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(16, 12, 16, 12)
        self._layout.setSpacing(6)
        self._layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    def _load_sessions(self):
        sessions = history.get_sessions(50)
        if not sessions:
            self._add_empty("还没有历史会话")
            return

        for s in sessions:
            self._add_session_card(s)

    def _add_empty(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: #3a2a4a; font-size: 12px; padding: 30px;")
        label.setAlignment(Qt.AlignCenter)
        self._layout.insertWidget(self._layout.count() - 1, label)

    def _add_session_card(self, session):
        card = QWidget()
        card.setStyleSheet("""
            QWidget { background-color: #140a20; border: 1px solid #1f0d38;
                border-radius: 8px; }
            QWidget:hover { border-color: #3a1a6e; }
        """)
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 10, 10)
        card_layout.setSpacing(8)

        # 左侧信息
        info = QVBoxLayout()
        info.setSpacing(2)

        title = session.get("title", "新会话")
        count = session.get("msg_count", 0)
        updated = session.get("updated_at", "")

        name_label = QLabel(f"💬 {title}")
        name_label.setStyleSheet("color: #e0d0f0; font-size: 12px; font-weight: bold;")
        info.addWidget(name_label)

        meta = f"{count} 条消息 · {updated}"
        meta_label = QLabel(meta)
        meta_label.setStyleSheet("color: #5a3a7a; font-size: 10px;")
        info.addWidget(meta_label)

        card_layout.addLayout(info, 1)

        # 按钮
        btn_enter = QPushButton("进入")
        btn_enter.setFixedSize(50, 26)
        btn_enter.setStyleSheet("""
            QPushButton { background-color: #5a2a9e; border: 1px solid #7a3aba;
                border-radius: 6px; font-size: 11px; font-weight: bold; color: #ffffff; }
            QPushButton:hover { background-color: #7a3aba; }
        """)
        btn_enter.setCursor(Qt.PointingHandCursor)
        sid = session["id"]
        btn_enter.clicked.connect(lambda checked, s=sid: self._enter_session(s))
        card_layout.addWidget(btn_enter)

        btn_del = QPushButton("删除")
        btn_del.setFixedSize(50, 26)
        btn_del.setStyleSheet("""
            QPushButton { background-color: transparent; border: 1px solid #5a1a2a;
                border-radius: 6px; font-size: 11px; color: #a05a6a; }
            QPushButton:hover { background-color: #2a0a10; border-color: #a05a6a; color: #d06a7a; }
        """)
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda checked, s=sid: self._delete_session(s))
        card_layout.addWidget(btn_del)

        self._layout.insertWidget(self._layout.count() - 1, card)

    def _enter_session(self, session_id):
        """进入某个历史会话"""
        self.session_selected.emit(session_id)
        self.accept()

    def _delete_session(self, session_id):
        confirm = QMessageBox.question(
            self, "确认删除", "确定删除这个会话？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            history.delete_session(session_id)
            self._refresh_list()

    def _refresh_list(self):
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._load_sessions()
