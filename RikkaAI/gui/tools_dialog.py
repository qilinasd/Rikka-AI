"""
RikkaAI - 工具列表弹窗
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QFrame,
)
from PyQt5.QtCore import Qt

from brain.tools import TOOL_DEFINITIONS
from gui import dialog_theme


class ToolsDialog(QDialog):
    """展示六花所有可用工具"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("工具列表")
        self.resize(480, 500)
        self.setMinimumSize(360, 300)
        self._colors = dialog_theme.colors()
        dialog_theme.apply(self)
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 顶栏
        header = QWidget()
        header.setObjectName("ToolsHeader")
        header.setFixedHeight(48)
        c = self._colors
        header.setStyleSheet(
            f"QWidget#ToolsHeader{{background:{c['surface']};border-bottom:1px solid {c['border_accent']};}}"
        )
        hd = QHBoxLayout(header)
        hd.setContentsMargins(20, 0, 16, 0)

        title = QLabel("🔧 可用工具")
        title.setStyleSheet(f"font-size:15px;font-weight:800;color:{c['accent']};")
        hd.addWidget(title)
        hd.addStretch()

        count = QLabel(f"{len(TOOL_DEFINITIONS)} 个")
        count.setStyleSheet(f"color:{c['muted']};font-size:11px;padding-right:8px;")
        hd.addWidget(count)

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(60, 26)
        close_btn.setStyleSheet(
            f"QPushButton{{background:transparent;border:1px solid {c['border_accent']};"
            f"border-radius:13px;font-size:11px;color:{c['muted']};}}"
            f"QPushButton:hover{{border-color:{c['accent']};color:{c['accent']};}}"
        )
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        hd.addWidget(close_btn)

        outer.addWidget(header)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            f"QScrollArea{{border:none;background:transparent;}}"
            f"QScrollBar:vertical{{background:transparent;width:6px;border:none;}}"
            f"QScrollBar::handle:vertical{{background:{c['border_accent']};border-radius:3px;min-height:30px;}}"
            f"QScrollBar::handle:vertical:hover{{background:{c['accent']};}}"
        )

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
            card.setObjectName("ToolCard")
            card.setStyleSheet(
                f"QWidget#ToolCard{{background:{c['surface_soft']};border:1px solid {c['border']};"
                f"border-radius:12px;border-left:3px solid {c['accent']};}}"
            )
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 8, 12, 8)
            card_layout.setSpacing(10)

            icon_label = QLabel(icon)
            icon_label.setStyleSheet("font-size:18px;background:transparent;")
            card_layout.addWidget(icon_label)

            info = QVBoxLayout()
            info.setSpacing(1)
            name_label = QLabel(name)
            name_label.setStyleSheet(f"color:{c['accent']};font-size:12px;font-weight:800;background:transparent;")
            info.addWidget(name_label)
            desc_label = QLabel(desc)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet(f"color:{c['muted']};font-size:11px;background:transparent;")
            info.addWidget(desc_label)

            card_layout.addLayout(info, 1)
            layout.insertWidget(layout.count() - 1, card)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
