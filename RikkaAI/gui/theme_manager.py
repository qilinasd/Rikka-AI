"""Runtime seasonal theme application for RikkaAI.

单一一套 QSS 主题在启动时加载；这里提供两种运行时外观：
- 主题：accent 色 + 各页背景 wash 染色（theme_override 生成追加在基础 QSS 后的覆盖段）
- 页面壁纸由每个主题的内置资源统一提供。

纯数据 + 生成器，不持有 Qt 组件；由 MainWindow 接线应用。
"""
import os
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Tuple

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

# ── 主题 ────────────────────────────────────────────────────────

THEMES = {
    "梦幻樱花主题": {
        "accent": "#d4679c",
        "accent_deep": "#b4528a",
        "accent_soft": "rgba(212,103,156,0.16)",
        "accent_text": "#ffffff",
        "text": "#3a2f4d",
        "card": "rgba(255,250,253,0.88)",
        "wash": QColor(252, 240, 248, 120),
    },
    "星夜静谧": {
        "accent": "#5b6ee1",
        "accent_deep": "#4553bd",
        "accent_soft": "rgba(91,110,225,0.16)",
        "accent_text": "#ffffff",
        "text": "#2e3557",
        "card": "rgba(247,249,255,0.88)",
        "wash": QColor(236, 240, 252, 120),
    },
    "极简浅色": {
        "accent": "#8a8aa0",
        "accent_deep": "#6f6f88",
        "accent_soft": "rgba(138,138,160,0.16)",
        "accent_text": "#ffffff",
        "text": "#353541",
        "card": "rgba(252,251,253,0.90)",
        "wash": QColor(247, 246, 250, 120),
    },
    "深色优雅": {
        "accent": "#9c7be0",
        "accent_deep": "#7d5fc0",
        "accent_soft": "rgba(156,123,224,0.20)",
        "accent_text": "#ffffff",
        "text": "#eae6f8",
        "card": "rgba(42,35,66,0.80)",
        "wash": QColor(28, 24, 40, 150),
    },
}

_DEFAULT_THEME = "梦幻樱花主题"
_CURRENT = _DEFAULT_THEME

_THEME_IMAGE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "assets", "images", "themes"
)

THEME_PAGE_IDS = (
    "home", "chat", "diary",
    "memory", "history", "surfing", "settings",
)

_THEME_PAGE_ALIASES = {
    "surf": "surfing",
    "surf_history": "surfing",
    "surf-history": "surfing",
}


def normalize_page_id(page_id):
    """Return a stable runtime page id used by the seasonal asset tree."""
    value = str(page_id or "home").strip().lower()
    value = _THEME_PAGE_ALIASES.get(value, value)
    if value not in THEME_PAGE_IDS:
        raise ValueError(f"unknown seasonal theme page: {page_id!r}")
    return value


def seasonal_background_path(theme_id, page_id="home"):
    """Path to one of the 4 season x 7 page-specific runtime artworks."""
    page_id = normalize_page_id(page_id)
    return os.path.join(_THEME_IMAGE_ROOT, str(theme_id), f"{page_id}.png")


@dataclass(frozen=True)
class SeasonalTheme:
    """Data-only seasonal palette and replaceable background contract."""

    id: str
    display_name: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    text: str
    card: str
    wash: Tuple[int, int, int, int]
    icon: str
    background_path: str
    fallback_background: str


@dataclass(frozen=True)
class ResolvedAppearance:
    """Effective appearance without mutating the user's manual preferences."""

    key: str
    mode: str
    theme_id: str
    display_name: str
    accent: str
    accent_hover: str
    accent_soft: str
    accent_text: str
    text: str
    card: str
    wash: Tuple[int, int, int, int]
    icon: str = ""
    background_path: str = ""
    fallback_background: str = "樱花湖畔"

    def wash_color(self):
        return QColor(*self.wash)


SEASONAL_THEMES = {
    "spring": SeasonalTheme(
        "spring", "春季主题", "#FFB7D5", "#F58AB8", "rgba(255,183,213,0.18)",
        "#35233A", "#3A2F4D", "rgba(255,250,253,0.88)", (255, 244, 250, 132),
        "sakura", os.path.join(_THEME_IMAGE_ROOT, "spring", "background.png"), "樱花湖畔",
    ),
    "summer": SeasonalTheme(
        "summer", "夏季主题", "#4FC3F7", "#259FCF", "rgba(79,195,247,0.18)",
        "#173349", "#263338", "rgba(247,254,255,0.88)", (238, 252, 253, 128),
        "leaf", os.path.join(_THEME_IMAGE_ROOT, "summer", "background.png"), "夏日湖畔",
    ),
    "autumn": SeasonalTheme(
        "autumn", "秋季主题", "#D65B2A", "#B94A20", "rgba(214,91,42,0.17)",
        "#FFFFFF", "#5B3A29", "rgba(255,250,244,0.88)", (255, 245, 232, 132),
        "maple", os.path.join(_THEME_IMAGE_ROOT, "autumn", "background.png"), "枫林夕照",
    ),
    "winter": SeasonalTheme(
        "winter", "冬季主题", "#7BA8FF", "#5C87E8", "rgba(123,168,255,0.18)",
        "#1E3153", "#2A3A5E", "rgba(248,251,255,0.90)", (243, 248, 255, 138),
        "snow", os.path.join(_THEME_IMAGE_ROOT, "winter", "background.png"), "雪山远景",
    ),
}


# These tokens are shared by the native dashboards and the WebEngine home.
# The generated artwork is intentionally visible through the surfaces, while
# the text and controls stay readable on both bright and dark scenes.
SEASONAL_STYLE_TOKENS = {
    "spring": {
        "surface": "rgba(255,252,255,0.84)",
        "surface_strong": "rgba(255,254,255,0.94)",
        "surface_soft": "rgba(255,247,252,0.66)",
        "data_surface": "rgba(255,252,255,0.82)",
        "field": "rgba(255,255,255,0.88)",
        "border": "rgba(255,255,255,0.78)",
        "border_accent": "rgba(238,142,192,0.38)",
        "text": "#33243d",
        "muted": "#6e5d76",
        "subtle": "#917f98",
        "nav": "rgba(255,248,253,0.78)",
        "nav_text": "#55405f",
        "chart": "#d77fb0",
        "focus": "#f08ab9",
    },
    "summer": {
        "surface": "rgba(248,253,255,0.84)",
        "surface_strong": "rgba(253,255,255,0.94)",
        "surface_soft": "rgba(239,251,255,0.68)",
        "data_surface": "rgba(244,252,255,0.82)",
        "field": "rgba(255,255,255,0.88)",
        "border": "rgba(255,255,255,0.80)",
        "border_accent": "rgba(79,195,247,0.40)",
        "text": "#18384b",
        "muted": "#557284",
        "subtle": "#7b96a3",
        "nav": "rgba(241,251,255,0.80)",
        "nav_text": "#3e6070",
        "chart": "#36add7",
        "focus": "#35b9e7",
    },
    "autumn": {
        "surface": "rgba(255,248,240,0.86)",
        "surface_strong": "rgba(255,252,246,0.94)",
        "surface_soft": "rgba(255,239,221,0.68)",
        "data_surface": "rgba(47,29,31,0.78)",
        "field": "rgba(255,247,237,0.90)",
        "border": "rgba(255,228,199,0.68)",
        "border_accent": "rgba(214,91,42,0.44)",
        "text": "#4b2f2a",
        "muted": "#76574a",
        "subtle": "#a48678",
        "nav": "rgba(43,27,33,0.78)",
        "nav_text": "#f4dfce",
        "chart": "#e07b40",
        "focus": "#e06b32",
        "data_text": "#fff2e5",
        "data_muted": "#e3c5b2",
        "data_subtle": "#b99887",
        "data_field": "rgba(67,39,39,0.84)",
        "data_border": "rgba(249,183,126,0.26)",
    },
    "winter": {
        "surface": "rgba(248,251,255,0.86)",
        "surface_strong": "rgba(253,255,255,0.95)",
        "surface_soft": "rgba(237,245,255,0.70)",
        "data_surface": "rgba(242,248,255,0.84)",
        "field": "rgba(255,255,255,0.90)",
        "border": "rgba(255,255,255,0.82)",
        "border_accent": "rgba(123,168,255,0.42)",
        "text": "#213252",
        "muted": "#5c708d",
        "subtle": "#8295ad",
        "nav": "rgba(240,247,255,0.82)",
        "nav_text": "#435d7e",
        "chart": "#6d8ee8",
        "focus": "#6f9dff",
    },
}


def appearance_tokens(appearance):
    """Return the visual token mapping used by native and web surfaces."""
    theme_id = getattr(appearance, "theme_id", "")
    tokens = SEASONAL_STYLE_TOKENS.get(theme_id)
    if tokens is not None:
        return dict(tokens)
    # Legacy named themes still use the old appearance contract, but receive
    # a complete token set so the upgraded controls remain coherent.
    dark = theme_id == "深色优雅"
    if dark:
        return {
            "surface": "rgba(42,35,66,0.82)", "surface_strong": "rgba(52,43,82,0.92)",
            "surface_soft": "rgba(61,50,95,0.66)", "data_surface": "rgba(42,35,66,0.82)",
            "field": "rgba(54,45,84,0.92)", "border": "rgba(180,153,235,0.24)",
            "border_accent": "rgba(156,123,224,0.42)", "text": "#eee9fb",
            "muted": "#c9c0df", "subtle": "#a69bbd", "nav": "rgba(30,26,48,0.84)",
            "nav_text": "#e5def4", "chart": "#ad8ded", "focus": "#ad8ded",
            "data_text": "#eee9fb", "data_muted": "#c9c0df", "data_subtle": "#a69bbd",
            "data_field": "rgba(54,45,84,0.92)", "data_border": "rgba(180,153,235,0.24)",
        }
    return {
        "surface": appearance.card or "rgba(255,255,255,0.86)",
        "surface_strong": "rgba(255,255,255,0.94)",
        "surface_soft": "rgba(255,255,255,0.68)",
        "data_surface": appearance.card or "rgba(255,255,255,0.86)",
        "field": "rgba(255,255,255,0.90)", "border": "rgba(255,255,255,0.76)",
        "border_accent": appearance.accent_soft, "text": appearance.text,
        "muted": "#756a80", "subtle": "#9a8fa2", "nav": "rgba(255,255,255,0.78)",
        "nav_text": appearance.text, "chart": appearance.accent, "focus": appearance.accent,
    }

_CURRENT_APPEARANCE = None


def season_for_date(day=None):
    """Return spring/summer/autumn/winter using the local meteorological calendar."""
    day = day or date.today()
    if not isinstance(day, date):
        raise TypeError("day must be a datetime.date")
    if 3 <= day.month <= 5:
        return "spring"
    if 6 <= day.month <= 8:
        return "summer"
    if 9 <= day.month <= 11:
        return "autumn"
    return "winter"


def next_season_transition(day=None):
    """Return the next fixed seasonal boundary after *day*."""
    day = day or date.today()
    if not isinstance(day, date):
        raise TypeError("day must be a datetime.date")
    if day.month < 3:
        return date(day.year, 3, 1)
    if day.month < 6:
        return date(day.year, 6, 1)
    if day.month < 9:
        return date(day.year, 9, 1)
    if day.month < 12:
        return date(day.year, 12, 1)
    return date(day.year + 1, 3, 1)


def _config_values(config_source):
    if isinstance(config_source, Mapping):
        return config_source
    return getattr(config_source, "_USER_CONFIG", {}) or {}


def configured_appearance_mode(config_source):
    """Migrate implicitly: saved appearance choices stay manual; untouched installs use auto."""
    values = _config_values(config_source)
    explicit = values.get("appearance_mode")
    if explicit in ("seasonal_auto", "manual"):
        return explicit
    manual_keys = ("appearance_theme",)
    return "manual" if any(key in values for key in manual_keys) else "seasonal_auto"


def resolve_appearance(config_source, day=None):
    """Resolve the current visual theme while preserving stored manual selections."""
    values = _config_values(config_source)
    mode = configured_appearance_mode(values)
    if mode == "seasonal_auto":
        seasonal = SEASONAL_THEMES[season_for_date(day)]
        return ResolvedAppearance(
            key=f"seasonal_auto:{seasonal.id}",
            mode=mode,
            theme_id=seasonal.id,
            display_name=seasonal.display_name,
            accent=seasonal.accent,
            accent_hover=seasonal.accent_hover,
            accent_soft=seasonal.accent_soft,
            accent_text=seasonal.accent_text,
            text=seasonal.text,
            card=seasonal.card,
            wash=seasonal.wash,
            icon=seasonal.icon,
            background_path=seasonal.background_path,
            fallback_background=seasonal.fallback_background,
        )

    theme_name = values.get("appearance_theme", _DEFAULT_THEME)
    theme_name = {
        "六花主题": "梦幻樱花主题",
        "跟随系统": "极简浅色",
        "浅色模式": "极简浅色",
        "深色模式": "深色优雅",
    }.get(theme_name, theme_name)
    if theme_name in SEASONAL_THEMES:
        seasonal = SEASONAL_THEMES[theme_name]
        return ResolvedAppearance(
            key=f"manual:{seasonal.id}",
            mode=mode,
            theme_id=seasonal.id,
            display_name=seasonal.display_name,
            accent=seasonal.accent,
            accent_hover=seasonal.accent_hover,
            accent_soft=seasonal.accent_soft,
            accent_text=seasonal.accent_text,
            text=seasonal.text,
            card=seasonal.card,
            wash=seasonal.wash,
            icon=seasonal.icon,
            fallback_background=seasonal.fallback_background,
        )

    if theme_name not in THEMES:
        theme_name = _DEFAULT_THEME
    theme = THEMES[theme_name]
    wash = theme["wash"]
    return ResolvedAppearance(
        key=f"manual:{theme_name}",
        mode=mode,
        theme_id=theme_name,
        display_name=theme_name,
        accent=theme["accent"],
        accent_hover=theme["accent_deep"],
        accent_soft=theme["accent_soft"],
        accent_text=theme["accent_text"],
        text=theme["text"],
        card=theme["card"],
        wash=(wash.red(), wash.green(), wash.blue(), wash.alpha()),
        fallback_background="樱花湖畔",
    )


def set_active_theme(name):
    """记录当前主题（供自绘控件读取 accent）。"""
    global _CURRENT, _CURRENT_APPEARANCE
    if isinstance(name, ResolvedAppearance):
        _CURRENT_APPEARANCE = name
        _CURRENT = name.theme_id
        return
    if name in THEMES:
        _CURRENT = name
        _CURRENT_APPEARANCE = None


def current_accent():
    """当前主题的 accent 十六进制色，自绘控件用它保持主题一致。"""
    if _CURRENT_APPEARANCE is not None:
        return _CURRENT_APPEARANCE.accent
    return THEMES.get(_CURRENT, THEMES[_DEFAULT_THEME])["accent"]


def current_appearance():
    """Return the active resolved appearance for transient UI surfaces."""
    if _CURRENT_APPEARANCE is not None:
        return _CURRENT_APPEARANCE
    return resolve_appearance({
        "appearance_mode": "manual", "appearance_theme": _CURRENT,
    })


def theme_wash(name):
    """主题对应的背景洗色（DashboardPage/聊天页的 _background_wash）。"""
    if isinstance(name, ResolvedAppearance):
        return name.wash_color()
    return THEMES.get(name, THEMES[_DEFAULT_THEME])["wash"]


def _surface_override(appearance):
    """QSS layer for the shared glass surfaces and readable data controls."""
    t = appearance_tokens(appearance)
    surface = t["surface"]
    strong = t["surface_strong"]
    soft_surface = t["surface_soft"]
    field = t["field"]
    border = t["border"]
    border_accent = t["border_accent"]
    text = t["text"]
    muted = t["muted"]
    subtle = t["subtle"]
    nav = t["nav"]
    nav_text = t["nav_text"]
    chart = t["chart"]
    focus = t["focus"]
    accent = appearance.accent
    deep = appearance.accent_hover
    soft = appearance.accent_soft
    accent_text = appearance.accent_text
    primary_background = (
        "qlineargradient(x1:0,y1:0,x2:1,y2:1,"
        f"stop:0 {accent}, stop:1 {deep})"
    )
    extra_dark = ""
    if appearance.theme_id in ("autumn", "深色优雅"):
        data_surface = t.get("data_surface", surface)
        data_text = t.get("data_text", text)
        data_muted = t.get("data_muted", muted)
        data_subtle = t.get("data_subtle", subtle)
        data_field = t.get("data_field", field)
        data_border = t.get("data_border", border_accent)
        extra_dark = f"""
#KnowledgePage #DashboardGlassCard, #MemoryPage #DashboardGlassCard,
#SurfHistoryPage #DashboardGlassCard, #MemoryDayCard,
#KnowledgePage #KnowledgeGlassCard, #SurfHistoryPage #SurfTimelineCard {{
    background:{data_surface}; border-color:{data_border};
}}
#KnowledgePage #DashboardTitle, #MemoryPage #DashboardTitle,
#SurfHistoryPage #DashboardTitle, #KnowledgePage #DashboardSectionTitle,
#MemoryPage #DashboardSectionTitle, #SurfHistoryPage #DashboardSectionTitle,
#KnowledgePage #DashboardRowTitle, #MemoryPage #DashboardRowTitle,
#SurfHistoryPage #SurfTimelineTitle {{ color:{data_text}; }}
#KnowledgePage #DashboardSubtitle, #MemoryPage #DashboardSubtitle,
#SurfHistoryPage #DashboardSubtitle, #KnowledgePage #DashboardMuted,
#MemoryPage #DashboardMuted, #SurfHistoryPage #DashboardMuted,
#MemoryPage #MemoryTimelineText, #SurfHistoryPage #SurfTimelineMeta {{ color:{data_muted}; }}
#KnowledgePage #DashboardStatTile, #MemoryPage #MemoryOverviewTile,
#SurfHistoryPage #SurfStatCard, #MemoryPage #MemoryTimelineRow,
#SurfHistoryPage #SurfTimelineSurface {{
    background:{data_field}; border-color:{data_border};
}}
#KnowledgePage QLineEdit, #MemoryPage QLineEdit,
#SurfHistoryPage QComboBox, #MemoryPage QComboBox {{
    background:{data_field}; color:{data_text}; border-color:{data_border};
}}
#KnowledgePage #DashboardStatCaption, #MemoryPage #DashboardStatCaption,
#SurfHistoryPage #SurfStatValue, #SurfHistoryPage #SurfTimelineTime {{ color:{data_subtle}; }}
#KnowledgePage #DashboardRowDetail, #MemoryPage #DashboardRowDetail {{ color:{data_muted}; }}
"""
    return f"""
/* Seasonal glass system: generated character art remains visible behind each page. */
#DashboardGlassCard, #SettingsNavPanel, #SettingsMainPanel,
#SettingsPage #SettingsOptionCard, #SettingsThemeCard,
#SettingsEffectCard, #DashboardStatTile, #MemoryOverviewTile,
#SurfStatCard, #SurfTimelineSurface, #ChatSessionPanel, #ChatStatCard,
#ChatTrendCard, #ChatInsightSummary, #InputComposer {{
    background:{surface}; border-color:{border};
}}
#DashboardStatTile, #MemoryOverviewTile, #SurfStatCard,
#SettingsPage #SettingsOptionCard {{ background:{soft_surface}; }}
#InputComposer {{
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 rgba(255,255,255,0.46), stop:1 rgba(255,255,255,0.24));
    border-color:{border_accent};
}}
#InputToolTray {{
    background:rgba(255,255,255,0.28);
    border-color:rgba(255,255,255,0.48);
}}
#SettingsPage QLineEdit, #SettingsPage QSpinBox, #SettingsPage QDoubleSpinBox,
#SettingsPage QComboBox, #SettingsPage QTextEdit, #InputField,
#SessionSearch, #ChatGlobalSearch, #SurfFilterCombo {{
    background:{field}; color:{text}; border-color:{border_accent};
}}
#InputField {{ selection-background-color:{soft}; }}
#InputField {{ background:{field}; }}
#SettingsPage QLineEdit:focus, #SettingsPage QSpinBox:focus,
#SettingsPage QDoubleSpinBox:focus, #SettingsPage QComboBox:focus,
#SettingsPage QTextEdit:focus, #InputField:focus, #SessionSearch:focus,
#ChatGlobalSearch:focus, #SurfFilterCombo:focus {{
    background:{strong}; border-color:{focus};
}}
#InputField:focus {{
    background:{strong}; border-color:{focus};
}}
#InputComposer, #InputToolTray {{ border-radius:18px; }}
#InputField {{ border-radius:15px; }}
#InputToolButton, #VoiceSvcButton {{ border-radius:12px; }}
#SendButton {{ min-width:58px; max-width:58px; min-height:52px; max-height:52px; padding:0; border-radius:16px; }}
#InputToolButton, #VoiceSvcButton {{
    min-width:0; max-width:16777215px; padding-left:6px; padding-right:6px;
    background:{soft_surface}; border-color:{border_accent}; color:{text};
}}
#AttachmentToolButton {{ border-color:{border_accent}; }}
#InputToolButton:hover, #VoiceSvcButton:hover {{
    background:{strong}; border-color:{focus}; color:{deep};
}}
#InputToolButton:pressed, #VoiceSvcButton:pressed {{
    background:{soft}; border-color:{accent}; color:{deep};
}}
#InputToolButton:disabled {{
    background:{soft_surface}; border-color:{border}; color:{subtle};
}}
#QQBridgeToolButton[state="connecting"], #VoiceSvcButton[state="starting"] {{
    background:rgba(245,188,91,0.20); border-color:rgba(213,145,42,0.42); color:#9a6817;
}}
#QQBridgeToolButton[state="online"], #VoiceSvcButton[state="ready"] {{
    background:rgba(92,194,139,0.18); border-color:rgba(65,164,111,0.40); color:#267c51;
}}
#VoiceToolButton[state="on"] {{
    background:{soft}; border-color:{accent}; color:{deep};
}}
#VoiceToolButton[state="off"] {{
    background:{soft_surface}; border-color:{border}; color:{subtle};
}}
#SendButton {{
    background:{primary_background}; color:{accent_text}; border-color:{border};
}}
#SendButton:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 {deep}, stop:1 {accent});
    border-color:{focus};
}}
#SendButton:pressed {{ background:{deep}; border-color:{deep}; }}
#SendButton:disabled {{ background:{soft_surface}; border-color:{border}; }}
#DashboardTitle, #DashboardSectionTitle, #DashboardRowTitle,
#HistoryRowTitle, #SettingsPageTitle, #SettingsSubheading,
#SettingsFieldLabel, #DashboardStatValue, #MemoryDayTitle,
#MemoryTimelineText, #SurfTimelineTitle, #SurfStatValue {{ color:{text}; }}
#DashboardSubtitle, #DashboardMuted, #DashboardRowDetail, #HistoryRowDetail,
#DashboardRowMeta, #DashboardStatCaption, #SettingsPageSubtitle,
#SettingsNavDetail, #SettingsChoiceDetail, #SettingsEffectDetail,
#MemoryDayText, #SurfTimelineMeta, #SurfTimelineTime, #ComposerHint {{ color:{muted}; }}
#DashboardGroupHeader, #SettingsNavTitle, #SettingsFieldValue,
#SettingsStorageMetric, #SettingsChoiceTitle {{ color:{nav_text}; }}
#SettingsNavTitle[active="true"] {{ color:{accent_text}; }}
#SettingsNavDetail[active="true"] {{ color:{accent_text}; }}
#SettingsNavPanel, #ChatNavSidebar {{ background:{nav}; }}
#SettingsNavList::item, #DashboardNavButton, #ChatNavButton {{ color:{nav_text}; }}
#SettingsNavList::item:hover, #DashboardNavButton:hover, #ChatNavButton:hover {{
    background:{appearance.accent_soft}; color:{text};
}}
#DashboardRowIcon, #DashboardPill, #DashboardTags, #SettingsThemeCard,
#SettingsEffectCard {{ border-color:{border_accent}; }}
#DashboardSegment, #DashboardChip, #DashboardSecondaryButton,
#DashboardActionButton {{ background:{soft_surface}; border-color:{border_accent}; color:{text}; }}
#DashboardSegment:hover, #DashboardChip:hover, #DashboardSecondaryButton:hover,
#DashboardActionButton:hover {{ background:{strong}; border-color:{focus}; color:{text}; }}
#DashboardSegment[active="true"], #DashboardChip[active="true"] {{
    background:{appearance.accent}; color:{appearance.accent_text}; border-color:{appearance.accent};
}}
#DashboardStatValue, #SettingsFieldValue, #MemoryDayArrow,
#SurfTimelineMarker, #SurfResultCount {{ color:{chart}; }}
#DashboardTitleIcon {{ border-color:{border_accent}; background:{strong}; }}
#ChatTopBar, #ChatSessionPanel {{ border-color:{border}; }}
#InputComposer {{ border-color:{border_accent}; }}
#ChatTopStatus, #ChatHeaderTitle, #ChatHeaderSubtitle {{ color:{text}; }}
#AIBubble {{ background:{strong}; border-color:{border}; }}
#AIBubbleMeta, #AIBubbleText {{ color:{text}; }}
#UserBubble {{ border-color:{border}; }}
#SettingsThemeCard[selected="true"] {{
    background:{appearance.accent_soft}; border-color:{appearance.accent};
}}
#SettingsPage QCheckBox {{ color:{text}; }}
#SettingsPage QSlider::groove:horizontal {{ background:{border_accent}; }}
#SettingsPage QSlider::sub-page:horizontal, #SettingsPage QSlider::handle:horizontal,
#SettingsPage QCheckBox::indicator:checked, #SettingsPage #SettingsToggle:checked {{ background:{appearance.accent}; }}
{extra_dark}
"""


def theme_override(name):
    """生成追加在基础 QSS 之后的 accent and glass override layer."""
    if isinstance(name, ResolvedAppearance):
        appearance = name
    else:
        appearance = resolve_appearance({
            "appearance_mode": "manual", "appearance_theme": name
        })
    accent = appearance.accent
    deep = appearance.accent_hover
    soft = appearance.accent_soft
    accent_text = appearance.accent_text
    text_color = appearance.text
    card = appearance.card
    seasonal_button_gradients = {
        "spring": ("#ff9bc8", "#b68af3"),
        "summer": ("#43bdf3", "#48c9ae"),
        "autumn": ("#c75432", "#e3a03c"),
        "winter": ("#5d82e8", "#82a9f4"),
    }
    button_start, button_end = seasonal_button_gradients.get(
        appearance.theme_id, (accent, deep)
    )
    primary_background = (
        "qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        f"stop:0 {button_start}, stop:1 {button_end})"
    )
    extra = ""
    if appearance.theme_id == "深色优雅":
        # 深色主题：基础 QSS 的文字是深色（为浅色背景设计），深背景上会看不见，这里整体适配
        extra = """
#MemoryDayCard { background:rgba(42,35,66,0.72); border-color:rgba(150,120,210,0.28); }
#MemoryDayHeader { border-bottom-color:rgba(150,120,210,0.16); }
#MemoryDayHeader:hover { background:rgba(150,120,220,0.12); }
#MemoryDayTitle { color:#eae6f8; }
#MemoryDayBody { background:rgba(34,28,54,0.55); }
#MemoryDayItem:hover { background:rgba(150,120,220,0.08); }
#MemoryDayText { color:#d6cfe8; }
#SettingsPage #SettingsPageTitle, #SettingsPage #SettingsFieldLabel,
#SettingsPage #SettingsSubheading, #SettingsPage #DashboardRowTitle { color:#eae6f8; }
#SettingsPage #SettingsPageSubtitle, #SettingsPage #DashboardMuted,
#SettingsPage #SettingsNavDetail, #SettingsPage #SettingsFieldValue,
#SettingsPage #SettingsStorageMetric, #SettingsPage #SettingsChoiceDetail,
#SettingsPage #SettingsEffectDetail { color:#c2bad8; }
#SettingsPage #SettingsNavList::item { color:#cfc8e2; }
#SettingsPage #SettingsNavList::item:hover { background:rgba(150,120,220,0.14); }
#SettingsPage #SettingsNavPanel, #SettingsPage #SettingsMainPanel {
    background:rgba(30,26,48,0.86); border-color:rgba(160,130,220,0.22);
}
#SettingsPage #SettingsOptionCard, #SettingsPage #SettingsThemeCard,
#SettingsPage #SettingsEffectCard {
    background:rgba(42,35,66,0.80); border-color:rgba(150,120,210,0.28);
}
#SettingsPage #SettingsPresetList { background:rgba(40,34,62,0.72); border-color:rgba(150,120,210,0.25); }
#SettingsPage #SettingsPresetRow { background:rgba(54,45,84,0.88); }
#SettingsPage QLineEdit, #SettingsPage QSpinBox, #SettingsPage QDoubleSpinBox,
#SettingsPage QComboBox, #SettingsPage QTextEdit {
    background:rgba(54,45,84,0.92); color:#eae6f8; border-color:rgba(150,120,210,0.32);
}
#SettingsPage QLineEdit:focus, #SettingsPage QComboBox:focus, #SettingsPage QSpinBox:focus,
#SettingsPage QDoubleSpinBox:focus, #SettingsPage QTextEdit:focus { background:#3c3260; }
#SettingsPage QCheckBox { color:#ddd6ec; }
#SettingsPage #DashboardSecondaryButton, #SettingsPage #DashboardActionButton {
    background:rgba(54,45,84,0.9); color:#ddd6ec; border-color:rgba(150,120,210,0.30);
}
#SettingsPage #DashboardSecondaryButton:disabled {
    background:rgba(54,45,84,0.46); color:#817991; border-color:rgba(150,120,210,0.14);
}
#SettingsPage #SettingsThemeCard[selected="true"] {
    background:rgba(150,120,220,0.20); border-color:{accent};
}
#SettingsPage #SettingsChoiceTitle { color:#d9d1ea; }
#SettingsPage #SettingsPersonaEditor { background:rgba(54,45,84,0.92); color:#eae6f8; }
"""
    return f"""
#DashboardPrimaryButton {{
    background:{primary_background}; color:{accent_text};
    border:1px solid {button_end};
}}
#DashboardPrimaryButton:hover {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {button_end}, stop:1 {button_start});
    border-color:{deep};
}}
#DashboardPrimaryButton:pressed {{ background:{deep}; border-color:{deep}; }}
#DashboardPrimaryButton:disabled {{
    background:rgba(150,145,160,0.20); color:rgba(110,105,120,0.55);
    border-color:rgba(130,125,140,0.14);
}}
#DashboardSecondaryButton:pressed, #DashboardActionButton:pressed,
#DashboardChip:pressed, #DashboardSegment:pressed {{
    background:{soft}; border-color:{accent}; color:{deep};
}}
#DashboardSecondaryButton:disabled, #DashboardActionButton:disabled,
#DashboardChip:disabled, #DashboardSegment:disabled {{
    background:rgba(150,145,160,0.12); color:rgba(110,105,120,0.48);
    border-color:rgba(130,125,140,0.10);
}}
#DashboardIconButton:pressed {{ background:{soft}; border:1px solid {accent}; }}
#NewSessionButton, #SendButton, #HomeSendButton,
#DiaryPage #DiaryPrimaryButton {{
    background:{accent}; color:{accent_text}; border-color:{accent};
}}
#NewSessionButton:hover, #SendButton:hover, #HomeSendButton:hover,
#DiaryPage #DiaryPrimaryButton:hover,
#DiaryPage #DiaryPrimaryButton:pressed {{
    background:{deep}; color:{accent_text}; border-color:{deep};
}}
#DashboardTextButton, #SettingsFieldValue, #MemoryDayArrow {{ color:{deep}; }}
#DashboardTextButton:hover, #DashboardActionButton:hover,
#DashboardSecondaryButton:hover {{ color:{deep}; border-color:{soft}; }}
#DashboardSegment[active="true"], #DashboardChip[active="true"],
#MemoryPage #DashboardNavButton[active="true"],
#MemoryPage #DashboardChip[active="true"] {{ background:{accent}; color:{accent_text}; }}
#DashboardTitleIcon, #DashboardGlassCard, #SettingsOptionCard {{ border-color:{soft}; }}
#SettingsPage #SettingsOptionCard {{ background:{card}; }}
#SettingsPageTitle, #HomeTextButton, #HomeProfileState {{ color:{deep}; }}
#HomeInput:focus, #HomeActionCard:hover, #HomeModeButton:hover {{ border-color:{accent}; }}
#SettingsSeasonStatus {{ color:{deep}; font-size:10px; }}
#SettingsThemeCard:disabled {{
    background:rgba(245,243,248,0.48); border-color:rgba(120,110,135,0.10);
}}
#SettingsThemeCard[selected="true"] {{
    background:{soft}; border-color:{accent};
}}
#SettingsChoiceCheck {{ background:{accent}; color:{accent_text}; }}
#SettingsThemeCard[selected="true"] #SettingsChoiceTitle {{ color:{deep}; }}
#SettingsPage QSlider::sub-page:horizontal {{ background:{accent}; }}
#SettingsPage QSlider::handle:horizontal {{ background:{accent}; }}
#SettingsPage QSlider::handle:horizontal:hover {{ background:{deep}; }}
#SettingsPage QCheckBox::indicator:checked {{ background:{accent}; }}
#SettingsPage #SettingsPresetRow[selected="true"] {{ border-color:{accent}; }}
#SettingsNavList::item:selected {{
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 {accent}, stop:1 {deep});
    border-left:3px solid {accent};
}}
#SettingsPage #DashboardActionButton:hover {{ color:{accent}; border-color:{soft}; }}
#SettingsPage #SettingsToggle:checked {{ background:{accent}; }}
#MemoryPage #MemorySearch:focus, #SurfHistoryPage #SurfFilterCombo:focus,
#SettingsTopBar #SettingsSearch:focus {{ border-color:{accent}; }}
#SurfHistoryPage #SurfTimelineMarker, #SurfHistoryPage #SurfResultCount,
#MemoryPage #MemoryFavoriteButton[active="true"] {{ color:{deep}; }}
#KnowledgePrimaryButton, #KnowledgeStorageProgress::chunk,
#KnowledgeTopicProgress::chunk {{ background:{accent}; color:{accent_text}; }}
#KnowledgePrimaryButton:hover {{ background:{deep}; }}
#KnowledgeSpaceList::item:selected {{ border-left-color:{accent}; background:{soft}; }}
#DiaryPage #DiaryTabs QTabBar::tab:selected {{
    color:{deep}; border-bottom:3px solid {accent};
}}
#DiaryPage #DiaryMoodButton:checked {{ border-color:{accent}; background:{soft}; }}
""" + extra + _surface_override(appearance)


# ── 背景 ────────────────────────────────────────────────────────

_BG_SIZE = QSize(1920, 1080)


def paint_background(name, size=_BG_SIZE):
    """按名字程序化绘制一张背景图；未知名字回退樱花湖畔。"""
    painter_fn = BACKGROUNDS.get(name, _paint_sakura)
    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)
    painter_fn(pixmap, size.width(), size.height())
    return pixmap


def _grad(painter, w, h, stops):
    grad = QLinearGradient(0, 0, 0, h)
    for pos, color in stops:
        grad.setColorAt(pos, QColor(color))
    painter.fillRect(QRectF(0, 0, w, h), grad)


def _paint_sakura(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#ffdcee"), (0.42, "#f3c9f4"), (0.72, "#d9b4f0"), (1.0, "#c9a2ea"),
    ])
    # 太阳光晕
    glow = QLinearGradient(0, 0, 0, h * 0.5)
    glow.setColorAt(0.0, QColor(255, 235, 250, 150))
    glow.setColorAt(1.0, QColor(255, 220, 245, 0))
    painter.fillRect(QRectF(w * 0.62, 0, w * 0.30, h * 0.5), glow)
    # 远岸剪影
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(150, 118, 200, 90))
    painter.drawRect(QRectF(0, h * 0.80, w, h * 0.20))
    painter.setBrush(QColor(180, 140, 220, 70))
    for i in range(6):
        cx = w * (0.08 + i * 0.17)
        painter.drawEllipse(QRectF(cx, h * 0.76, w * 0.12, h * 0.09))
    # 飘落花瓣
    painter.setBrush(QColor(255, 160, 205, 200))
    for x, y, r, rot in (
        (0.08, 0.16, 8, 20), (0.18, 0.34, 10, -35), (0.30, 0.20, 7, 60),
        (0.42, 0.42, 9, -10), (0.55, 0.26, 8, 40), (0.68, 0.40, 10, -55),
        (0.80, 0.20, 7, 15), (0.90, 0.36, 9, -25), (0.25, 0.60, 8, 30),
        (0.50, 0.62, 7, -45), (0.74, 0.58, 9, 10), (0.92, 0.66, 8, 50),
    ):
        painter.save()
        painter.translate(w * x, h * y)
        painter.rotate(rot)
        painter.drawEllipse(QRectF(-r, -r * 0.55, r * 2, r * 1.1))
        painter.restore()
    painter.end()


def _paint_summer(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#79d8ff"), (0.48, "#d9f5ff"), (0.66, "#61c9dc"), (1.0, "#4aaab3"),
    ])
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 255, 255, 180))
    for x, y, sw, sh in (
        (0.10, 0.16, 0.18, 0.07), (0.42, 0.10, 0.15, 0.06), (0.74, 0.22, 0.20, 0.08),
    ):
        painter.drawEllipse(QRectF(w * x, h * y, w * sw, h * sh))
        painter.drawEllipse(QRectF(w * (x + 0.05), h * (y - 0.025), w * sw * 0.55, h * sh * 1.15))
    # Distant green hills and a bright lake, kept deliberately quiet behind UI glass.
    painter.setBrush(QColor(54, 151, 130, 115))
    painter.drawPolygon(
        QPointF(0, h * 0.61), QPointF(w * 0.20, h * 0.43),
        QPointF(w * 0.43, h * 0.60), QPointF(w * 0.66, h * 0.40),
        QPointF(w, h * 0.61), QPointF(w, h * 0.72), QPointF(0, h * 0.72),
    )
    painter.setBrush(QColor(87, 205, 219, 175))
    painter.drawRect(QRectF(0, h * 0.62, w, h * 0.38))
    painter.setPen(QPen(QColor(255, 255, 255, 80), 2))
    for y in (0.69, 0.76, 0.84, 0.92):
        painter.drawLine(int(w * 0.08), int(h * y), int(w * 0.92), int(h * y))
    painter.setPen(Qt.NoPen)
    for x, y, color in (
        (0.06, 0.76, "#8fd3ff"), (0.12, 0.82, "#b7a6ef"),
        (0.83, 0.78, "#77c8e8"), (0.90, 0.86, "#b9a6ed"),
    ):
        painter.setBrush(QColor(color))
        for dx, dy in ((0, 0), (14, -5), (-12, -4), (6, 11), (-8, 10)):
            painter.drawEllipse(QRectF(w * x + dx, h * y + dy, 20, 20))
    painter.end()


def _paint_autumn(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#ffd9a3"), (0.45, "#f7ae72"), (0.72, "#d96b3e"), (1.0, "#8d3b2c"),
    ])
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(255, 235, 176, 210))
    painter.drawEllipse(QRectF(w * 0.67, h * 0.17, h * 0.15, h * 0.15))
    painter.setBrush(QColor(117, 69, 52, 105))
    painter.drawPolygon(
        QPointF(0, h * 0.68), QPointF(w * 0.24, h * 0.45),
        QPointF(w * 0.47, h * 0.65), QPointF(w * 0.72, h * 0.42),
        QPointF(w, h * 0.66), QPointF(w, h), QPointF(0, h),
    )
    painter.setBrush(QColor(205, 94, 46, 130))
    painter.drawRect(QRectF(0, h * 0.72, w, h * 0.28))
    painter.setPen(QPen(QColor(88, 48, 37, 160), 14))
    painter.drawLine(0, int(h * 0.06), int(w * 0.24), int(h * 0.42))
    painter.drawLine(w, int(h * 0.04), int(w * 0.82), int(h * 0.38))
    painter.setPen(Qt.NoPen)
    leaf_colors = ("#d84a1b", "#ed7623", "#f4a12c", "#b93d20")
    for index, (x, y, r, rot) in enumerate((
        (0.04, 0.10, 28, 18), (0.10, 0.18, 34, -20), (0.17, 0.12, 25, 34),
        (0.88, 0.12, 30, -24), (0.94, 0.20, 36, 20), (0.79, 0.18, 24, 42),
        (0.18, 0.55, 18, 16), (0.48, 0.30, 16, -36), (0.72, 0.52, 20, 28),
    )):
        painter.save()
        painter.translate(w * x, h * y)
        painter.rotate(rot)
        painter.setBrush(QColor(leaf_colors[index % len(leaf_colors)]))
        painter.drawEllipse(QRectF(-r, -r * 0.55, r * 2, r * 1.1))
        painter.restore()
    painter.end()


def _paint_snow(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#dceafc"), (0.55, "#eef5fd"), (1.0, "#f9fbfd"),
    ])
    # 远山
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(168, 192, 220, 120))
    for i, base in enumerate((0.34, 0.50, 0.42)):
        painter.drawPolygon(
            QPointF(0, h * (base + 0.28)), QPointF(w * 0.22, h * base),
            QPointF(w * 0.45, h * (base + 0.26)), QPointF(w * 0.72, h * (base + 0.06)),
            QPointF(w, h * (base + 0.30)), QPointF(w, h * (base + 0.28)),
        )
    # 雪顶
    painter.setBrush(QColor(255, 255, 255, 220))
    painter.drawPolygon(
        QPointF(w * 0.16, h * 0.46), QPointF(w * 0.22, h * 0.34),
        QPointF(w * 0.28, h * 0.46),
    )
    painter.drawPolygon(
        QPointF(w * 0.62, h * 0.56), QPointF(w * 0.72, h * 0.42),
        QPointF(w * 0.82, h * 0.56),
    )
    # 近处雪原
    painter.setBrush(QColor(255, 255, 255, 200))
    painter.drawRect(QRectF(0, h * 0.82, w, h * 0.18))
    # 雪花
    painter.setPen(QPen(QColor(120, 150, 200, 90), 2))
    for x, y in (
        (0.12, 0.20), (0.28, 0.10), (0.45, 0.24), (0.62, 0.12),
        (0.78, 0.22), (0.90, 0.10), (0.36, 0.42), (0.70, 0.40),
    ):
        painter.drawPoint(int(w * x), int(h * y))
    painter.end()


def _paint_stars(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#0c1130"), (0.5, "#1a2755"), (1.0, "#2f4a7c"),
    ])
    # 星
    for x, y, r, a in (
        (0.08, 0.10, 2.2, 220), (0.18, 0.24, 1.4, 150), (0.30, 0.08, 1.8, 200),
        (0.42, 0.30, 2.0, 230), (0.56, 0.12, 1.6, 170), (0.68, 0.26, 2.4, 210),
        (0.80, 0.10, 1.8, 190), (0.90, 0.22, 1.4, 160), (0.24, 0.44, 1.6, 180),
        (0.50, 0.42, 1.8, 200), (0.76, 0.40, 2.0, 220), (0.94, 0.38, 1.4, 160),
    ):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 250, 235, a))
        painter.drawEllipse(QRectF(w * x, h * y, r * 2, r * 2))
    # 月
    moon = QPainterPath()
    moon.addEllipse(QRectF(w * 0.72, h * 0.10, w * 0.10, h * 0.10))
    painter.setBrush(QColor(255, 244, 214, 230))
    painter.drawPath(moon)
    # 地平线微光
    horizon = QLinearGradient(0, h * 0.78, 0, h)
    horizon.setColorAt(0.0, QColor(120, 100, 190, 0))
    horizon.setColorAt(1.0, QColor(120, 100, 190, 90))
    painter.fillRect(QRectF(0, h * 0.78, w, h * 0.22), horizon)
    # 湖面倒影
    painter.setBrush(QColor(20, 26, 58, 160))
    painter.drawRect(QRectF(0, h * 0.86, w, h * 0.14))
    painter.end()


def _paint_courtyard(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#f7ecd9"), (0.45, "#ecdcbe"), (0.8, "#d8c39d"), (1.0, "#c3aa80"),
    ])
    # 拱门（远景亭子剪影）
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(120, 96, 70, 90))
    painter.drawRect(QRectF(w * 0.40, h * 0.34, w * 0.20, h * 0.40))
    arch = QPainterPath()
    arch.addRect(QRectF(w * 0.44, h * 0.40, w * 0.12, h * 0.30))
    painter.setBrush(QColor(236, 218, 174, 255))
    painter.drawPath(arch)
    # 屋顶
    roof = QPainterPath()
    roof.moveTo(w * 0.34, h * 0.34)
    roof.lineTo(w * 0.50, h * 0.24)
    roof.lineTo(w * 0.66, h * 0.34)
    roof.closeSubpath()
    painter.setBrush(QColor(110, 86, 62, 120))
    painter.drawPath(roof)
    # 枝影（画面两侧）
    painter.setPen(QPen(QColor(96, 72, 50, 90), 4))
    painter.drawLine(int(w * 0.05), h, int(w * 0.16), int(h * 0.30))
    painter.drawLine(int(w * 0.95), h, int(w * 0.84), int(h * 0.26))
    painter.setPen(QPen(QColor(96, 72, 50, 90), 2))
    for i in range(5):
        painter.drawLine(int(w * 0.16), int(h * (0.30 + i * 0.02)), int(w * (0.20 + i * 0.03)), int(h * (0.20 + i * 0.05)))
    # 石板路
    painter.setBrush(QColor(180, 150, 110, 60))
    painter.drawPolygon(
        QPointF(w * 0.44, h * 0.72), QPointF(w * 0.56, h * 0.72),
        QPointF(w * 0.60, h), QPointF(w * 0.40, h),
    )
    painter.end()


def _paint_city(pm, w, h):
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    _grad(painter, w, h, [
        (0.0, "#191433"), (0.5, "#322a5e"), (1.0, "#5a4486"),
    ])
    # 天际线
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(16, 12, 34, 210))
    base = h * 0.62
    bldg = (
        (0.00, 0.34), (0.08, 0.46), (0.15, 0.28), (0.22, 0.50), (0.30, 0.38),
        (0.37, 0.52), (0.45, 0.30), (0.52, 0.44), (0.60, 0.36), (0.67, 0.50),
        (0.75, 0.32), (0.82, 0.46), (0.90, 0.38), (0.97, 0.48),
    )
    for x, height in bldg:
        painter.drawRect(QRectF(w * x, base - h * height, w * 0.10, h * (height + 0.38)))
    # 灯光窗
    painter.setBrush(QColor(255, 214, 140, 210))
    for x, y, n in (
        (0.10, 0.42, 4), (0.18, 0.32, 6), (0.32, 0.42, 5), (0.47, 0.34, 7),
        (0.62, 0.40, 5), (0.77, 0.36, 6), (0.92, 0.42, 4),
    ):
        for i in range(n):
            painter.drawRect(QRectF(w * (x + (i % 3) * 0.030), h * (y + (i // 3) * 0.045), w * 0.008, h * 0.016))
    # 城市微光
    glow = QLinearGradient(0, h * 0.70, 0, h)
    glow.setColorAt(0.0, QColor(255, 190, 120, 0))
    glow.setColorAt(1.0, QColor(255, 190, 120, 70))
    painter.fillRect(QRectF(0, h * 0.70, w, h * 0.30), glow)
    painter.end()


BACKGROUNDS = {
    "樱花湖畔": _paint_sakura,
    "夏日湖畔": _paint_summer,
    "枫林夕照": _paint_autumn,
    "雪山远景": _paint_snow,
    "星空夜幕": _paint_stars,
    "古风庭院": _paint_courtyard,
    "城市夜景": _paint_city,
}


def load_theme_background(appearance, size=_BG_SIZE, page_id="home"):
    """Load the page artwork for the active seasonal theme.

    Seasonal installs use the page-specific image tree. Legacy named themes
    retain a procedural fallback for migration compatibility.
    """
    page_id = normalize_page_id(page_id)
    if isinstance(appearance, SeasonalTheme):
        appearance = ResolvedAppearance(
            key=f"seasonal_auto:{appearance.id}",
            mode="seasonal_auto",
            theme_id=appearance.id,
            display_name=appearance.display_name,
            accent=appearance.accent,
            accent_hover=appearance.accent_hover,
            accent_soft=appearance.accent_soft,
            accent_text=appearance.accent_text,
            text=appearance.text,
            card=appearance.card,
            wash=appearance.wash,
            icon=appearance.icon,
            background_path=appearance.background_path,
            fallback_background=appearance.fallback_background,
        )
    if not isinstance(appearance, ResolvedAppearance):
        raise TypeError("appearance must be SeasonalTheme or ResolvedAppearance")

    candidates = []
    if appearance.mode == "seasonal_auto":
        seasonal = SEASONAL_THEMES.get(appearance.theme_id)
        default_path = seasonal.background_path if seasonal is not None else ""
        uses_default_path = bool(
            default_path and appearance.background_path
            and os.path.abspath(appearance.background_path) == os.path.abspath(default_path)
        )
        if uses_default_path:
            candidates.append(seasonal_background_path(appearance.theme_id, page_id))
        if appearance.background_path:
            candidates.append(appearance.background_path)
    elif appearance.mode == "manual" and appearance.theme_id in SEASONAL_THEMES:
        candidates.append(seasonal_background_path(appearance.theme_id, page_id))
    for path in candidates:
        if path and os.path.isfile(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                return pixmap
    return paint_background(appearance.fallback_background, size)
