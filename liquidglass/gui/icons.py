"""Serves icon-theme icons to QML as image://lgicon/<name>."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtQuick import QQuickImageProvider


class IconProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, name: str, size: QSize, requested: QSize) -> QPixmap:  # noqa: N802
        side = max(requested.width(), requested.height(), 16) if requested.isValid() else 64
        icon = QIcon.fromTheme(name)
        pm = icon.pixmap(QSize(side, side)) if not icon.isNull() else QPixmap()
        if pm.isNull():
            pm = QPixmap(side, side)
            pm.fill(0)
        if size is not None:
            size.setWidth(pm.width())
            size.setHeight(pm.height())
        return pm
