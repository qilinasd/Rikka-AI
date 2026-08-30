"""Responsive, aspect-preserving home background layer."""

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QLabel


class HomeBackground(QLabel):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setObjectName("HomeBackground")
        self._source = QPixmap(path)
        self._wash = QColor(0, 0, 0, 0)
        self.setAlignment(Qt.AlignCenter)

    def set_background(self, pixmap, wash=None):
        self._source = QPixmap(pixmap)
        self._wash = QColor(wash) if wash is not None else QColor(0, 0, 0, 0)
        self._render_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_background()

    def _render_background(self):
        if self._source.isNull() or self.width() <= 0 or self.height() <= 0:
            return
        scaled = self._source.scaled(
            self.width(), self.height(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        x = max(0, (scaled.width() - self.width()) // 2)
        y = max(0, (scaled.height() - self.height()) // 2)
        cover = scaled.copy(x, y, self.width(), self.height())

        result = QPixmap(self.size())
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(clip)
        painter.drawPixmap(0, 0, cover)
        if self._wash.alpha():
            painter.fillRect(self.rect(), self._wash)
        painter.end()
        self.setPixmap(result)
