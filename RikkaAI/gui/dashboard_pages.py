"""Full-screen history, memory, and settings dashboards."""

import json
import os
import re
from collections import Counter
from datetime import date, datetime, timedelta

from PyQt5.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QShortcut,
    QSlider,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import config
import brain.history as history
import gui.theme_manager as theme_manager
from brain import memory_vault
from gui.chat_top_bar import ChatTopBar
from gui.settings_assets import (
    settings_asset_icon, settings_asset_pixmap, tinted_settings_asset_icon,
)
from gui.settings_widgets import PresetEditDialog, PresetItemWidget
from gui.surf_history_dialog import SurfTagRow, tag_row_size


OUTLINE_DIR = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")
STORAGE_REFERENCE_BYTES = 1024 ** 3


def icon_path(name):
    return os.path.join(OUTLINE_DIR, f"{name}.svg")


def settings_preview_pixmap(kind):
    """Create a compact theme preview without adding another binary asset."""
    pixmap = QPixmap(112, 58)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    if kind == "六花主题":
        source = QPixmap(os.path.join(config.ASSETS_DIR, "images", "home", "home_background.png"))
        if not source.isNull():
            painter.drawPixmap(pixmap.rect(), source, source.rect())
        else:
            painter.fillRect(pixmap.rect(), QColor("#8c66df"))
    else:
        palettes = {
            "跟随系统": ("#f8f5ff", "#ddd4f7"),
            "浅色模式": ("#fffafd", "#e8ddff"),
            "深色模式": ("#25213d", "#51467d"),
            "星空夜幕": ("#10152f", "#374c92"),
            "城市夜景": ("#25204b", "#7450a0"),
            "自定义背景": ("#6a5e91", "#c4b9e2"),
        }
        gradient = QLinearGradient(0, 0, pixmap.width(), pixmap.height())
        start, end = palettes.get(kind, ("#e8ddff", "#aa8ce8"))
        gradient.setColorAt(0.0, QColor(start))
        gradient.setColorAt(1.0, QColor(end))
        painter.fillRect(pixmap.rect(), gradient)
        painter.setPen(QColor(255, 255, 255, 115))
        for x in range(12, pixmap.width(), 18):
            painter.drawEllipse(x, 12 + (x % 19), 2, 2)
    painter.end()
    return pixmap


def tinted_pixmap(source, color):
    """Tint a transparent glyph while preserving its antialiased shape."""
    result = QPixmap(source.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color))
    painter.end()
    return result


class SettingsTopBar(ChatTopBar):
    """Reference-style split search and window controls for settings."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsTopBar")
        layout = self.layout()
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(3)
        layout.insertStretch(1, 1)

        self.search.setObjectName("SettingsSearch")
        self.search.setFixedSize(528, 46)
        self._shortcut_hint = QLabel("Ctrl + K", self.search)
        self._shortcut_hint.setObjectName("SettingsSearchShortcut")
        self._shortcut_hint.setAlignment(Qt.AlignCenter)
        self._shortcut_hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.search.textChanged.connect(self._update_shortcut_hint)
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.activated.connect(self.search.setFocus)

        action_buttons = [
            button for button in self.findChildren(QPushButton)
            if button.objectName() == "ChatTopAction"
        ]
        for button in action_buttons:
            button.setFixedSize(48, 40)
        if action_buttons:
            action_buttons[-1].setProperty("active", True)

        for button in self.findChildren(QPushButton):
            if button.objectName() == "ChatWindowButton":
                button.setFixedSize(34, 40)
        avatar = self.findChild(QLabel, "ChatTopAvatar")
        if avatar is not None:
            avatar.setFixedSize(30, 30)
        self.status.setFixedWidth(36)
        self.status.setAlignment(Qt.AlignCenter)

    def _update_shortcut_hint(self, text):
        self._shortcut_hint.setVisible(not bool(text))

    def resizeEvent(self, event):
        self._shortcut_hint.setGeometry(self.search.width() - 76, 0, 66, self.search.height())
        super().resizeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(129, 88, 198, 42), 1))
        painter.setBrush(QColor(255, 255, 255, 218))
        painter.drawRoundedRect(QRectF(self.search.geometry()), 15, 15)

        actions = [
            button for button in self.findChildren(QPushButton)
            if button.objectName() == "ChatTopAction"
        ]
        if actions:
            left = max(0, actions[0].geometry().left() - 8)
            controls = QRectF(left, 0, self.width() - left, self.height())
            painter.drawRoundedRect(controls, 13, 13)
        painter.end()


class SettingsToggle(QPushButton):
    """Compact accessible switch used by the appearance cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsToggle")
        self.setCheckable(True)
        self.setFixedSize(38, 20)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0.5, 2.5, self.width() - 1, self.height() - 5)
        painter.setPen(QPen(QColor(124, 79, 215, 92) if self.hasFocus() else Qt.transparent, 1))
        painter.setBrush(QColor(theme_manager.current_accent()) if self.isChecked() else QColor("#ddd5e8"))
        painter.drawRoundedRect(track, 7.5, 7.5)
        diameter = 12
        knob_x = self.width() - diameter - 3 if self.isChecked() else 3
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QRectF(knob_x, 4, diameter, diameter))
        painter.end()


class SettingsNavItem(QWidget):
    """Two-line category item used by the full settings dashboard."""

    def __init__(self, name, detail, icon_name, parent=None):
        super().__init__(parent)
        self._name = name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(10)
        self._icon_name = icon_name
        self._icon = QLabel()
        self._icon.setObjectName("SettingsNavIcon")
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setFixedSize(30, 30)
        layout.addWidget(self._icon)
        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(2)
        title = QLabel(name)
        title.setObjectName("SettingsNavTitle")
        copy.addWidget(title)
        subtitle = QLabel(detail)
        subtitle.setObjectName("SettingsNavDetail")
        subtitle.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        copy.addWidget(subtitle)
        layout.addLayout(copy, 1)
        self.set_active(False)

    def set_active(self, active):
        self.setProperty("active", bool(active))
        pixmap = settings_asset_pixmap(f"nav.{self._icon_name}", QSize(20, 20))
        if active and not pixmap.isNull():
            pixmap = tinted_pixmap(pixmap, "#ffffff")
        elif not pixmap.isNull():
            pixmap = tinted_pixmap(pixmap, theme_manager.current_accent())
        self._icon.setPixmap(pixmap)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


def directory_size(path):
    total = 0
    if os.path.isdir(path):
        for root, _, filenames in os.walk(path):
            for filename in filenames:
                try:
                    total += os.path.getsize(os.path.join(root, filename))
                except OSError:
                    pass
    elif os.path.isfile(path):
        try:
            total = os.path.getsize(path)
        except OSError:
            pass
    return total


def format_file_size(size_bytes):
    size = float(max(0, size_bytes))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            decimals = 0 if unit in ("B", "KB") else 1
            return f"{size:.{decimals}f} {unit}"
        size /= 1024


class ElidedLabel(QLabel):
    """Single-line plain-text label that keeps long content readable and safe."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = str(text or "")
        self.setTextFormat(Qt.PlainText)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(self._full_text)
        self._refresh_text()

    def setText(self, text):
        self._full_text = str(text or "")
        self.setToolTip(self._full_text)
        self._refresh_text()

    def resizeEvent(self, event):
        self._refresh_text()
        super().resizeEvent(event)

    def _refresh_text(self):
        width = max(0, self.contentsRect().width())
        text = self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width)
        QLabel.setText(self, text)


def add_group_header(list_widget, text):
    item = QListWidgetItem()
    item.setFlags(Qt.NoItemFlags)
    item.setData(Qt.UserRole, "group")
    item.setSizeHint(QSize(0, 34))
    label = QLabel(str(text))
    label.setObjectName("DashboardGroupHeader")
    label.setContentsMargins(8, 0, 0, 0)
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    list_widget.addItem(item)
    list_widget.setItemWidget(item, label)


class DashboardPage(QFrame):
    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    window_action = pyqtSignal(str)
    window_drag = pyqtSignal(int, int, str)

    def __init__(self, object_name, title, subtitle, icon_name, parent=None,
                 top_bar_cls=ChatTopBar):
        super().__init__(parent)
        self.setObjectName(object_name)
        self._background = QPixmap(
            os.path.join(config.ASSETS_DIR, "images", "home", "home_background.png")
        )
        self._background_wash = QColor(247, 243, 255, 76)
        self._overlay = QGridLayout(self)
        self._overlay.setContentsMargins(0, 0, 0, 0)
        self._overlay.setSpacing(0)

        self.content = QWidget()
        self.content.setObjectName("DashboardContent")
        self.root = QVBoxLayout(self.content)
        self.root.setContentsMargins(214, 66, 18, 18)
        self.root.setSpacing(12)
        self.root.addLayout(self._build_heading(title, subtitle, icon_name))

        self.top_bar = top_bar_cls()
        self.top_bar.search.setFixedWidth(350)
        self.top_bar.history_requested.connect(self.history_requested.emit)
        self.top_bar.memo_requested.connect(self.memo_requested.emit)
        self.top_bar.tools_requested.connect(self.tools_requested.emit)
        self.top_bar.settings_requested.connect(self.settings_requested.emit)
        self.top_bar.window_action.connect(self.window_action.emit)
        self.top_bar.window_drag.connect(self.window_drag.emit)
        self._overlay.addWidget(self.content, 0, 0)
        self._overlay.addWidget(self.top_bar, 0, 0, Qt.AlignTop | Qt.AlignRight)

    def _build_heading(self, title, subtitle, icon_name):
        row = QHBoxLayout()
        self.heading_row = row
        row.setSpacing(12)
        badge = QLabel()
        badge.setObjectName("DashboardTitleIcon")
        badge.setPixmap(QIcon(icon_path(icon_name)).pixmap(25, 25))
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(42, 42)
        row.addWidget(badge)
        copy = QVBoxLayout()
        copy.setSpacing(3)
        heading = QLabel(title)
        heading.setObjectName("DashboardTitle")
        copy.addWidget(heading)
        hint = QLabel(subtitle)
        hint.setObjectName("DashboardSubtitle")
        copy.addWidget(hint)
        row.addLayout(copy)
        row.addStretch()
        return row

    def add_heading_action(self, widget):
        """Append a page-level action to the shared heading row."""
        self.heading_row.addWidget(widget)

    def card(self, width=0):
        widget = QFrame()
        widget.setObjectName("DashboardGlassCard")
        if width:
            widget.setFixedWidth(width)
        return widget

    def section_row(self, title, action=None, callback=None):
        row = QHBoxLayout()
        label = QLabel(title)
        label.setObjectName("DashboardSectionTitle")
        row.addWidget(label)
        row.addStretch()
        if action:
            button = QPushButton(action)
            button.setObjectName("DashboardTextButton")
            button.setCursor(Qt.PointingHandCursor)
            if callback:
                button.clicked.connect(callback)
            row.addWidget(button)
        return row

    def set_appearance_background(self, pixmap, wash):
        self._background = QPixmap(pixmap)
        self._background_wash = QColor(wash)
        self._background_wash.setAlpha(min(72, self._background_wash.alpha()))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self._background.isNull():
            scaled = self._background.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            x = max(0, (scaled.width() - self.width()) // 2)
            y = max(0, (scaled.height() - self.height()) // 2)
            source = scaled.rect().adjusted(x, y, -x, -y)
            painter.drawPixmap(self.rect(), scaled, source)
        if self._background_wash.alpha():
            painter.fillRect(self.rect(), self._background_wash)


class MiniTrendWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(84)
        self.labels = []
        self.values = []

    def set_data(self, labels, values):
        self.labels, self.values = list(labels), list(values)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        bounds = self.rect().adjusted(12, 12, -12, -24)
        painter.setPen(QPen(QColor(116, 77, 184, 24), 1))
        for step in range(4):
            y = bounds.top() + bounds.height() * step / 3
            painter.drawLine(bounds.left(), int(y), bounds.right(), int(y))
        if not self.values:
            return
        peak = max(max(self.values), 1)
        points = []
        for index, value in enumerate(self.values):
            x = bounds.left() + bounds.width() * index / max(1, len(self.values) - 1)
            y = bounds.bottom() - bounds.height() * value / peak * 0.86
            points.append((x, y))
        painter.setPen(QPen(QColor("#8054df"), 2))
        for index in range(1, len(points)):
            painter.drawLine(int(points[index - 1][0]), int(points[index - 1][1]),
                             int(points[index][0]), int(points[index][1]))
        painter.setBrush(QColor("#8054df"))
        painter.setPen(Qt.NoPen)
        for x, y in points:
            painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
        painter.setPen(QColor("#8c809d"))
        for index, label in enumerate(self.labels):
            x = bounds.left() + bounds.width() * index / max(1, len(self.labels) - 1)
            painter.drawText(QRectF(x - 18, bounds.bottom() + 5, 36, 16), Qt.AlignCenter, str(label))


class DonutWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(100, 100)
        self.value = 0
        self.caption = ""
        self.display_text = "0%"
        self._segments = []  # list of (label, bytes, QColor)

    def set_value(self, value, caption="", display_text=None):
        self.value = max(0, min(100, int(value)))
        self.caption = caption
        self.display_text = str(display_text) if display_text is not None else f"{self.value}%"
        self._segments = []
        self.update()

    def set_segments(self, segments, caption="", display_text=None):
        """Render a multi-segment donut. segments: list of (label, bytes, QColor).

        Total is the sum of all segment bytes; the center shows the overall
        percentage (relative to display_text) and the caption below it."""
        self._segments = list(segments)
        total = sum(seg[1] for seg in self._segments)
        self.caption = caption
        if display_text is not None:
            self.display_text = str(display_text)
        elif total > 0:
            self.display_text = "已存"
        else:
            self.display_text = "暂无数据"
        self.value = 100 if total > 0 else 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(11, 11, 78, 78)
        painter.setPen(QPen(QColor(119, 83, 181, 26), 10, Qt.SolidLine, Qt.RoundCap))
        painter.drawArc(rect, 0, 360 * 16)
        total = sum(seg[1] for seg in self._segments)
        if self._segments and total > 0:
            start = 90 * 16
            for label, byte_count, color in self._segments:
                span = int(round(byte_count / total * 360 * 16))
                if span <= 0:
                    continue
                painter.setPen(QPen(color, 10, Qt.SolidLine, Qt.RoundCap))
                painter.drawArc(rect, start, -span)
                start -= span
        elif self.value > 0:
            painter.setPen(QPen(QColor("#8053df"), 10, Qt.SolidLine, Qt.RoundCap))
            painter.drawArc(rect, 90 * 16, -self.value * 360 * 16 // 100)
        painter.setPen(QColor("#413451"))
        painter.drawText(QRectF(10, 26, 80, 30), Qt.AlignCenter, self.display_text)
        if self.caption:
            painter.setPen(QColor("#8b809a"))
            painter.drawText(QRectF(10, 54, 80, 20), Qt.AlignCenter, self.caption)


class RadialMemoryWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.nodes = []

    def set_nodes(self, nodes):
        self.nodes = list(nodes)[:8]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        # 8 个环绕位置（设计稿：中心「你」+ 7~8 个关联节点）
        positions = (
            (0.50, 0.08), (0.84, 0.24), (0.90, 0.56), (0.72, 0.88),
            (0.28, 0.88), (0.10, 0.56), (0.16, 0.24), (0.50, 0.52),
        )
        count = len(self.nodes)
        for index, name in enumerate(self.nodes[:8]):
            px, py = positions[index % 8]
            # 节点多时用更小的半径防重叠
            radius = 0.86 if count <= 6 else 0.78
            x = cx + (px - 0.5) * self.width() * radius
            y = cy + (py - 0.5) * self.height() * radius
            painter.setPen(QPen(QColor(126, 84, 222, 68), 1))
            painter.drawLine(int(cx), int(cy), int(x), int(y))
            painter.setBrush(QColor(255, 255, 255, 210))
            painter.setPen(QPen(QColor(132, 89, 224, 80), 1))
            painter.drawEllipse(QRectF(x - 25, y - 17, 50, 34))
            painter.setPen(QColor("#7650c9"))
            painter.drawText(QRectF(x - 32, y - 10, 64, 20), Qt.AlignCenter, str(name)[:7])
        painter.setBrush(QColor("#8054df")); painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(cx - 25, cy - 25, 50, 50))
        painter.setPen(QColor("white"))
        painter.drawText(QRectF(cx - 25, cy - 25, 50, 50), Qt.AlignCenter, "你")


class HistoryRow(QWidget):
    open_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self, session, preview, parent=None):
        super().__init__(parent)
        self.session_id = int(session["id"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(13)
        icon = QLabel()
        icon.setObjectName("DashboardRowIcon")
        icon.setPixmap(QIcon(icon_path("chat")).pixmap(19,19))
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(44,44)
        layout.addWidget(icon)
        copy = QVBoxLayout(); copy.setSpacing(8)
        title = ElidedLabel(session.get("title") or "新会话")
        title.setObjectName("HistoryRowTitle")
        title.setFixedHeight(40)
        title.setContentsMargins(0, 4, 0, 4)
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        copy.addWidget(title)
        detail = ElidedLabel(preview or "和六花继续上一次的话题")
        detail.setObjectName("HistoryRowDetail")
        detail.setFixedHeight(30)
        detail.setContentsMargins(0, 2, 0, 2)
        detail.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        copy.addWidget(detail)
        layout.addLayout(copy,1)
        meta = QVBoxLayout(); meta.setSpacing(4)
        time = QLabel(str(session.get("updated_at", ""))[11:16])
        time.setObjectName("DashboardRowMeta"); time.setAlignment(Qt.AlignRight)
        meta.addWidget(time)
        count = QLabel(f"{int(session.get('msg_count',0))} 条消息")
        count.setObjectName("DashboardPill"); count.setAlignment(Qt.AlignCenter)
        meta.addWidget(count)
        layout.addLayout(meta)
        enter = QPushButton()
        enter.setObjectName("DashboardIconButton")
        enter.setIcon(QIcon(icon_path("back")))
        enter.setToolTip("进入会话")
        enter.clicked.connect(lambda: self.open_requested.emit(self.session_id))
        layout.addWidget(enter)
        delete = QPushButton()
        delete.setObjectName("DashboardIconButton")
        delete.setIcon(QIcon(icon_path("delete")))
        delete.setToolTip("删除记录")
        delete.clicked.connect(lambda: self.delete_requested.emit(self.session_id))
        layout.addWidget(delete)


class HistoryPage(DashboardPage):
    session_selected = pyqtSignal(int)
    history_cleared = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("HistoryPage", "历史记录", "回顾与六花的每一次对话，珍藏你的思考与灵感", "history", parent)
        self.top_bar.search.setPlaceholderText("搜索历史记录…")
        self.top_bar.search_changed.connect(self.refresh_data)
        self._active_filter = "全部"
        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        filters = QHBoxLayout(); filters.setSpacing(5)
        self.filter_buttons = []
        for index, text in enumerate(("全部","对话","AI 音乐","其他")):
            button = QPushButton(text); button.setObjectName("DashboardSegment")
            button.setProperty("active", index == 0); button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, value=text: self._set_filter(value))
            filters.addWidget(button); self.filter_buttons.append(button)
        filters.addStretch()
        sort = QPushButton("按时间排序"); sort.setObjectName("DashboardSecondaryButton")
        sort.setIcon(QIcon(icon_path("time"))); filters.addWidget(sort)
        clear = QPushButton("清空记录"); clear.setObjectName("DashboardDangerButton")
        clear.setIcon(QIcon(icon_path("delete"))); clear.clicked.connect(self._clear_all)
        filters.addWidget(clear)
        self.root.addLayout(filters)

        body = QHBoxLayout(); body.setSpacing(12)
        center = self.card(); center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(12,12,12,12)
        self.list = QListWidget(); self.list.setObjectName("DashboardList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.itemDoubleClicked.connect(self._open_item)
        center_layout.addWidget(self.list)
        body.addWidget(center,1)

        self.rail = QWidget(); self.rail.setFixedWidth(285)
        rail = QVBoxLayout(self.rail); rail.setContentsMargins(0,0,0,0); rail.setSpacing(12)
        stats = self.card(); stats_layout=QVBoxLayout(stats); stats_layout.setContentsMargins(15,14,15,15)
        stats_layout.addLayout(self.section_row("历史统计"))
        grid=QGridLayout(); grid.setSpacing(7); self.stat_values=[]
        for i,title in enumerate(("对话总数","消息总量","今日对话","今日消息")):
            tile=QFrame(); tile.setObjectName("DashboardStatTile"); tl=QVBoxLayout(tile); tl.setContentsMargins(10,9,10,9); tl.setSpacing(4)
            cap=QLabel(title); cap.setObjectName("DashboardStatCaption"); tl.addWidget(cap)
            val=QLabel("0"); val.setObjectName("DashboardStatValue"); tl.addWidget(val); self.stat_values.append(val)
            grid.addWidget(tile,i//2,i%2)
        stats_layout.addLayout(grid); rail.addWidget(stats)
        trend=self.card(); trend_layout=QVBoxLayout(trend); trend_layout.setContentsMargins(15,14,15,12)
        trend_layout.addLayout(self.section_row("最近 7 天活跃")); self.trend=MiniTrendWidget(); trend_layout.addWidget(self.trend)
        rail.addWidget(trend,1)
        tags=self.card(); tags_layout=QVBoxLayout(tags); tags_layout.setContentsMargins(15,14,15,12)
        tags_layout.addLayout(self.section_row("最近常用标签")); self.tags_label=QLabel(); self.tags_label.setObjectName("DashboardTags"); self.tags_label.setWordWrap(True)
        tags_layout.addWidget(self.tags_label); rail.addWidget(tags)
        actions=self.card(); actions_layout=QGridLayout(actions); actions_layout.setContentsMargins(12,12,12,12); actions_layout.setSpacing(8)
        for i,(text,icon,slot) in enumerate((("搜索记录","search",lambda:self.top_bar.search.setFocus()),("导出记录","download",self._export_history),("标签筛选","discover",lambda:self._set_filter("其他")),("清空记录","delete",self._clear_all))):
            button=QPushButton(text); button.setObjectName("DashboardActionButton"); button.setIcon(QIcon(icon_path(icon))); button.clicked.connect(slot)
            actions_layout.addWidget(button,i//2,i%2)
        rail.addWidget(actions)
        body.addWidget(self.rail)
        self.root.addLayout(body,1)

    def _set_filter(self, value):
        self._active_filter=value
        for button in self.filter_buttons:
            button.setProperty("active",button.text()==value); button.style().unpolish(button); button.style().polish(button)
        self.refresh_data(self.top_bar.search.text())

    def refresh_data(self, query=None):
        query = self.top_bar.search.text() if query is None else str(query)
        sessions=history.get_sessions(100)
        if query.strip(): sessions=[s for s in sessions if query.lower() in str(s.get("title","")).lower()]
        keywords={"AI 绘画":("画","图","绘"),"AI 音乐":("音乐","歌","旋律"),"工作流":("工作流","自动化"),"插件":("插件",)}
        if self._active_filter in keywords:
            sessions=[s for s in sessions if any(k in str(s.get("title","")) for k in keywords[self._active_filter])]
        elif self._active_filter in ("对话", "其他"):
            # 「对话」= 普通聊天会话（标题不含任何工具类关键词）；「其他」同义兜底
            known=sum((list(v) for v in keywords.values()),[])
            sessions=[s for s in sessions if not any(k in str(s.get("title","")) for k in known)]
        self.list.clear(); last_group=None
        today=date.today(); yesterday=today-timedelta(days=1)
        for session in sessions:
            raw=str(session.get("updated_at","")); group="更早"
            try:
                day=datetime.strptime(raw[:10],"%Y-%m-%d").date()
                group="今天" if day==today else "昨天" if day==yesterday else "更早"
            except ValueError: pass
            if group!=last_group:
                add_group_header(self.list, group); last_group=group
            messages=history.get_messages(int(session["id"])); preview=""
            if messages: preview=str(messages[-1].get("content","")).replace("\n"," ")[:120]
            item=QListWidgetItem(); item.setData(Qt.UserRole,int(session["id"])); item.setSizeHint(QSize(0,112)); self.list.addItem(item)
            widget=HistoryRow(session,preview); widget.open_requested.connect(self.session_selected.emit); widget.delete_requested.connect(self._delete_session)
            self.list.setItemWidget(item,widget)
        if not sessions: self.list.addItem("没有找到历史记录")
        analytics=history.get_chat_analytics(7)
        for label,value in zip(self.stat_values,(analytics["total_sessions"],analytics["total_messages"],analytics["today_sessions"],analytics["today_messages"])): label.setText(f"{value:,}")
        self.trend.set_data(analytics["labels"],analytics["values"])
        words=Counter()
        for session in history.get_sessions(50):
            for word in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}|[\u4e00-\u9fff]{2,6}",str(session.get("title",""))): words[word]+=1
        self.tags_label.setText("   ".join(f"# {word}  {count}" for word,count in words.most_common(7)) or "暂无标签")

    def _open_item(self,item):
        sid=item.data(Qt.UserRole)
        if isinstance(sid,int): self.session_selected.emit(sid)

    def _delete_session(self,sid):
        if QMessageBox.question(self,"删除记录","确定删除这条历史会话吗？",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            history.delete_session(sid); self.refresh_data()

    def _clear_all(self):
        if QMessageBox.question(self,"清空历史","确定删除全部本地会话和消息吗？此操作无法恢复。",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            history.clear_all_sessions(); config.save_user_config({"last_session_id":0}); self.refresh_data(); self.history_cleared.emit()

    def _export_history(self):
        path,_=QFileDialog.getSaveFileName(self,"导出历史记录","RikkaAI-history.json","JSON (*.json)")
        if not path:return
        payload=[]
        for session in history.get_sessions(1000): payload.append({**session,"messages":history.get_messages(session["id"])})
        try:
            with open(path,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
            QMessageBox.information(self,"导出完成",f"已导出 {len(payload)} 个会话")
        except OSError as exc: QMessageBox.warning(self,"导出失败",str(exc))

    def resizeEvent(self,event):
        if hasattr(self,"rail"): self.rail.setVisible(self.width()>=1160)
        super().resizeEvent(event)


class MemoryDayCard(QWidget):
    """按天聚合的记忆卡片：一天一条，卡片内列出当天各时段的记忆（像日记）。
    点击标题栏可折叠/展开。"""

    def __init__(self, day_label, items, expanded=True, parent=None):
        super().__init__(parent)
        self._expanded = expanded
        self.setObjectName("MemoryDayCard")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 标题栏：日期 + 当天条数 + 展开箭头（用 QFrame + 鼠标事件，避免 QPushButton 内置布局干扰）
        self._header = QFrame()
        self._header.setObjectName("MemoryDayHeader")
        self._header.setCursor(Qt.PointingHandCursor)
        self._header.mousePressEvent = lambda e: self._toggle()
        hl = QHBoxLayout(self._header)
        hl.setContentsMargins(14, 9, 12, 9)
        hl.setSpacing(8)
        self._arrow_label = QLabel("▾" if expanded else "▸")
        self._arrow_label.setObjectName("MemoryDayArrow")
        self._arrow_label.setFixedWidth(16)
        hl.addWidget(self._arrow_label)
        day = QLabel(day_label)
        day.setObjectName("MemoryDayTitle")
        hl.addWidget(day)
        hl.addStretch()
        count = QLabel(f"{len(items)} 条记忆")
        count.setObjectName("DashboardMuted")
        hl.addWidget(count)
        outer.addWidget(self._header)

        # 内容区：当天各时段记忆
        self._body = QWidget()
        self._body.setObjectName("MemoryDayBody")
        bl = QVBoxLayout(self._body)
        bl.setContentsMargins(12, 4, 12, 8)
        bl.setSpacing(2)
        for item in items:
            row = QWidget()
            row.setObjectName("MemoryDayItem")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(10)
            t = QLabel(str(item.get("created_at", ""))[11:16] or "--:--")
            t.setObjectName("DashboardRowMeta")
            t.setFixedWidth(48)
            rl.addWidget(t)
            content = ElidedLabel(str(item.get("content", "")).replace("\n", " ")[:160])
            content.setObjectName("MemoryDayText")
            rl.addWidget(content, 1)
            main_cat, sub_cat = memory_vault.normalize_category(str(item.get("category") or ""))
            pill = QLabel(sub_cat or main_cat or "一般")
            pill.setObjectName("DashboardPill")
            pill.setProperty("tone", main_cat if main_cat in memory_vault.MEMORY_CATEGORIES else "一般")
            pill.setAlignment(Qt.AlignCenter)
            rl.addWidget(pill)
            # 收藏星标
            fav = QLabel("★" if item.get("favorite") else "☆")
            fav.setObjectName("MemoryDayFav")
            fav.setAlignment(Qt.AlignCenter)
            fav.setFixedWidth(18)
            fav.setCursor(Qt.PointingHandCursor)
            fav.setToolTip("收藏" if not item.get("favorite") else "取消收藏")
            fid = int(item.get("id") or 0)
            fav.mousePressEvent = lambda e, f=fav, rid=fid: self._toggle_fav(e, f, rid)
            rl.addWidget(fav)
            bl.addWidget(row)
        outer.addWidget(self._body)
        self._body.setVisible(expanded)

    def _toggle_fav(self, event, fav_label, fragment_id):
        new_val = memory_vault.toggle_favorite(fragment_id)
        if new_val is not None:
            fav_label.setText("★" if new_val else "☆")
            fav_label.setToolTip("取消收藏" if new_val else "收藏")

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        self._arrow_label.setText("▾" if self._expanded else "▸")


class MemoryRow(QWidget):
    view_requested = pyqtSignal(int)
    delete_requested = pyqtSignal(int)

    def __init__(self,fragment,parent=None):
        super().__init__(parent)
        self.setObjectName("MemoryTimelineRow")
        self.fragment_id = int(fragment.get("id") or 0)
        layout=QHBoxLayout(self); layout.setContentsMargins(12,7,10,7); layout.setSpacing(9)
        time=QLabel(str(fragment.get("created_at",""))[11:16] or "--:--"); time.setObjectName("DashboardRowMeta"); time.setFixedWidth(42); layout.addWidget(time)
        main_cat, sub_cat = memory_vault.normalize_category(str(fragment.get("category") or ""))
        icon_names={"重要的事":"star","喜好":"favorite","日常":"emoji","系统":"settings"}
        icon=QLabel(); icon.setObjectName("DashboardRowIcon"); icon.setProperty("tone",main_cat); icon.setPixmap(QIcon(icon_path(icon_names.get(main_cat,"memory"))).pixmap(17,17)); icon.setAlignment(Qt.AlignCenter); icon.setFixedSize(34,34); layout.addWidget(icon)
        detail=ElidedLabel(str(fragment.get("content","")).replace("\n"," ")[:220]); detail.setObjectName("MemoryTimelineText"); detail.setToolTip(str(fragment.get("content","") or "")); layout.addWidget(detail,1)
        main_pill = QLabel(main_cat)
        main_pill.setObjectName("DashboardPill")
        main_pill.setProperty("tone", main_cat)
        main_pill.setAlignment(Qt.AlignCenter)
        layout.addWidget(main_pill)
        category = QLabel(sub_cat or main_cat or "一般")
        category.setObjectName("DashboardPill")
        category.setAlignment(Qt.AlignCenter)
        category.setProperty("tone", main_cat)
        layout.addWidget(category)
        favorite = QPushButton("★" if fragment.get("favorite") else "☆")
        favorite.setObjectName("MemoryFavoriteButton")
        favorite.setProperty("active", bool(fragment.get("favorite")))
        favorite.setToolTip("取消收藏" if fragment.get("favorite") else "收藏")
        favorite.clicked.connect(lambda: self._toggle_favorite(favorite))
        layout.addWidget(favorite)
        view = QPushButton()
        view.setObjectName("DashboardIconButton")
        view.setIcon(QIcon(icon_path("discover")))
        view.setToolTip("查看记忆")
        view.clicked.connect(lambda: self.view_requested.emit(self.fragment_id))
        layout.addWidget(view)
        delete = QPushButton()
        delete.setObjectName("DashboardIconButton")
        delete.setIcon(QIcon(icon_path("delete")))
        delete.setToolTip("删除记忆")
        delete.setProperty("tone", "danger")
        delete.clicked.connect(lambda: self.delete_requested.emit(self.fragment_id))
        layout.addWidget(delete)

    def _toggle_favorite(self, button):
        active = memory_vault.toggle_favorite(self.fragment_id)
        if active is None:
            return
        button.setText("★" if active else "☆")
        button.setProperty("active", bool(active))
        button.setToolTip("取消收藏" if active else "收藏")
        button.style().unpolish(button)
        button.style().polish(button)


class MemoryPage(DashboardPage):
    advanced_requested=pyqtSignal()

    def __init__(self,parent=None):
        super().__init__(
            "MemoryPage","记忆","六花记得你的一切，与你共同成长","memory",
            parent, top_bar_cls=SettingsTopBar,
        )
        self.top_bar.search.setPlaceholderText("搜索记忆内容、关键词或标签...")
        self.top_bar.search.setFixedWidth(500)
        self.top_bar.search_changed.connect(self._on_search_changed)
        self._active_filter="全部"
        self._visible_limit=60
        self._build_ui(); self.refresh_data()

    def _build_ui(self):
        new_btn = QPushButton("＋ 新建记忆")
        new_btn.setObjectName("DashboardPrimaryButton")
        new_btn.setCursor(Qt.PointingHandCursor)
        new_btn.clicked.connect(self._new_memory)
        self.add_heading_action(new_btn)

        grid=QGridLayout(); grid.setSpacing(10); self.stat_values=[]
        for i,(title,icon) in enumerate((("总记忆数","ai"),("重要的事","star"),("喜好","favorite"),("日常","emoji"),("系统","settings"))):
            tile=QFrame(); tile.setObjectName("MemoryOverviewTile"); tile.setProperty("tone",icon); tl=QHBoxLayout(tile); tl.setContentsMargins(14,12,14,12); tl.setSpacing(10)
            badge=QLabel(); badge.setPixmap(QIcon(icon_path(icon)).pixmap(20,20)); badge.setObjectName("MemoryTileBadge"); badge.setProperty("tone",icon); badge.setAlignment(Qt.AlignCenter); badge.setFixedSize(38,38); tl.addWidget(badge,0,Qt.AlignVCenter)
            copy=QVBoxLayout(); copy.setSpacing(2); cap=QLabel(title); cap.setObjectName("DashboardStatCaption"); copy.addWidget(cap); val=QLabel("0"); val.setObjectName("DashboardStatValue"); copy.addWidget(val); tl.addLayout(copy)
            tl.addStretch(); grid.addWidget(tile,0,i); self.stat_values.append(val)
        self.root.addLayout(grid)

        body=QHBoxLayout(); body.setSpacing(12)
        self.left=QWidget(); self.left.setFixedWidth(205); left=QVBoxLayout(self.left); left.setContentsMargins(0,0,0,0); left.setSpacing(12)
        quick=self.card(); quick.setFixedHeight(270); ql=QVBoxLayout(quick); ql.setContentsMargins(14,14,14,14); ql.setSpacing(6); ql.setAlignment(Qt.AlignTop); ql.addLayout(self.section_row("记忆快速访问"))
        self.quick_buttons={}
        for text,icon,filter_name in (("重要的事","star","重要的事"),("喜好","favorite","喜好"),("日常","emoji","日常"),("系统","settings","系统")):
            button=QPushButton(text); button.setObjectName("DashboardNavButton"); button.setIcon(QIcon(icon_path(icon))); button.clicked.connect(lambda _=False,v=filter_name:self._set_filter(v)); ql.addWidget(button); self.quick_buttons[filter_name]=button
        left.addWidget(quick)
        storage=self.card(); sl=QVBoxLayout(storage); sl.setContentsMargins(14,14,14,14); sl.setSpacing(8); sl.addLayout(self.section_row("记忆存储"))
        self.storage_donut=DonutWidget(); sl.addWidget(self.storage_donut,0,Qt.AlignHCenter)
        self.legend_rows=[]
        for key,color in (("重要的事","#8150df"),("喜好","#ef7bb4"),("日常","#f4a747"),("系统","#6a7fe0"),("其他","#b49ae8")):
            row=QWidget(); row.setObjectName("MemoryLegendRow"); rh=QHBoxLayout(row); rh.setContentsMargins(6,0,6,0); rh.setSpacing(6)
            dot=QLabel(); dot.setFixedSize(8,8); dot.setStyleSheet(f"background:{color};border-radius:4px;")
            lab=QLabel(key); lab.setObjectName("DashboardMuted"); lab.setStyleSheet("color:#8b809a;font-size:10px;")
            size=QLabel("--"); size.setObjectName("DashboardMuted"); size.setStyleSheet("color:#8b809a;font-size:10px;font-weight:700;"); size.setAlignment(Qt.AlignRight)
            rh.addWidget(dot); rh.addWidget(lab,1); rh.addWidget(size); sl.addWidget(row); self.legend_rows.append((key,size))
        self.storage_text=QLabel(); self.storage_text.setObjectName("DashboardMuted"); self.storage_text.setAlignment(Qt.AlignCenter); sl.addWidget(self.storage_text); left.addWidget(storage)
        body.addWidget(self.left)

        center=self.card(); center_layout=QVBoxLayout(center); center_layout.setContentsMargins(14,12,14,10); center_layout.setSpacing(8)
        filters=QHBoxLayout(); title=QLabel("记忆时间线"); title.setObjectName("DashboardSectionTitle"); filters.addWidget(title); filters.addStretch(); self.filter_buttons=[]
        for index,text in enumerate(("全部","⭐ 收藏","重要的事","喜好","日常","系统")):
            button=QPushButton(text); button.setObjectName("DashboardChip"); button.setProperty("active",index==0); button.clicked.connect(lambda _=False,v=text:self._set_filter(v)); filters.addWidget(button); self.filter_buttons.append(button)
        center_layout.addLayout(filters); self.list=QListWidget(); self.list.setObjectName("DashboardList"); self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.list.setSelectionMode(QListWidget.NoSelection); center_layout.addWidget(self.list)
        self.load_more_btn=QPushButton("加载更多记忆")
        self.load_more_btn.setObjectName("DashboardLoadMore")
        self.load_more_btn.clicked.connect(self._load_more)
        center_layout.addWidget(self.load_more_btn)
        body.addWidget(center,1)

        self.rail=QWidget(); self.rail.setFixedWidth(285); rail=QVBoxLayout(self.rail); rail.setContentsMargins(0,0,0,0); rail.setSpacing(10)
        graph=self.card(); gl=QVBoxLayout(graph); gl.setContentsMargins(14,13,14,13); gl.addLayout(self.section_row("记忆图谱")); self.graph=RadialMemoryWidget(); gl.addWidget(self.graph); rail.addWidget(graph)
        strength=self.card(); stl=QHBoxLayout(strength); stl.setContentsMargins(14,13,14,13); copy=QVBoxLayout(); copy.setSpacing(5); h=QLabel("记忆强度分布"); h.setObjectName("DashboardSectionTitle"); copy.addWidget(h); self.strength_label=QLabel(); self.strength_label.setObjectName("DashboardMuted"); copy.addWidget(self.strength_label); stl.addLayout(copy,1); self.strength=DonutWidget(); stl.addWidget(self.strength); rail.addWidget(strength)
        trend=self.card(); trl=QVBoxLayout(trend); trl.setContentsMargins(14,13,14,13); trl.addLayout(self.section_row("记忆趋势")); self.trend=MiniTrendWidget(); trl.addWidget(self.trend); rail.addWidget(trend,1)
        actions=self.card(); al=QGridLayout(actions); al.setContentsMargins(12,12,12,12); al.setSpacing(8)
        for i,(text,icon,slot) in enumerate((("导出记忆","download",self._export_memories),("整理记忆","refresh",self._consolidate_memories),("记忆设置","settings",self.advanced_requested.emit),("隐私控制","lock",self.advanced_requested.emit))):
            button=QPushButton(text); button.setObjectName("DashboardActionButton"); button.setIcon(QIcon(icon_path(icon))); button.clicked.connect(slot); al.addWidget(button,i//2,i%2)
        rail.addWidget(actions); body.addWidget(self.rail)
        self.root.addLayout(body,1)

        # 装饰元素：从素材图纸裁剪的花朵/蝴蝶，作为覆盖标签叠在卡片之上（鼠标穿透）
        from gui.memory_assets import memory_asset_pixmap
        title_icon = self.findChild(QLabel, "DashboardTitleIcon")
        title_flower = memory_asset_pixmap("flower", QSize(34, 34))
        if title_icon is not None and not title_flower.isNull():
            title_icon.setPixmap(title_flower)
        self._decor_flower_label = QLabel(self)
        self._decor_flower_label.setVisible(False)
        self._decor_flower_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._decor_butterfly_label = QLabel(self)
        self._decor_butterfly_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        butterfly = memory_asset_pixmap("butterfly", QSize(42, 42))
        if not butterfly.isNull():
            self._decor_butterfly_label.setPixmap(butterfly)
            self._decor_butterfly_label.resize(42, 42)
        self._reposition_decor()

    def set_appearance_background(self, pixmap, wash):
        super().set_appearance_background(pixmap, wash)
        from gui.memory_assets import memory_asset_pixmap
        title_icon = self.findChild(QLabel, "DashboardTitleIcon")
        flower = memory_asset_pixmap("flower", QSize(34, 34))
        if title_icon is not None and not flower.isNull():
            title_icon.setPixmap(flower)
        butterfly = memory_asset_pixmap("butterfly", QSize(42, 42))
        if not butterfly.isNull():
            self._decor_butterfly_label.setPixmap(butterfly)
            self._decor_butterfly_label.resize(42, 42)
            self._decor_butterfly_label.show()
        self._reposition_decor()

    def _on_search_changed(self, text):
        self._visible_limit=60
        self.refresh_data(text)

    def _set_filter(self,value):
        self._active_filter=value
        self._visible_limit=60
        for button in self.filter_buttons: button.setProperty("active",button.text()==value); button.style().unpolish(button); button.style().polish(button)
        self.refresh_data(self.top_bar.search.text())

    def _load_more(self):
        self._visible_limit += 60
        self.refresh_data(self.top_bar.search.text())

    def refresh_data(self,query=None):
        query=self.top_bar.search.text() if query is None else str(query)
        fav_only = self._active_filter == "⭐ 收藏"
        try:
            all_fragments=memory_vault.get_recent_fragments(limit=1000)
            fragments=(memory_vault.get_recent_fragments(limit=1000,query=query.strip(),favorite_only=fav_only)
                       if (query.strip() or fav_only) else list(all_fragments))
        except Exception:
            all_fragments=[]; fragments=[]
        if self._active_filter!="全部" and not fav_only:
            fragments=[f for f in fragments if memory_vault.normalize_category(str(f.get("category","")))[0]==self._active_filter]
        if fav_only:
            fragments=[f for f in fragments if f.get("favorite")]
        def _main_cat(fragment):
            return memory_vault.normalize_category(str(fragment.get("category") or ""))[0]
        total=len(all_fragments)
        cat_stats=Counter(_main_cat(fragment) for fragment in all_fragments)
        values=(total,cat_stats.get("重要的事",0),cat_stats.get("喜好",0),cat_stats.get("日常",0),cat_stats.get("系统",0))
        for label,value in zip(self.stat_values,values): label.setText(f"{value:,}")
        for key,button in self.quick_buttons.items():
            button.setText(f"{key}    {cat_stats.get(key,0)}")
            button.setProperty("active",self._active_filter==key)
            button.style().unpolish(button); button.style().polish(button)
        self.list.clear(); last_day=None
        visible=fragments[:self._visible_limit]
        for fragment in visible:
            day=str(fragment.get("created_at",""))[:10] or "较早"
            if day!=last_day:
                if day==date.today().isoformat(): day_label="今天"
                elif day==(date.today()-timedelta(days=1)).isoformat(): day_label="昨天"
                else: day_label=day
                add_group_header(self.list,day_label); last_day=day
            item=QListWidgetItem(); item.setSizeHint(QSize(0,54)); self.list.addItem(item)
            row=MemoryRow(fragment)
            row.view_requested.connect(self._view_memory)
            row.delete_requested.connect(self._delete_memory)
            self.list.setItemWidget(item,row)
        if not fragments:self.list.addItem("没有找到相关记忆")
        remaining=max(0,len(fragments)-len(visible))
        self.load_more_btn.setVisible(remaining>0)
        self.load_more_btn.setText(f"加载更多记忆（还有 {remaining} 条）")
        graph_nodes = []
        for f in all_fragments:
            _, sub = memory_vault.normalize_category(str(f.get("category") or ""))
            if sub and sub not in graph_nodes:
                graph_nodes.append(sub)
        self.graph.set_nodes(graph_nodes[:7])
        weights=[float(f.get("emotional_weight",.5)) for f in all_fragments]
        if weights:
            n=len(weights); strong=int(sum(1 for w in weights if w>=.7)/n*100); mid=int(sum(1 for w in weights if .4<=w<.7)/n*100); weak=max(0,100-strong-mid)
            self.strength.set_value(strong,"强记忆",f"{strong}%"); self.strength_label.setText(f"强记忆 {strong}%\n中等 {mid}%  弱 {weak}%")
        else:
            self.strength.set_value(0,"","暂无"); self.strength_label.setText("暂无记忆")
        daily=Counter(str(f.get("created_at",""))[:10] for f in all_fragments); days=[date.today()-timedelta(days=i) for i in range(6,-1,-1)]; self.trend.set_data([f"{d.month}/{d.day}" for d in days],[daily[d.isoformat()] for d in days])
        used=directory_size(config.MEMORY_DIR); size_text=format_file_size(used)
        buckets=self._category_storage_bytes(all_fragments)
        seg_colors=(("#8150df","重要的事"),("#ef7bb4","喜好"),("#f4a747","日常"),("#6a7fe0","系统"),("#b49ae8","其他"))
        segments=[(label,bytes_,QColor(color)) for color,label in seg_colors if (bytes_:=buckets[label])>0]
        self.storage_donut.set_segments(segments,"本地占用",size_text)
        for label,size_label in self.legend_rows:
            size_label.setText(format_file_size(buckets[label]) if buckets[label] else "--")
        self.storage_text.setText(f"共 {total} 条 · {size_text}"); self.storage_text.setToolTip("根据本地记忆数据库与配置文件实时计算。")

    def _category_storage_bytes(self, fragments):
        """把记忆内容按大类桶累计字节数（重要的事/喜好/日常/系统/其他），供存储圆环分段。"""
        buckets={"重要的事":0,"喜好":0,"日常":0,"系统":0,"其他":0}
        for fragment in fragments:
            main=memory_vault.normalize_category(str(fragment.get("category") or ""))[0]
            key=main if main in buckets else "其他"
            buckets[key]+=len(str(fragment.get("content","")).encode("utf-8"))
        return buckets

    def _consolidate_memories(self):
        try:
            count = memory_vault.consolidate_fragments()
            self.refresh_data()
            QMessageBox.information(self, "整理完成", f"六花整理了 {count} 个记忆主题")
        except Exception as exc:
            QMessageBox.warning(self, "整理失败", str(exc))

    def _new_memory(self):
        """「+ 新建记忆」：弹输入框新增一条记忆（设计稿）。"""
        text, ok = QInputDialog.getMultiLineText(
            self, "新建记忆", "记下这一刻：\n（六花会把它加入记忆时间线）", ""
        )
        if not ok:
            return
        text = (text or "").strip()
        if not text:
            return
        from PyQt5.QtWidgets import QDialog, QComboBox, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("选择分类")
        dl = QVBoxLayout(dlg)
        dl.addWidget(QLabel("分类："))
        combo = QComboBox()
        combo.addItems(["重要的事", "喜好", "日常", "系统"])
        dl.addWidget(combo)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dl.addWidget(btns)
        if dlg.exec_() == QDialog.Accepted:
            memory_vault.add_memory(text, category=combo.currentText())
            self.refresh_data()
            QMessageBox.information(self, "已记住", "六花记住啦～")

    def _export_memories(self):
        path,_=QFileDialog.getSaveFileName(self,"导出记忆","RikkaAI-memories.json","JSON (*.json)")
        if not path:return
        try:
            payload=memory_vault.search("",top_k=1000)
            with open(path,"w",encoding="utf-8") as f:json.dump(payload,f,ensure_ascii=False,indent=2)
            QMessageBox.information(self,"导出完成",f"已导出 {len(payload)} 条记忆")
        except (OSError,ValueError) as exc: QMessageBox.warning(self,"导出失败",str(exc))

    def _view_memory(self, fragment_id):
        """查看单条记忆：取详情后弹详情对话框。"""
        fragment=memory_vault.get_fragment(fragment_id)
        if not fragment:
            QMessageBox.information(self,"查看记忆","这条记忆已经不存在了")
            self.refresh_data(); return
        from gui.memory_detail_dialog import MemoryDetailDialog
        MemoryDetailDialog(fragment, self).exec_()

    def _delete_memory(self, fragment_id):
        """删除单条记忆：确认后删除并刷新。"""
        fragment=memory_vault.get_fragment(fragment_id)
        if not fragment:
            QMessageBox.information(self,"删除记忆","这条记忆已经不存在了")
            self.refresh_data(); return
        title=str(fragment.get("entity") or fragment.get("category") or "这条记忆")
        ret=QMessageBox.question(self,"删除记忆",f"确定要删除「{title}」吗？\n删除后无法恢复。",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if ret!=QMessageBox.Yes:return
        if memory_vault.delete_fragment(fragment_id):
            QMessageBox.information(self,"删除记忆","已删除")
        self.refresh_data()

    def paintEvent(self, event):
        super().paintEvent(event)  # 背景 + wash 由基类绘制

    def _reposition_decor(self):
        """把装饰元素定位到页面角落（卡片之上、鼠标穿透）。"""
        if not hasattr(self, "_decor_flower_label"):
            return
        self._decor_butterfly_label.raise_()
        self._decor_butterfly_label.move(self.width() - 48, self.height() - 78)

    def resizeEvent(self,event):
        if hasattr(self,"rail"): self.rail.setVisible(self.width()>=1180); self.left.setVisible(self.width()>=1040)
        self._reposition_decor()
        super().resizeEvent(event)


class SettingsChoiceCard(QFrame):
    """Clickable visual choice card used for theme modes."""

    selected = pyqtSignal(str)

    def __init__(self, value, title, detail, preview, object_name, compact=False, parent=None):
        super().__init__(parent)
        self.value = value
        self._selected = False
        self._compact_card = bool(compact)
        self.setObjectName(object_name)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(detail or title)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 7 if compact else 8)
        layout.setSpacing(4 if compact else 3)

        image = QLabel()
        self._preview_image = image
        image.setAlignment(Qt.AlignCenter)
        image.setAttribute(Qt.WA_TransparentForMouseEvents)
        image.setPixmap(preview)
        image.setFixedHeight(82 if compact else 72)
        layout.addWidget(image)

        self._check = QLabel("✓", self)
        self._check.setObjectName("SettingsChoiceCheck")
        self._check.setAlignment(Qt.AlignCenter)
        self._check.setFixedSize(20, 20)
        self._check.setVisible(False)

        title_label = QLabel(title)
        title_label.setObjectName("SettingsChoiceTitle")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(title_label)
        if detail:
            detail_label = QLabel(detail)
            self._detail_label = detail_label
            detail_label.setObjectName("SettingsChoiceDetail")
            detail_label.setWordWrap(True)
            detail_label.setAttribute(Qt.WA_TransparentForMouseEvents)
            layout.addWidget(detail_label)

    def set_responsive(self, compact):
        """Shrink choice cards and previews when settings uses a narrow grid."""
        compact = bool(compact)
        if self._compact_card:
            self.setFixedSize(82 if compact else 104, 92 if compact else 130)
            self._preview_image.setFixedHeight(50 if compact else 82)
        else:
            self.setFixedSize(120 if compact else 155, 102 if compact else 142)
            self._preview_image.setFixedHeight(48 if compact else 72)

    def set_selected(self, selected):
        self._selected = bool(selected)
        self._check.setVisible(self._selected)
        self.setProperty("selected", self._selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def is_selected(self):
        return self._selected

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.selected.emit(self.value)
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        self._check.move(self.width() - self._check.width() - 7, 12)
        super().resizeEvent(event)


class SettingsPage(DashboardPage):
    config_changed=pyqtSignal()

    def __init__(self,parent=None):
        super().__init__(
            "SettingsPage", "设置", "定制你的专属 AI 助手六花", "settings",
            parent=parent, top_bar_cls=SettingsTopBar,
        )
        settings_background = QPixmap(os.path.join(
            config.ASSETS_DIR, "images", "settings", "settings_scene_background.png"
        ))
        if not settings_background.isNull():
            self._background = settings_background
        self._background_wash = QColor(0, 0, 0, 0)
        self.top_bar.search.setPlaceholderText("搜索设置项...")
        self._overlay.removeWidget(self.top_bar)
        self.top_bar.setParent(self)
        self.top_bar.raise_()
        self.top_bar.setMinimumWidth(0)
        self.top_bar.setMaximumWidth(1115)
        self.top_bar.search.setMinimumWidth(220)
        self.top_bar.search.setMaximumWidth(528)
        self.top_bar.search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.top_bar.search.setFixedHeight(46)
        self.root.setContentsMargins(278, 78, 18, 18)
        self.root.setSpacing(24)
        self._loading_appearance = False
        title_icon = self.findChild(QLabel, "DashboardTitleIcon")
        if title_icon:
            title_icon.setFixedSize(48, 48)
            title_icon.setPixmap(settings_asset_icon("sidebar.settings").pixmap(28, 28))
        self._build_ui()
        self.top_bar.search_changed.connect(self._filter_settings)
        self.load_settings()
        self._decorate_settings_buttons()

    def set_appearance_background(self, pixmap, wash):
        super().set_appearance_background(pixmap, wash)
        title_icon = self.findChild(QLabel, "DashboardTitleIcon")
        if title_icon is not None:
            title_icon.setPixmap(
                tinted_settings_asset_icon(
                    "sidebar.settings", theme_manager.current_accent()
                ).pixmap(28, 28)
            )
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            widget = self.nav.itemWidget(item)
            if isinstance(widget, SettingsNavItem):
                widget.set_active(index == self.nav.currentRow())
        self._refresh_settings_button_icons()
        if hasattr(self, "_seasonal_toggle") and self._seasonal_toggle.isChecked():
            self._sync_appearance_controls()

    def _build_ui(self):
        body=QHBoxLayout(); body.setSpacing(0); body.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        nav=self.card(255); nav.setObjectName("SettingsNavPanel"); nav.setFixedHeight(737); self._settings_nav_panel = nav; nl=QVBoxLayout(nav); nl.setContentsMargins(10,11,10,10); nl.setSpacing(6)
        categories=(("外观设置","主题模式与视觉效果","theme"),("对话与回复","回复风格、模型参数、对话记忆","chat"),("方案设置","模型预设方案配置","ai"),("智能搜图","搜索参数与视觉分析配置","drawing"),("冲浪设置","六花主动上网冲浪与兴趣标签参数","web"),("记忆与隐私","记忆管理、行为规则、数据导入导出","privacy"),("主动聊天","主动关心、摸鱼彩蛋、开机自启","proactive"),("语音设置","TTS 引擎与变声参数","voice"),("GPT-SoVITS","六花音色合成引擎的推理参数与服务","gptsovits"),("Sleep-time Compute","深度记忆整合与后台反思","time"))
        self.nav=QListWidget(); self.nav.setObjectName("SettingsNavList")
        self.nav.setIconSize(QSize(20,20))
        self._settings_categories = categories
        self._settings_search_terms = (
            "外观 主题 透明 模糊 动画 动态 季节 自动 春夏秋冬",
            "对话 回复 风格 创造力 长度 模型 联网 记忆 引用",
            "方案 预设 模型 API 添加 使用 切换 删除",
            "智能搜图 图片 搜索 候选 视觉 分析 上限 返回",
            "冲浪 上网 B站 视频 推荐 兴趣 标签 冷却 衰减 反馈 间隔 自动",
            "记忆 隐私 数据 权限 人设 行为规则 导入 导出 记录",
            "主动 聊天 关心 摸鱼 彩蛋 开机自启 轮换",
            "语音 TTS 引擎 变声 模型 推理 参数 音色",
            "GPT-SoVITS 六花 合成 引擎 推理 采样 步数 温度 top_k top_p 重复 惩罚 语速 切分 参考 音频 文字 服务 地址 超时",
            "Sleep-time Compute 深度 记忆 整合 后台 反思 凌晨 回溯 天数 模型 DeepSeek 去重 合并 模式 叙事 定时 执行",
        )
        for name, detail, icon in categories:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 56))
            self.nav.addItem(item)
            nav_item = SettingsNavItem(name, detail, icon)
            nav_item.setObjectName("SettingsNavItem")
            self.nav.setItemWidget(item, nav_item)
        self.nav.currentRowChanged.connect(self._switch_page); nl.addWidget(self.nav, 1)

        # Decorative card from the supplied design. It intentionally contains
        # no account or connection status widget — 六花风格的星樱寄语。
        promo = QFrame(); promo.setObjectName("SettingsNavPromo"); promo.setFixedHeight(137)
        promo_layout = QHBoxLayout(promo); promo_layout.setContentsMargins(3, 6, 8, 6); promo_layout.setSpacing(5)
        globe = QLabel(); globe.setPixmap(settings_asset_pixmap("decorative.globe", QSize(100, 116))); globe.setFixedSize(100, 116); globe.setAlignment(Qt.AlignCenter); promo_layout.addWidget(globe)
        promo_copy = QVBoxLayout(); promo_copy.setContentsMargins(0, 18, 0, 0); promo_copy.setSpacing(5)
        promo_title = QLabel("✦ 六花陪伴你的每一天 ✦"); promo_title.setObjectName("SettingsPromoTitle"); promo_copy.addWidget(promo_title)
        promo_detail = QLabel("愿我们的一次次相遇\n都能成为美好的记忆\n—— 邪王真眼，见证着这一切 ——"); promo_detail.setObjectName("SettingsPromoDetail"); promo_detail.setWordWrap(True); promo_copy.addWidget(promo_detail)
        promo_copy.addStretch(); promo_layout.addLayout(promo_copy, 1)
        nl.addWidget(promo)
        body.addWidget(nav, 0, Qt.AlignTop)
        body.addSpacing(17)
        self.pages=QStackedWidget(); self.pages.setObjectName("SettingsPages")
        self.pages.setFixedSize(731, 737)
        self.pages.addWidget(self._appearance_page()); self.pages.addWidget(self._chat_page()); self.pages.addWidget(self._ai_page()); self.pages.addWidget(self._search_page()); self.pages.addWidget(self._surf_page()); self.pages.addWidget(self._privacy_page()); self.pages.addWidget(self._proactive_page()); self.pages.addWidget(self._voice_page()); self.pages.addWidget(self._gptsovits_page()); self.pages.addWidget(self._sleep_compute_page()); body.addWidget(self.pages)
        self._pages_scroll = QScrollArea()
        self._pages_scroll.setObjectName("SettingsPagesScroll")
        self._pages_scroll.setWidgetResizable(False)
        self._pages_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._pages_scroll.setFrameShape(QFrame.NoFrame)
        self._pages_scroll.setWidget(self.pages)
        body.replaceWidget(self.pages, self._pages_scroll)
        self.root.addLayout(body); self.root.addStretch(1); self.nav.setCurrentRow(0)

        # 六花风格装饰：右上角樱花、左下角金星（鼠标穿透，不挡操作）
        self._settings_decor = []
        for text, color, size, x_align_right in (
            ("❀", "#f2a8c8", 34, True),
            ("✦", "#e8c77e", 26, False),
        ):
            deco = QLabel(text, self)
            deco.setStyleSheet(f"color:{color};background:transparent;")
            deco.setFont(self.font())
            f = deco.font(); f.setPointSize(size); deco.setFont(f)
            deco.setAttribute(Qt.WA_TransparentForMouseEvents)
            deco.adjustSize()
            deco.hide()
            self._settings_decor.append((deco, x_align_right))
        self._reposition_settings_decor()

    def _decorate_settings_buttons(self):
        """Attach semantic icons to settings commands instead of text-only controls."""
        rules = (
            (("保存", "应用", "使用"), "action.save"),
            (("添加", "新增", "新建"), "action.add"),
            (("删除", "清空"), "action.delete"),
            (("恢复", "重置", "刷新"), "action.reset"),
            (("导出",), "action.export"),
            (("导入", "上传"), "action.import"),
            (("复制",), "action.copy"),
            (("搜索", "浏览", "选择"), "action.search"),
            (("管理", "编辑"), "action.edit"),
            (("启动", "试听", "测试语音"), "action.voice"),
            (("停止",), "action.stop"),
        )
        for button in self.findChildren(QPushButton):
            if button.objectName() in (
                "ChatTopAction", "ChatWindowButton", "SettingsToggle"
            ):
                continue
            text = button.text().strip()
            icon_name = next(
                (asset for words, asset in rules if any(word in text for word in words)),
                "",
            )
            if not icon_name:
                continue
            button.setProperty("settingsIcon", icon_name)
            button.setIconSize(QSize(15, 15))
        self._refresh_settings_button_icons()

    def _refresh_settings_button_icons(self):
        accent = theme_manager.current_accent()
        for button in self.findChildren(QPushButton):
            icon_name = button.property("settingsIcon")
            if not icon_name:
                continue
            if not button.isEnabled():
                color = "#9b94a6"
            elif button.objectName() == "DashboardPrimaryButton":
                color = "#ffffff"
            elif button.objectName() == "DashboardDangerButton":
                color = "#c54164"
            else:
                color = accent
            button.setIcon(tinted_settings_asset_icon(icon_name, color))

    def _reposition_settings_decor(self):
        try:
            if not hasattr(self, "_settings_decor"):
                return
            for deco, right in self._settings_decor:
                if right:
                    deco.move(self.width() - deco.width() - 26, 66)
                else:
                    deco.move(282, self.height() - deco.height() - 30)
                deco.show()
        except Exception:
            pass

    def _page_shell(self,title,subtitle):
        page=self.card(); page.setObjectName("SettingsMainPanel"); layout=QVBoxLayout(page); layout.setContentsMargins(27,22,27,20); layout.setSpacing(10)
        heading=QLabel(f"❀ {title}"); heading.setObjectName("SettingsPageTitle"); layout.addWidget(heading)
        hint=QLabel(subtitle); hint.setObjectName("SettingsPageSubtitle"); hint.setWordWrap(True); layout.addWidget(hint)
        divider=QFrame(); divider.setObjectName("SettingsPageDivider"); divider.setFixedHeight(1); layout.addWidget(divider)
        return page,layout

    def _appearance_page(self):
        page,layout=self._page_shell("外观设置","自定义界面外观，打造专属的使用体验")
        layout.addSpacing(5)
        auto_card=QFrame(); auto_card.setObjectName("SettingsOptionCard"); auto_card.setFixedHeight(58)
        auto_row=QHBoxLayout(auto_card); auto_row.setContentsMargins(14,8,14,8); auto_row.setSpacing(12)
        auto_copy=QVBoxLayout(); auto_copy.setContentsMargins(0,0,0,0); auto_copy.setSpacing(2)
        auto_title=QLabel("跟随季节自动切换"); auto_title.setObjectName("SettingsFieldLabel"); auto_copy.addWidget(auto_title)
        self._seasonal_status=QLabel(); self._seasonal_status.setObjectName("SettingsSeasonStatus"); auto_copy.addWidget(self._seasonal_status)
        auto_row.addLayout(auto_copy,1)
        self._seasonal_toggle=SettingsToggle(); self._seasonal_toggle.setToolTip("按系统本地日期自动切换春夏秋冬主题")
        self._seasonal_toggle.toggled.connect(self._on_seasonal_mode_changed); auto_row.addWidget(self._seasonal_toggle,0,Qt.AlignVCenter)
        layout.addWidget(auto_card)
        theme_label=QLabel("主题模式"); theme_label.setObjectName("SettingsSubheading"); theme_label.setProperty("compact", True); layout.addWidget(theme_label)
        modes=QGridLayout(); modes.setHorizontalSpacing(16); modes.setVerticalSpacing(10); modes.setAlignment(Qt.AlignLeft); self._theme_choice_layout = modes; self.theme_buttons=[]
        theme_data=(("spring","春季主题","樱花与柔粉色调"),("summer","夏季主题","晴空与清凉水色"),("autumn","秋季主题","枫叶与暖橙色调"),("winter","冬季主题","雪景与清冷蓝色"))
        for value,text,detail in theme_data:
            preview=theme_manager.load_theme_background(
                theme_manager.SEASONAL_THEMES[value], QSize(137,72), page_id="settings"
            )
            button=SettingsChoiceCard(value,text,detail,preview,"SettingsThemeCard")
            button.setFixedSize(155,142); button.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed); button.setMinimumHeight(142); button.selected.connect(self._choose_theme); modes.addWidget(button, 0, len(self.theme_buttons)); self.theme_buttons.append(button)
        layout.addLayout(modes)
        layout.addSpacing(14)
        theme_hint = QLabel("切换主题即可同步更新整套界面的色彩、图标与场景。")
        theme_hint.setObjectName("SettingsPageSubtitle")
        theme_hint.setWordWrap(True)
        layout.addWidget(theme_hint)
        layout.addStretch(); return page

    def _chat_page(self):
        page,layout=self._page_shell("对话设置","调节六花的回复风格、长度和联网能力")
        temp=QFrame(); temp.setObjectName("SettingsOptionCard"); tl=QVBoxLayout(temp); tl.setContentsMargins(14,12,14,12); tl.setSpacing(8); temp_title=QLabel("回复创造力"); temp_title.setObjectName("SettingsFieldLabel"); tl.addWidget(temp_title); self.temperature=QSlider(Qt.Horizontal); self.temperature.setRange(10,100); tl.addWidget(self.temperature); self.temperature_value=QLabel(); self.temperature_value.setObjectName("SettingsFieldValue"); self.temperature.valueChanged.connect(lambda v:self.temperature_value.setText(f"{v/100:.2f}")); tl.addWidget(self.temperature_value,0,Qt.AlignRight); layout.addWidget(temp)
        token=QFrame(); token.setObjectName("SettingsOptionCard"); tr=QHBoxLayout(token); tr.setContentsMargins(14,12,14,12); token_title=QLabel("最大回复长度"); token_title.setObjectName("SettingsFieldLabel"); tr.addWidget(token_title); tr.addStretch(); self.max_tokens=QSpinBox(); self.max_tokens.setRange(512,32768); self.max_tokens.setSingleStep(512); self.max_tokens.setSuffix(" tokens"); tr.addWidget(self.max_tokens); layout.addWidget(token)
        abilities=QFrame(); abilities.setObjectName("SettingsOptionCard"); al=QVBoxLayout(abilities); al.setContentsMargins(14,12,14,12); al.setSpacing(10); self.memory_check=QCheckBox("启用长期记忆与知识图谱"); self.web_check=QCheckBox("允许联网搜索与联网搜图"); self.citations_check=QCheckBox("联网回答附带引用来源"); [al.addWidget(w) for w in (self.memory_check,self.web_check,self.citations_check)]; layout.addWidget(abilities)
        actions=QHBoxLayout(); actions.addStretch(); save=QPushButton("保存设置"); save.setObjectName("DashboardPrimaryButton"); save.clicked.connect(self._save_chat); actions.addWidget(save); layout.addLayout(actions); layout.addStretch(); return page

    def _privacy_page(self):
        page,layout=self._page_shell("记忆与隐私","查看本地数据位置，管理记忆、行为规则与数据")
        scroll=QScrollArea(); scroll.setObjectName("SettingsScrollArea"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner=QWidget(); il=QVBoxLayout(inner); il.setContentsMargins(0,6,6,6); il.setSpacing(9)
        try: stats=memory_vault.get_stats()
        except Exception: stats={"fragments":0,"entities":0}
        db=QFrame(); db.setObjectName("SettingsOptionCard"); dl=QVBoxLayout(db); dl.setContentsMargins(14,12,14,12); dl.setSpacing(6); db_title=QLabel(f"记忆数据库  ·  {stats.get('fragments',0):,} 条记忆 / {stats.get('entities',0):,} 个实体"); db_title.setObjectName("SettingsFieldLabel"); dl.addWidget(db_title); path=QLabel(os.path.join(config.USER_CONFIG_DIR,"rikkai.db")); path.setObjectName("DashboardMuted"); path.setTextInteractionFlags(Qt.TextSelectableByMouse); dl.addWidget(path); il.addWidget(db)
        memo=QFrame(); memo.setObjectName("SettingsOptionCard"); ml=QVBoxLayout(memo); ml.setContentsMargins(14,12,14,12); ml.setSpacing(6); memo_title=QLabel("备忘录与人设文件"); memo_title.setObjectName("SettingsFieldLabel"); ml.addWidget(memo_title); mp=QLabel(os.path.join(config.ROOT_DIR,"persona")); mp.setObjectName("DashboardMuted"); ml.addWidget(mp); il.addWidget(memo)
        persona=QFrame(); persona.setObjectName("SettingsOptionCard"); pal=QVBoxLayout(persona); pal.setContentsMargins(14,12,14,12); pal.setSpacing(6)
        persona_title=QLabel("行为规则"); persona_title.setObjectName("SettingsFieldLabel"); pal.addWidget(persona_title)
        persona_hint=QLabel("直接编辑人设、行为规范和备忘录，让六花变得更像你想要的样子。"); persona_hint.setObjectName("DashboardMuted"); persona_hint.setWordWrap(True); pal.addWidget(persona_hint)
        select_row=QHBoxLayout(); select_row.addWidget(QLabel("当前文件")); self._persona_combo=QComboBox(); persona_dir=os.path.join(config.ROOT_DIR,"persona"); display_names={"character.md":"人设","system_rules.md":"行为规范","memo.md":"备忘录"}
        if os.path.isdir(persona_dir):
            for fname in sorted(os.listdir(persona_dir)):
                if fname.endswith(".md"):
                    self._persona_combo.addItem(display_names.get(fname,fname), os.path.join(persona_dir,fname))
        self._persona_combo.currentIndexChanged.connect(self._load_persona_file); select_row.addWidget(self._persona_combo,1); pal.addLayout(select_row)
        self._readonly_label=QLabel(""); self._readonly_label.setWordWrap(True); self._readonly_label.setObjectName("DashboardMuted"); pal.addWidget(self._readonly_label)
        self._persona_editor=QTextEdit(); self._persona_editor.setObjectName("SettingsPersonaEditor"); self._persona_editor.setMinimumHeight(200); pal.addWidget(self._persona_editor)
        p_actions=QHBoxLayout(); p_actions.addStretch(); reset_btn=QPushButton("恢复默认"); reset_btn.setObjectName("DashboardSecondaryButton"); reset_btn.clicked.connect(self._reset_persona_file); p_actions.addWidget(reset_btn); save_p=QPushButton("保存修改"); save_p.setObjectName("DashboardPrimaryButton"); save_p.clicked.connect(self._save_persona_file); p_actions.addWidget(save_p); pal.addLayout(p_actions)
        il.addWidget(persona)
        auto=QFrame(); auto.setObjectName("SettingsOptionCard"); al=QVBoxLayout(auto); al.setContentsMargins(14,12,14,12); al.setSpacing(8)
        auto_title=QLabel("日记自动收尾"); auto_title.setObjectName("SettingsFieldLabel"); al.addWidget(auto_title)
        auto_hint=QLabel("每天在设定时间自动把当天的对话流水提炼成六花视角的日记；启动时还会补写昨天遗漏的日记。"); auto_hint.setObjectName("DashboardMuted"); auto_hint.setWordWrap(True); al.addWidget(auto_hint)
        self._das_enabled=SettingsToggle(); al.addLayout(self._settings_field("启用自动写日记",self._das_enabled))
        self._das_hour=QComboBox()
        for h in range(24):
            self._das_hour.addItem(f"{h:02d}:00", h)
        al.addLayout(self._settings_field("每天生成时间",self._das_hour))
        auto_actions=QHBoxLayout(); auto_actions.addStretch(); auto_save=QPushButton("保存设置"); auto_save.setObjectName("DashboardPrimaryButton"); auto_save.clicked.connect(self._save_diary_auto); auto_actions.addWidget(auto_save); al.addLayout(auto_actions)
        self._das_enabled.setChecked(bool(getattr(config, "DIARY_AUTO_SUMMARY_ENABLED", True)))
        self._das_hour.setCurrentIndex(int(getattr(config, "DIARY_AUTO_SUMMARY_HOUR", 23)))
        il.addWidget(auto)
        data=QFrame(); data.setObjectName("SettingsOptionCard"); dal=QVBoxLayout(data); dal.setContentsMargins(14,12,14,12); dal.setSpacing(8)
        data_title=QLabel("数据管理"); data_title.setObjectName("SettingsFieldLabel"); dal.addWidget(data_title)
        data_actions=QHBoxLayout(); export=QPushButton("导出设置"); export.setObjectName("DashboardSecondaryButton"); export.clicked.connect(self._export_settings); data_actions.addWidget(export); import_=QPushButton("导入设置"); import_.setObjectName("DashboardSecondaryButton"); import_.clicked.connect(self._import_settings); data_actions.addWidget(import_); clear=QPushButton("清空对话记录"); clear.setObjectName("DashboardDangerButton"); clear.clicked.connect(self._clear_history); data_actions.addWidget(clear); data_actions.addStretch(); dal.addLayout(data_actions)
        il.addWidget(data)
        scroll.setWidget(inner); layout.addWidget(scroll,1)
        if self._persona_combo.count()>0: self._load_persona_file()
        return page

    def _ai_page(self):
        page,layout=self._page_shell("方案设置","管理模型预设方案")
        scroll=QScrollArea(); scroll.setObjectName("SettingsScrollArea"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner=QWidget(); il=QVBoxLayout(inner); il.setContentsMargins(0,6,6,6); il.setSpacing(12)
        preset=QFrame(); preset.setObjectName("SettingsOptionCard"); pl=QVBoxLayout(preset); pl.setContentsMargins(16,14,16,14); pl.setSpacing(8)
        header=QHBoxLayout(); header.setContentsMargins(0,0,0,0); header.setSpacing(14)
        header_copy=QVBoxLayout(); header_copy.setContentsMargins(0,0,0,0); header_copy.setSpacing(3)
        preset_title=QLabel("模型预设方案"); preset_title.setObjectName("SettingsFieldLabel"); header_copy.addWidget(preset_title)
        preset_hint=QLabel("在这里添加多组 API 方案，点击「使用」即可一键切换当前对话模型。"); preset_hint.setObjectName("DashboardMuted"); preset_hint.setWordWrap(True); header_copy.addWidget(preset_hint)
        header.addLayout(header_copy,1)
        top_row=QHBoxLayout(); top_row.setContentsMargins(0,0,0,0); top_row.setSpacing(8); add_btn=QPushButton("+ 添加方案"); add_btn.setObjectName("DashboardSecondaryButton"); add_btn.setFixedSize(104,36); add_btn.clicked.connect(self._on_add_preset); top_row.addWidget(add_btn); self._delete_preset_btn=QPushButton("删除"); self._delete_preset_btn.setObjectName("DashboardSecondaryButton"); self._delete_preset_btn.setFixedSize(80,36); self._delete_preset_btn.setEnabled(False); self._delete_preset_btn.clicked.connect(self._on_del_preset); top_row.addWidget(self._delete_preset_btn); header.addLayout(top_row)
        pl.addLayout(header)
        self._pl=QListWidget(); self._pl.setObjectName("SettingsPresetList"); self._pl.setMinimumHeight(240); self._pl.setSpacing(6); self._pl.setUniformItemSizes(True); self._pl.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self._pl.currentItemChanged.connect(self._on_preset_selection_changed); pl.addWidget(self._pl,1); il.addWidget(preset,1)
        scroll.setWidget(inner); layout.addWidget(scroll,1); return page

    def _search_page(self):
        page,layout=self._page_shell("智能搜图","六花帮你找图时的搜索参数")
        scroll=QScrollArea(); scroll.setObjectName("SettingsScrollArea"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner=QWidget(); il=QVBoxLayout(inner); il.setContentsMargins(0,6,6,6); il.setSpacing(12)
        search=QFrame(); search.setObjectName("SettingsOptionCard"); sl=QVBoxLayout(search); sl.setContentsMargins(16,14,16,14); sl.setSpacing(8)
        search_title=QLabel("搜索参数"); search_title.setObjectName("SettingsFieldLabel"); sl.addWidget(search_title)
        search_hint=QLabel("候选越多越容易找到合适的图，但整体也会更慢；「视觉分析上限」控制逐图用 AI 理解的张数。"); search_hint.setObjectName("DashboardMuted"); search_hint.setWordWrap(True); sl.addWidget(search_hint)
        self._smr=self._make_settings_spinbox(1,10," 张"); sl.addLayout(self._settings_field("返回图片数",self._smr))
        self._smc=self._make_settings_spinbox(5,50," 张"); sl.addLayout(self._settings_field("SearXNG 候选",self._smc))
        self._sma=self._make_settings_spinbox(3,30," 张"); sl.addLayout(self._settings_field("视觉分析上限",self._sma))
        note=QLabel("提示：需要本地运行 SearXNG 实例（默认 http://localhost:8080）。"); note.setObjectName("DashboardMuted"); note.setWordWrap(True); sl.addWidget(note)
        il.addWidget(search)
        actions=QHBoxLayout(); actions.addStretch(); save=QPushButton("保存设置"); save.setObjectName("DashboardPrimaryButton"); save.clicked.connect(self._save_smart_search); actions.addWidget(save); il.addLayout(actions); il.addStretch()
        scroll.setWidget(inner); layout.addWidget(scroll,1); return page

    def _surf_page(self):
        page,layout=self._page_shell("冲浪设置","让六花定期主动去B站冲浪、按兴趣挑视频推荐给你")
        scroll=QScrollArea(); scroll.setObjectName("SettingsScrollArea"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner=QWidget(); il=QVBoxLayout(inner); il.setContentsMargins(0,6,6,6); il.setSpacing(10)
        # 主动冲浪节奏
        rhythm=QFrame(); rhythm.setObjectName("SettingsOptionCard"); rl=QVBoxLayout(rhythm); rl.setContentsMargins(14,12,14,12); rl.setSpacing(8)
        rhythm_title=QLabel("主动冲浪"); rhythm_title.setObjectName("SettingsFieldLabel"); rl.addWidget(rhythm_title)
        rhythm_hint=QLabel("开启后，六花每隔一段时间会偷偷去B站逛一圈，挑最感兴趣的话题找视频，然后以消息形式推荐给你。"); rhythm_hint.setObjectName("DashboardMuted"); rhythm_hint.setWordWrap(True); rl.addWidget(rhythm_hint)
        self._surf_enabled=SettingsToggle(); rl.addLayout(self._settings_field("启用主动冲浪",self._surf_enabled))
        self._surf_interval=self._make_settings_spinbox(1,1440," 分钟"); rl.addLayout(self._settings_field_hint("冲浪间隔",self._surf_interval,"每隔多久去冲浪一次。调小=更频繁地主动推荐（想测试就调 1 分钟），调大=更安静。默认 180 分钟（3小时）。"))
        self._surf_tags_round=self._make_settings_spinbox(1,10," 个"); rl.addLayout(self._settings_field_hint("每次挑标签数",self._surf_tags_round,"每次冲浪随机挑几个兴趣标签去搜。挑得越多，一次推荐越丰富。默认 4 个。"))
        self._surf_limit=self._make_settings_spinbox(1,10," 条"); rl.addLayout(self._settings_field_hint("单标签最多条数",self._surf_limit,"每个标签最多推荐几条。星级高的标签会优先拿满配额（3★以上 2 条、其余 1 条）。默认 2 条。"))
        il.addWidget(rhythm)
        # 兴趣标签参数
        tag=QFrame(); tag.setObjectName("SettingsOptionCard"); tl=QVBoxLayout(tag); tl.setContentsMargins(14,12,14,12); tl.setSpacing(8)
        tag_title=QLabel("兴趣标签参数"); tag_title.setObjectName("SettingsFieldLabel"); tl.addWidget(tag_title)
        tag_hint=QLabel("六花用兴趣标签决定冲浪时搜什么。分数越高越常被选中；点 👍/👎 会调整标签分数，太久没搜的标签会慢慢衰减。"); tag_hint.setObjectName("DashboardMuted"); tag_hint.setWordWrap(True); tl.addWidget(tag_hint)
        self._surf_cooldown=self._make_settings_spinbox(0,168," 小时"); tl.addLayout(self._settings_field_hint("标签搜索冷却",self._surf_cooldown,"同一个标签搜过一次后，多久内不再重复搜它。调 0=不冷却（测试用，可每分钟重复搜）。默认 48 小时。"))
        self._surf_decay=self._make_settings_spinbox(0,20," 分/周"); tl.addLayout(self._settings_field_hint("分数衰减",self._surf_decay,"标签分数每 7 天自然衰减多少分，让旧兴趣慢慢让位给新兴趣。调 0=不衰减。默认 3 分。"))
        self._surf_liked=self._make_settings_spinbox(1,50," 分"); tl.addLayout(self._settings_field_hint("👍 加分",self._surf_liked,"你点 👍 时，这条记录对应的兴趣标签加多少分。默认 10 分。"))
        self._surf_disliked=self._make_settings_spinbox(1,50," 分"); tl.addLayout(self._settings_field_hint("👎 扣分",self._surf_disliked,"你点 👎 时，这条记录对应的兴趣标签扣多少分。默认 5 分。"))
        il.addWidget(tag)
        # 兴趣标签管理
        manage=QFrame(); manage.setObjectName("SettingsOptionCard"); ml=QVBoxLayout(manage); ml.setContentsMargins(14,12,14,12); ml.setSpacing(8)
        manage_header=QHBoxLayout(); manage_header.setSpacing(8)
        manage_title=QLabel("兴趣标签"); manage_title.setObjectName("SettingsFieldLabel"); manage_header.addWidget(manage_title)
        manage_header.addStretch()
        self._surf_tag_input=QLineEdit(); self._surf_tag_input.setObjectName("SettingsLineEdit"); self._surf_tag_input.setPlaceholderText("添加兴趣标签…"); self._surf_tag_input.setClearButtonEnabled(True); manage_header.addWidget(self._surf_tag_input,1)
        add_btn=QPushButton("添加"); add_btn.setObjectName("DashboardSecondaryButton"); add_btn.setCursor(Qt.PointingHandCursor); add_btn.clicked.connect(self._on_surf_add_tag); manage_header.addWidget(add_btn)
        ml.addLayout(manage_header)
        self._surf_tag_list=QListWidget(); self._surf_tag_list.setObjectName("SurfTagList"); self._surf_tag_list.setSelectionMode(QListWidget.NoSelection); self._surf_tag_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self._surf_tag_list.setMinimumHeight(120); ml.addWidget(self._surf_tag_list)
        manage_note=QLabel("标签也可在「冲浪记录」页管理。手动添加的标签会优先成为六花的冲浪话题。"); manage_note.setObjectName("DashboardMuted"); manage_note.setWordWrap(True); ml.addWidget(manage_note)
        il.addWidget(manage)
        actions=QHBoxLayout(); actions.addStretch(); save=QPushButton("保存设置"); save.setObjectName("DashboardPrimaryButton"); save.clicked.connect(self._save_surf); actions.addWidget(save); il.addLayout(actions); il.addStretch()
        scroll.setWidget(inner); layout.addWidget(scroll,1)
        self._refresh_surf_tags()
        return page

    def _on_surf_add_tag(self):
        from brain import surf as surf_mod
        kw=self._surf_tag_input.text().strip()
        if not kw: return
        surf_mod.get_store().add_tag(kw, source="manual")
        self._surf_tag_input.clear(); self._refresh_surf_tags()

    def _on_surf_toggle_tag(self, keyword):
        from brain import surf as surf_mod
        store=surf_mod.get_store()
        paused=any(t["keyword"]==keyword and t.get("status")=="paused" for t in store.get_tags())
        (store.resume_tag if paused else store.pause_tag)(keyword)
        self._refresh_surf_tags()

    def _on_surf_delete_tag(self, keyword):
        from brain import surf as surf_mod
        surf_mod.get_store().remove_tag(keyword)
        self._refresh_surf_tags()

    def _refresh_surf_tags(self):
        from brain import surf as surf_mod
        self._surf_tag_list.clear()
        for tag in surf_mod.get_store().get_tags():
            item=QListWidgetItem(); item.setSizeHint(tag_row_size())
            self._surf_tag_list.addItem(item)
            self._surf_tag_list.setItemWidget(item, SurfTagRow(tag, self._on_surf_toggle_tag, self._on_surf_delete_tag))
        if not surf_mod.get_store().get_tags():
            empty=QListWidgetItem("还没有兴趣标签～ 在上面输入一个试试，或让六花去冲浪几次自动积累。")
            empty.setTextAlignment(Qt.AlignCenter)
            self._surf_tag_list.addItem(empty)

    def _save_surf(self):
        config.save_user_config({
            "surf_auto_enabled": self._surf_enabled.isChecked(),
            "surf_auto_interval_min": self._surf_interval.value(),
            "surf_tags_per_round": self._surf_tags_round.value(),
            "surf_search_limit": self._surf_limit.value(),
            "surf_tag_cooldown_hours": self._surf_cooldown.value(),
            "surf_tag_decay_per_7_days": self._surf_decay.value(),
            "surf_reaction_liked": self._surf_liked.value(),
            "surf_reaction_disliked": self._surf_disliked.value(),
        }); self.config_changed.emit(); QMessageBox.information(self,"已保存","冲浪设置已更新（下一次冲浪生效）")

    def _proactive_page(self):
        page,layout=self._page_shell("主动聊天","让六花在恰当的时候回来找你，也能决定是否开启摸鱼彩蛋")
        basic=QFrame(); basic.setObjectName("SettingsOptionCard"); bl=QVBoxLayout(basic); bl.setContentsMargins(14,12,14,12); bl.setSpacing(8)
        self._pcb=QCheckBox("开启链式主动关心"); bl.addWidget(self._pcb)
        self._qqcb=QCheckBox("主动消息同步发QQ"); bl.addWidget(self._qqcb)
        self._ascb=QCheckBox("开机自启"); bl.addWidget(self._ascb)
        self._rt=self._make_settings_spinbox(5,100," 轮后新会话"); bl.addLayout(self._settings_field("自动轮换",self._rt)); layout.addWidget(basic)
        slack=QFrame(); slack.setObjectName("SettingsOptionCard"); sl2=QVBoxLayout(slack); sl2.setContentsMargins(14,12,14,12); sl2.setSpacing(8)
        slack_title=QLabel("摸鱼彩蛋"); slack_title.setObjectName("SettingsFieldLabel"); sl2.addWidget(slack_title)
        hint=QLabel("允许六花偶尔偷看屏幕，做更有趣的主动搭话。"); hint.setObjectName("DashboardMuted"); sl2.addWidget(hint)
        self._slack_cb=QCheckBox("启用摸鱼彩蛋"); sl2.addWidget(self._slack_cb)
        self._sp=self._make_settings_spinbox(5,100," %"); sl2.addLayout(self._settings_field("触发概率",self._sp))
        self._sc=self._make_settings_spinbox(5,300," 分钟"); sl2.addLayout(self._settings_field("观察冷却",self._sc)); layout.addWidget(slack)
        actions=QHBoxLayout(); actions.addStretch(); save=QPushButton("保存设置"); save.setObjectName("DashboardPrimaryButton"); save.clicked.connect(self._save_proactive); actions.addWidget(save); layout.addLayout(actions); layout.addStretch(); return page

    def _voice_page(self):
        page,layout=self._page_shell("语音设置","本地TTS合成干声 + DDSP变声成六花音色。六花自己决定何时开口（speak 工具）。")
        scroll=QScrollArea(); scroll.setObjectName("SettingsScrollArea"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner=QWidget(); il=QVBoxLayout(inner); il.setContentsMargins(0,6,6,6); il.setSpacing(10)
        switch=QFrame(); switch.setObjectName("SettingsOptionCard"); wl=QVBoxLayout(switch); wl.setContentsMargins(14,12,14,12); wl.setSpacing(6)
        self._voice_enabled=SettingsToggle(); wl.addLayout(self._settings_field("启用六花语音",self._voice_enabled)); il.addWidget(switch)
        model=QFrame(); model.setObjectName("SettingsOptionCard"); ml=QVBoxLayout(model); ml.setContentsMargins(14,12,14,12); ml.setSpacing(6)
        model_title=QLabel("DDSP 变声模型"); model_title.setObjectName("SettingsFieldLabel"); ml.addWidget(model_title)
        model_hint=QLabel("六花音色的训练模型（.pt 文件）路径。"); model_hint.setObjectName("DashboardMuted"); ml.addWidget(model_hint)
        self._voice_model=QLineEdit(); self._voice_model.setObjectName("SettingsLineEdit"); ml.addWidget(self._voice_model); il.addWidget(model)
        tts=QFrame(); tts.setObjectName("SettingsOptionCard"); ttl=QVBoxLayout(tts); ttl.setContentsMargins(14,12,14,12); ttl.setSpacing(6)
        tts_title=QLabel("TTS 引擎"); tts_title.setObjectName("SettingsFieldLabel"); ttl.addWidget(tts_title)
        tts_hint=QLabel("gptsovits=用六花微调模型直接合成她的声音(推荐,免DDSP)；vits=MeloTTS干声+DDSP变声；kokoro=24kHz轻量。"); tts_hint.setObjectName("DashboardMuted"); tts_hint.setWordWrap(True); ttl.addWidget(tts_hint)
        self._voice_engine=QComboBox(); self._voice_engine.addItem("gptsovits (六花定制音色)","gptsovits"); self._voice_engine.addItem("vits (MeloTTS 44.1kHz)","vits"); self._voice_engine.addItem("kokoro (24kHz 轻量)","kokoro"); ttl.addLayout(self._settings_field("引擎",self._voice_engine)); il.addWidget(tts)
        infer=QFrame(); infer.setObjectName("SettingsOptionCard"); infl=QVBoxLayout(infer); infl.setContentsMargins(14,12,14,12); infl.setSpacing(6)
        infer_title=QLabel("推理参数"); infer_title.setObjectName("SettingsFieldLabel"); infl.addWidget(infer_title)
        infer_hint=QLabel("影响合成速度与听感，通常保持默认即可。"); infer_hint.setObjectName("DashboardMuted"); infl.addWidget(infer_hint)
        self._voice_step=self._make_settings_spinbox(1,200," 步"); infl.addLayout(self._settings_field("推理步数",self._voice_step))
        self._voice_method=QComboBox(); self._voice_method.addItems(["euler","rk4"]); infl.addLayout(self._settings_field("采样器",self._voice_method))
        self._voice_ts=QDoubleSpinBox(); self._voice_ts.setRange(0.0,1.0); self._voice_ts.setSingleStep(0.1); infl.addLayout(self._settings_field("t_start",self._voice_ts))
        self._voice_key=self._make_settings_spinbox(-12,12," 半音"); infl.addLayout(self._settings_field("音高偏移",self._voice_key)); il.addWidget(infer)
        speech=QFrame(); speech.setObjectName("SettingsOptionCard"); sfl=QVBoxLayout(speech); sfl.setContentsMargins(14,12,14,12); sfl.setSpacing(6)
        speech_title=QLabel("说话偏好"); speech_title.setObjectName("SettingsFieldLabel"); sfl.addWidget(speech_title)
        self._voice_lang=QComboBox(); self._voice_lang.addItem("日本語（日语）","ja"); self._voice_lang.addItem("中文","zh"); sfl.addLayout(self._settings_field("六花语言",self._voice_lang))
        self._voice_max_chars=self._make_settings_spinbox(10,300," 字"); sfl.addLayout(self._settings_field("单次最长字数",self._voice_max_chars))
        self._voice_speed=QDoubleSpinBox(); self._voice_speed.setRange(0.5,2.0); self._voice_speed.setSingleStep(0.1); sfl.addLayout(self._settings_field("TTS 语速",self._voice_speed)); il.addWidget(speech)
        post=QFrame(); post.setObjectName("SettingsOptionCard"); pol=QVBoxLayout(post); pol.setContentsMargins(14,12,14,12); pol.setSpacing(6)
        post_title=QLabel("高频压平（降电音）"); post_title.setObjectName("SettingsFieldLabel"); pol.addWidget(post_title)
        post_hint=QLabel("对合成成品（gptsovits/vits/kokoro 都生效）做温和低通，压掉 vocoder 高频毛刺和电音感。若听感发闷可调高截止频率或关掉。"); post_hint.setObjectName("DashboardMuted"); post_hint.setWordWrap(True); pol.addWidget(post_hint)
        self._voice_lowpass=SettingsToggle(); pol.addLayout(self._settings_field("启用高频压平",self._voice_lowpass))
        self._voice_lowpass_cutoff=self._make_settings_spinbox(5000,18000," Hz"); pol.addLayout(self._settings_field("截止频率",self._voice_lowpass_cutoff)); il.addWidget(post)
        actions=QHBoxLayout(); actions.addStretch(); save=QPushButton("保存设置"); save.setObjectName("DashboardPrimaryButton"); save.clicked.connect(self._save_voice_settings); actions.addWidget(save); il.addLayout(actions)
        scroll.setWidget(inner); layout.addWidget(scroll,1); return page

    def _gptsovits_page(self):
        page,layout=self._page_shell("GPT-SoVITS 设置","六花定制音色引擎（v4）的详细参数。改动保存后对下一次合成生效，无需重启服务。")
        scroll=QScrollArea(); scroll.setObjectName("SettingsScrollArea"); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        inner=QWidget(); il=QVBoxLayout(inner); il.setContentsMargins(0,6,6,6); il.setSpacing(10)
        infer=QFrame(); infer.setObjectName("SettingsOptionCard"); infl=QVBoxLayout(infer); infl.setContentsMargins(14,12,14,12); infl.setSpacing(6)
        infer_title=QLabel("推理参数"); infer_title.setObjectName("SettingsFieldLabel"); infl.addWidget(infer_title)
        infer_hint=QLabel("控制六花声音的采样方式与稳定性。多数情况保持默认即可，遇到沙哑/电音/复读再针对性调。"); infer_hint.setObjectName("DashboardMuted"); infer_hint.setWordWrap(True); infl.addWidget(infer_hint)
        self._gv_speed=QDoubleSpinBox(); self._gv_speed.setRange(0.3,2.0); self._gv_speed.setSingleStep(0.05); infl.addLayout(self._settings_field_hint("语速",self._gv_speed,"调小→更慢更沉稳、咬字更清楚；调大→更活泼，过大易吞字含糊。默认 0.9（略放慢）。"))
        self._gv_temp=QDoubleSpinBox(); self._gv_temp.setRange(0.1,2.0); self._gv_temp.setSingleStep(0.05); infl.addLayout(self._settings_field_hint("温度",self._gv_temp,"调小→发音更稳更干净、不易沙哑；调大→语气更丰富多变，过大易沙哑/电音/破音。默认 0.7。"))
        self._gv_topk=self._make_settings_spinbox(1,100); infl.addLayout(self._settings_field_hint("top_k",self._gv_topk,"调小→候选词更少、更稳定；调大→选择更多、更自然多变，过大易出怪音。默认 5。"))
        self._gv_topp=QDoubleSpinBox(); self._gv_topp.setRange(0.1,1.0); self._gv_topp.setSingleStep(0.05); infl.addLayout(self._settings_field_hint("top_p",self._gv_topp,"调小→更保守确定；调大→更随机多样，接近 1 时与 top_k 叠加，过大易不稳定。默认 1.0。"))
        self._gv_steps=self._make_settings_spinbox(1,128); infl.addLayout(self._settings_field_hint("采样步数",self._gv_steps,"调小→合成更快、声音略糙；调大→音质更细腻圆润，但更慢更吃显存。默认 32。"))
        self._gv_rp=QDoubleSpinBox(); self._gv_rp.setRange(1.0,2.0); self._gv_rp.setSingleStep(0.05); infl.addLayout(self._settings_field_hint("重复惩罚",self._gv_rp,"调小→更自由、容易复读/卡词；调大→更避免复读，过大会生硬/丢字。默认 1.35。"))
        self._gv_split=QComboBox()
        for val,desc in (("cut5","cut5 智能切分（推荐）"),("cut0","cut0 按标点整句"),("cut1","cut1 短句"),("cut2","cut2"),("cut3","cut3"),("cut4","cut4")):
            self._gv_split.addItem(desc,val)
        infl.addLayout(self._settings_field_hint("文本切分",self._gv_split,"cut0 长句更连贯但更慢；cut5 智能切分更稳。短句基本无差别。"))
        il.addWidget(infer)
        ref=QFrame(); ref.setObjectName("SettingsOptionCard"); rfl=QVBoxLayout(ref); rfl.setContentsMargins(14,12,14,12); rfl.setSpacing(6)
        ref_title=QLabel("参考音频"); ref_title.setObjectName("SettingsFieldLabel"); rfl.addWidget(ref_title)
        ref_hint=QLabel("合成时以此为「音色条件」。换参考音频 = 换音色/说话风格，音频与文字必须内容一致。"); ref_hint.setObjectName("DashboardMuted"); ref_hint.setWordWrap(True); rfl.addWidget(ref_hint)
        self._gv_ref_audio=QLineEdit(); self._gv_ref_audio.setObjectName("SettingsLineEdit"); rfl.addLayout(self._settings_field_hint("音频路径",self._gv_ref_audio,"六花参考干声（.wav）。改了它，下面的参考文字也要同步改成同一句话。"))
        self._gv_ref_text=QLineEdit(); self._gv_ref_text.setObjectName("SettingsLineEdit"); rfl.addLayout(self._settings_field_hint("参考文字",self._gv_ref_text,"参考音频对应的逐字文字。与音频不一致会让音色和语气偏移。"))
        self._gv_prompt_lang=QComboBox(); self._gv_prompt_lang.addItem("日本語（日语）","ja"); self._gv_prompt_lang.addItem("中文","zh"); rfl.addLayout(self._settings_field_hint("音频语言",self._gv_prompt_lang,"参考音频说的是哪种语言就用哪个。六花参考都是日语，保持 ja；换中文参考音频才改 zh。"))
        il.addWidget(ref)
        svc=QFrame(); svc.setObjectName("SettingsOptionCard"); scl=QVBoxLayout(svc); scl.setContentsMargins(14,12,14,12); scl.setSpacing(6)
        svc_title=QLabel("语音服务"); svc_title.setObjectName("SettingsFieldLabel"); scl.addWidget(svc_title)
        svc_hint=QLabel("本地 GPT-SoVITS 服务（api_v2.py）的连接与启动配置。"); svc_hint.setObjectName("DashboardMuted"); svc_hint.setWordWrap(True); scl.addWidget(svc_hint)
        self._gv_url=QLineEdit(); self._gv_url.setObjectName("SettingsLineEdit"); scl.addLayout(self._settings_field_hint("服务地址",self._gv_url,"改端口后需与启动配置一致，否则合成会连不上。一般保持默认 9880。"))
        self._gv_start_timeout=self._make_settings_spinbox(30,300," 秒"); scl.addLayout(self._settings_field_hint("启动超时",self._gv_start_timeout,"调小→等不及会误报启动失败；调大→模型加载慢时能等更久，但真的失败时也要多等。默认 90。"))
        il.addWidget(svc)
        actions=QHBoxLayout(); actions.addStretch(); save=QPushButton("保存设置"); save.setObjectName("DashboardPrimaryButton"); save.clicked.connect(self._save_gptsovits); actions.addWidget(save); il.addLayout(actions)
        scroll.setWidget(inner); layout.addWidget(scroll,1); return page

    def _make_settings_spinbox(self,minimum,maximum,suffix=""):
        spinbox=QSpinBox(); spinbox.setRange(minimum,maximum); spinbox.setSuffix(suffix); spinbox.setMinimumWidth(110); return spinbox

    def _settings_field(self,label_text,widget):
        row=QHBoxLayout(); row.setContentsMargins(0,0,0,0); row.setSpacing(10)
        label=QLabel(label_text); label.setObjectName("SettingsFieldLabel"); row.addWidget(label); row.addStretch(); row.addWidget(widget); return row

    def _settings_field_hint(self,label_text,widget,hint):
        box=QVBoxLayout(); box.setContentsMargins(0,0,0,0); box.setSpacing(2)
        row=QHBoxLayout(); row.setContentsMargins(0,0,0,0); row.setSpacing(10)
        label=QLabel(label_text); label.setObjectName("SettingsFieldLabel"); row.addWidget(label); row.addStretch(); row.addWidget(widget); box.addLayout(row)
        h=QLabel(hint); h.setObjectName("DashboardMuted"); h.setWordWrap(True); h.setAlignment(Qt.AlignLeft); box.addWidget(h)
        return box

    def _refresh_preset_list(self):
        self._pl.clear()
        for preset in config.get_presets():
            item=QListWidgetItem(); widget=PresetItemWidget(preset)
            widget.selection_requested.connect(lambda item=item: self._pl.setCurrentItem(item))
            widget.manage_clicked.connect(self._on_manage_preset)
            widget.use_clicked.connect(self._on_use_preset)
            hint=widget.sizeHint(); item.setSizeHint(QSize(hint.width(),max(hint.height(),widget.minimumHeight())))
            self._pl.addItem(item); self._pl.setItemWidget(item, widget)

    def _on_preset_selection_changed(self,current,previous):
        previous_widget=self._pl.itemWidget(previous) if previous else None
        if previous_widget: previous_widget.set_selected(False)
        current_widget=self._pl.itemWidget(current) if current else None
        if current_widget: current_widget.set_selected(True)
        self._delete_preset_btn.setEnabled(current is not None)

    def _on_add_preset(self):
        name,ok=QInputDialog.getText(self,"添加预设","预设名称",QLineEdit.Normal,"")
        if ok and name.strip():
            config.add_preset(name.strip(),"","",""); self._refresh_preset_list()

    def _on_del_preset(self):
        current=self._pl.currentItem()
        if not current: return
        widget=self._pl.itemWidget(current)
        preset_name=widget._data["name"] if widget else current.text()
        if QMessageBox.question(self,"确认删除",f"确定删除“{preset_name}”吗？",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            config.delete_preset(preset_name); self._refresh_preset_list()

    def _on_manage_preset(self,preset):
        dialog=PresetEditDialog(preset["name"],preset.get("api_key",""),preset.get("model",""),preset.get("api_base",""),self)
        if dialog.exec_()==QDialog.Accepted: self._refresh_preset_list()

    def _on_use_preset(self,preset):
        ok=config.save_user_config({"api_key":preset.get("api_key",""),"model":preset.get("model",""),"api_base":preset.get("api_base","")})
        if ok:
            self.config_changed.emit(); QMessageBox.information(self,"已应用",f"已切换到预设「{preset['name']}」")
        else: QMessageBox.warning(self,"失败","配置保存失败")

    def _save_smart_search(self):
        config.save_user_config({"smart_search_max_results":self._smr.value(),"smart_search_max_analyze":self._sma.value(),"smart_search_max_candidates":self._smc.value()}); self.config_changed.emit(); QMessageBox.information(self,"已保存","智能搜图设置已更新")

    def _save_proactive(self):
        config.save_user_config({"proactive_enabled":self._pcb.isChecked(),"proactive_qq_enabled":self._qqcb.isChecked(),"proactive_slack_enabled":self._slack_cb.isChecked(),"proactive_slack_prob":self._sp.value(),"proactive_slack_cooldown":self._sc.value(),"rotation_threshold":self._rt.value(),"auto_start":self._ascb.isChecked()}); self.config_changed.emit(); QMessageBox.information(self,"已保存","主动聊天设置已更新")

    def _save_diary_auto(self):
        config.save_user_config({"diary_auto_summary_enabled": self._das_enabled.isChecked(), "diary_auto_summary_hour": self._das_hour.currentData()}); self.config_changed.emit(); QMessageBox.information(self,"已保存","日记自动收尾设置已更新")

    def _save_voice_settings(self,notify=True):
        config.save_user_config({"voice_enabled":self._voice_enabled.isChecked(),"voice_tts_engine":self._voice_engine.currentData(),"voice_model_path":self._voice_model.text().strip(),"voice_infer_step":self._voice_step.value(),"voice_method":self._voice_method.currentText(),"voice_t_start":self._voice_ts.value(),"voice_key":self._voice_key.value(),"voice_max_chars":self._voice_max_chars.value(),"voice_tts_speed":self._voice_speed.value(),"voice_post_lowpass":self._voice_lowpass.isChecked(),"voice_post_lowpass_cutoff":self._voice_lowpass_cutoff.value(),"persona_language":self._voice_lang.currentData()}); self.config_changed.emit()
        if notify: QMessageBox.information(self,"已保存","语音设置已更新（语言切换下一条消息生效）")

    def _save_gptsovits(self,notify=True):
        config.save_user_config({
            "gptsovits_speed_factor":self._gv_speed.value(),
            "gptsovits_temperature":self._gv_temp.value(),
            "gptsovits_top_k":self._gv_topk.value(),
            "gptsovits_top_p":self._gv_topp.value(),
            "gptsovits_sample_steps":self._gv_steps.value(),
            "gptsovits_repetition_penalty":self._gv_rp.value(),
            "gptsovits_text_split_method":self._gv_split.currentData(),
            "gptsovits_ref_audio":self._gv_ref_audio.text().strip(),
            "gptsovits_ref_text":self._gv_ref_text.text().strip(),
            "gptsovits_prompt_lang":self._gv_prompt_lang.currentData(),
            "gptsovits_url":self._gv_url.text().strip(),
            "gptsovits_start_timeout":self._gv_start_timeout.value(),
        }); self.config_changed.emit()
        if notify: QMessageBox.information(self,"已保存","GPT-SoVITS 参数已更新（下一次合成生效）")

    def _sleep_compute_page(self):
        """Sleep-time Compute 设置页面 - 深度记忆整合"""
        from gui.sleep_compute_settings import SleepComputeSettingsWidget
        page, layout = self._page_shell(
            "Sleep-time Compute",
            "每天凌晨自动运行深度记忆整合，识别重复记忆、提取行为模式、生成连贯叙事，让六花越来越懂你。"
        )
        # 直接使用已开发好的完整设置界面
        sleep_widget = SleepComputeSettingsWidget()
        layout.addWidget(sleep_widget, 1)
        return page

    def _load_persona_file(self):
        index=self._persona_combo.currentIndex()
        if index<0: return
        path=self._persona_combo.itemData(index)
        if not path or not os.path.exists(path):
            self._persona_editor.setPlainText("(文件不存在)"); return
        with open(path,"r",encoding="utf-8") as f: content=f.read()
        self._persona_editor.setPlainText(content)
        filename=os.path.basename(path)
        if filename=="system_rules.md": self._readonly_label.setText("修改行为规范会影响六花的主动性和系统行为。")
        elif filename=="character.md": self._readonly_label.setText("人设文件会定义六花的说话方式、语气与核心性格。")
        else: self._readonly_label.setText("备忘录通常由六花和你一起维护。")

    def _save_persona_file(self):
        index=self._persona_combo.currentIndex()
        if index<0:
            QMessageBox.warning(self,"提示","没有选中的文件"); return
        path=self._persona_combo.itemData(index)
        with open(path,"w",encoding="utf-8") as f: f.write(self._persona_editor.toPlainText())
        QMessageBox.information(self,"已保存","文件已保存，新会话会使用最新内容")

    def _reset_persona_file(self):
        index=self._persona_combo.currentIndex()
        if index<0: return
        path=self._persona_combo.itemData(index)
        filename=os.path.basename(path) if path else ""
        if QMessageBox.question(self,"确认重置",f"确定把“{filename}”恢复成默认内容吗？",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes: return
        defaults={
            "character.md":"""# 小鸟游六花

## 基本设定
- 名字：小鸟游六花
- 身份：邪王真眼使，你的陪伴型 AI 同伴

## 性格特征
- 会认真记住用户提到的事
- 语气自然、轻微中二、带一点傲娇
- 在关心用户时偏温柔，不要机械

## 说话风格
- 以中文自然对话为主
- 偶尔提到“契约者”“邪王真眼”等角色设定
""",
            "system_rules.md":"""# 行为规范

## 输出风格
- 回答自然、口语化
- 不要堆砌模板句

## 主动聊天
- 在合适的时候主动关心用户
- 注意昼夜节奏，深夜避免打扰

## 记忆与成长
- 值得记住的事可以写入 memo
- 新的自我理解可以补充到人设文件
""",
            "memo.md":"""# 六花的备忘录

这里记录值得长期记住的事。
""",
        }
        content=defaults.get(filename)
        if content is None:
            QMessageBox.information(self,"提示","该文件没有默认模板"); return
        with open(path,"w",encoding="utf-8") as f: f.write(content)
        self._persona_editor.setPlainText(content)
        QMessageBox.information(self,"已重置",f"{filename} 已恢复默认内容")

    def _switch_page(self,row):
        self.pages.setCurrentIndex(row)
        for index in range(self.nav.count()):
            item = self.nav.item(index)
            widget = self.nav.itemWidget(item)
            if widget is not None:
                widget.set_active(index == row)

    def select_category(self,name):
        """按分类名跳到设置页对应导航项（供外部打开指定分区）。"""
        for index in range(self.nav.count()):
            item=self.nav.item(index)
            widget=self.nav.itemWidget(item)
            if widget is not None and getattr(widget,"_name",None)==name:
                self.nav.setCurrentRow(index); return

    def _filter_settings(self, query):
        normalized = "".join(str(query).casefold().split())
        first_match = None
        for index, (name, detail, _icon) in enumerate(self._settings_categories):
            haystack = "".join((name + detail + self._settings_search_terms[index]).casefold().split())
            matches = not normalized or normalized in haystack
            self.nav.item(index).setHidden(not matches)
            if matches and first_match is None:
                first_match = index
        if normalized and first_match is not None:
            self.nav.setCurrentRow(first_match)

    def _choose_theme(self,value):
        if (getattr(self, "_seasonal_toggle", None) is not None
                and self._seasonal_toggle.isChecked() and not self._loading_appearance):
            return
        for button in self.theme_buttons: button.set_selected(button.value == value)
        self._persist_appearance()

    def _persist_appearance(self):
        if self._loading_appearance:
            return
        self._save_appearance()

    def _seasonal_status_text(self):
        today = date.today()
        current = theme_manager.SEASONAL_THEMES[theme_manager.season_for_date(today)]
        transition = theme_manager.next_season_transition(today)
        upcoming = theme_manager.SEASONAL_THEMES[theme_manager.season_for_date(transition)]
        return f"当前：{current.display_name} · {transition.month}月{transition.day}日切换为{upcoming.display_name}"

    def _sync_appearance_controls(self):
        automatic = self._seasonal_toggle.isChecked()
        self._seasonal_status.setText(
            self._seasonal_status_text() if automatic else "已关闭 · 使用下方手动主题"
        )
        # Keep previews vivid while automatic mode is active.  The click
        # handlers still guard against manual changes; disabling the widgets
        # would make Qt desaturate the supplied artwork and hide the seasonal
        # palette the user is choosing to preview.
        for button in self.theme_buttons:
            button.setEnabled(True)
            button.setProperty("seasonalLocked", automatic)
            button.style().unpolish(button)
            button.style().polish(button)

    def _on_seasonal_mode_changed(self, enabled):
        self._sync_appearance_controls()
        if self._loading_appearance:
            return
        config.save_user_config({
            "appearance_mode": "seasonal_auto" if enabled else "manual"
        })
        self.config_changed.emit()

    def load_settings(self):
        config.reload_from_file(); values=getattr(config,"_USER_CONFIG",{}) or {}
        self._loading_appearance = True
        theme = values.get("appearance_theme", "spring")
        theme = {
            "六花主题": "spring",
            "梦幻樱花主题": "spring",
            "星夜静谧": "winter",
            "跟随系统": "summer",
            "浅色模式": "summer",
            "极简浅色": "summer",
            "深色模式": "winter",
            "深色优雅": "winter",
        }.get(theme, theme)
        self._choose_theme(theme)
        self._seasonal_toggle.setChecked(
            theme_manager.configured_appearance_mode(values) == "seasonal_auto"
        )
        self._sync_appearance_controls()
        self._loading_appearance = False
        chat=config.get_chat_settings(); self.temperature.setValue(int(float(chat["temperature"])*100)); self.max_tokens.setValue(int(chat["chat_max_tokens"])); self.memory_check.setChecked(bool(chat["chat_memory_enabled"])); self.web_check.setChecked(bool(chat["chat_web_search_enabled"])); self.citations_check.setChecked(bool(chat["chat_citations_enabled"]))
        self._smr.setValue(int(config.SMART_SEARCH_MAX_RESULTS)); self._smc.setValue(int(config.SMART_SEARCH_MAX_CANDIDATES)); self._sma.setValue(int(config.SMART_SEARCH_MAX_ANALYZE))
        self._pcb.setChecked(bool(config.PROACTIVE_ENABLED)); self._qqcb.setChecked(bool(getattr(config,"PROACTIVE_QQ_ENABLED",False))); self._slack_cb.setChecked(bool(config.PROACTIVE_SLACK_ENABLED)); self._sp.setValue(int(config.PROACTIVE_SLACK_PROB)); self._sc.setValue(int(getattr(config,"PROACTIVE_SLACK_COOLDOWN",60))); self._rt.setValue(int(config.ROTATION_THRESHOLD)); self._ascb.setChecked(bool(config.AUTO_START))
        self._das_enabled.setChecked(bool(getattr(config,"DIARY_AUTO_SUMMARY_ENABLED",True))); didx=self._das_hour.findData(int(getattr(config,"DIARY_AUTO_SUMMARY_HOUR",23))); self._das_hour.setCurrentIndex(didx if didx>=0 else 23)
        self._surf_enabled.setChecked(bool(getattr(config,"SURF_AUTO_ENABLED",True))); self._surf_interval.setValue(int(getattr(config,"SURF_AUTO_INTERVAL_MIN",180))); self._surf_tags_round.setValue(int(getattr(config,"SURF_TAGS_PER_ROUND",4))); self._surf_limit.setValue(int(getattr(config,"SURF_SEARCH_LIMIT",2))); self._surf_cooldown.setValue(int(getattr(config,"SURF_TAG_COOLDOWN_HOURS",48))); self._surf_decay.setValue(int(getattr(config,"SURF_TAG_DECAY_PER_7_DAYS",3))); self._surf_liked.setValue(int(getattr(config,"SURF_REACTION_LIKED",10))); self._surf_disliked.setValue(int(getattr(config,"SURF_REACTION_DISLIKED",5)))
        self._refresh_surf_tags()
        self._voice_enabled.setChecked(bool(config.VOICE_ENABLED)); self._voice_model.setText(str(config.VOICE_MODEL_PATH)); self._voice_step.setValue(int(config.VOICE_INFER_STEP)); self._voice_method.setCurrentText(config.VOICE_METHOD); self._voice_ts.setValue(float(config.VOICE_T_START)); self._voice_key.setValue(int(config.VOICE_KEY)); self._voice_max_chars.setValue(int(config.VOICE_MAX_CHARS)); self._voice_speed.setValue(float(config.VOICE_TTS_SPEED)); self._voice_lowpass.setChecked(bool(config.VOICE_POST_LOWPASS)); self._voice_lowpass_cutoff.setValue(int(config.VOICE_POST_LOWPASS_CUTOFF))
        idx=self._voice_engine.findData(config.VOICE_TTS_ENGINE); self._voice_engine.setCurrentIndex(idx if idx>=0 else 0)
        lidx=self._voice_lang.findData(config.PERSONA_LANGUAGE); self._voice_lang.setCurrentIndex(lidx if lidx>=0 else 0)
        self._gv_speed.setValue(float(config.GPT_SOVITS_SPEED_FACTOR)); self._gv_temp.setValue(float(config.GPT_SOVITS_TEMPERATURE)); self._gv_topk.setValue(int(config.GPT_SOVITS_TOP_K)); self._gv_topp.setValue(float(config.GPT_SOVITS_TOP_P)); self._gv_steps.setValue(int(config.GPT_SOVITS_SAMPLE_STEPS)); self._gv_rp.setValue(float(config.GPT_SOVITS_REPETITION_PENALTY))
        sidx=self._gv_split.findData(config.GPT_SOVITS_TEXT_SPLIT_METHOD); self._gv_split.setCurrentIndex(sidx if sidx>=0 else 0)
        self._gv_ref_audio.setText(str(config.GPT_SOVITS_REF_AUDIO)); self._gv_ref_text.setText(str(config.GPT_SOVITS_REF_TEXT))
        plidx=self._gv_prompt_lang.findData(config.GPT_SOVITS_PROMPT_LANG); self._gv_prompt_lang.setCurrentIndex(plidx if plidx>=0 else 0)
        self._gv_url.setText(str(config.GPT_SOVITS_URL)); self._gv_start_timeout.setValue(int(config.GPT_SOVITS_START_TIMEOUT))
        self._refresh_preset_list()

    def _save_appearance(self, notify=False):
        selected=next((b.value for b in self.theme_buttons if b.is_selected()),"spring"); config.save_user_config({"appearance_mode":"seasonal_auto" if self._seasonal_toggle.isChecked() else "manual","appearance_theme":selected}); self.config_changed.emit()
        if notify: QMessageBox.information(self,"已保存","外观偏好已保存")

    def _save_chat(self):
        config.save_user_config({"temperature":self.temperature.value()/100,"chat_max_tokens":self.max_tokens.value(),"chat_memory_enabled":self.memory_check.isChecked(),"chat_web_search_enabled":self.web_check.isChecked(),"chat_citations_enabled":self.citations_check.isChecked()}); self.config_changed.emit(); QMessageBox.information(self,"已保存","对话设置已更新")

    def _clear_history(self):
        if QMessageBox.question(self,"清空对话记录","确定删除全部本地会话和消息吗？",QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes: history.clear_all_sessions(); config.save_user_config({"last_session_id":0}); self.config_changed.emit(); QMessageBox.information(self,"已清空","全部对话记录已删除")

    def _export_settings(self):
        path,_=QFileDialog.getSaveFileName(self,"导出设置","RikkaAI-settings.json","JSON (*.json)")
        if not path:return
        try:
            payload=dict(getattr(config,"_USER_CONFIG",{}) or {})
            with open(path,"w",encoding="utf-8") as f:json.dump(payload,f,ensure_ascii=False,indent=2)
            QMessageBox.information(self,"导出完成","设置文件已保存")
        except OSError as exc:QMessageBox.warning(self,"导出失败",str(exc))

    def _import_settings(self):
        path,_=QFileDialog.getOpenFileName(self,"导入设置","","JSON (*.json)")
        if not path:return
        try:
            with open(path,"r",encoding="utf-8") as f:payload=json.load(f)
            if not isinstance(payload,dict):raise ValueError("设置文件格式不正确")
            if QMessageBox.question(self,"导入设置","导入会覆盖同名设置项，是否继续？",QMessageBox.Yes|QMessageBox.No)!=QMessageBox.Yes:return
            config.save_user_config(payload); self.load_settings(); self.config_changed.emit(); QMessageBox.information(self,"导入完成","设置已经更新")
        except (OSError,ValueError,json.JSONDecodeError) as exc:QMessageBox.warning(self,"导入失败",str(exc))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._reposition_settings_decor()
        if self.top_bar is not None:
            w = max(0, min(self.width() - 20, 1115 if self.width() >= 1250 else max(600, self.width() - 190)))
            self.top_bar.setGeometry(max(0, self.width() - w), 23, w, 46)
        # Keep the desktop composition, but switch to a compact two-column
        # choice grid and narrower navigation before the window reaches its
        # supported minimum width.
        try:
            if hasattr(self, "pages"):
                compact = self.width() < 1250
                left = 190 if compact else 278
                nav_width = 210 if compact else 255
                gap = 12 if compact else 17
                self.root.setContentsMargins(left, 78, 12 if compact else 18, 18)
                self.root.setSpacing(18 if compact else 24)
                self._settings_nav_panel.setFixedWidth(nav_width)
                height = max(520, min(737, self.height() - 112))
                self._settings_nav_panel.setFixedHeight(height)
                avail = self.width() - left - (12 if compact else 18) - nav_width - gap
                self.pages.setFixedWidth(min(731, max(440, avail)))
                self._pages_scroll.setMinimumHeight(height)
                self._pages_scroll.setMaximumHeight(height)
                self._pages_scroll.setFixedWidth(min(731, max(440, avail)))
                if hasattr(self, "_theme_choice_layout"):
                    for button in self.theme_buttons:
                        button.set_responsive(compact)
                    self._reflow_choice_grid(self._theme_choice_layout, self.theme_buttons, 2 if compact else 4)
        except Exception:
            pass

    @staticmethod
    def _reflow_choice_grid(layout, buttons, columns):
        for button in buttons:
            layout.removeWidget(button)
        for index, button in enumerate(buttons):
            layout.addWidget(button, index // columns, index % columns)
