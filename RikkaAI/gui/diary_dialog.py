"""
RikkaAI - 日记查看弹窗（含导出到文件）
"""
import os
from datetime import datetime

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QListWidget,
    QListWidgetItem, QTextEdit, QSplitter, QMessageBox,
)
from PyQt5.QtCore import Qt

import brain.diary as diary
import config


class DiaryDialog(QDialog):
    """查看每日日记，可导出到 diaries/ 文件夹"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("日记")
        self.resize(600, 500)
        self.setMinimumSize(400, 350)
        self.setStyleSheet("""
            QDialog { background-color: #0f0a18; }
        """)
        self._setup_ui()
        self._load_diaries()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶栏
        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #120b1a; border-bottom: 1px solid #2a1050;")
        hd = QHBoxLayout(header)
        hd.setContentsMargins(20, 0, 16, 0)
        title = QLabel("📖 六花的日记")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        hd.addWidget(title)
        hd.addStretch()

        export_btn = QPushButton("导出")
        export_btn.setFixedSize(60, 26)
        export_btn.setStyleSheet("""
            QPushButton { background-color: transparent; border: 1px solid #2a1050;
                border-radius: 13px; font-size: 11px; color: #7a5aaa; }
            QPushButton:hover { border-color: #5a2a9e; color: #c084fc; }
        """)
        export_btn.setCursor(Qt.PointingHandCursor)
        export_btn.clicked.connect(self._export_current)
        hd.addWidget(export_btn)

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

        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #2a1050; }")

        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background-color: #0d0a14; border: none; color: #e0d0f0; font-size: 12px; }
            QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #1a0d2e; }
            QListWidget::item:selected { background-color: #2d1b4e; color: #ffd700; }
            QListWidget::item:hover { background-color: #1a0d2e; }
        """)
        self._list.itemClicked.connect(self._show_diary)
        splitter.addWidget(self._list)

        self._content = QTextEdit()
        self._content.setReadOnly(True)
        self._content.setStyleSheet("""
            QTextEdit { background-color: #0f0a18; border: none; color: #d4c0e0; font-size: 13px; padding: 16px; }
        """)
        splitter.addWidget(self._content)

        splitter.setSizes([180, 420])
        outer.addWidget(splitter, 1)

    def _load_diaries(self):
        diaries = diary.get_all_diaries(30)
        self._diary_list = diaries
        for d in diaries:
            item = QListWidgetItem(f"{d['date']}\n{d['title'][:20]}")
            item.setData(Qt.UserRole, d["date"])
            item.setToolTip(d.get("summary", ""))
            self._list.addItem(item)

    def _show_diary(self, item):
        date_str = item.data(Qt.UserRole)
        d = diary.get_diary(date_str)
        if not d:
            self._content.setPlainText("无记录")
            return
        self._current_diary = d
        content = (
            f"📅 {d.get('date', '')}\n"
            f"📌 {d.get('title', '')}\n"
            f"😊 心情: {d.get('mood', '')}\n\n"
            f"【摘要】\n{d.get('summary', '')}\n\n"
            f"【详情】\n{d.get('details', '')}"
        )
        self._content.setPlainText(content)

    def _export_current(self):
        """导出当前日记到 diaries/ 文件夹"""
        if not hasattr(self, '_current_diary') or not self._current_diary:
            QMessageBox.information(self, "提示", "请先在左侧选择一篇日记")
            return

        d = self._current_diary
        date_str = d.get("date", datetime.now().strftime("%Y%m%d"))
        md = (
            f"# {d.get('title', '六花的日记')}\n\n"
            f"**日期：{date_str}**\n\n"
            f"---\n\n"
            f"{d.get('details', '')}\n\n"
            f"---\n\n"
            f"**摘要：** {d.get('summary', '')}\n"
            f"**心情：** {d.get('mood', '')}\n"
        )

        os.makedirs(config.DIARY_DIR, exist_ok=True)
        filepath = os.path.join(config.DIARY_DIR, f"diary_{date_str}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)

        QMessageBox.information(self, "导出成功", f"已保存到:\n{filepath}")
