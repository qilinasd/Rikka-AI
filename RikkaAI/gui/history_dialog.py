"""
RikkaAI history dialog.
"""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget

import brain.history as history
import config
from gui import dialog_theme


ACCENT = "#b78eff"
ACCENT_DARK = "#8d69e0"
PINK = "#ffb8cf"
BORDER = "#eadff9"
TEXT = "#544978"
TEXT_MUTED = "#8e83ab"
SURFACE = "rgba(255,255,255,0.86)"
SURFACE_SOFT = "rgba(255,255,255,0.56)"
FIELD = "rgba(255,255,255,0.90)"


class HistoryDialog(QDialog):
    session_selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("历史记录")
        self.resize(760, 620)
        self.setMinimumSize(620, 520)
        self._apply_theme()
        self._setup_ui()
        self._load_sessions()

    def _apply_theme(self):
        global ACCENT, ACCENT_DARK, PINK, BORDER, TEXT, TEXT_MUTED, SURFACE, SURFACE_SOFT, FIELD
        c = dialog_theme.colors()
        ACCENT, ACCENT_DARK, PINK, BORDER, TEXT, TEXT_MUTED = c["accent"], c["accent"], c["accent"], c["border_accent"], c["text"], c["muted"]
        SURFACE, SURFACE_SOFT, FIELD = c["surface"], c["surface_soft"], c["field"]
        self.setStyleSheet(
            f"""
            QDialog {{
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c['surface_soft']}, stop:0.5 {c['surface']}, stop:1 {c['surface_soft']});
            }}
            QLabel {{ color:{TEXT}; }}
            QScrollArea {{ border:none; background:transparent; }}
            QScrollBar:vertical {{
                background:transparent;
                width:8px;
                border:none;
                margin:6px 2px;
            }}
            QScrollBar::handle:vertical {{
                background:{c['border_accent']};
                border-radius:4px;
                min-height:42px;
            }}
            QScrollBar::handle:vertical:hover {{
                background:{c['accent']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:transparent;
                border:none;
            }}
            """
        )

    def _shell(self):
        shell = QWidget()
        shell.setObjectName("DialogShell")
        shell.setStyleSheet(
            f"QWidget#DialogShell{{background:{SURFACE};border:1px solid {BORDER};border-radius:22px;}}"
        )
        return shell

    def _secondary_button(self, text):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background:{FIELD};
                border:1px solid {BORDER};
                border-radius:16px;
                color:{TEXT_MUTED};
                font-size:12px;
                padding:0 16px;
            }}
            QPushButton:hover {{
                border-color:{BORDER};
                color:{ACCENT_DARK};
                background:{SURFACE};
            }}
            """
        )
        return button

    def _primary_button(self, text):
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"""
            QPushButton {{
                background:{ACCENT};
                border:none;
                border-radius:14px;
                color:#ffffff;
                font-size:12px;
                font-weight:700;
                padding:0 14px;
            }}
            QPushButton:hover {{
                background:{ACCENT};
            }}
            """
        )
        return button

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        header = self._shell()
        header.setFixedHeight(82)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setPixmap(
            QPixmap(
                os.path.join(
                    config.ASSETS_DIR, "images", "branding", "rikka_mark.png"
                )
            ).scaled(38, 38, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        badge.setStyleSheet(
            "background:transparent;border:none;"
        )
        header_layout.addWidget(badge)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)
        title = QLabel("历史记录")
        title.setStyleSheet(f"font-size:24px;font-weight:700;color:{ACCENT_DARK};")
        title_block.addWidget(title)
        subtitle = QLabel("快速回到旧会话，继续上次和六花聊到的话题。")
        subtitle.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        title_block.addWidget(subtitle)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        close_btn = self._secondary_button("关闭")
        close_btn.setFixedSize(82, 36)
        close_btn.clicked.connect(self.accept)
        header_layout.addWidget(close_btn)
        outer.addWidget(header)

        body = self._shell()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 16, 16, 16)
        body_layout.setSpacing(12)

        hint = QLabel("最近的 50 个会话会展示在这里，点击“进入”可直接切换。")
        hint.setStyleSheet(f"font-size:12px;color:{TEXT_MUTED};")
        body_layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._layout.addStretch()
        scroll.setWidget(content)
        body_layout.addWidget(scroll, 1)
        outer.addWidget(body, 1)

    def _load_sessions(self):
        sessions = history.get_sessions(50)
        if not sessions:
            self._add_empty("还没有历史会话")
            return
        for session in sessions:
            self._add_session_card(session)

    def _add_empty(self, text):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(f"padding:36px;font-size:13px;color:{TEXT_MUTED};")
        self._layout.insertWidget(self._layout.count() - 1, label)

    def _add_session_card(self, session):
        card = QWidget()
        card.setObjectName("HistorySessionCard")
        card.setStyleSheet(
            f"QWidget#HistorySessionCard{{background:{SURFACE_SOFT};border:1px solid {BORDER};border-radius:14px;}}"
        )
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        dot = QLabel("✦")
        dot.setAlignment(Qt.AlignCenter)
        dot.setFixedSize(34, 34)
        dot.setStyleSheet(
            f"background:{FIELD};border:1px solid {BORDER};border-radius:17px;color:{PINK};font-size:15px;font-weight:700;"
        )
        layout.addWidget(dot)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(4)
        title = QLabel(session.get("title", "新会话"))
        title.setStyleSheet(f"font-size:14px;font-weight:700;color:{TEXT};")
        info.addWidget(title)
        meta = QLabel(f"{session.get('msg_count', 0)} 条消息  ·  {session.get('updated_at', '')}")
        meta.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        info.addWidget(meta)
        layout.addLayout(info, 1)

        sid = session["id"]
        enter_btn = self._primary_button("进入")
        enter_btn.setFixedSize(78, 36)
        enter_btn.clicked.connect(lambda checked=False, s=sid: self._enter_session(s))
        layout.addWidget(enter_btn)

        delete_btn = self._secondary_button("删除")
        delete_btn.setFixedSize(74, 36)
        delete_btn.clicked.connect(lambda checked=False, s=sid: self._delete_session(s))
        layout.addWidget(delete_btn)

        self._layout.insertWidget(self._layout.count() - 1, card)

    def _enter_session(self, session_id):
        self.session_selected.emit(session_id)
        self.accept()

    def _delete_session(self, session_id):
        if QMessageBox.question(
            self,
            "确认删除",
            "确定删除这个会话吗？",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            history.delete_session(session_id)
            self._refresh_list()

    def _refresh_list(self):
        while self._layout.count() > 1:
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._load_sessions()
