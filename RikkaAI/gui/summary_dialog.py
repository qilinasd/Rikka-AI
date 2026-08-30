"""
RikkaAI summary dialog.
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTextEdit, QVBoxLayout, QWidget

import config
from gui import dialog_theme


SUMMARY_BASE = os.path.join(config.ROOT_DIR, "summaries")
DIR_MAP = {
    "日报": os.path.join(SUMMARY_BASE, "daily"),
    "周记": os.path.join(SUMMARY_BASE, "weekly"),
    "月报": os.path.join(SUMMARY_BASE, "monthly"),
    "年鉴": os.path.join(SUMMARY_BASE, "yearly"),
}

ACCENT = "#b78eff"
ACCENT_DARK = "#8d69e0"
BORDER = "#eadff9"
TEXT = "#544978"
TEXT_MUTED = "#8e83ab"
SURFACE = "rgba(255,255,255,0.86)"
FIELD = "rgba(255,255,255,0.90)"


class SummaryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("摘要与年鉴")
        self.resize(980, 640)
        self.setMinimumSize(860, 560)
        self._ensure_dirs()
        self._apply_theme()
        self._setup_ui()
        self._refresh_files()

    def _ensure_dirs(self):
        for directory in DIR_MAP.values():
            os.makedirs(directory, exist_ok=True)

    def _apply_theme(self):
        global ACCENT, ACCENT_DARK, BORDER, TEXT, TEXT_MUTED, SURFACE, FIELD
        c = dialog_theme.colors()
        ACCENT, ACCENT_DARK, BORDER, TEXT, TEXT_MUTED = c["accent"], c["accent"], c["border_accent"], c["text"], c["muted"]
        SURFACE, FIELD = c["surface"], c["field"]
        self.setStyleSheet(
            f"""
            QDialog {{
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c['surface_soft']}, stop:0.5 {c['surface']}, stop:1 {c['surface_soft']});
            }}
            QLabel {{ color:{TEXT}; }}
            QListWidget {{
                background:transparent;
                border:none;
                outline:none;
            }}
            QListWidget::item {{
                min-height:42px;
                margin:4px 0;
                padding:0 12px;
                border-radius:14px;
                color:{TEXT_MUTED};
            }}
            QListWidget::item:selected {{
                background:{c['accent_soft']};
                border:1px solid {c['border_accent']};
                color:{ACCENT_DARK};
                font-weight:700;
            }}
            QTextEdit {{
                background:{c['field']};
                border:1px solid {BORDER};
                border-radius:20px;
                padding:16px;
                color:{TEXT};
                font-size:13px;
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

        badge = QLabel("≡")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(36, 36)
        badge.setStyleSheet(
            f"background:{FIELD};border:1px solid {BORDER};border-radius:18px;color:{ACCENT_DARK};font-size:18px;font-weight:700;"
        )
        header_layout.addWidget(badge)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)
        title = QLabel("摘要与年鉴")
        title.setStyleSheet(f"font-size:24px;font-weight:700;color:{ACCENT_DARK};")
        title_block.addWidget(title)
        subtitle = QLabel("查看日报、周记、月报和年鉴，把聊天整理成长期档案。")
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
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(14, 14, 14, 14)
        body_layout.setSpacing(14)

        nav_shell = QWidget()
        nav_shell.setFixedWidth(160)
        nav_layout = QVBoxLayout(nav_shell)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(10)
        nav_title = QLabel("分类")
        nav_title.setStyleSheet(f"font-size:12px;font-weight:700;color:{TEXT_MUTED};padding-left:6px;")
        nav_layout.addWidget(nav_title)

        self._category_list = QListWidget()
        for name in DIR_MAP:
            self._category_list.addItem(name)
        self._category_list.currentRowChanged.connect(self._switch_category)
        nav_layout.addWidget(self._category_list, 1)
        body_layout.addWidget(nav_shell)

        file_shell = QWidget()
        file_shell.setFixedWidth(240)
        file_layout = QVBoxLayout(file_shell)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_layout.setSpacing(10)
        file_title = QLabel("文件")
        file_title.setStyleSheet(f"font-size:12px;font-weight:700;color:{TEXT_MUTED};padding-left:6px;")
        file_layout.addWidget(file_title)
        self._file_list = QListWidget()
        self._file_list.currentRowChanged.connect(self._show_file)
        file_layout.addWidget(self._file_list, 1)
        body_layout.addWidget(file_shell)

        viewer_shell = QWidget()
        viewer_layout = QVBoxLayout(viewer_shell)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.setSpacing(10)
        viewer_title = QLabel("内容预览")
        viewer_title.setStyleSheet(f"font-size:12px;font-weight:700;color:{TEXT_MUTED};padding-left:6px;")
        viewer_layout.addWidget(viewer_title)
        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        viewer_layout.addWidget(self._viewer, 1)
        body_layout.addWidget(viewer_shell, 1)

        outer.addWidget(body, 1)
        self._current_dir = list(DIR_MAP.values())[0]
        self._category_list.setCurrentRow(0)

    def _switch_category(self, row):
        if row < 0:
            return
        self._current_dir = list(DIR_MAP.values())[row]
        self._refresh_files()

    def _refresh_files(self):
        self._file_list.blockSignals(True)
        self._file_list.clear()
        self._files = []
        if os.path.isdir(self._current_dir):
            for filename in sorted(os.listdir(self._current_dir), reverse=True):
                if filename.endswith(".md"):
                    self._files.append(filename)
                    self._file_list.addItem(QListWidgetItem(filename.replace(".md", "")))
        self._file_list.blockSignals(False)
        if self._files:
            self._file_list.setCurrentRow(0)
        else:
            self._viewer.setPlainText("当前分类下还没有摘要文件。")

    def _show_file(self, row):
        if row < 0 or row >= len(self._files):
            self._viewer.clear()
            return
        path = os.path.join(self._current_dir, self._files[row])
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._viewer.setPlainText(f.read())
        except Exception as exc:
            self._viewer.setPlainText(f"读取失败: {exc}")
