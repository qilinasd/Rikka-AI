"""Cropped visual assets for the Sleep-time Compute settings page."""

import os
from functools import lru_cache

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QPixmap

import config


SHEET_PATH = os.path.join(
    config.ASSETS_DIR,
    "images",
    "sleep_compute",
    "sleep_compute_visual_assets.png",
)

# Rectangles are measured against the supplied 1536 x 1024 transparent sheet.
_ASSET_RECTS = {
    "model.crystal": (815, 705, 170, 165),
    "decor.moon": (735, 0, 195, 200),
    "decor.petals": (1120, 240, 310, 150),
}


@lru_cache(maxsize=1)
def _sheet():
    return QPixmap(SHEET_PATH)


def sleep_compute_asset_pixmap(name, size=None):
    """Return one transparent crop from the user-supplied visual sheet."""
    rect = _ASSET_RECTS.get(name)
    sheet = _sheet()
    if rect is None or sheet.isNull():
        return QPixmap()

    result = sheet.copy(*rect)
    if size is not None and not result.isNull():
        result = result.scaled(
            QSize(size), Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    return result
