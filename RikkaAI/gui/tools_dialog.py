"""
RikkaAI - 工具列表弹窗
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QFrame,
)
from PyQt5.QtCore import Qt

from brain.tools import TOOL_DEFINITIONS


class ToolsDialog(QDialog):
    """展示六花所有可用工具"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("工具列表")
        self.resize(480, 500)
        self.setMinimumSize(360, 300)
        self.setStyleSheet("""
            QDialog { background-color: #0f0a18; }
        """)
        self._setup_ui()

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

        title = QLabel("🔧 可用工具")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        hd.addWidget(title)
        hd.addStretch()

        count = QLabel(f"{len(TOOL_DEFINITIONS)} 个")
        count.setStyleSheet("color: #5a3a7a; font-size: 11px; padding-right: 8px;")
        hd.addWidget(count)

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

        # 滚动区域
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
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        layout.addStretch()

        # 生成卡片
        icons = ["📁", "📝", "✏️", "📂", "🔍", "🔎", "⏰", "💻", "🚀", "📖", "➕", "🌐"]
        for i, t in enumerate(TOOL_DEFINITIONS):
            fn = t["function"]
            name = fn["name"]
            desc = fn["description"]
            icon = icons[i] if i < len(icons) else "🔧"

            card = QWidget()
            card.setStyleSheet("""
                QWidget { background-color: #140a20; border: 1px solid #1f0d38;
                    border-radius: 8px; border-left: 3px solid #5a2a9e; }
            """)
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(10)

            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size: 18px; background: transparent;")
            card_layout.addWidget(icon_label)

            info = QVBoxLayout()
            info.setSpacing(1)
            name_label = QLabel(name)
            name_label.setStyleSheet("color: #c084fc; font-size: 12px; font-weight: bold; background: transparent;")
            info.addWidget(name_label)
            desc_label = QLabel(desc)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #7a5aaa; font-size: 11px; background: transparent;")
            info.addWidget(desc_label)

            card_layout.addLayout(info, 1)
            layout.insertWidget(layout.count() - 1, card)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
