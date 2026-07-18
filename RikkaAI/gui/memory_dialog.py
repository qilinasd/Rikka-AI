"""
RikkaAI - 记忆内容弹窗（板块分类）
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QLineEdit,
    QMessageBox,
)
from PyQt5.QtCore import Qt

CATEGORIES = [
    ("❤️喜欢的", "#ff69b4"),
    ("⭐重要的事", "#ffd700"),
    ("🎯想做的事", "#00d4aa"),
    ("📝日常", "#7a5aaa"),
]


class MemoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("记忆")
        self.resize(500, 500)
        self.setMinimumSize(380, 360)
        self.setStyleSheet("QDialog { background-color: #0f0a18; }")
        self._current_cat = CATEGORIES[0][0]
        self._setup_ui()
        self._load_memories()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header.setStyleSheet("background-color: #120b1a; border-bottom: 1px solid #2a1050;")
        hd = QHBoxLayout(header)
        hd.setContentsMargins(20,0,16,0)
        title = QLabel("🧠 六花的记忆")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        hd.addWidget(title)
        hd.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(60,26)
        close_btn.setStyleSheet("QPushButton{background:transparent;border:1px solid #2a1050;border-radius:13px;font-size:11px;color:#7a5aaa}QPushButton:hover{border-color:#5a2a9e;color:#c084fc}")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        hd.addWidget(close_btn)
        outer.addWidget(header)

        nav_bar = QWidget()
        nav_bar.setStyleSheet("background-color: #0d0a14; border-bottom: 1px solid #1f0d38;")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(12,8,12,8); nav_layout.setSpacing(6)
        self._nav_btns = []
        for cat_name, color in CATEGORIES:
            btn = QPushButton(cat_name)
            btn.setFixedHeight(30); btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"QPushButton{{background:transparent;border:1px solid {color};border-radius:6px;font-size:11px;color:{color};padding:0 10px}}QPushButton:hover{{background:{color}22;}}")
            btn.clicked.connect(lambda checked, c=cat_name: self._switch_category(c))
            nav_layout.addWidget(btn); self._nav_btns.append(btn)
        outer.addWidget(nav_bar)

        input_bar = QWidget()
        input_bar.setStyleSheet("background-color: #0d0a14; border-bottom: 1px solid #1f0d38;")
        inp = QHBoxLayout(input_bar)
        inp.setContentsMargins(16,10,16,10); inp.setSpacing(8)
        self._memory_input = QLineEdit()
        self._memory_input.setPlaceholderText(f"输入想让六花记住的内容…（将保存到{self._current_cat}）")
        self._memory_input.setStyleSheet("QLineEdit{background:#1a0d2e;border:1px solid #2a1050;border-radius:6px;padding:6px 10px;color:#e0d0f0;font-size:12px}QLineEdit:focus{border-color:#7a3aba}QLineEdit::placeholder{color:#3a2a4a}")
        self._memory_input.returnPressed.connect(self._on_add)
        inp.addWidget(self._memory_input, 1)
        add_btn = QPushButton("记住")
        add_btn.setFixedSize(54,28)
        add_btn.setStyleSheet("QPushButton{background:#5a2a9e;border:1px solid #7a3aba;border-radius:14px;font-size:11px;font-weight:bold;color:#fff}QPushButton:hover{background:#7a3aba}")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(self._on_add)
        inp.addWidget(add_btn)
        outer.addWidget(input_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{border:none;background:transparent}QScrollBar:vertical{background:#0d0a14;width:5px;border:none}QScrollBar::handle:vertical{background:#2a1050;border-radius:2px;min-height:30px}QScrollBar::handle:vertical:hover{background:#4a2080}")
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(16,12,16,12)
        self._list_layout.setSpacing(6)
        self._list_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    def _switch_category(self, cat_name):
        self._current_cat = cat_name
        self._memory_input.setPlaceholderText(f"输入想让六花记住的内容…（将保存到{cat_name}）")
        for btn in self._nav_btns:
            _, color = CATEGORIES[[c[0] for c in CATEGORIES].index(btn.text())]
            if btn.text() == cat_name:
                btn.setStyleSheet(f"QPushButton{{background:{color}44;border:1px solid {color};border-radius:6px;font-size:11px;color:#fff;padding:0 10px}}")
            else:
                btn.setStyleSheet(f"QPushButton{{background:transparent;border:1px solid {color};border-radius:6px;font-size:11px;color:{color};padding:0 10px}}QPushButton:hover{{background:{color}22;}}")
        self._refresh_list()

    def _load_memories(self):
        parent = self.parent()
        if not hasattr(parent, 'memory'):
            self._add_empty("记忆系统尚未初始化"); return
        all_memories = parent.memory.get_all()
        current = [m for m in all_memories if m.get("category", "📝日常") == self._current_cat]
        if not current:
            self._add_empty(f"「{self._current_cat}」还没有记忆")
            return
        for m in current:
            self._add_card(m)

    def _add_empty(self, text):
        label = QLabel(text)
        label.setStyleSheet("color: #3a2a4a; font-size: 12px; padding: 30px;")
        label.setAlignment(Qt.AlignCenter)
        self._list_layout.insertWidget(self._list_layout.count() - 1, label)

    def _add_card(self, m):
        color = "#7a5aaa"
        for cat, col in CATEGORIES:
            if cat == self._current_cat: color = col; break
        card = QWidget()
        card.setStyleSheet(f"QWidget{{background:#140a20;border:1px solid #1f0d38;border-radius:8px;border-left:3px solid {color}}}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12,8,12,8); card_layout.setSpacing(3)
        top_row = QHBoxLayout(); top_row.setSpacing(6)
        time_label = QLabel(m.get("created_at",""))
        time_label.setStyleSheet("color:#3a2a4a;font-size:9px;background:transparent;")
        top_row.addWidget(time_label); top_row.addStretch()
        btn_del = QPushButton("✕")
        btn_del.setFixedSize(20,20)
        btn_del.setStyleSheet("QPushButton{background:transparent;border:none;font-size:12px;color:#5a3a5a}QPushButton:hover{color:#d06a7a}")
        btn_del.setCursor(Qt.PointingHandCursor)
        btn_del.clicked.connect(lambda checked, x=m["id"]: self._delete_memory(x))
        top_row.addWidget(btn_del); card_layout.addLayout(top_row)
        text_label = QLabel(m["content"])
        text_label.setWordWrap(True)
        text_label.setStyleSheet("color:#d4c0e0;font-size:12px;background:transparent;")
        text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_layout.addWidget(text_label)
        self._list_layout.insertWidget(self._list_layout.count() - 1, card)

    def _delete_memory(self, memory_id):
        if QMessageBox.question(self,"确认删除","确定删除这条记忆？",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            parent = self.parent()
            if hasattr(parent, 'memory'): parent.memory.delete_memory(memory_id)
            self._refresh_list()

    def _on_add(self):
        text = self._memory_input.text().strip()
        if not text: return
        parent = self.parent()
        if hasattr(parent, 'memory'): parent.memory.add_memory(text, self._current_cat)
        self._memory_input.clear()
        self._refresh_list()

    def _refresh_list(self):
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._load_memories()
