"""
RikkaAI - 六花的冲浪记录对话框
展示结构化冲浪记录（来源/时间/标题/链接/搜索结果详情），支持筛选、搜索、清空。
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from brain import surf
from gui import dialog_theme

ACCENT = "#b78eff"
ACCENT_DARK = "#8d69e0"
PINK = "#ffb8cf"
BORDER = "#eadff9"
TEXT = "#544978"
TEXT_MUTED = "#8e83ab"
FIELD = "#ffffff"
ACCENT_SOFT = "#f0e6ff"


def _refresh_palette():
    global ACCENT, ACCENT_DARK, PINK, BORDER, TEXT, TEXT_MUTED, FIELD, ACCENT_SOFT
    c = dialog_theme.colors()
    ACCENT = c["accent"]
    ACCENT_DARK = c["accent"]
    PINK = c["accent"]
    BORDER = c["border_accent"]
    TEXT = c["text"]
    TEXT_MUTED = c["muted"]
    FIELD = c["field"]
    ACCENT_SOFT = c["accent_soft"]

_SOURCE_LABELS = {
    "bilibili": "B站",
    "web": "网页",
    "image_search": "搜图",
    "smart_search": "智能搜图",
    "image": "图片",
    "github": "GitHub",
    "youtube": "YouTube",
}


def _source_label(source):
    return _SOURCE_LABELS.get(source, source)


class SurfTagRow(QWidget):
    """兴趣标签行：关键词 + 星级 + 暂停/恢复 + 删除。"""

    def __init__(self, tag, on_toggle, on_delete, parent=None):
        super().__init__(parent)
        _refresh_palette()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        score = tag.get("base_score", 50) + tag.get("boost_score", 0)
        stars = "★" * min(5, max(1, score // 20))
        paused = tag.get("status") == "paused"
        text = QLabel(f"{tag['keyword']}  {stars}")
        text.setStyleSheet(
            f"color:{TEXT_MUTED if paused else TEXT};"
            f"font-size:12px;font-weight:650;"
        )
        text.setToolTip(f"基础分 {tag.get('base_score', 50)} · 加成 {tag.get('boost_score', 0)}")
        layout.addWidget(text)
        layout.addStretch()
        source = QLabel(f"({tag.get('source', 'auto')})")
        source.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
        layout.addWidget(source)
        toggle = QPushButton("恢复" if paused else "暂停")
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.setStyleSheet(
            f"color:{ACCENT_DARK};background:{FIELD};border:1px solid {BORDER};"
            f"border-radius:8px;padding:2px 10px;font-size:10px;"
        )
        toggle.clicked.connect(lambda _=False: on_toggle(tag["keyword"]))
        layout.addWidget(toggle)
        delete = QPushButton("删除")
        delete.setCursor(Qt.PointingHandCursor)
        delete.setStyleSheet(
            f"color:#c54164;background:{FIELD};border:1px solid rgba(220,72,109,0.25);"
            "border-radius:8px;padding:2px 10px;font-size:10px;"
        )
        delete.clicked.connect(lambda _=False: on_delete(tag["keyword"]))
        layout.addWidget(delete)


def tag_row_size():
    from PyQt5.QtCore import QSize
    return QSize(0, 42)


class SurfRecordCard(QWidget):
    """一条冲浪记录卡片：来源徽章 + 标题 + 打开链接 + 详情 + 搜索结果 + 👍/👎 反馈。"""

    def __init__(self, record, on_react=None, on_favorite=None, parent=None):
        super().__init__(parent)
        _refresh_palette()
        self._record = record
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(6)
        src = QLabel(_source_label(str(record.get("source") or "web")))
        src.setStyleSheet(
            f"background:{ACCENT_DARK};color:#ffffff;border-radius:8px;"
            f"padding:2px 10px;font-size:11px;font-weight:700;"
        )
        header.addWidget(src)
        if record.get("tag"):
            tag = QLabel(str(record["tag"]))
            tag.setStyleSheet(
                f"color:{ACCENT_DARK};background:{ACCENT_SOFT};border-radius:8px;"
                f"padding:2px 8px;font-size:10px;"
            )
            header.addWidget(tag)
        header.addStretch()
        time_text = str(record.get("time") or "")[:16]
        if time_text:
            t = QLabel(time_text)
            t.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
            header.addWidget(t)
        layout.addLayout(header)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel(str(record.get("title") or "（无标题）"))
        title.setStyleSheet(f"color:{TEXT};font-size:13px;font-weight:700;")
        title.setWordWrap(True)
        title_row.addWidget(title, 1)
        url = str(record.get("url") or "")
        if url:
            open_btn = QPushButton("打开 ↗")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.setStyleSheet(
                f"color:{ACCENT_DARK};background:{FIELD};border:1px solid {BORDER};"
                f"border-radius:8px;padding:3px 10px;font-size:10px;"
            )
            open_btn.clicked.connect(lambda _=False, u=url: self._open_url(u))
            title_row.addWidget(open_btn)
        if on_favorite is not None:
            fav = QPushButton("★" if record.get("favorite") else "☆")
            fav.setCursor(Qt.PointingHandCursor)
            fav.setToolTip("收藏" if not record.get("favorite") else "取消收藏")
            fav.setStyleSheet(
                f"color:{'#e8b23a' if record.get('favorite') else '#b9aed8'};"
                f"background:{FIELD};border:1px solid {BORDER};"
                f"border-radius:8px;padding:3px 10px;font-size:12px;"
            )
            fav.clicked.connect(lambda _=False, rid=record.get("id", ""): on_favorite(rid))
            title_row.addWidget(fav)
        layout.addLayout(title_row)

        detail = str(record.get("detail") or "").strip()
        if detail:
            d = QLabel(detail[:220])
            d.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
            d.setWordWrap(True)
            layout.addWidget(d)

        results = record.get("results") or []
        if results:
            lines = []
            for x in results[:3]:
                r_title = str(x.get("title") or "链接")
                r_meta = " · ".join(
                    str(x.get(k) or "") for k in ("author", "play") if x.get(k)
                )
                r_url = str(x.get("url") or "")
                lines.append(f"· {r_title}" + (f"（{r_meta}）" if r_meta else "") +
                             (f"  {r_url}" if r_url else ""))
            rs = QLabel("\n".join(lines))
            rs.setStyleSheet(
                f"color:{TEXT};background:{FIELD};border:1px solid {BORDER};"
                f"border-radius:8px;padding:6px 9px;font-size:11px;"
            )
            rs.setWordWrap(True)
            layout.addWidget(rs)

        # 👍/👎 反馈（对整条记录，调整对应兴趣标签分数）
        if on_react is not None:
            react_row = QHBoxLayout()
            react_row.setSpacing(6)
            hint = QLabel("这个方向的推荐你喜欢吗？")
            hint.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;")
            react_row.addWidget(hint)
            react_row.addStretch()
            reaction = record.get("reaction", "")
            for key, symbol, color in (("liked", "👍 喜欢", "#2f9d6b"),
                                       ("disliked", "👎 不喜欢", "#d0485a")):
                btn = QPushButton(symbol)
                btn.setCursor(Qt.PointingHandCursor)
                selected = reaction == key
                btn.setStyleSheet(
                    f"color:{color if selected else TEXT_MUTED};"
                    f"background:{'rgba(47,157,107,0.12)' if selected else FIELD};"
                    f"border:1px solid {'#2f9d6b' if selected else BORDER};"
                    f"border-radius:8px;padding:3px 10px;font-size:10px;"
                )
                btn.clicked.connect(
                    lambda _=False, k=key: on_react(record.get("id", ""), k)
                )
                react_row.addWidget(btn)
            layout.addLayout(react_row)

        line = QFrame()
        line.setStyleSheet(f"background:{BORDER};")
        line.setFixedHeight(1)
        layout.addWidget(line)

    @staticmethod
    def _open_url(url):
        try:
            os.startfile(url)
        except Exception:
            pass


class SurfHistoryDialog(QDialog):
    """六花的冲浪记录：来源筛选 + 关键词搜索 + 清空。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("六花的冲浪记录")
        self.resize(800, 640)
        self.setMinimumSize(640, 520)
        self._apply_theme()
        self._setup_ui()
        self.reload()

    def _apply_theme(self):
        global ACCENT, ACCENT_DARK, PINK, BORDER, TEXT, TEXT_MUTED, FIELD, ACCENT_SOFT
        c = dialog_theme.colors()
        self._colors = c
        _refresh_palette()
        self.setStyleSheet(
            f"""
            QDialog {{
                background:qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {c['surface_soft']}, stop:0.5 {c['surface']}, stop:1 {c['surface_soft']});
            }}
            QLabel {{ color:{TEXT}; }}
            QLineEdit, QComboBox {{
                min-height:32px;
                background:{c['field']};
                border:1px solid {BORDER};
                border-radius:9px;
                padding:0 10px;
                font-size:12px;
                color:{TEXT};
            }}
            QComboBox::drop-down {{ border:none; width:22px; }}
            QListWidget {{ background:transparent; border:none; outline:none; }}
            QListWidget::item {{ background:transparent; border:none; margin:3px 0; }}
            QListWidget::item:selected {{ background:transparent; }}
            QScrollBar:vertical {{
                background:transparent; width:8px; border:none; margin:6px 2px;
            }}
            QScrollBar::handle:vertical {{
                background:{c['border_accent']}; border-radius:4px; min-height:42px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:transparent; border:none;
            }}
            """
        )

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("❀ 六花的冲浪记录")
        title.setStyleSheet(f"color:{TEXT};font-size:19px;font-weight:800;")
        header.addWidget(title)
        header.addStretch()
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        header.addWidget(self.stats_label)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.source_combo = QComboBox()
        self.source_combo.setMinimumWidth(110)
        self.source_combo.currentIndexChanged.connect(lambda _: self.reload())
        toolbar.addWidget(self.source_combo)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索记录标题、标签或结果…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _: self.reload())
        toolbar.addWidget(self.search_edit, 1)
        clear_btn = QPushButton("清空记录")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            f"color:#c54164;background:{FIELD};border:1px solid rgba(220,72,109,0.25);"
            f"border-radius:9px;padding:5px 12px;font-size:11px;"
        )
        clear_btn.clicked.connect(self._confirm_clear)
        toolbar.addWidget(clear_btn)
        root.addLayout(toolbar)

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QListWidget.NoSelection)
        root.addWidget(self.list, 1)

    def reload(self):
        source = self.source_combo.currentData() or ""
        query = self.search_edit.text().strip()
        rows = surf.get_records(limit=100, source=source, query=query)
        self.list.clear()
        if not rows:
            empty = QListWidgetItem("还没有冲浪记录～ 让六花去搜点什么吧！")
            empty.setTextAlignment(Qt.AlignCenter)
            self.list.addItem(empty)
        for record in rows:
            item = QListWidgetItem()
            item.setSizeHint(record_widget_size(record))
            card = SurfRecordCard(record)
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
        # refresh source combo options + stats
        current = self.source_combo.currentData() or ""
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem("全部来源", "")
        for s in surf.get_store().sources():
            self.source_combo.addItem(_source_label(s), s)
        idx = self.source_combo.findData(current)
        self.source_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.source_combo.blockSignals(False)
        stats = surf.get_surf_stats()
        total = stats.get("total", 0)
        self.stats_label.setText(f"共 {total} 条记录 · 去重 {stats.get('seen', 0)} 个链接")

    def _confirm_clear(self):
        if surf.get_surf_stats().get("total", 0) == 0:
            return
        if QMessageBox.question(
            self, "清空记录", "确定要清空全部冲浪记录吗？",
            QMessageBox.Yes | QMessageBox.No,
        ) == QMessageBox.Yes:
            surf.clear_records()
            self.reload()


def record_widget_size(record):
    from PyQt5.QtCore import QSize
    base = 126  # 标题 + 反馈行
    if record.get("detail"):
        base += 28
    if record.get("results"):
        base += 46
    return QSize(0, base)
