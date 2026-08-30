"""
RikkaAI memo dialog.
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

import config
from gui import dialog_theme


ACCENT_DARK = "#8d69e0"
BORDER = "#eadff9"
TEXT = "#544978"
TEXT_MUTED = "#8e83ab"
SURFACE = "rgba(255,255,255,0.86)"
FIELD = "rgba(255,255,255,0.90)"


class MemoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("备忘录")
        self.resize(760, 580)
        self.setMinimumSize(620, 460)
        self._apply_theme()
        self._setup_ui()
        self._load_memo()

    def _apply_theme(self):
        global ACCENT_DARK, BORDER, TEXT, TEXT_MUTED, SURFACE, FIELD
        c = dialog_theme.colors()
        ACCENT_DARK, BORDER, TEXT, TEXT_MUTED = c["accent"], c["border_accent"], c["text"], c["muted"]
        SURFACE, FIELD = c["surface"], c["field"]
        self.setStyleSheet(
            f"""
            QDialog {{
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c['surface_soft']}, stop:0.45 {c['surface']}, stop:1 {c['surface_soft']});
            }}
            QTextEdit {{
                background:{FIELD};
                border:1px solid {BORDER};
                border-radius:20px;
                padding:16px;
                color:{TEXT};
                font-size:13px;
                font-family:'Microsoft YaHei', 'SimHei', monospace;
                line-height:1.8;
            }}
            """
        )

    def _shell(self):
        shell = QWidget()
        shell.setObjectName("DialogShell")
        shell.setStyleSheet(
            f"QWidget#DialogShell{{background:{SURFACE};border:1px solid {BORDER};"
            "border-top:1px solid rgba(255,255,255,0.95);border-radius:22px;}"
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

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        header = self._shell()
        header.setFixedHeight(82)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        badge = QLabel("✎")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(36, 36)
        badge.setStyleSheet(
            f"background:{FIELD};border:1px solid {BORDER};border-radius:18px;color:{ACCENT_DARK};font-size:18px;font-weight:700;"
        )
        header_layout.addWidget(badge)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)
        title = QLabel("备忘录")
        title.setStyleSheet(f"font-size:24px;font-weight:700;color:{ACCENT_DARK};")
        title_block.addWidget(title)
        subtitle = QLabel("这里记录六花和你共同保留下来的长期信息。")
        subtitle.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        title_block.addWidget(subtitle)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        close_btn = self._secondary_button("关闭")
        close_btn.setFixedSize(82, 36)
        close_btn.clicked.connect(self.accept)
        header_layout.addWidget(close_btn)
        outer.addWidget(header)

        content_shell = self._shell()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        note = QLabel("六花会把值得长期记住的事写在这里，比如喜好、约定和重要状态。")
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:12px;color:{TEXT_MUTED};line-height:1.6;")
        content_layout.addWidget(note)

        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        content_layout.addWidget(self._viewer, 1)
        outer.addWidget(content_shell, 1)

    def _load_memo(self):
        memo_path = os.path.join(config.ROOT_DIR, "persona", "memo.md")
        if os.path.exists(memo_path):
            with open(memo_path, "r", encoding="utf-8") as f:
                self._viewer.setPlainText(f.read())
        else:
            self._viewer.setPlainText("(备忘录文件不存在)")
