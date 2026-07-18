"""
RikkaAI - 备忘本弹窗
"""
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QListWidget,
    QListWidgetItem, QTextEdit, QSplitter, QLineEdit,
    QInputDialog, QMessageBox, QComboBox,
)
from PyQt5.QtCore import Qt

import brain.notes as notes


class NotesDialog(QDialog):
    """管理备忘本"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("备忘本")
        self.resize(600, 500)
        self.setMinimumSize(400, 350)
        self.setStyleSheet("""
            QDialog { background-color: #0f0a18; }
        """)
        self._current_id = None
        self._setup_ui()
        self._load_notes()

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
        title = QLabel("📝 备忘本")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #c084fc;")
        hd.addWidget(title)
        hd.addStretch()

        self._btn_add = QPushButton("+ 新建")
        self._btn_add.setFixedSize(64, 26)
        self._btn_add.setStyleSheet("""
            QPushButton { background-color: #5a2a9e; border: 1px solid #7a3aba;
                border-radius: 13px; font-size: 11px; font-weight: bold; color: #fff; }
            QPushButton:hover { background-color: #7a3aba; }
        """)
        self._btn_add.setCursor(Qt.PointingHandCursor)
        self._btn_add.clicked.connect(self._on_add)
        hd.addWidget(self._btn_add)

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

        # 左侧列表
        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget { background-color: #0d0a14; border: none; color: #e0d0f0; font-size: 12px; }
            QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #1a0d2e; }
            QListWidget::item:selected { background-color: #2d1b4e; color: #ffd700; }
            QListWidget::item:hover { background-color: #1a0d2e; }
        """)
        self._list.itemClicked.connect(self._show_note)
        splitter.addWidget(self._list)

        # 右侧编辑区
        right = QWidget()
        right.setStyleSheet("background-color: #0f0a18;")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(8)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("备忘标题")
        self._title_edit.setStyleSheet("""
            QLineEdit { background-color: #1a0d2e; border: 1px solid #2a1050;
                border-radius: 6px; padding: 6px 10px; color: #e0d0f0; font-size: 13px; }
            QLineEdit:focus { border: 1px solid #7a3aba; }
        """)
        rl.addWidget(self._title_edit)

        self._cat_combo = QComboBox()
        self._cat_combo.addItems(["一般", "学习", "工作", "灵感", "待办"])
        self._cat_combo.setStyleSheet("""
            QComboBox { background-color: #1a0d2e; border: 1px solid #2a1050;
                border-radius: 6px; padding: 4px 8px; color: #c084fc; font-size: 11px; }
            QComboBox:hover { border-color: #5a2a9e; }
        """)
        rl.addWidget(self._cat_combo)

        self._content_edit = QTextEdit()
        self._content_edit.setPlaceholderText("写下你的备忘内容…")
        self._content_edit.setStyleSheet("""
            QTextEdit { background-color: #1a0d2e; border: 1px solid #2a1050;
                border-radius: 6px; padding: 8px; color: #e0d0f0; font-size: 12px; }
            QTextEdit:focus { border: 1px solid #7a3aba; }
        """)
        rl.addWidget(self._content_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_save = QPushButton("保存")
        self._btn_save.setFixedSize(64, 28)
        self._btn_save.setStyleSheet("""
            QPushButton { background-color: #5a2a9e; border: 1px solid #7a3aba;
                border-radius: 14px; font-size: 11px; font-weight: bold; color: #fff; }
            QPushButton:hover { background-color: #7a3aba; }
        """)
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self._btn_save)

        self._btn_del = QPushButton("删除")
        self._btn_del.setFixedSize(64, 28)
        self._btn_del.setStyleSheet("""
            QPushButton { background-color: transparent; border: 1px solid #5a1a2a;
                border-radius: 14px; font-size: 11px; color: #a05a6a; }
            QPushButton:hover { background-color: #2a0a10; }
        """)
        self._btn_del.setCursor(Qt.PointingHandCursor)
        self._btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_del)

        rl.addLayout(btn_row)
        splitter.addWidget(right)
        splitter.setSizes([180, 420])
        outer.addWidget(splitter, 1)

    def _load_notes(self):
        self._list.clear()
        for n in notes.get_all():
            item = QListWidgetItem(f"{n['title'] or '无标题'}")
            item.setData(Qt.UserRole, n["id"])
            self._list.addItem(item)

    def _show_note(self, item):
        nid = item.data(Qt.UserRole)
        n = notes.get(nid)
        if n:
            self._current_id = n["id"]
            self._title_edit.setText(n.get("title", ""))
            self._content_edit.setPlainText(n.get("content", ""))
            idx = self._cat_combo.findText(n.get("category", "一般"))
            if idx >= 0:
                self._cat_combo.setCurrentIndex(idx)

    def _on_add(self):
        title, ok = QInputDialog.getText(self, "新建备忘", "备忘标题：")
        if ok and title.strip():
            notes.add(title.strip(), "", "一般")
            self._load_notes()

    def _on_save(self):
        if self._current_id is None:
            notes.add(
                self._title_edit.text().strip() or "无标题",
                self._content_edit.toPlainText(),
                self._cat_combo.currentText(),
            )
        else:
            notes.update(
                self._current_id,
                self._title_edit.text().strip() or "无标题",
                self._content_edit.toPlainText(),
                self._cat_combo.currentText(),
            )
        self._load_notes()

    def _on_delete(self):
        if self._current_id is None:
            return
        confirm = QMessageBox.question(
            self, "确认删除", "确定删除这条备忘？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            notes.delete(self._current_id)
            self._current_id = None
            self._title_edit.clear()
            self._content_edit.clear()
            self._load_notes()
