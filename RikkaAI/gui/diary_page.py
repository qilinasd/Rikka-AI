"""RikkaAI diary workspace.

The page keeps the existing diary and period-summary storage contracts while
presenting them as a searchable, calendar-driven timeline.
"""

import calendar as calendar_module
import json
import os
import sqlite3
from datetime import date, datetime, timedelta

from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QImage, QLinearGradient, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import config
from brain import diary as diary_module
from brain.memory_summary import SUMMARY_DIRS
from gui.chat_top_bar import ChatTopBar


PERIOD_LABEL = {"weekly": "周记", "monthly": "月报", "yearly": "年鉴"}
PERIOD_AUTO = {
    "weekly": "每周日 21:00 自动生成",
    "monthly": "每月最后一天自动生成",
    "yearly": "每年 12 月 31 日自动生成",
}
PERIOD_ICON = {"weekly": "calendar", "monthly": "discover", "yearly": "memory"}

OUTLINE_DIR = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")
FIGMA_ICON_DIR = os.path.join(config.ASSETS_DIR, "figma", "icons")
VISUAL_ASSET_PATH = os.path.join(
    config.ASSETS_DIR, "images", "diary", "diary_visual_assets.png"
)
BACKGROUND_PATH = os.path.join(config.ASSETS_DIR, "images", "home", "home_background.png")

# Coordinates on the supplied 1536 x 1024 visual asset sheet.
TITLE_ICON_SOURCE = QRect(201, 149, 78, 79)
MOOD_CHARACTER_SOURCE = QRect(272, 442, 104, 104)

TAG_SPECS = {
    "对话": {"icon": "chat", "title": "对话记忆", "keywords": ()},
    "偏好": {"icon": "favorite", "title": "偏好记忆", "keywords": ("喜欢", "偏好", "最爱", "讨厌")},
    "知识": {"icon": "discover", "title": "知识记忆", "keywords": ("知识", "学习", "代码", "bug", "技术", "教程", "项目")},
    "情绪": {"icon": "emoji", "title": "情绪记忆", "keywords": ("心情", "开心", "难过", "疲惫", "生气", "担心", "温暖")},
    "重要": {"icon": "star", "title": "重要记忆", "keywords": ("重要", "生日", "纪念", "约定", "务必")},
    "灵感": {"icon": "discover", "title": "灵感记忆", "keywords": ("灵感", "创意", "想法", "设计")},
    "提醒": {"icon": "notification", "title": "提醒记忆", "keywords": ("提醒", "记得", "待办", "别忘")},
    "其他": {"icon": "more", "title": "日常记忆", "keywords": ("日常", "今天", "天气")},
}
TAG_ORDER = tuple(TAG_SPECS)

MOODS = (
    ("开心", "开心", "smile"),
    ("平静", "平静", "calm"),
    ("思考", "思考", "think"),
    ("疲惫", "疲惫", "tired"),
    ("难过", "难过", "sad"),
)
MOOD_SYMBOLS = {"开心": ":D", "平静": ":)", "思考": "?", "疲惫": "zZ", "难过": ":("}
MOOD_COPY = {
    "开心": "今天也要元气满满哦～",
    "平静": "安静地珍藏今天的时光～",
    "思考": "邪王真眼正在认真思考～",
    "疲惫": "辛苦了，今晚早点休息吧～",
    "难过": "六花会陪在契约者身边～",
}


def _icon_path(name):
    return os.path.join(OUTLINE_DIR, f"{name}.svg")


def _tinted_icon(path, color, size=18):
    source = QIcon(path).pixmap(QSize(size, size))
    if source.isNull():
        return QIcon(path)
    result = QPixmap(source.size())
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, source)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(result.rect(), QColor(color))
    painter.end()
    return QIcon(result)


def _transparent_sheet_asset(sheet, source):
    """Remove the sheet's near-white presentation background from a small crop."""
    if sheet.isNull():
        return QPixmap()
    image = sheet.copy(source).toImage().convertToFormat(QImage.Format_ARGB32)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            distance = max(255 - color.red(), 255 - color.green(), 255 - color.blue())
            color.setAlpha(max(0, min(255, (distance - 3) * 8)))
            image.setPixelColor(x, y, color)
    return QPixmap.fromImage(image)


def _fmt_date(value):
    text = str(value or "")
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return f"{text[0:4]}年{text[5:7]}月{text[8:10]}日"
    return text


def _get_db():
    conn = sqlite3.connect(
        os.path.join(config.USER_CONFIG_DIR, "rikkai.db"), timeout=10
    )
    conn.row_factory = sqlite3.Row
    return conn


def _flow_parts(line, fallback_time=""):
    text = str(line or "").strip()
    if text.startswith("[") and "]" in text:
        closing = text.index("]")
        return text[1:closing].strip(), text[closing + 1:].strip()
    return fallback_time, text


def _classify_entry(text):
    lower = str(text or "").lower()
    # Higher-signal categories win over generic dialogue wording.
    for name in ("重要", "提醒", "偏好", "知识", "情绪", "灵感", "其他"):
        if any(keyword.lower() in lower for keyword in TAG_SPECS[name]["keywords"]):
            return name
    if "契约者" in lower or "六花" in lower or "对话" in lower:
        return "对话"
    return "其他"


def _entry_count(details):
    return sum(1 for line in str(details or "").splitlines() if line.strip())


def _json_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


class DiaryDateItemWidget(QWidget):
    def __init__(self, date_text, count, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 0, 8, 0)
        layout.setSpacing(6)
        label = QLabel(date_text)
        label.setObjectName("DiaryDateItemText")
        layout.addWidget(label, 1)
        badge = QLabel(f"{count} 条")
        badge.setObjectName("DiaryDateItemCount")
        layout.addWidget(badge)


class DiaryCalendarWidget(QWidget):
    """Compact month grid with entry markers and deterministic styling."""

    date_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiaryCalendar")
        self._month = date.today().replace(day=1)
        self._selected = date.today()
        self._entry_dates = set()
        self._day_buttons = []
        self._build_ui()
        self._render_month()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        navigation = QHBoxLayout()
        navigation.setContentsMargins(0, 0, 0, 0)
        previous = QPushButton("<")
        previous.setObjectName("DiaryCalendarNav")
        previous.setFixedSize(27, 27)
        previous.setCursor(Qt.PointingHandCursor)
        previous.setToolTip("上个月")
        previous.clicked.connect(lambda: self._move_month(-1))
        navigation.addWidget(previous)
        navigation.addStretch()
        self.month_label = QLabel()
        self.month_label.setObjectName("DiaryCalendarMonth")
        self.month_label.setAlignment(Qt.AlignCenter)
        navigation.addWidget(self.month_label)
        navigation.addStretch()
        following = QPushButton(">")
        following.setObjectName("DiaryCalendarNav")
        following.setFixedSize(27, 27)
        following.setCursor(Qt.PointingHandCursor)
        following.setToolTip("下个月")
        following.clicked.connect(lambda: self._move_month(1))
        navigation.addWidget(following)
        root.addLayout(navigation)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(2)
        grid.setVerticalSpacing(2)
        for column, label in enumerate(("日", "一", "二", "三", "四", "五", "六")):
            weekday = QLabel(label)
            weekday.setObjectName("DiaryCalendarWeekday")
            weekday.setAlignment(Qt.AlignCenter)
            weekday.setFixedHeight(17)
            grid.addWidget(weekday, 0, column)
        for index in range(42):
            button = QPushButton()
            button.setObjectName("DiaryCalendarDay")
            button.setFixedHeight(24)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _checked=False, target=button: self._select_button(target)
            )
            self._day_buttons.append(button)
            grid.addWidget(button, index // 7 + 1, index % 7)
        root.addLayout(grid)

    def _move_month(self, offset):
        month_index = self._month.year * 12 + self._month.month - 1 + offset
        self._month = date(month_index // 12, month_index % 12 + 1, 1)
        self._render_month()

    def _select_button(self, button):
        selected = button.property("calendarDate")
        if not isinstance(selected, date):
            return
        self._selected = selected
        self._month = selected.replace(day=1)
        self._render_month()
        self.date_selected.emit(selected.isoformat())

    def set_entry_dates(self, values):
        self._entry_dates = {
            parsed for value in values
            for parsed in [self._parse_date(value)] if parsed is not None
        }
        self._render_month()

    def set_selected_date(self, value):
        selected = self._parse_date(value)
        if selected is None:
            return
        self._selected = selected
        self._month = selected.replace(day=1)
        self._render_month()

    @staticmethod
    def _parse_date(value):
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value or "")[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    def _render_month(self):
        self.month_label.setText(f"{self._month.year}年{self._month.month:02d}月")
        weeks = list(
            calendar_module.Calendar(firstweekday=6).monthdatescalendar(
                self._month.year, self._month.month
            )
        )
        while len(weeks) < 6:
            start = weeks[-1][-1] + timedelta(days=1)
            weeks.append([start + timedelta(days=offset) for offset in range(7)])
        days = [day for week in weeks[:6] for day in week]
        today = date.today()
        for button, day in zip(self._day_buttons, days):
            button.setText(str(day.day))
            button.setProperty("calendarDate", day)
            button.setProperty("outside", day.month != self._month.month)
            button.setProperty("hasEntry", day in self._entry_dates)
            button.setProperty("selected", day == self._selected)
            button.setProperty("today", day == today)
            button.setToolTip(day.strftime("%Y-%m-%d"))
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()


class DiaryInsightsPanel(QWidget):
    """Right rail that keeps its preferred width without raising the page minimum."""

    def sizeHint(self):
        return QSize(286, 600)

    def minimumSizeHint(self):
        return QSize(0, 0)


class DiaryTopBarHost(QWidget):
    """Overlay host with a wide preferred size and a compact zero minimum."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preferred_width = 900

    def set_preferred_width(self, width):
        self._preferred_width = max(0, int(width))
        self.updateGeometry()

    def sizeHint(self):
        return QSize(self._preferred_width, 58)

    def minimumSizeHint(self):
        return QSize(0, 0)


class DiaryPage(QFrame):
    """Diary, weekly, monthly, and yearly memory browser."""

    history_requested = pyqtSignal()
    memo_requested = pyqtSignal()
    tools_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    window_action = pyqtSignal(str)
    window_drag = pyqtSignal(int, int, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DiaryPage")
        self._background = QPixmap(BACKGROUND_PATH)
        self._background_wash = QColor(247, 243, 255, 190)
        self._sheet = QPixmap(VISUAL_ASSET_PATH)
        self._diary_rows = []
        self._period_rows = {level: [] for level in PERIOD_LABEL}
        self._diary_error = ""
        self._period_errors = {level: "" for level in PERIOD_LABEL}
        self._selected_diary = None
        self._global_query = ""
        self._date_query = ""
        self._build_ui()
        self.refresh_data()

    def set_appearance_background(self, pixmap, wash):
        self._background = QPixmap(pixmap)
        self._background_wash = QColor(wash)
        self._background_wash.setAlpha(min(72, self._background_wash.alpha()))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#eee8ff"))
        if not self._background.isNull():
            scaled = self._background.scaled(
                self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            source_x = max(0, (scaled.width() - self.width()) // 2)
            source_y = max(0, (scaled.height() - self.height()) // 2)
            painter.drawPixmap(
                self.rect(), scaled, QRect(source_x, source_y, self.width(), self.height())
            )
        wash = QLinearGradient(0, 0, self.width(), self.height())
        start = QColor(self._background_wash)
        start.setAlpha(min(118, self._background_wash.alpha() + 28))
        middle = QColor(self._background_wash)
        middle.setAlpha(min(102, self._background_wash.alpha() + 14))
        end = QColor(self._background_wash)
        wash.setColorAt(0.0, start)
        wash.setColorAt(0.48, middle)
        wash.setColorAt(1.0, end)
        painter.fillRect(self.rect(), wash)

    # -- UI -----------------------------------------------------------------

    def _build_ui(self):
        overlay = QGridLayout(self)
        overlay.setContentsMargins(0, 0, 0, 0)
        overlay.setSpacing(0)

        self.content = QWidget()
        self.content.setObjectName("DiaryContentRoot")
        self.root = QVBoxLayout(self.content)
        self.root.setContentsMargins(220, 72, 22, 18)
        self.root.setSpacing(18)
        self.root.addLayout(self._build_heading())

        workspace = QHBoxLayout()
        workspace.setSpacing(16)

        main_column = QVBoxLayout()
        main_column.setSpacing(14)
        self.stats_layout = QHBoxLayout()
        self.stats_layout.setSpacing(12)
        main_column.addLayout(self.stats_layout)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("DiaryTabs")
        self.tabs.setDocumentMode(True)
        self.diary_tab = self._build_diary_tab()
        self.weekly_tab = self._build_period_tab("weekly")
        self.monthly_tab = self._build_period_tab("monthly")
        self.yearly_tab = self._build_period_tab("yearly")
        for widget, label, icon_name in (
            (self.diary_tab, "日记", "calendar"),
            (self.weekly_tab, "周记", "quote"),
            (self.monthly_tab, "月报", "discover"),
            (self.yearly_tab, "年鉴", "memory"),
        ):
            self.tabs.addTab(
                widget, _tinted_icon(_icon_path(icon_name), "#7d52dc", 17), label
            )
        main_column.addWidget(self.tabs, 1)
        workspace.addLayout(main_column, 1)

        self.insights_panel = self._build_insights_panel()
        workspace.addWidget(self.insights_panel)
        self.root.addLayout(workspace, 1)

        self.top_bar = ChatTopBar()
        self.top_bar.setProperty("diaryTheme", True)
        self.top_bar.search.setPlaceholderText("搜索记忆内容、关键词或标签…")
        self.top_bar.search_changed.connect(self._apply_global_search)
        self.top_bar.history_requested.connect(self.history_requested.emit)
        self.top_bar.memo_requested.connect(self.memo_requested.emit)
        self.top_bar.tools_requested.connect(self.tools_requested.emit)
        self.top_bar.settings_requested.connect(self.settings_requested.emit)
        self.top_bar.window_action.connect(self.window_action.emit)
        self.top_bar.window_drag.connect(self.window_drag.emit)
        self.top_bar_host = DiaryTopBarHost()
        self.top_bar_host.setObjectName("DiaryTopBarHost")
        self.top_bar_host.setFixedHeight(ChatTopBar.BAR_HEIGHT + ChatTopBar.TOP_MARGIN)
        self.top_bar_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.top_bar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        top_layout = QHBoxLayout(self.top_bar_host)
        top_layout.setContentsMargins(0, ChatTopBar.TOP_MARGIN, ChatTopBar.RIGHT_MARGIN, 0)
        top_layout.addWidget(self.top_bar)

        overlay.addWidget(self.content, 0, 0)
        overlay.addWidget(self.top_bar_host, 0, 0, Qt.AlignTop | Qt.AlignRight)

    def _build_heading(self):
        row = QHBoxLayout()
        row.setSpacing(13)
        icon = QLabel()
        icon.setObjectName("DiaryTitleIcon")
        icon.setFixedSize(58, 58)
        icon.setAlignment(Qt.AlignCenter)
        if not self._sheet.isNull():
            crop = self._sheet.copy(TITLE_ICON_SOURCE).scaled(
                52, 52, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            icon.setPixmap(crop)
        else:
            icon.setPixmap(QIcon(_icon_path("calendar")).pixmap(30, 30))
        row.addWidget(icon)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("六花的日记本")
        title.setObjectName("DiaryTitle")
        copy.addWidget(title)
        subtitle = QLabel("对话流水、心情、周记、月报与年鉴——和契约者一起度过的每一天")
        subtitle.setObjectName("DiarySubtitle")
        copy.addWidget(subtitle)
        row.addLayout(copy)
        row.addStretch()

        add_button = QPushButton("新建记忆")
        add_button.setObjectName("DiaryPrimaryButton")
        add_button.setIcon(_tinted_icon(_icon_path("plus"), "#ffffff", 16))
        add_button.setIconSize(QSize(16, 16))
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.setToolTip("向今天追加一条新记忆")
        add_button.clicked.connect(self._add_memory)
        row.addWidget(add_button)
        return row

    def _stat_card(self, caption, value, icon_name, accent):
        card = QFrame()
        card.setObjectName("DiaryStatCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setMinimumWidth(120)
        card.setFixedHeight(82)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        icon = QLabel()
        icon.setObjectName("DiaryStatIcon")
        icon.setProperty("accent", accent)
        icon.setFixedSize(38, 38)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(_tinted_icon(_icon_path(icon_name), accent, 19).pixmap(19, 19))
        layout.addWidget(icon)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        caption_label = QLabel(caption)
        caption_label.setObjectName("DiaryStatCaption")
        copy.addWidget(caption_label)
        value_label = QLabel(value)
        value_label.setObjectName("DiaryStatValue")
        value_label.setStyleSheet(f"color:{accent};")
        copy.addWidget(value_label)
        layout.addLayout(copy, 1)
        return card

    def _build_diary_tab(self):
        tab = QWidget()
        tab.setObjectName("DiaryDailyTab")
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        date_panel = QFrame()
        date_panel.setObjectName("DiaryDatePanel")
        date_panel.setFixedWidth(192)
        self.date_panel = date_panel
        date_layout = QVBoxLayout(date_panel)
        date_layout.setContentsMargins(8, 9, 8, 9)
        date_layout.setSpacing(7)
        self.date_search = QLineEdit()
        self.date_search.setObjectName("DiaryDateSearch")
        self.date_search.setPlaceholderText("搜索日期或内容…")
        self.date_search.setClearButtonEnabled(True)
        self.date_search.addAction(
            _tinted_icon(_icon_path("search"), "#7f69ae", 14), QLineEdit.LeadingPosition
        )
        self.date_search.textChanged.connect(self._apply_date_search)
        date_layout.addWidget(self.date_search)
        self.diary_list = QListWidget()
        self.diary_list.setObjectName("DiaryList")
        self.diary_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.diary_list.currentItemChanged.connect(self._on_diary_current_changed)
        date_layout.addWidget(self.diary_list, 1)
        self.diary_count_label = QLabel("0 个日期")
        self.diary_count_label.setObjectName("DiaryListFooter")
        date_layout.addWidget(self.diary_count_label)
        layout.addWidget(date_panel)

        timeline_panel = QFrame()
        timeline_panel.setObjectName("DiaryTimelinePanel")
        timeline_layout = QVBoxLayout(timeline_panel)
        timeline_layout.setContentsMargins(16, 14, 14, 12)
        timeline_layout.setSpacing(10)
        header = QHBoxLayout()
        self.diary_detail_date = QLabel("选择一篇日记")
        self.diary_detail_date.setObjectName("DiaryDetailDate")
        header.addWidget(self.diary_detail_date)
        header.addStretch()
        timeline_layout.addLayout(header)

        self.diary_detail = QScrollArea()
        self.diary_detail.setObjectName("DiaryScroll")
        self.diary_detail.setWidgetResizable(True)
        self.diary_detail.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.diary_detail_body = QWidget()
        self.diary_detail_body.setObjectName("DiaryTimelineBody")
        self.diary_detail_layout = QVBoxLayout(self.diary_detail_body)
        self.diary_detail_layout.setContentsMargins(0, 3, 2, 3)
        self.diary_detail_layout.setSpacing(12)
        self.diary_detail.setWidget(self.diary_detail_body)
        timeline_layout.addWidget(self.diary_detail, 1)
        layout.addWidget(timeline_panel, 1)
        return tab

    def _build_period_tab(self, level):
        tab = QWidget()
        tab.setObjectName("DiaryPeriodTab")
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        list_panel = QFrame()
        list_panel.setObjectName("DiaryDatePanel")
        list_panel.setFixedWidth(220)
        panel_layout = QVBoxLayout(list_panel)
        panel_layout.setContentsMargins(10, 11, 10, 9)
        panel_layout.setSpacing(6)
        title = QLabel(f"{PERIOD_LABEL[level]}档案")
        title.setObjectName("DiaryPanelTitle")
        panel_layout.addWidget(title)
        hint = QLabel(PERIOD_AUTO[level])
        hint.setObjectName("DiaryPanelHint")
        hint.setWordWrap(True)
        panel_layout.addWidget(hint)
        period_list = QListWidget()
        period_list.setObjectName("DiaryPeriodList")
        period_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        period_list.currentItemChanged.connect(
            lambda current, _previous, selected_level=level:
            self._on_period_selected(selected_level, current)
        )
        panel_layout.addWidget(period_list, 1)
        layout.addWidget(list_panel)

        detail_panel = QFrame()
        detail_panel.setObjectName("DiaryTimelinePanel")
        detail_panel_layout = QVBoxLayout(detail_panel)
        detail_panel_layout.setContentsMargins(13, 12, 10, 10)
        detail = QScrollArea()
        detail.setObjectName("DiaryScroll")
        detail.setWidgetResizable(True)
        detail.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("DiaryTimelineBody")
        detail_layout = QVBoxLayout(body)
        detail_layout.setContentsMargins(2, 2, 4, 2)
        detail.setWidget(body)
        detail_panel_layout.addWidget(detail)
        layout.addWidget(detail_panel, 1)

        setattr(self, f"_{level}_list", period_list)
        setattr(self, f"_{level}_detail", detail_layout)
        return tab

    def _build_insights_panel(self):
        panel = DiaryInsightsPanel()
        panel.setObjectName("DiaryInsights")
        panel.setMaximumWidth(286)
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        stats_card = QFrame()
        stats_card.setObjectName("DiarySideCard")
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(13, 10, 13, 10)
        stats_layout.setSpacing(6)
        stats_layout.addWidget(self._side_title("日记统计", "calendar"))
        stats_grid = QGridLayout()
        stats_grid.setContentsMargins(0, 0, 0, 0)
        stats_grid.setHorizontalSpacing(8)
        self._stat_values = {}
        for col, (key, caption) in enumerate(
            (("days", "记录天数"), ("streak", "连续天数"), ("written", "已写篇数"))
        ):
            box = QVBoxLayout()
            box.setSpacing(1)
            value = QLabel("--")
            value.setObjectName("DiaryStatBig")
            value.setAlignment(Qt.AlignCenter)
            box.addWidget(value)
            cap = QLabel(caption)
            cap.setObjectName("DiaryStatCap")
            cap.setAlignment(Qt.AlignCenter)
            box.addWidget(cap)
            stats_grid.addLayout(box, 0, col)
            self._stat_values[key] = value
        stats_layout.addLayout(stats_grid)
        layout.addWidget(stats_card)

        calendar_card = QFrame()
        calendar_card.setObjectName("DiarySideCard")
        calendar_layout = QVBoxLayout(calendar_card)
        calendar_layout.setContentsMargins(13, 12, 13, 10)
        calendar_layout.setSpacing(6)
        calendar_layout.addWidget(self._side_title("记忆日历", "calendar"))
        self.calendar = DiaryCalendarWidget()
        self.calendar.setFixedHeight(214)
        self.calendar.date_selected.connect(self._calendar_date_changed)
        calendar_layout.addWidget(self.calendar)
        layout.addWidget(calendar_card)

        trend_card = QFrame()
        trend_card.setObjectName("DiarySideCard")
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(13, 10, 13, 10)
        trend_layout.setSpacing(5)
        trend_layout.addWidget(self._side_title("心情趋势", "emoji"))
        self._mood_dots = []
        dots_row = QHBoxLayout()
        dots_row.setSpacing(6)
        for _ in range(7):
            dot = QLabel()
            dot.setObjectName("DiaryMoodDot")
            dot.setFixedSize(24, 24)
            dot.setAlignment(Qt.AlignCenter)
            dots_row.addWidget(dot)
            self._mood_dots.append(dot)
        trend_layout.addLayout(dots_row)
        self._mood_day_labels = []
        days_row = QHBoxLayout()
        days_row.setSpacing(6)
        for _ in range(7):
            day = QLabel("")
            day.setObjectName("DiaryMoodDay")
            day.setAlignment(Qt.AlignCenter)
            days_row.addWidget(day)
            self._mood_day_labels.append(day)
        trend_layout.addLayout(days_row)
        layout.addWidget(trend_card)

        mood_card = QFrame()
        mood_card.setObjectName("DiarySideCard")
        mood_layout = QVBoxLayout(mood_card)
        mood_layout.setContentsMargins(13, 11, 13, 11)
        mood_layout.setSpacing(7)
        mood_layout.addWidget(self._side_title("今日心情", "emoji"))
        mood_header = QHBoxLayout()
        self.mood_character = QLabel()
        self.mood_character.setObjectName("DiaryMoodCharacter")
        self.mood_character.setFixedSize(82, 66)
        self.mood_character.setAlignment(Qt.AlignCenter)
        character = _transparent_sheet_asset(self._sheet, MOOD_CHARACTER_SOURCE)
        if not character.isNull():
            self.mood_character.setPixmap(
                character.scaled(78, 66, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            fallback = QPixmap(
                os.path.join(config.ASSETS_DIR, "images", "avatar.png")
            )
            if not fallback.isNull():
                self.mood_character.setPixmap(
                    fallback.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        mood_header.addWidget(self.mood_character)
        self.mood_copy = QLabel("把今天的心情告诉六花吧～")
        self.mood_copy.setObjectName("DiaryMoodCopy")
        self.mood_copy.setWordWrap(True)
        mood_header.addWidget(self.mood_copy, 1)
        mood_layout.addLayout(mood_header)
        mood_row = QHBoxLayout()
        mood_row.setSpacing(4)
        self.mood_buttons = {}
        for mood, label, _key in MOODS:
            button = QPushButton(f"{MOOD_SYMBOLS[mood]}\n{label}")
            button.setObjectName("DiaryMoodButton")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolTip(f"将今天的心情设为{label}")
            button.clicked.connect(
                lambda checked=False, selected=mood: self._set_today_mood(selected)
            )
            mood_row.addWidget(button, 1)
            self.mood_buttons[mood] = button
        mood_layout.addLayout(mood_row)
        layout.addWidget(mood_card)
        layout.addStretch()
        return panel

    def _side_title(self, text, icon_name):
        heading = QWidget()
        heading.setObjectName("DiarySideHeading")
        layout = QHBoxLayout(heading)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        icon = QLabel()
        icon.setFixedSize(17, 17)
        icon.setPixmap(
            _tinted_icon(_icon_path(icon_name), "#7c4fd5", 15).pixmap(15, 15)
        )
        layout.addWidget(icon)
        label = QLabel(text)
        label.setObjectName("DiarySideTitle")
        layout.addWidget(label)
        layout.addStretch()
        return heading

    # -- Daily timeline ------------------------------------------------------

    def _on_diary_current_changed(self, item, _previous=None):
        if item is None:
            return
        row = item.data(Qt.UserRole)
        if row:
            self._show_diary_detail(row)

    def _show_diary_detail(self, row):
        self._selected_diary = dict(row)
        self._clear_layout(self.diary_detail_layout)
        self.diary_detail.verticalScrollBar().setValue(0)  # 切换日记时回到顶部
        date_text = _fmt_date(row.get("date", ""))
        self.diary_detail_date.setText(date_text)

        # 六花写的日记正文（主显示）
        story = str(row.get("summary") or "").strip()
        if story:
            self.diary_detail_layout.addWidget(
                self._story_card(date_text, row.get("mood", ""), story)
            )
        else:
            empty = QLabel("六花还没有写这一天的日记～")
            empty.setObjectName("DiaryStoryEmpty")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            self.diary_detail_layout.addWidget(empty)

        self.diary_detail_layout.addStretch()
        self._sync_mood_display(row.get("mood", "") if row.get("date") == date.today().isoformat() else None)

    def _story_card(self, date_text, mood, story):
        """六花写的当天日记（随笔小作文）卡片：按段落排版，保证阅读舒适。"""
        card = QFrame()
        card.setObjectName("DiaryStoryCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(10)
        title = QLabel("六花的日记")
        title.setObjectName("DiaryStoryTitle")
        header.addWidget(title)
        header.addStretch()
        mood_text = str(mood or "").strip()
        if mood_text:
            mood_label = QLabel(f"心情：{mood_text}")
            mood_label.setObjectName("DiaryStoryMood")
            mood_label.setWordWrap(True)
            header.addWidget(mood_label)
        layout.addLayout(header)

        # 按空行拆成段落，每段一个 QLabel，段间距更自然
        paragraphs = [p.strip() for p in str(story).splitlines() if p.strip()]
        if not paragraphs:
            paragraphs = [str(story)]
        for paragraph in paragraphs:
            body = QLabel(paragraph)
            body.setObjectName("DiaryStoryText")
            body.setTextFormat(Qt.PlainText)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(body)
        return card

    def _show_diary_empty(self, text="没有找到匹配的日记"):
        self._selected_diary = None
        self.diary_detail_date.setText("日记时间线")
        self._clear_layout(self.diary_detail_layout)
        empty = QLabel(text)
        empty.setObjectName("DiaryEmpty")
        empty.setAlignment(Qt.AlignCenter)
        self.diary_detail_layout.addWidget(empty, 1)

    def _apply_global_search(self, text):
        self._global_query = str(text or "").strip().lower()
        self._render_diary_list()
        for level in PERIOD_LABEL:
            self._render_period_list(level)

    def _apply_date_search(self, text):
        self._date_query = str(text or "").strip().lower()
        self._render_diary_list()

    def _parse_date_query(self, query):
        """把搜索输入解析成日期条件；解析不了返回 None。

        支持：2026-08-14 / 2026/8/14 / 2026.08.14 / 2026年8月14日 / 20260814
              2026-08 / 2026年8月 / 202608 / 2026年
              8-14 / 8/14 / 8月14日 / 0814
              08（月份） / 14（日） / 2026（年份）
        """
        q = str(query or "").strip()
        if not q:
            return None
        if q.isdigit():
            if len(q) == 1:
                forms = (("%m", "month"), ("%d", "day"))
            elif len(q) == 2:
                forms = (("%m", "month"), ("%d", "day"))  # "08"→8月；"14"→14日
            elif len(q) == 3:
                forms = (("%m%d", "monthday"),)
            elif len(q) == 4:
                forms = (("%Y%m%d", "full"), ("%m%d", "monthday"), ("%Y", "year"))
            elif len(q) == 8:
                forms = (("%Y%m%d", "full"),)
            else:
                forms = ()
        else:
            forms = (
                ("%Y-%m-%d", "full"), ("%Y/%m/%d", "full"), ("%Y.%m.%d", "full"),
                ("%Y年%m月%d日", "full"), ("%Y%m%d", "full"),
                ("%Y-%m", "prefix"), ("%Y/%m", "prefix"), ("%Y年%m月", "prefix"), ("%Y%m", "prefix"),
                ("%m-%d", "monthday"), ("%m/%d", "monthday"), ("%m月%d日", "monthday"), ("%m%d", "monthday"),
                ("%m", "month"), ("%d", "day"),
                ("%Y", "year"), ("%Y年", "year"),
            )
        for fmt, kind in forms:
            try:
                parsed = datetime.strptime(q, fmt)
            except ValueError:
                continue
            if kind == "full":
                return {"kind": "full", "value": parsed.strftime("%Y-%m-%d")}
            if kind == "prefix":
                return {"kind": "prefix", "value": parsed.strftime("%Y-%m")}
            if kind == "monthday":
                return {"kind": "monthday", "value": parsed.strftime("%m-%d")}
            if kind == "month":
                return {"kind": "month", "value": parsed.strftime("%m")}
            if kind == "day":
                return {"kind": "day", "value": parsed.strftime("%d")}
            if kind == "year":
                return {"kind": "year", "value": parsed.strftime("%Y")}
        return None

    def _is_date_like(self, query):
        """输入看起来像日期（纯数字 / 含分隔符 / 含年月日）时，只按日期匹配。"""
        q = str(query or "").strip()
        if not q:
            return False
        if q.isdigit() and len(q) <= 8:
            return True
        if any(ch in q for ch in "-/."):
            return True
        return any(ch in q for ch in "年月日")

    def _matches_diary(self, row):
        if self._global_query:
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("date", "title", "summary", "details", "mood")
            ).lower()
            if self._global_query not in haystack:
                return False
        q = self._date_query
        if not q:
            return True
        condition = self._parse_date_query(q)
        if condition is not None:
            value = str(row.get("date") or "")
            if condition["kind"] == "full":
                return value == condition["value"]
            if condition["kind"] == "prefix":
                return value.startswith(condition["value"])
            if condition["kind"] == "monthday":
                return len(value) >= 10 and value[5:10] == condition["value"]
            if condition["kind"] == "month":
                return len(value) >= 7 and value[5:7] == condition["value"]
            if condition["kind"] == "day":
                return len(value) >= 10 and value[8:10] == condition["value"]
            if condition["kind"] == "year":
                return value.startswith(condition["value"])
        # 日期样式的输入只在日期里找，避免正文时间戳/数字串扰
        if self._is_date_like(q):
            return False
        haystack = " ".join(
            str(row.get(key) or "")
            for key in ("date", "title", "summary", "details", "mood")
        ).lower()
        return q.lower() in haystack

    def _render_diary_list(self, preferred_date=None):
        selected_date = preferred_date or (
            self._selected_diary.get("date") if self._selected_diary else ""
        )
        visible = [row for row in self._diary_rows if self._matches_diary(row)]
        self.diary_list.blockSignals(True)
        self.diary_list.clear()
        target_item = None
        for row in visible:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, row)
            item.setSizeHint(QSize(0, 50))
            item.setToolTip(row.get("title") or f"{row.get('date', '')} 的日常")
            self.diary_list.addItem(item)
            self.diary_list.setItemWidget(
                item,
                DiaryDateItemWidget(_fmt_date(row.get("date", "")), _entry_count(row.get("details"))),
            )
            if row.get("date") == selected_date:
                target_item = item
        self.diary_list.blockSignals(False)
        self.diary_count_label.setText(f"{len(visible)} 个日期")
        if not visible:
            self._show_diary_empty(self._diary_error or "没有找到匹配的日记")
            return
        target_item = target_item or self.diary_list.item(0)
        self.diary_list.setCurrentItem(target_item)

    def _calendar_date_changed(self, date_key):
        row = next(
            (entry for entry in self._diary_rows if entry.get("date") == date_key), None
        )
        if row is None:
            self.diary_list.setCurrentRow(-1)
            self._show_diary_empty(f"{_fmt_date(date_key)}还没有记录")
            self.diary_detail_date.setText(_fmt_date(date_key))
            return
        if not self._matches_diary(row):
            self.top_bar.search.blockSignals(True)
            self.date_search.blockSignals(True)
            self.top_bar.search.clear()
            self.date_search.clear()
            self.top_bar.search.blockSignals(False)
            self.date_search.blockSignals(False)
            self._global_query = ""
            self._date_query = ""
            for level in PERIOD_LABEL:
                self._render_period_list(level)
            self._render_diary_list(date_key)
            return
        self._select_diary_by_date(date_key)

    def _select_diary_by_date(self, date_key):
        for index in range(self.diary_list.count()):
            item = self.diary_list.item(index)
            row = item.data(Qt.UserRole)
            if row and row.get("date") == date_key:
                if self.diary_list.currentItem() is item:
                    self._show_diary_detail(row)
                else:
                    self.diary_list.setCurrentItem(item)
                self.diary_list.scrollToItem(item)
                return True
        return False

    # -- Period summaries ----------------------------------------------------

    def _render_period_list(self, level):
        period_list = getattr(self, f"_{level}_list")
        records = self._period_rows[level]
        query = self._global_query
        if query:
            records = [
                row for row in records
                if query in " ".join(
                    str(row.get(key) or "")
                    for key in ("period_key", "title", "content")
                ).lower()
            ]
        period_list.blockSignals(True)
        period_list.clear()
        for row in records:
            key = str(row.get("period_key") or "")
            display = _fmt_date(key) if len(key) >= 8 else key
            item = QListWidgetItem(f"{display}\n{row.get('title') or PERIOD_LABEL[level]}")
            item.setData(Qt.UserRole, row)
            item.setSizeHint(QSize(0, 58))
            item.setToolTip(str(row.get("title") or ""))
            period_list.addItem(item)
        period_list.blockSignals(False)
        if records:
            period_list.setCurrentRow(0)
        else:
            detail_layout = getattr(self, f"_{level}_detail")
            self._clear_layout(detail_layout)
            empty = QLabel(
                self._period_errors[level] or f"还没有匹配的{PERIOD_LABEL[level]}～"
            )
            empty.setObjectName("DiaryEmpty")
            empty.setAlignment(Qt.AlignCenter)
            detail_layout.addWidget(empty, 1)

    def _on_period_selected(self, level, item):
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if not data:
            return
        detail_layout = getattr(self, f"_{level}_detail")
        self._clear_layout(detail_layout)

        card = QFrame()
        card.setObjectName("DiaryPeriodDetail")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(10)
        title_row = QHBoxLayout()
        icon = QLabel()
        icon.setObjectName("DiaryPeriodIcon")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(
            _tinted_icon(_icon_path(PERIOD_ICON[level]), "#7e53dc", 17).pixmap(17, 17)
        )
        title_row.addWidget(icon)
        title = QLabel(str(data.get("title") or PERIOD_LABEL[level]))
        title.setObjectName("DiaryPeriodTitle")
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        title_row.addWidget(title, 1)
        layout.addLayout(title_row)
        meta_parts = [PERIOD_LABEL[level], _fmt_date(data.get("period_key", ""))]
        if data.get("event_count"):
            meta_parts.append(f"{data.get('event_count')} 个事件")
        meta = QLabel("  ·  ".join(part for part in meta_parts if part))
        meta.setObjectName("DiaryDetailMeta")
        layout.addWidget(meta)

        content = str(data.get("content") or "").strip()
        if content:
            body = QLabel(content)
            body.setObjectName("DiaryPeriodContent")
            body.setTextFormat(Qt.PlainText)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(body)

        highlights = _json_list(data.get("highlights"))
        if highlights:
            highlight_title = QLabel("本期亮点")
            highlight_title.setObjectName("DiaryPanelTitle")
            layout.addWidget(highlight_title)
            for highlight in highlights:
                label = QLabel(f"✦  {highlight}")
                label.setObjectName("DiaryHighlight")
                label.setTextFormat(Qt.PlainText)
                label.setWordWrap(True)
                layout.addWidget(label)
        layout.addStretch()
        detail_layout.addWidget(card)

    # -- Data ---------------------------------------------------------------

    def refresh_data(self):
        selected_date = self._selected_diary.get("date") if self._selected_diary else ""
        self._load_diaries(selected_date)
        for level in PERIOD_LABEL:
            self._load_periods(level)
        self._load_stats()

    def _load_diaries(self, selected_date=""):
        conn = None
        self._diary_error = ""
        try:
            conn = _get_db()
            self._diary_rows = [
                dict(row) for row in conn.execute("SELECT * FROM diary ORDER BY date DESC").fetchall()
            ]
        except Exception:
            self._diary_rows = []
            self._diary_error = "日记数据库暂时无法读取，请稍后刷新。"
        finally:
            if conn is not None:
                conn.close()
        self._render_diary_list(selected_date)
        self._update_calendar_marks()
        self._update_diary_stats()
        self._update_mood_trend()
        today_row = next(
            (row for row in self._diary_rows if row.get("date") == date.today().isoformat()),
            None,
        )
        self._sync_mood_display(today_row.get("mood", "") if today_row else "")

    def _load_periods(self, level):
        records = []
        conn = None
        self._period_errors[level] = ""
        try:
            conn = _get_db()
            records = [
                dict(row) for row in conn.execute(
                    "SELECT * FROM mf_summaries WHERE level=? ORDER BY period_key DESC",
                    (level,),
                ).fetchall()
            ]
        except Exception:
            records = []
            self._period_errors[level] = f"{PERIOD_LABEL[level]}数据库暂时无法读取，请稍后刷新。"
        finally:
            if conn is not None:
                conn.close()
        known = {str(row.get("period_key") or "") for row in records}
        directory = SUMMARY_DIRS[level]
        if os.path.isdir(directory):
            for filename in sorted(os.listdir(directory), reverse=True):
                if not filename.endswith(".md"):
                    continue
                key = filename[:-3]
                if key in known:
                    continue
                try:
                    with open(os.path.join(directory, filename), "r", encoding="utf-8") as handle:
                        content = handle.read()
                except OSError:
                    continue
                title = content.split("\n", 1)[0].lstrip("# ").strip() if content else key
                records.append(
                    {"period_key": key, "title": title, "content": content, "highlights": []}
                )
        records.sort(key=lambda row: str(row.get("period_key") or ""), reverse=True)
        self._period_rows[level] = records
        self._render_period_list(level)

    def _load_stats(self):
        self._clear_layout(self.stats_layout)
        today = date.today()
        iso_year, iso_week, _weekday = today.isocalendar()
        current_week_key = f"{iso_year}-W{iso_week:02d}"
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        days = len(self._diary_rows)
        weeks = 0
        months = 0
        years = 0
        for row in self._period_rows["weekly"]:
            key = str(row.get("period_key") or "")
            in_week = key == current_week_key
            try:
                key_date = datetime.strptime(key[:10], "%Y-%m-%d").date()
                in_week = in_week or week_start <= key_date <= week_end
            except ValueError:
                pass
            weeks += int(in_week)
        months = sum(
            1 for row in self._period_rows["monthly"]
            if str(row.get("period_key") or "").startswith(today.strftime("%Y-%m"))
        )
        years = sum(
            1 for row in self._period_rows["yearly"]
            if str(row.get("period_key") or "").startswith(str(today.year))
        )
        today_row = next(
            (row for row in self._diary_rows if row.get("date") == today.isoformat()), None
        )
        today_count = _entry_count(today_row.get("details")) if today_row else 0

        cards = (
            ("累计记录天数", f"{days} 天", "calendar", "#7953dc"),
            ("本周周记", f"{weeks} 篇", "quote", "#7b5ce1"),
            ("本月月报", f"{months} 篇", "discover", "#6984e8"),
            ("今年年鉴", f"{years} 篇", "star", "#efa65a"),
            ("今天流水", f"{today_count} 条", "emoji", "#9a53e8"),
        )
        for card in cards:
            self.stats_layout.addWidget(self._stat_card(*card), 1)

    def _update_calendar_marks(self):
        self.calendar.set_entry_dates(row.get("date", "") for row in self._diary_rows)
        if self._selected_diary:
            self.calendar.set_selected_date(self._selected_diary.get("date", ""))

    def _update_diary_stats(self):
        """右侧「日记统计」：记录天数 / 连续天数 / 已写篇数。"""
        try:
            rows = self._diary_rows
            total = len(rows)
            streak = 0
            cursor = date.today()
            while cursor.isoformat() in {row.get("date") for row in rows}:
                streak += 1
                cursor -= timedelta(days=1)
            written = sum(1 for row in rows if (row.get("summary") or "").strip())
            for key, value in (("days", f"{total}"), ("streak", f"{streak}"), ("written", f"{written}")):
                if key in self._stat_values:
                    self._stat_values[key].setText(value)
        except Exception:
            pass

    def _update_mood_trend(self):
        """右侧「心情趋势」：最近 7 天的心情圆点。"""
        try:
            by_date = {row.get("date"): str(row.get("mood") or "") for row in self._diary_rows}
            colors = {
                "开心": "#f2b3c9",
                "平静": "#9db8ea",
                "思考": "#b7a4ea",
                "疲惫": "#a9a9b8",
                "难过": "#7f8cb8",
            }
            today = date.today()
            for i in range(7):
                day = today - timedelta(days=6 - i)
                dot = self._mood_dots[i]
                self._mood_day_labels[i].setText(str(day.day))
                mood_text = by_date.get(day.isoformat(), "")
                if mood_text:
                    key = next((name for name, _label, _key in MOODS if name in mood_text), "")
                    color = colors.get(key, "#d9cdf0")
                    dot.setStyleSheet(f"background:{color};border-radius:12px;")
                    dot.setToolTip(f"{day.isoformat()}\n心情：{mood_text}")
                else:
                    dot.setStyleSheet("border:1px dashed rgba(139,118,178,0.45);border-radius:12px;")
                    dot.setToolTip(f"{day.isoformat()}\n没有记录")
        except Exception:
            pass

    # -- Actions ------------------------------------------------------------

    def _add_memory(self):
        text, accepted = QInputDialog.getMultiLineText(
            self, "新建记忆", "写下这一刻想保存的内容："
        )
        text = " · ".join(
            line.strip() for line in str(text or "").splitlines() if line.strip()
        )
        if not accepted or not text:
            return
        today_row = diary_module.get_or_create_today()
        timestamp = datetime.now().strftime("%H:%M")
        diary_module.append_details(today_row["date"], f"[{timestamp}] {text}")
        self.refresh_data()
        self._select_diary_by_date(today_row["date"])

    def _set_today_mood(self, mood):
        today_row = diary_module.get_or_create_today()
        diary_module.update_diary(today_row["date"], mood=mood)
        self.refresh_data()
        self._select_diary_by_date(today_row["date"])

    def _sync_mood_display(self, mood):
        if mood is None:
            return
        mood_text = str(mood or "")
        selected = next((name for name, _label, _key in MOODS if name in mood_text), "")
        for name, button in self.mood_buttons.items():
            button.blockSignals(True)
            button.setChecked(name == selected)
            button.blockSignals(False)
        self.mood_copy.setText(MOOD_COPY.get(selected, "把今天的心情告诉六花吧～"))

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                widget = item.widget()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())

    def resizeEvent(self, event):
        width = self.width()
        if hasattr(self, "insights_panel"):
            self.insights_panel.setVisible(width >= 1270 and self.height() >= 720)
        if hasattr(self, "date_panel"):
            self.date_panel.setFixedWidth(174 if width < 1120 else 192)
        if hasattr(self, "top_bar_host"):
            available = self.top_bar.sizeHint().width() + ChatTopBar.RIGHT_MARGIN
            self.top_bar_host.set_preferred_width(available)
            self.top_bar_host.setMinimumWidth(0)
            self.top_bar_host.setMaximumWidth(available)
            self.top_bar.search.setFixedWidth(ChatTopBar.SEARCH_WIDTH)
        super().resizeEvent(event)
