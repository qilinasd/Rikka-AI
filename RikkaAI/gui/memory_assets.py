"""Cropped decorative assets from the memory page design sheet.

The source sheet (`memory_visual_assets.png`) is a dense multi-panel design
board rather than a clean icon grid, so elements are cropped by region
rectangle instead of by icon center (see `_REGION_RECTS`).
"""

import os
from functools import lru_cache

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

import config


SHEET_PATH = os.path.join(
    config.ASSETS_DIR, "images", "memory", "memory_visual_assets.png"
)
DECORATION_DIR = os.path.join(
    config.ROOT_DIR, "ui_assets", "04_Illustration", "Decoration"
)
_FALLBACKS = {
    "flower": "seasonal-flower.svg",
    "butterfly": "seasonal-butterfly.svg",
}

# (x, y, w, h) region rectangles in the 1672 x 941 source sheet,
# calibrated against the design board (vision-verified flower / butterfly).
_REGION_RECTS = {
    "flower": (1173, 82, 79, 71),         # 粉花装饰
    "butterfly": (1554, 90, 68, 61),      # 紫蝶装饰
}

# Regions that sit on a near-white background and need the white stripped out.
_STRIP_BG = {"flower", "butterfly"}


@lru_cache(maxsize=1)
def _sheet():
    return QPixmap(SHEET_PATH)


def _transparent_pixmap(source):
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


def memory_asset_pixmap(name, size=None):
    """Return a decorative element cropped from the memory sheet.

    Returns an empty QPixmap (never raises) when the sheet is missing or the
    region is unknown, so callers can skip decoration gracefully.
    """
    sheet = _sheet()
    if sheet.isNull():
        fallback = _FALLBACKS.get(name)
        if not fallback:
            return QPixmap()
        target = size or QSize(64, 64)
        source = QIcon(os.path.join(DECORATION_DIR, fallback)).pixmap(target)
        if source.isNull():
            return QPixmap()
        try:
            from gui.theme_manager import current_accent
            color = current_accent()
        except Exception:
            color = "#A478FF"
        result = QPixmap(source.size())
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, source)
        painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), QColor(color))
        painter.end()
        return result

    rect = _REGION_RECTS.get(name)
    if rect is None:
        return QPixmap()

    result = sheet.copy(*rect)
    if name in _STRIP_BG:
        result = _transparent_pixmap(result)
    if size is not None and not result.isNull():
        result = result.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return result


def memory_asset_icon(name):
    return QIcon(memory_asset_pixmap(name, QSize(44, 44)))
