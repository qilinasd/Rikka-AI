"""Glassmorphic emotional status card for the native chat workspace.

视觉对齐素材/情感界面.png：头像 + 语录 + 心情胶囊，
两列图标统计卡（情绪/精力/好感度/需求×5）+ 主动意愿/成功概率宽卡 + 蝴蝶星光装饰。
"""

import os
from datetime import datetime

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QSizePolicy, QSpinBox, QVBoxLayout,
    QWidget,
)

import config


_ASSET_DIR = os.path.join(config.ASSETS_DIR, "images", "emotion", "components")
_ICONS = {
    "mood": "mood_happy", "emotion_energy": "energy", "affection": "affection",
    "social": "social", "mastery": "mastery", "novelty": "novelty",
    "rest": "rest", "loneliness": "rest", "initiative_drive": "initiative",
    "proactive_success_probability": "success",
}
_MOOD_DOTS = {"happy": 5, "neutral": 3, "sad": 2, "angry": 1}
_FALLBACK_QUOTE = "无论是晴天还是雨天，我都会一直在你身边。"


def _pixmap(name, size):
    path = os.path.join(_ASSET_DIR, name + ".png")
    pixmap = QPixmap(path)
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not pixmap.isNull() else pixmap


class EmotionDetailsDialog(QDialog):
    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionDetailsDialog")
        self.setWindowTitle("六花的情感状态详情")
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        title = QLabel(f"{snapshot.get('mood_emoji', '😐')} 当前情绪：{snapshot.get('mood_label', '平静')}")
        title.setObjectName("EmotionDetailsTitle")
        root.addWidget(title)
        note = QLabel(snapshot.get("mood_note", ""))
        note.setWordWrap(True)
        note.setObjectName("EmotionDetailsNote")
        root.addWidget(note)
        labels = {
            "emotion_energy": "精力", "affection": "好感度", "social": "社交需求",
            "mastery": "掌控成就需求", "novelty": "新奇需求", "rest": "休息需求",
            "energy": "精力", "loneliness": "孤独感",
            "initiative_drive": "主动意愿", "proactive_success_probability": "主动成功概率",
        }
        rows = QVBoxLayout()
        rows.setSpacing(7)
        basic = [("emotion_energy", snapshot.get("emotion_energy")), ("affection", snapshot.get("affection"))]
        needs = snapshot.get("needs") or {}
        for key in ("social", "mastery", "novelty", "rest", "energy", "loneliness"):
            basic.append((key, needs.get(key)))
        basic.extend([
            ("initiative_drive", snapshot.get("initiative_drive")),
            ("proactive_success_probability", snapshot.get("proactive_success_probability")),
        ])
        for key, value in basic:
            row = QHBoxLayout()
            label = QLabel(labels.get(key, key))
            row.addWidget(label)
            row.addStretch()
            if value is None:
                text = "未启用"
            elif key in ("initiative_drive", "proactive_success_probability"):
                text = f"{float(value):.2f} / 1.00"
            else:
                text = f"{int(value)} / 100"
            row.addWidget(QLabel(text))
            rows.addLayout(row)
        root.addLayout(rows)
        enabled = "已启用" if snapshot.get("needs_enabled") else "未启用（仅显示基础情绪）"
        foot = QLabel(f"需求系统：{enabled}\n更新时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n这是六花根据互动计算出的当前状态，不代表真实意识或主观体验。")
        foot.setWordWrap(True)
        foot.setObjectName("EmotionDetailsFootnote")
        root.addWidget(foot)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)


class _ElidedLabel(QLabel):
    """空间不足时自动省略号——保证同行的数值永不被裁切。"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._full = str(text or "")
        QLabel.setText(self, self._full)

    def setText(self, text):
        self._full = str(text or "")
        self._update_elide()

    def text(self):
        return self._full

    def resizeEvent(self, event):
        self._update_elide()
        super().resizeEvent(event)

    def _update_elide(self):
        QLabel.setText(
            self,
            self.fontMetrics().elidedText(
                self._full, Qt.ElideRight, max(0, self.contentsRect().width())
            ),
        )
        if self._full:
            self.setToolTip(self._full)


class _MetricCard(QFrame):
    """两列统计卡：圆形图标 chip + 标签/数值 + 渐变进度条。"""

    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionStatCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 8, 9, 9)
        lay.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(4)
        icon_label = QLabel()
        icon_label.setFixedSize(22, 22)
        icon_label.setPixmap(_pixmap(icon, 22))
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        top.addWidget(icon_label)
        self.label = _ElidedLabel(label)
        self.label.setObjectName("EmotionStatLabel")
        top.addWidget(self.label, 1)
        self.value = QLabel("—")
        self.value.setObjectName("EmotionStatValue")
        top.addWidget(self.value)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setObjectName("EmotionMetricBar")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(6)
        lay.addWidget(self.bar)

    def set_metric(self, raw):
        enabled = raw is not None
        self.bar.setValue(max(0, min(100, int(raw))) if enabled else 0)
        self.bar.setEnabled(enabled)
        self.value.setText(f"{int(raw)}/100" if enabled else "未启用")


class _MoodCard(QFrame):
    """情绪卡：图标 + 情绪词 + 五段圆点（点亮数随心情）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionStatCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 8, 9, 9)
        lay.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(5)
        icon_label = QLabel()
        icon_label.setFixedSize(22, 22)
        icon_label.setPixmap(_pixmap("mood_happy", 22))
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        top.addWidget(icon_label)
        label = QLabel("情绪")
        label.setObjectName("EmotionStatLabel")
        top.addWidget(label)
        top.addStretch()
        self.value = QLabel("平静")
        self.value.setObjectName("EmotionStatValue")
        top.addWidget(self.value)
        lay.addLayout(top)
        self.dots = QLabel()
        self.dots.setObjectName("EmotionMoodDots")
        self.dots.setTextFormat(Qt.RichText)
        self.dots.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.dots)
        self.set_mood("neutral")

    def set_mood(self, mood, label=None, locked=False):
        lit = _MOOD_DOTS.get(mood, 3)
        on = '<span style="color:#f3b5ff;">●</span>'
        off = '<span style="color:rgba(255,255,255,0.30);">●</span>'
        self.dots.setText("&#8201;".join([on] * lit + [off] * (5 - lit)))
        if label:
            self.value.setText(label + (" 🔒" if locked else ""))


class _WideCard(QFrame):
    """主动意愿/成功概率整行大卡：图标 + 标签 + 大数值 + 进度条。"""

    def __init__(self, icon, label, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionWideCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 10)
        lay.setSpacing(5)
        top = QHBoxLayout()
        top.setSpacing(7)
        icon_label = QLabel()
        icon_label.setFixedSize(26, 26)
        icon_label.setPixmap(_pixmap(icon, 26))
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        top.addWidget(icon_label)
        self.label = QLabel(label)
        self.label.setObjectName("EmotionWideLabel")
        top.addWidget(self.label)
        top.addStretch()
        self.value = QLabel("—")
        self.value.setObjectName("EmotionWideValue")
        top.addWidget(self.value)
        lay.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setObjectName("EmotionMetricBar")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(7)
        lay.addWidget(self.bar)

    def set_fraction(self, raw):
        enabled = raw is not None
        pct = int(round(float(raw) * 100)) if enabled else 0
        self.bar.setValue(max(0, min(100, pct)))
        self.bar.setEnabled(enabled)
        self.value.setText(f"{float(raw):.2f}/1.00" if enabled else "未启用")


class EmotionSettingsDialog(QDialog):
    """手动设置情感/需求数值（情感面板「设置」入口）。

    主动意愿/成功概率由需求状态自动计算，仅展示不可编辑。"""

    MOODS = [("开心", "happy"), ("平静", "neutral"), ("低落", "sad"), ("生气", "angry")]

    def __init__(self, snapshot, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionSettingsDialog")
        self.setWindowTitle("设置情感数值")
        self.setMinimumWidth(360)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(10)

        title = QLabel("手动设置情感数值")
        title.setObjectName("EmotionDetailsTitle")
        root.addWidget(title)
        note = QLabel("数值仅存于本机，之后的互动会继续更新它们。")
        note.setObjectName("EmotionDetailsNote")
        root.addWidget(note)

        needs_enabled = bool(snapshot.get("needs_enabled"))
        needs = snapshot.get("needs") or {}

        form = QFormLayout()
        form.setSpacing(8)

        self.mood = QComboBox()
        for label, key in self.MOODS:
            self.mood.addItem(label, key)
        idx = self.mood.findData(snapshot.get("mood", "neutral"))
        self.mood.setCurrentIndex(idx if idx >= 0 else 1)
        form.addRow("情绪", self.mood)

        self.energy = self._spin(int(snapshot.get("emotion_energy") or 0))
        form.addRow("精力", self.energy)
        self.affection = self._spin(int(snapshot.get("affection") or 0))
        form.addRow("好感度", self.affection)

        self._needs_spins = {}
        for key, label in (
            ("social", "社交需求"), ("mastery", "掌控成就需求"),
            ("novelty", "新奇需求"), ("rest", "休息需求"), ("loneliness", "孤独感"),
        ):
            spin = self._spin(int(needs.get(key) or 0))
            spin.setEnabled(needs_enabled)
            if not needs_enabled:
                spin.setToolTip("需求系统未启用")
            self._needs_spins[key] = spin
            form.addRow(label, spin)

        self.drive = self._dspin(float(snapshot.get("initiative_drive") or 0.0))
        self.drive.setEnabled(False)
        self.drive.setToolTip("由需求状态自动计算")
        form.addRow("主动意愿（自动）", self.drive)
        self.prob = self._dspin(float(snapshot.get("proactive_success_probability") or 0.0))
        self.prob.setEnabled(False)
        self.prob.setToolTip("由需求状态自动计算")
        form.addRow("成功概率（自动）", self.prob)

        root.addLayout(form)
        if not needs_enabled:
            hint = QLabel("需求系统未启用：只有情绪/精力/好感度可以设置。")
            hint.setObjectName("EmotionDetailsFootnote")
            root.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("DashboardSecondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("DashboardPrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        root.addLayout(buttons)

    @staticmethod
    def _spin(value):
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(max(0, min(100, int(value))))
        return spin

    @staticmethod
    def _dspin(value):
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setValue(max(0.0, min(1.0, float(value))))
        return spin

    def values(self) -> dict:
        out = {
            "mood": self.mood.currentData(),
            "emotion_energy": self.energy.value(),
            "affection": self.affection.value(),
        }
        for key, spin in self._needs_spins.items():
            if spin.isEnabled():
                out[key] = spin.value()
        return out


class EmotionLockDialog(QDialog):
    """勾选哪些情感/需求字段被锁定（锁定的数值不被日常互动自动更新）。"""

    CHOICES = [
        ("mood", "情绪"), ("emotion_energy", "精力"), ("affection", "好感度"),
        ("social", "社交需求"), ("mastery", "掌控成就需求"), ("novelty", "新奇需求"),
        ("rest", "休息需求"), ("loneliness", "孤独感"),
    ]

    def __init__(self, locked, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionLockDialog")
        self.setWindowTitle("锁定情感数值")
        self.setMinimumWidth(320)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(10)

        title = QLabel("锁定数值")
        title.setObjectName("EmotionDetailsTitle")
        root.addWidget(title)
        note = QLabel(
            "勾选的字段不会被日常互动自动更新（相当于定住），"
            "仍可在「设置」里手动修改。"
        )
        note.setWordWrap(True)
        note.setObjectName("EmotionDetailsNote")
        root.addWidget(note)

        self._boxes = {}
        locked = set(locked or [])
        for key, label in self.CHOICES:
            box = QCheckBox(label)
            box.setChecked(key in locked)
            root.addWidget(box)
            self._boxes[key] = box

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        cancel.setObjectName("DashboardSecondaryButton")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton("保存")
        save.setObjectName("DashboardPrimaryButton")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def locked_set(self) -> set:
        return {key for key, box in self._boxes.items() if box.isChecked()}


class EmotionStatusPanel(QFrame):
    """Fixed-width status card; callers provide snapshots from AgentCore."""

    values_edited = pyqtSignal(dict)
    locks_changed = pyqtSignal(set)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("EmotionStatusPanel")
        self.setFixedWidth(348)
        self._snapshot = {}
        self._cards = {}
        self._locked = set()
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        # ── 头部：图标 + 标题 + 详细信息 ──
        header = QHBoxLayout()
        header.setSpacing(6)
        sparkle = QLabel()
        sparkle.setFixedSize(16, 16)
        sparkle.setPixmap(_pixmap("sparkle", 16))
        sparkle.setAttribute(Qt.WA_TransparentForMouseEvents)
        header.addWidget(sparkle)
        self.title = QLabel("情感状态")
        self.title.setObjectName("EmotionPanelTitle")
        header.addWidget(self.title)
        header.addStretch()
        self.details = QPushButton("详细信息")
        self.details.setObjectName("EmotionDetailsButton")
        self.details.setCursor(Qt.PointingHandCursor)
        self.details.clicked.connect(self._show_details)
        header.addWidget(self.details)
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setObjectName("EmotionDetailsButton")
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setToolTip("手动修改情感与需求数值")
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.settings_btn)
        self.lock_btn = QPushButton("锁定")
        self.lock_btn.setObjectName("EmotionDetailsButton")
        self.lock_btn.setCursor(Qt.PointingHandCursor)
        self.lock_btn.setToolTip("锁定数值：不被日常互动自动更新")
        self.lock_btn.clicked.connect(self._open_locks)
        header.addWidget(self.lock_btn)
        root.addLayout(header)

        # ── 档案块：头像（自带光环花饰） + 语录 + 名字 + 心情胶囊 ──
        # 定高容器：防止整列被剩余空间撑开，导致「六花/心情」与头像之间出现大空隙
        profile_card = QFrame()
        profile_card.setObjectName("EmotionProfileBlock")
        profile_card.setFixedHeight(118)
        profile = QHBoxLayout(profile_card)
        profile.setContentsMargins(0, 0, 0, 0)
        profile.setSpacing(10)
        avatar = QLabel()
        avatar.setObjectName("EmotionAvatar")
        avatar.setFixedSize(112, 112)
        avatar.setPixmap(_pixmap("avatar", 110))
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setAttribute(Qt.WA_TransparentForMouseEvents)
        profile.addWidget(avatar, 0, Qt.AlignTop)
        side = QVBoxLayout()
        side.setSpacing(7)
        self.note = QLabel()
        self.note.setObjectName("EmotionQuote")
        self.note.setWordWrap(True)
        side.addWidget(self.note, 0, Qt.AlignTop)
        identity = QHBoxLayout()
        identity.setSpacing(8)
        name = QLabel("六花")
        name.setObjectName("EmotionCharName")
        identity.addWidget(name)
        self.mood = QLabel("♡ 平静")
        self.mood.setObjectName("EmotionMoodPill")
        identity.addWidget(self.mood)
        identity.addStretch()
        side.addLayout(identity)
        side.addStretch()
        profile.addLayout(side, 1)
        root.addWidget(profile_card)

        # ── 两列统计卡：情绪 + 7 项指标 ──
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._mood_card = _MoodCard()
        grid.addWidget(self._mood_card, 0, 0)
        row_specs = [
            ("emotion_energy", "精力"), ("affection", "好感度"),
            ("social", "社交需求"), ("mastery", "掌控成就需求"),
            ("novelty", "新奇需求"), ("rest", "休息需求"), ("loneliness", "孤独感"),
        ]
        positions = [(0, 1), (1, 0), (1, 1), (2, 0), (2, 1), (3, 0), (3, 1)]
        for (key, label), pos in zip(row_specs, positions):
            card = _MetricCard(_ICONS.get(key, "mood_happy"), label)
            grid.addWidget(card, *pos)
            self._cards[key] = card
        root.addLayout(grid)

        # ── 整行大卡：主动意愿 / 主动成功概率 ──
        self._drive_card = _WideCard("initiative", "主动意愿")
        root.addWidget(self._drive_card)
        self._success_card = _WideCard("success", "主动成功概率")
        root.addWidget(self._success_card)

        root.addStretch()

        # ── 装饰：右上蝴蝶、左下星光（穿透鼠标，不挡点击） ──
        self._deco_butterfly = QLabel(self)
        self._deco_butterfly.setPixmap(_pixmap("butterfly", 88))
        self._deco_butterfly.setAttribute(Qt.WA_TransparentForMouseEvents)
        butterfly_fx = QGraphicsOpacityEffect(self._deco_butterfly)
        butterfly_fx.setOpacity(0.45)
        self._deco_butterfly.setGraphicsEffect(butterfly_fx)
        self._deco_sparkle = QLabel(self)
        self._deco_sparkle.setPixmap(_pixmap("sparkle", 60))
        self._deco_sparkle.setAttribute(Qt.WA_TransparentForMouseEvents)
        sparkle_fx = QGraphicsOpacityEffect(self._deco_sparkle)
        sparkle_fx.setOpacity(0.35)
        self._deco_sparkle.setGraphicsEffect(sparkle_fx)
        self._place_decorations()

    def _place_decorations(self):
        pm = self._deco_butterfly.pixmap()
        if pm and not pm.isNull():
            self._deco_butterfly.move(self.width() - pm.width() - 2, 88)
        pm = self._deco_sparkle.pixmap()
        if pm and not pm.isNull():
            self._deco_sparkle.move(2, self.height() - pm.height() - 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_decorations()

    def sizeHint(self):
        return QSize(348, 780)

    def _show_details(self):
        EmotionDetailsDialog(self._snapshot, self).exec_()

    def _open_settings(self):
        dialog = EmotionSettingsDialog(self._snapshot, self)
        if dialog.exec_() == QDialog.Accepted:
            self.values_edited.emit(dialog.values())

    def _open_locks(self):
        dialog = EmotionLockDialog(self._locked, self)
        if dialog.exec_() == QDialog.Accepted:
            self.set_locked(dialog.locked_set())
            self.locks_changed.emit(self._locked)

    def set_locked(self, locked):
        """更新锁定的字段集合并刷新面板（🔒 标记 + 按钮计数）。"""
        self._locked = {k for k in (locked or set())}
        n = len(self._locked)
        self.lock_btn.setText(f"已锁 {n}" if n else "锁定")
        self.lock_btn.setToolTip(
            "已锁定：" + "、".join(
                label for key, label in EmotionLockDialog.CHOICES if key in self._locked
            ) if n else "锁定数值：不被日常互动自动更新"
        )
        if self._snapshot:
            self.refresh(self._snapshot)

    def refresh(self, snapshot):
        self._snapshot = dict(snapshot or {})
        mood = self._snapshot.get("mood", "neutral")
        self.setProperty("mood", mood)
        mood_label = self._snapshot.get("mood_label", "平静")
        self.mood.setText(f"♡ {mood_label}")
        note = str(self._snapshot.get("mood_note", "") or "").strip()
        self.note.setText(f"「{note}」" if note else f"「{_FALLBACK_QUOTE}」")
        self._mood_card.set_mood(mood, mood_label, "mood" in self._locked)
        needs = self._snapshot.get("needs") or {}
        for key, card in self._cards.items():
            raw = self._snapshot.get(key) if key in ("emotion_energy", "affection") else needs.get(key)
            card.set_metric(raw)
            if key in self._locked and raw is not None:
                card.value.setText(f"{card.value.text()} 🔒")
        self._drive_card.set_fraction(self._snapshot.get("initiative_drive"))
        self._success_card.set_fraction(self._snapshot.get("proactive_success_probability"))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
