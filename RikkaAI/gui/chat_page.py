"""Background container for the native desktop chat workspace."""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QFrame

import config


class ChatBackgroundPage(QFrame):
    """Paint the supplied chat artwork edge-to-edge without distortion."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ChatPage")
        path = os.path.join(
            config.ASSETS_DIR,
            "images",
            "chat",
            "chat_background.png",
        )
        self._background = QPixmap(path)
        self._background_wash = QColor(0, 0, 0, 0)

    def set_appearance_background(self, pixmap, wash):
        self._background = QPixmap(pixmap)
        self._background_wash = QColor(wash)
        self._background_wash.setAlpha(min(72, self._background_wash.alpha()))
        self.update()

    def paintEvent(self, event):
        if self._background.isNull():
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        scaled = self._background.scaled(
            self.size(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        x = (scaled.width() - self.width()) // 2
        y = (scaled.height() - self.height()) // 2
        source = scaled.rect().adjusted(x, y, -x, -y)
        painter.drawPixmap(self.rect(), scaled, source)
        if self._background_wash.alpha():
            painter.fillRect(self.rect(), self._background_wash)
