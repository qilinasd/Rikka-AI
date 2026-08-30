"""
RikkaAI memory detail dialog — 查看单条记忆的完整信息。
"""
import json

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from brain import memory_vault
from gui import dialog_theme


ACCENT_DARK = "#8d69e0"
BORDER = "#eadff9"
TEXT = "#544978"
TEXT_MUTED = "#8e83ab"
SURFACE = "rgba(255,255,255,0.86)"
FIELD = "rgba(255,255,255,0.90)"

# 情绪权重 -> 图标（按 emotional_weight 数值分级）
EMOTION_ICONS = [(0.8, "💖"), (0.6, "💙"), (0.4, "💚")]


def _emotion_tag(weight):
    for threshold, icon in EMOTION_ICONS:
        if weight >= threshold:
            return icon
    return "🤍"


class MemoryDetailDialog(QDialog):
    def __init__(self, fragment, parent=None):
        super().__init__(parent)
        self._fragment = fragment or {}
        self.setWindowTitle("记忆详情")
        self.resize(640, 520)
        self.setMinimumSize(540, 420)
        self._apply_theme()
        self._setup_ui()
        self._populate()

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

    def _meta_row(self, label, value):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        key = QLabel(label)
        key.setStyleSheet(f"color:{TEXT_MUTED};font-size:11px;")
        key.setFixedWidth(64)
        layout.addWidget(key)
        val = QLabel(str(value) if value else "—")
        val.setStyleSheet(f"color:{TEXT};font-size:12px;")
        val.setWordWrap(True)
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(val, 1)
        return row

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        outer.setSpacing(14)

        header = self._shell()
        header.setFixedHeight(82)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(12)

        badge = QLabel("📖")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(36, 36)
        badge.setStyleSheet(
            f"background:{FIELD};border:1px solid {BORDER};border-radius:18px;color:{ACCENT_DARK};font-size:18px;font-weight:700;"
        )
        header_layout.addWidget(badge)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(2)
        title = QLabel("记忆详情")
        title.setStyleSheet(f"font-size:24px;font-weight:700;color:{ACCENT_DARK};")
        title_block.addWidget(title)
        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet(f"font-size:11px;color:{TEXT_MUTED};")
        title_block.addWidget(self._subtitle)
        header_layout.addLayout(title_block)
        header_layout.addStretch()

        self._pill = QLabel()
        self._pill.setStyleSheet("font-size:12px;font-weight:700;padding:5px 12px;border-radius:11px;border:1px solid transparent;")
        header_layout.addWidget(self._pill)

        close_btn = self._secondary_button("关闭")
        close_btn.setFixedSize(82, 36)
        close_btn.clicked.connect(self.accept)
        header_layout.addWidget(close_btn)
        outer.addWidget(header)

        content_shell = self._shell()
        content_layout = QVBoxLayout(content_shell)
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(10)

        self._meta = QVBoxLayout()
        self._meta.setSpacing(6)
        content_layout.addLayout(self._meta)

        sep = QLabel("记忆内容")
        sep.setStyleSheet(f"color:{ACCENT_DARK};font-size:12px;font-weight:700;")
        content_layout.addWidget(sep)

        self._viewer = QTextEdit()
        self._viewer.setReadOnly(True)
        self._viewer.setStyleSheet(
            f"""
            QTextEdit {{
                background:{FIELD};
                border:1px solid {BORDER};
                border-radius:16px;
                padding:12px;
                color:{TEXT};
                font-size:13px;
                font-family:'Microsoft YaHei', 'SimHei', monospace;
                line-height:1.7;
            }}
            """
        )
        content_layout.addWidget(self._viewer, 1)
        outer.addWidget(content_shell, 1)

    def _populate(self):
        frag = self._fragment
        main_cat, sub_cat = memory_vault.normalize_category(str(frag.get("category") or ""))
        self._subtitle.setText(f"主体：{frag.get('entity') or '—'}")
        # 分类 pill 着色（与记忆页保持一致的 tone 映射）
        tone = main_cat if main_cat in memory_vault.MEMORY_CATEGORIES else "一般"
        pill_colors = {
            "重要的事": ("#8150df", "rgba(129,80,223,0.12)"),
            "喜好": ("#d05296", "rgba(239,123,180,0.14)"),
            "日常": ("#c0862c", "rgba(244,167,71,0.16)"),
            "系统": ("#4b5fc0", "rgba(106,127,224,0.14)"),
            "一般": ("#8a6fd0", "rgba(180,154,232,0.16)"),
        }
        color, bg = pill_colors.get(tone, pill_colors["一般"])
        self._pill.setText(f"{main_cat or '一般'}{(' · ' + sub_cat) if sub_cat else ''}")
        self._pill.setStyleSheet(
            f"font-size:12px;font-weight:700;padding:5px 12px;border-radius:11px;border:1px solid transparent;background:{bg};color:{color};"
        )

        weight = float(frag.get("emotional_weight") or 0.5)
        emotion = f"{_emotion_tag(weight)} 情绪权重 {weight:.2f}"

        created = str(frag.get("created_at") or "—").replace("T", " ")

        source = frag.get("source") or ""
        source_id = frag.get("source_id") or ""
        source_text = source if source else "—"
        if source and source_id:
            source_text = f"{source}（{source_id}）"

        keywords = frag.get("keywords")
        keyword_text = ""
        if keywords:
            try:
                parsed = json.loads(keywords) if isinstance(keywords, str) else keywords
                if isinstance(parsed, list):
                    keyword_text = "、".join(str(k) for k in parsed)
            except (ValueError, TypeError):
                keyword_text = str(keywords)

        for label, value in (
            ("分类", f"{main_cat or '一般'}{(' / ' + sub_cat) if sub_cat else ''}"),
            ("情绪", emotion),
            ("来源", source_text),
            ("时间", created),
        ):
            self._meta.addWidget(self._meta_row(label, value))
        if keyword_text:
            self._meta.addWidget(self._meta_row("关键词", keyword_text))

        self._viewer.setPlainText(str(frag.get("content") or "（无内容）"))
