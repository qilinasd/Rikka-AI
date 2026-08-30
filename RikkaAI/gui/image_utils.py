"""Small image helpers shared by the Qt interface."""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPainterPath, QPixmap


def _cover_pixmap(path, width, height):
    source = QPixmap(path)
    if source.isNull():
        return QPixmap()
    scaled = source.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    return scaled.copy(x, y, width, height)


def circular_pixmap(path, size):
    source = _cover_pixmap(path, size, size)
    if source.isNull():
        return source
    result = QPixmap(size, size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return result


def rounded_cover_pixmap(path, width, height, radius=8):
    source = _cover_pixmap(path, width, height)
    if source.isNull():
        return source
    result = QPixmap(width, height)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, source)
    painter.end()
    return result
