"""Full-page surfing history dashboard."""

from collections import Counter
from datetime import date, datetime, timedelta
import os
import re
from urllib.parse import quote, urljoin, urlparse

from PyQt5.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import config
from brain import surf
from gui.dashboard_pages import (
    DashboardPage,
    DonutWidget,
    ElidedLabel,
    MiniTrendWidget,
    SettingsTopBar,
    add_group_header,
    icon_path,
)
from gui.chat_top_bar import ChatTopBar
from gui.surf_history_dialog import SurfTagRow, tag_row_size
from gui import dialog_theme


_CAT_COLORS = {
    "视频": "#f08db9",
    "网页": "#56a9df",
    "知识": "#59b88a",
    "图片": "#6bc5d6",
    "技术": "#8f70df",
    "其他": "#aaa3b7",
}

_SOURCE_CATEGORIES = {
    "bilibili": "视频",
    "youtube": "视频",
    "web": "网页",
    "argo": "知识",
    "smart_search": "图片",
    "image_search": "图片",
    "image": "图片",
    "github": "技术",
}

_SOURCE_LABELS = {
    "bilibili": "B站",
    "youtube": "YouTube",
    "web": "网页",
    "argo": "Argo",
    "smart_search": "智能搜图",
    "image_search": "搜图",
    "image": "图片",
    "github": "GitHub",
}

_SOURCE_HOSTS = {
    "bilibili": "bilibili.com",
    "youtube": "youtube.com",
    "github": "github.com",
}


def _host_from_url(url):
    """Return a normalized hostname for a record URL, if one is available."""
    value = str(url or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    try:
        return (urlparse(value).hostname or "").lower().strip(".")
    except ValueError:
        return ""


def _url_from_detail(detail):
    """Recover the first URL from text-only search records (web/Argo)."""
    match = re.search(r"https?://[^\s<>\"']+", str(detail or ""))
    return match.group(0).rstrip(".,);]}") if match else ""


class _FaviconWorkerSignals(QObject):
    finished = pyqtSignal(str, bytes)


class _FaviconWorker(QRunnable):
    """Fetch one site's icon without blocking the Qt GUI thread."""

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.signals = _FaviconWorkerSignals()

    @staticmethod
    def _icon_href(html, base_url):
        """Read icon declarations regardless of rel/href attribute order."""
        def attr(tag, name):
            match = re.search(
                rf"\b{name}\s*=\s*(?:['\"]([^'\"]*)['\"]|([^\s>]+))",
                tag,
                flags=re.I,
            )
            return (match.group(1) or match.group(2)).strip() if match else ""

        for tag in re.findall(r"<link\b[^>]*>", html or "", flags=re.I):
            rel = attr(tag, "rel")
            href = attr(tag, "href")
            if not rel or not href:
                continue
            rel_tokens = {part.lower() for part in rel.split()}
            if rel_tokens.intersection({"icon", "shortcut", "apple-touch-icon"}):
                return urljoin(base_url, href)
        return ""

    def run(self):
        payload = b""
        try:
            import requests

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                ),
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            }
            base_url = f"https://{self.host}/"
            candidates = [f"https://{self.host}/favicon.ico"]

            # Standard browser behavior: honor the page's explicit <link rel="icon">.
            try:
                page = requests.get(base_url, headers=headers, timeout=8, allow_redirects=True)
                if page.ok:
                    declared = self._icon_href(page.text[:600_000], page.url or base_url)
                    if declared:
                        candidates.insert(0, declared)
            except Exception:
                pass

            encoded = quote(self.host, safe=".-")
            candidates.extend((
                f"https://icons.duckduckgo.com/ip3/{encoded}.ico",
                f"https://www.google.com/s2/favicons?domain={encoded}&sz=64",
            ))
            seen = set()
            for url in candidates:
                if not url or url in seen:
                    continue
                seen.add(url)
                try:
                    response = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
                    data = response.content or b""
                    if response.ok and len(data) >= 16:
                        # QPixmap.loadFromData validates the actual image in the UI thread.
                        payload = data
                        break
                except Exception:
                    continue
        except Exception:
            pass
        self.signals.finished.emit(self.host, payload)


class _FaviconLoader(QObject):
    """Threaded favicon cache shared by all visible timeline rows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache = {}
        self._pending = {}
        self._pool = QThreadPool.globalInstance()

    def request(self, host, callback):
        host = str(host or "").lower().strip(".")
        if not host:
            return
        if host in self._cache:
            callback(self._cache[host])
            return
        self._pending.setdefault(host, []).append(callback)
        if len(self._pending[host]) > 1:
            return
        worker = _FaviconWorker(host)
        worker.signals.finished.connect(self._finished)
        self._pool.start(worker)

    def _finished(self, host, payload):
        pixmap = QPixmap()
        if payload:
            pixmap.loadFromData(payload)
        self._cache[host] = pixmap
        callbacks = self._pending.pop(host, [])
        for callback in callbacks:
            try:
                callback(pixmap)
            except RuntimeError:
                # A row may have been removed while its request was in flight.
                pass


_favicon_loader = None


def _get_favicon_loader():
    global _favicon_loader
    if _favicon_loader is None:
        _favicon_loader = _FaviconLoader()
    return _favicon_loader


class FaviconLabel(QLabel):
    """Stable 38px favicon surface with a domain-initial fallback."""

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self._host = str(host or "").lower()
        self.setObjectName("SurfFavicon")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(38, 38)
        self.setText((self._host.split(".")[0] or "web")[:2].upper())
        if self._host:
            _get_favicon_loader().request(self._host, self._set_pixmap)

    def _set_pixmap(self, pixmap):
        if pixmap.isNull() or not self._host:
            return
        scaled = pixmap.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setText("")
        self.setPixmap(scaled)
        self.setProperty("loaded", True)
        self.style().unpolish(self)
        self.style().polish(self)


def _source_label(source):
    source = str(source or "web")
    return _SOURCE_LABELS.get(source, source or "网页")


def _record_category(record):
    return _SOURCE_CATEGORIES.get(str(record.get("source") or ""), "其他")


def _record_datetime(record):
    raw = str(record.get("time") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _record_display(record):
    """Promote useful nested result metadata over generic search titles."""
    title = str(record.get("title") or "无标题").strip()
    url = str(record.get("url") or "").strip()
    author = ""
    results = record.get("results") or []
    if results and isinstance(results[0], dict):
        first = results[0]
        nested_title = str(first.get("title") or "").strip()
        if nested_title and (
            str(record.get("source") or "") == "bilibili"
            or title.startswith("B站:")
            or title in ("", "无标题")
        ):
            title = nested_title
        url = url or str(first.get("url") or "").strip()
        author = str(first.get("author") or "").strip()
    url = url or _url_from_detail(record.get("detail"))
    if title.count("\ufffd") >= 2:
        title = str(record.get("tag") or "").strip() or "编码异常的历史记录"
    return title or "无标题", url, author


class SurfStatCard(QFrame):
    """Compact stat card using the repository's violet line icons."""

    def __init__(self, title, icon_name, suffix="", tone="violet", parent=None):
        super().__init__(parent)
        self.setObjectName("SurfStatCard")
        self.setProperty("tone", tone)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self._suffix = str(suffix or "").strip()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(13, 10, 13, 10)
        layout.setSpacing(10)
        badge = QLabel()
        badge.setObjectName("SurfStatIcon")
        badge.setProperty("tone", tone)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(38, 38)
        badge.setPixmap(QIcon(icon_path(icon_name)).pixmap(20, 20))
        layout.addWidget(badge)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        caption = QLabel(title)
        caption.setObjectName("DashboardStatCaption")
        caption.setMinimumHeight(18)
        caption.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        copy.addWidget(caption)
        self.value_label = QLabel(self._format_value(0))
        self.value_label.setObjectName("SurfStatValue")
        self.value_label.setMinimumHeight(29)
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        copy.addWidget(self.value_label)
        layout.addLayout(copy, 1)

    def _format_value(self, value):
        return f"{value} {self._suffix}" if self._suffix else str(value)

    def set_value(self, value):
        self.value_label.setText(self._format_value(value))


class SurfTimelineRow(QWidget):
    """Page-specific compact timeline row; dialog cards remain unchanged."""

    def __init__(self, record, on_favorite, parent=None):
        super().__init__(parent)
        self._record = record
        self._record_id = str(record.get("id") or "")
        title, url, author = _record_display(record)
        stamp = _record_datetime(record)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 2, 2, 2)
        outer.setSpacing(8)

        time_label = QLabel(stamp.strftime("%H:%M") if stamp else "--:--")
        time_label.setObjectName("SurfTimelineTime")
        time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        time_label.setFixedWidth(42)
        outer.addWidget(time_label)

        marker = QLabel("●")
        marker.setObjectName("SurfTimelineMarker")
        marker.setAlignment(Qt.AlignCenter)
        marker.setFixedWidth(14)
        outer.addWidget(marker)

        surface = QFrame()
        surface.setObjectName("SurfTimelineSurface")
        row = QHBoxLayout(surface)
        row.setContentsMargins(12, 8, 10, 8)
        row.setSpacing(10)

        source = str(record.get("source") or "web")
        host = _host_from_url(url) or _SOURCE_HOSTS.get(source, "")
        row.addWidget(FaviconLabel(host))

        copy = QVBoxLayout()
        copy.setSpacing(4)
        title_label = ElidedLabel(title)
        title_label.setObjectName("SurfTimelineTitle")
        title_label.setToolTip(title)
        title_label.setMinimumHeight(20)
        copy.addWidget(title_label)
        meta_parts = []
        if host:
            meta_parts.append(host)
        elif record.get("detail"):
            meta_parts.append(str(record.get("detail") or "").splitlines()[0][:120])
        if author:
            meta_parts.append(author)
        tag_text = str(record.get("tag") or "").strip()
        if tag_text and tag_text != title:
            meta_parts.append(tag_text)
        meta = ElidedLabel("  ·  ".join(meta_parts) or "本地冲浪记录")
        meta.setObjectName("SurfTimelineMeta")
        meta.setToolTip(url or meta.text())
        copy.addWidget(meta)
        row.addLayout(copy, 1)

        source_pill = QLabel(_source_label(source))
        source_pill.setObjectName("SurfSourcePill")
        source_pill.setProperty("category", _record_category(record))
        source_pill.setAlignment(Qt.AlignCenter)
        source_pill.setFixedSize(52, 28)
        row.addWidget(source_pill)

        result_count = len(record.get("results") or [])
        if result_count or url:
            result_count = max(1, result_count)
            result_meta = QWidget()
            result_meta.setObjectName("SurfResultMeta")
            result_layout = QHBoxLayout(result_meta)
            result_layout.setContentsMargins(3, 0, 3, 0)
            result_layout.setSpacing(3)
            result_icon = QLabel()
            result_icon.setObjectName("SurfResultIcon")
            result_icon.setAlignment(Qt.AlignCenter)
            result_icon.setPixmap(QIcon(icon_path("quote")).pixmap(13, 13))
            result_layout.addWidget(result_icon)
            result_label = QLabel(f"{result_count} 页")
            result_label.setObjectName("SurfResultCount")
            result_layout.addWidget(result_label)
            row.addWidget(result_meta)

        favorite = QPushButton("★" if record.get("favorite") else "☆")
        favorite.setObjectName("SurfFavoriteButton")
        favorite.setProperty("active", bool(record.get("favorite")))
        favorite.setToolTip("取消收藏" if record.get("favorite") else "收藏")
        favorite.clicked.connect(lambda: on_favorite(self._record_id))
        row.addWidget(favorite)

        more_button = QPushButton()
        more_button.setObjectName("SurfMoreButton")
        more_button.setIcon(QIcon(icon_path("more")))
        more_button.setIconSize(QSize(16, 16))
        more_button.setToolTip("更多操作" if url else "这条记录没有可用链接")
        more_button.setEnabled(bool(url))
        more_button.clicked.connect(lambda: self._show_more_menu(more_button, url))
        row.addWidget(more_button)

        outer.addWidget(surface, 1)

    @staticmethod
    def _show_more_menu(button, url):
        if not url:
            return
        menu = QMenu(button)
        menu.setObjectName("SurfRowMenu")
        open_action = menu.addAction(QIcon(icon_path("discover")), "打开网页")
        copy_action = menu.addAction(QIcon(icon_path("share")), "复制链接")
        chosen = menu.exec_(button.mapToGlobal(button.rect().bottomLeft()))
        if chosen == open_action:
            QDesktopServices.openUrl(QUrl(url))
        elif chosen == copy_action:
            QApplication.clipboard().setText(url)


class SurfTagManagerDialog(QDialog):
    """Keep interest-tag controls available without crushing the timeline."""

    def __init__(self, on_changed=None, parent=None):
        super().__init__(parent)
        palette = dialog_theme.colors()
        self.setStyleSheet(
            f"QDialog{{background:{palette['surface_soft']};color:{palette['text']};}}"
            f"QLabel{{color:{palette['text']};}} QLineEdit{{background:{palette['field']};"
            f"color:{palette['text']};border:1px solid {palette['border_accent']};border-radius:10px;"
            f"padding:0 10px;}} QListWidget{{background:{palette['surface']};border:1px solid {palette['border_accent']};border-radius:12px;}}"
        )
        self._on_changed = on_changed
        self.setObjectName("SurfTagManagerDialog")
        self.setWindowTitle("管理冲浪兴趣")
        self.resize(560, 440)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        title = QLabel("兴趣标签")
        title.setObjectName("DashboardSectionTitle")
        root.addWidget(title)
        helper = QLabel("六花会优先探索启用的标签；你可以随时暂停或删除不想继续关注的兴趣。")
        helper.setObjectName("DashboardMuted")
        helper.setWordWrap(True)
        root.addWidget(helper)

        add_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("添加兴趣标签...")
        self.input.returnPressed.connect(self._add)
        add_row.addWidget(self.input, 1)
        add_button = QPushButton("添加")
        add_button.setObjectName("DashboardPrimaryButton")
        add_button.clicked.connect(self._add)
        add_row.addWidget(add_button)
        root.addLayout(add_row)

        self.list = QListWidget()
        self.list.setObjectName("SurfTagList")
        self.list.setSelectionMode(QListWidget.NoSelection)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.list, 1)

        close_button = QPushButton("完成")
        close_button.setObjectName("DashboardSecondaryButton")
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button, 0, Qt.AlignRight)
        self._refresh()

    def _changed(self):
        self._refresh()
        if self._on_changed:
            self._on_changed()

    def _add(self):
        keyword = self.input.text().strip()
        if not keyword:
            return
        surf.get_store().add_tag(keyword, source="manual")
        self.input.clear()
        self._changed()

    def _toggle(self, keyword):
        store = surf.get_store()
        paused = any(
            item.get("keyword") == keyword and item.get("status") == "paused"
            for item in store.get_tags()
        )
        (store.resume_tag if paused else store.pause_tag)(keyword)
        self._changed()

    def _delete(self, keyword):
        surf.get_store().remove_tag(keyword)
        self._changed()

    def _refresh(self):
        self.list.clear()
        tags = surf.get_store().get_tags()
        for tag in tags:
            item = QListWidgetItem()
            item.setSizeHint(tag_row_size())
            self.list.addItem(item)
            self.list.setItemWidget(item, SurfTagRow(tag, self._toggle, self._delete))
        if not tags:
            empty = QListWidgetItem("还没有兴趣标签")
            empty.setTextAlignment(Qt.AlignCenter)
            self.list.addItem(empty)


class SurfHistoryPage(DashboardPage):
    def __init__(self, parent=None):
        super().__init__(
            "SurfHistoryPage",
            "冲浪记录",
            "六花的网上冲浪足迹：搜索、浏览与发现",
            "workflow",
            parent,
            top_bar_cls=SettingsTopBar,
        )
        scene = QPixmap(os.path.join(
            config.ASSETS_DIR, "images", "settings", "settings_scene_background.png"
        ))
        if not scene.isNull():
            self._background = scene
        self._background_wash = QColor(250, 246, 255, 30)
        self.top_bar.search.setPlaceholderText("搜索记录标题、标签或结果...")
        self.top_bar.search.setFixedWidth(ChatTopBar.SEARCH_WIDTH)
        self.top_bar.search_changed.connect(self._on_query_changed)
        self._favorite_only = False
        self._visible_limit = 60
        self._build_ui()
        self.refresh_data()

    def _build_ui(self):
        heading_item = self.root.takeAt(0)
        heading_layout = heading_item.layout()

        left_panel = QWidget()
        left_panel.setObjectName("SurfMainColumn")
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)
        left.addLayout(heading_layout)

        stats = QHBoxLayout()
        stats.setSpacing(9)
        self._stat_today = SurfStatCard("今日记录", "workflow", "条", "pink")
        self._stat_total = SurfStatCard("累计记录", "history", "条", "violet")
        self._stat_seen = SurfStatCard("已发现链接", "discover", "个", "blue")
        self._stat_fav = SurfStatCard("收藏记录", "favorite", "条", "gold")
        for card in (self._stat_today, self._stat_total, self._stat_seen, self._stat_fav):
            stats.addWidget(card, 1)
        left.addLayout(stats)

        filter_card = self.card()
        filter_card.setObjectName("SurfFilterCard")
        filters = QHBoxLayout(filter_card)
        filters.setContentsMargins(10, 8, 10, 8)
        filters.setSpacing(7)
        self._tab_all = QPushButton("全部记录")
        self._tab_all.setObjectName("DashboardChip")
        self._tab_all.setProperty("active", True)
        self._tab_all.clicked.connect(lambda: self._set_favorite_filter(False))
        filters.addWidget(self._tab_all)
        self._tab_fav = QPushButton("收藏记录")
        self._tab_fav.setObjectName("DashboardChip")
        self._tab_fav.clicked.connect(lambda: self._set_favorite_filter(True))
        filters.addWidget(self._tab_fav)
        filters.addStretch()

        self.date_combo = QComboBox()
        self.date_combo.setObjectName("SurfFilterCombo")
        self.date_combo.addItem("全部日期", "all")
        self.date_combo.addItem("今天", "today")
        self.date_combo.addItem("近 7 天", "7")
        self.date_combo.addItem("近 30 天", "30")
        self.date_combo.currentIndexChanged.connect(self._filter_changed)
        filters.addWidget(self.date_combo)

        self.type_combo = QComboBox()
        self.type_combo.setObjectName("SurfFilterCombo")
        self.type_combo.addItem("全部类型", "")
        for category in ("视频", "网页", "知识", "图片", "技术", "其他"):
            self.type_combo.addItem(category, category)
        self.type_combo.currentIndexChanged.connect(self._filter_changed)
        filters.addWidget(self.type_combo)

        self.source_combo = QComboBox()
        self.source_combo.setObjectName("SurfFilterCombo")
        self.source_combo.currentIndexChanged.connect(self._filter_changed)
        filters.addWidget(self.source_combo)

        clear_button = QPushButton()
        clear_button.setObjectName("DashboardIconButton")
        clear_button.setProperty("tone", "danger")
        clear_button.setIcon(QIcon(icon_path("delete")))
        clear_button.setToolTip("清空全部冲浪记录")
        clear_button.clicked.connect(self._confirm_clear)
        filters.addWidget(clear_button)
        left.addWidget(filter_card)

        timeline_card = self.card()
        timeline_card.setObjectName("SurfTimelineCard")
        timeline = QVBoxLayout(timeline_card)
        timeline.setContentsMargins(13, 11, 13, 10)
        timeline.setSpacing(7)
        timeline.addLayout(self.section_row("浏览时间线"))
        self.list = QListWidget()
        self.list.setObjectName("SurfHistoryList")
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setSelectionMode(QListWidget.NoSelection)
        timeline.addWidget(self.list, 1)
        self.load_more = QPushButton("加载更多记录")
        self.load_more.setObjectName("DashboardLoadMore")
        self.load_more.clicked.connect(self._load_more)
        timeline.addWidget(self.load_more)
        self.rail = QWidget()
        self.rail.setObjectName("SurfInsightsRail")
        self.rail.setFixedWidth(300)
        rail = QVBoxLayout(self.rail)
        rail.setContentsMargins(0, 0, 0, 0)
        rail.setSpacing(11)

        trend_card = self.card()
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(13, 11, 13, 10)
        trend_layout.setSpacing(4)
        trend_layout.addLayout(self.section_row("冲浪概览", "近 7 天"))
        self._trend = MiniTrendWidget()
        self._trend.setMinimumHeight(98)
        trend_layout.addWidget(self._trend)
        rail.addWidget(trend_card)

        category_card = self.card()
        category_layout = QVBoxLayout(category_card)
        category_layout.setContentsMargins(13, 11, 13, 10)
        category_layout.setSpacing(5)
        category_layout.addLayout(self.section_row("网站分类分布"))
        category_row = QHBoxLayout()
        category_row.setSpacing(8)
        self._cat_donut = DonutWidget()
        self._cat_donut.setFixedSize(92, 92)
        category_row.addWidget(self._cat_donut)
        self._cat_list = QVBoxLayout()
        self._cat_list.setSpacing(2)
        category_row.addLayout(self._cat_list, 1)
        category_layout.addLayout(category_row)
        rail.addWidget(category_card)

        tags_card = self.card()
        tags_layout = QVBoxLayout(tags_card)
        tags_layout.setContentsMargins(13, 11, 13, 11)
        tags_layout.setSpacing(7)
        tags_layout.addLayout(self.section_row("热门标签", "管理兴趣", self._manage_tags))
        self._hot_grid = QGridLayout()
        self._hot_grid.setSpacing(5)
        tags_layout.addLayout(self._hot_grid)
        rail.addWidget(tags_card)

        favorites_card = self.card()
        favorites_card.setMinimumHeight(178)
        favorites_card.setMaximumHeight(220)
        favorites_layout = QVBoxLayout(favorites_card)
        favorites_layout.setContentsMargins(13, 11, 13, 10)
        favorites_layout.setSpacing(5)
        favorites_layout.addLayout(self.section_row("最近收藏", "查看全部", lambda: self._set_favorite_filter(True)))
        self._fav_list = QVBoxLayout()
        self._fav_list.setSpacing(4)
        favorites_layout.addLayout(self._fav_list)
        rail.addWidget(favorites_card)
        rail.addStretch()

        # Keep the insights rail aligned with the timeline, below the title,
        # stats, and filters instead of placing it at the page top.
        content_row = QHBoxLayout()
        content_row.setSpacing(14)
        content_row.addWidget(timeline_card, 1)
        content_row.addWidget(self.rail)
        left.addLayout(content_row, 1)
        self.root.addWidget(left_panel, 1)

    def _on_query_changed(self, _text):
        self._visible_limit = 60
        self.refresh_data()

    def _filter_changed(self, _index):
        self._visible_limit = 60
        self.refresh_data()

    def _set_favorite_filter(self, favorite_only):
        self._favorite_only = bool(favorite_only)
        self._visible_limit = 60
        self._tab_all.setProperty("active", not self._favorite_only)
        self._tab_fav.setProperty("active", self._favorite_only)
        for button in (self._tab_all, self._tab_fav):
            button.style().unpolish(button)
            button.style().polish(button)
        self.refresh_data()

    def _load_more(self):
        self._visible_limit += 60
        self.refresh_data()

    def _on_favorite(self, record_id):
        surf.toggle_favorite(record_id)
        self.refresh_data()

    def _manage_tags(self):
        SurfTagManagerDialog(self.refresh_data, self).exec_()

    def _set_tag_search(self, tag):
        self.top_bar.search.setText(str(tag))
        self.top_bar.search.setFocus()

    def _date_matches(self, record):
        mode = self.date_combo.currentData() or "all"
        if mode == "all":
            return True
        stamp = _record_datetime(record)
        if stamp is None:
            return False
        today = date.today()
        if mode == "today":
            return stamp.date() == today
        try:
            days = int(mode)
        except (TypeError, ValueError):
            return True
        return stamp.date() >= today - timedelta(days=max(0, days - 1))

    def refresh_data(self):
        query = self.top_bar.search.text().strip()
        source = self.source_combo.currentData() or ""
        all_rows = surf.get_records(limit=500)
        rows = surf.get_records(
            limit=500,
            source=source,
            query=query,
            favorite_only=self._favorite_only,
        )
        category = self.type_combo.currentData() or ""
        rows = [
            record for record in rows
            if self._date_matches(record)
            and (not category or _record_category(record) == category)
        ]

        current_source = source
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItem("全部来源", "")
        for value in surf.get_store().sources():
            self.source_combo.addItem(_source_label(value), value)
        index = self.source_combo.findData(current_source)
        self.source_combo.setCurrentIndex(index if index >= 0 else 0)
        self.source_combo.blockSignals(False)

        self.list.clear()
        visible = rows[:self._visible_limit]
        last_day = None
        for record in visible:
            stamp = _record_datetime(record)
            day_key = stamp.date().isoformat() if stamp else "较早"
            if day_key != last_day:
                if stamp and stamp.date() == date.today():
                    day_label = "今天"
                elif stamp and stamp.date() == date.today() - timedelta(days=1):
                    day_label = "昨天"
                elif stamp:
                    day_label = stamp.strftime("%Y年%m月%d日")
                else:
                    day_label = "较早记录"
                add_group_header(self.list, day_label)
                last_day = day_key
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 76))
            self.list.addItem(item)
            self.list.setItemWidget(
                item,
                SurfTimelineRow(record, self._on_favorite),
            )
        if not rows:
            empty = QListWidgetItem("没有找到符合条件的冲浪记录")
            empty.setTextAlignment(Qt.AlignCenter)
            empty.setSizeHint(QSize(0, 90))
            self.list.addItem(empty)

        remaining = max(0, len(rows) - len(visible))
        self.load_more.setVisible(remaining > 0)
        self.load_more.setText(f"加载更多记录（还有 {remaining} 条）")
        self._refresh_insights(all_rows)

    def _refresh_insights(self, all_rows):
        stats = surf.get_surf_stats()
        today = date.today()
        today_count = sum(
            1 for record in all_rows
            if (stamp := _record_datetime(record)) is not None and stamp.date() == today
        )
        self._stat_today.set_value(today_count)
        self._stat_total.set_value(stats.get("total", len(all_rows)))
        self._stat_seen.set_value(stats.get("seen", 0))
        self._stat_fav.set_value(stats.get("favorites", 0))

        days = [today - timedelta(days=index) for index in range(6, -1, -1)]
        daily = Counter(
            stamp.date().isoformat()
            for record in all_rows
            if (stamp := _record_datetime(record)) is not None
        )
        self._trend.set_data(
            [f"{day.month}/{day.day}" for day in days],
            [daily[day.isoformat()] for day in days],
        )

        categories = Counter(_record_category(record) for record in all_rows)
        total = sum(categories.values())
        top = categories.most_common(6)
        self._cat_donut.set_segments(
            [
                (name, count, QColor(_CAT_COLORS.get(name, "#aaa3b7")))
                for name, count in top
            ],
            "总计",
            str(total),
        )
        self._clear_layout(self._cat_list)
        denominator = max(1, total)
        for name, count in top:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(5)
            dot = QLabel()
            dot.setFixedSize(7, 7)
            dot.setStyleSheet(
                f"background:{_CAT_COLORS.get(name, '#aaa3b7')};border-radius:3px;"
            )
            layout.addWidget(dot)
            label = QLabel(name)
            label.setObjectName("DashboardMuted")
            layout.addWidget(label, 1)
            percent = QLabel(f"{round(count / denominator * 100)}%")
            percent.setObjectName("SurfLegendValue")
            layout.addWidget(percent)
            self._cat_list.addWidget(row)
        if not top:
            empty = QLabel("暂无分类数据")
            empty.setObjectName("DashboardMuted")
            self._cat_list.addWidget(empty)

        self._clear_layout(self._hot_grid)
        hot_tags = Counter(
            str(record.get("tag") or "").strip()
            for record in all_rows
            if str(record.get("tag") or "").strip()
        ).most_common(8)
        for index, (tag, count) in enumerate(hot_tags):
            short_tag = tag if len(tag) <= 12 else tag[:11] + "..."
            chip = QPushButton(f"#{short_tag}  {count}")
            chip.setObjectName("SurfTagChip")
            chip.setToolTip(f"搜索标签：{tag}")
            chip.clicked.connect(lambda _checked=False, value=tag: self._set_tag_search(value))
            self._hot_grid.addWidget(chip, index // 2, index % 2)
        if not hot_tags:
            empty = QLabel("暂无热门标签")
            empty.setObjectName("DashboardMuted")
            self._hot_grid.addWidget(empty, 0, 0, 1, 2)

        self._clear_layout(self._fav_list)
        favorites = [record for record in all_rows if record.get("favorite")][:4]
        for record in favorites:
            title, url, _author = _record_display(record)
            button = QPushButton(title)
            button.setObjectName("SurfFavoriteRow")
            button.setToolTip(url or title)
            button.setEnabled(bool(url))
            button.clicked.connect(
                lambda _checked=False, value=url: QDesktopServices.openUrl(QUrl(value))
            )
            self._fav_list.addWidget(button)
        if not favorites:
            empty = QLabel("还没有收藏记录")
            empty.setObjectName("DashboardMuted")
            self._fav_list.addWidget(empty)
        self._fav_list.addStretch()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                SurfHistoryPage._clear_layout(child_layout)

    def _confirm_clear(self):
        if surf.get_surf_stats().get("total", 0) == 0:
            return
        result = QMessageBox.question(
            self,
            "清空记录",
            "确定要清空全部冲浪记录吗？兴趣标签会保留。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if result == QMessageBox.Yes:
            surf.clear_records()
            self._visible_limit = 60
            self.refresh_data()

    def resizeEvent(self, event):
        if hasattr(self, "rail"):
            if self.width() >= 1350:
                self.rail.setFixedWidth(320)
            elif self.width() >= 1120:
                self.rail.setFixedWidth(275)
            else:
                self.rail.setFixedWidth(235)
        super().resizeEvent(event)
