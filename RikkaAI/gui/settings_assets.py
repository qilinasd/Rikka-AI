"""Cropped UI assets from the settings design sprite sheet."""

import os
from functools import lru_cache

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

import config


SHEET_PATH = os.path.join(
    config.ASSETS_DIR, "images", "settings", "settings_visual_assets.png"
)
CRYSTAL_BALL_PATH = os.path.join(
    config.ASSETS_DIR, "images", "settings", "settings_crystal_ball.png"
)
OUTLINE_DIR = os.path.join(config.ROOT_DIR, "ui_assets", "03_Icons", "Outline")

_SVG_FALLBACKS = {
    "sidebar.home": "home", "sidebar.chat": "chat",
    "sidebar.drawing": "drawing",
    "sidebar.diary": "edit",
    "sidebar.workflow": "workflow", "sidebar.plugin": "plugin",
    "sidebar.memory": "memory", "sidebar.history": "history",
    "sidebar.settings": "settings", "nav.profile": "profile",
    "nav.theme": "theme", "nav.chat": "chat", "nav.ai": "ai",
    "nav.drawing": "drawing", "nav.web": "web", "nav.memory": "memory",
    "nav.privacy": "privacy", "nav.notification": "notification",
    "nav.proactive": "proactive", "nav.workflow": "workflow",
    "nav.voice": "voice", "nav.gptsovits": "gptsovits",
    "nav.plugin": "plugin", "nav.help": "help", "action.edit": "edit",
    "nav.time": "time", "action.run": "send",
    "action.save": "save", "action.reset": "refresh",
    "action.search": "search", "action.share": "share",
    "action.upload": "upload", "action.download": "download",
    "action.delete": "delete", "action.more": "more",
    "action.import": "upload", "action.export": "download",
    "action.copy": "copy", "action.refresh": "refresh",
    "action.add": "plus", "action.voice": "voice", "action.stop": "stop",
    "status.loading": "refresh",
}

# Icon centers in the 1536 x 1024 source sheet. Keeping the source as one
# design-owned image avoids maintaining a second, slightly different icon set.
_ICON_CENTERS = {
    "sidebar.home": (56, 85),
    "sidebar.chat": (135, 85),
    "sidebar.drawing": (288, 85),
    "sidebar.diary": (369, 230),
    "sidebar.workflow": (442, 85),
    "sidebar.plugin": (517, 85),
    "sidebar.memory": (595, 85),
    "sidebar.history": (671, 85),
    "sidebar.settings": (747, 85),
    "nav.profile": (54, 230),
    "nav.theme": (150, 230),
    "nav.chat": (247, 230),
    "nav.ai": (345, 230),
    "nav.drawing": (288, 85),
    "nav.memory": (444, 230),
    "nav.notification": (547, 230),
    "nav.workflow": (442, 85),
    "nav.plugin": (646, 230),
    "nav.help": (746, 230),
    "action.edit": (56, 757),
    "action.save": (138, 757),
    "action.reset": (220, 757),
    "action.search": (303, 757),
    "action.share": (386, 757),
    "action.upload": (469, 757),
    "action.download": (552, 757),
    "action.delete": (635, 757),
    "action.more": (719, 757),
    "action.import": (56, 839),
    "action.export": (138, 839),
    "action.copy": (220, 839),
    "action.refresh": (469, 839),
    "status.loading": (475, 972),
}

_PREVIEW_RECTS = {
    "theme.system": (31, 357, 126, 71),
    "theme.light": (183, 357, 127, 71),
    "theme.dark": (337, 357, 127, 71),
    "theme.rikka": (490, 357, 141, 71),
    "background.sakura": (31, 531, 112, 104),
    "background.snow": (162, 531, 112, 104),
    "background.stars": (291, 531, 112, 104),
    "background.courtyard": (420, 531, 112, 104),
    "background.city": (548, 531, 112, 104),
}


@lru_cache(maxsize=1)
def _sheet():
    return QPixmap(SHEET_PATH)


def _transparent_icon(source):
    """Remove the near-white sprite-sheet background around a glyph."""
    image = source.toImage().convertToFormat(QImage.Format_ARGB32)
    corner = QColor.fromRgba(image.pixel(0, 0))
    for y in range(image.height()):
        for x in range(image.width()):
            color = QColor.fromRgba(image.pixel(x, y))
            delta = max(
                abs(color.red() - corner.red()),
                abs(color.green() - corner.green()),
                abs(color.blue() - corner.blue()),
            )
            color.setAlpha(max(0, min(255, (delta - 3) * 11)))
            image.setPixelColor(x, y, color)
    return QPixmap.fromImage(image)


def _scaled_cover(source, size):
    scaled = source.scaled(
        size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
    )
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    return scaled.copy(x, y, size.width(), size.height())


def _svg_fallback(name, size):
    icon_name = _SVG_FALLBACKS.get(name)
    if not icon_name:
        return QPixmap()
    path = os.path.join(OUTLINE_DIR, f"{icon_name}.svg")
    if not os.path.isfile(path):
        return QPixmap()
    target = size or QSize(44, 44)
    return QIcon(path).pixmap(target)


def settings_asset_pixmap(name, size=None):
    """Return a glyph or preview cropped from the provided settings sheet."""
    if name == "decorative.globe":
        result = QPixmap(CRYSTAL_BALL_PATH)
        if size is not None and not result.isNull():
            result = result.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return result

    sheet = _sheet()

    if name in _ICON_CENTERS:
        if sheet.isNull():
            return _svg_fallback(name, size)
        center_x, center_y = _ICON_CENTERS[name]
        result = _transparent_icon(sheet.copy(center_x - 22, center_y - 22, 44, 44))
        if result.isNull():
            return _svg_fallback(name, size)
        if size is not None:
            result = result.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        return result

    rect = _PREVIEW_RECTS.get(name)
    if rect is None:
        return _svg_fallback(name, size)
    if sheet.isNull():
        return QPixmap()
    result = sheet.copy(*rect)
    if size is not None:
        result = _scaled_cover(result, size)
    return result


def settings_asset_icon(name):
    return QIcon(settings_asset_pixmap(name, QSize(44, 44)))


def tinted_settings_asset_icon(name, color):
    pixmap = settings_asset_pixmap(name, QSize(44, 44))
    if pixmap.isNull():
        return QIcon()
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(color))
    painter.end()
    return QIcon(tinted)
