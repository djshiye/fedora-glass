"""The pointer style picker's helpers: the styles to show, pictures of each pointer
(image://lgcursor/<theme>/<shape>), and trying a style on the app's own pointer.

Nothing here changes the desktop: the chosen style is saved with the other settings
and set by Apply (targets/cursor.py)."""

from __future__ import annotations

import configparser

from PySide6.QtCore import Property, QObject, QSize, Qt, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtQuick import QQuickImageProvider

from .. import cursors
from ..env import Env


def _image(env: Env, theme: str, shape: str, size: int) -> tuple[QImage, int, int] | None:
    """One pointer shape as a QImage with its hotspot, or None."""
    if theme == cursors.KEEP:
        theme = cursors.current_theme(env)
    path = cursors.find_cursor(env, theme, shape)
    if path is not None and (img := cursors.read_xcursor(path, size)) is not None:
        q = QImage(img.argb, img.width, img.height, img.width * 4,
                   QImage.Format.Format_ARGB32_Premultiplied).copy()
        return q, img.xhot, img.yhot
    if (png := cursors.preview_png(theme, shape)) is not None:
        q = QImage(str(png))
        if not q.isNull():
            return q, 0, 0
    return None


def _bbox(img: QImage) -> tuple[int, int, int, int] | None:
    """The box around the pointer's visible pixels (x0, y0, x1, y1), or None if empty."""
    a = img.convertToFormat(QImage.Format.Format_ARGB32)
    w, h, stride = a.width(), a.height(), a.bytesPerLine()
    bits = bytes(a.constBits())[:stride * h]
    xs, ys = [], []
    for y in range(h):
        row = bits[y * stride:y * stride + w * 4]
        alpha = row[3::4]
        if any(v > 24 for v in alpha):
            ys.append(y)
            first = next(i for i, v in enumerate(alpha) if v > 24)
            last = w - 1 - next(i for i, v in enumerate(reversed(alpha)) if v > 24)
            xs += [first, last]
    if not ys:
        return None
    return min(xs), ys[0], max(xs) + 1, ys[-1] + 1


class CursorImages(QQuickImageProvider):
    """image://lgcursor/<theme>/<shape>: a picture of the pointer for the picker.

    Themes draw their pointers at different sizes inside the same square (WhiteSur's
    arrow fills half of it, Bibata's most of it), so each theme is scaled so its arrow is
    the same height, and every shape is centred. Shapes keep their sizes within a theme."""

    def __init__(self, env: Env) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._env = env
        self._scale: dict[tuple[str, int], float] = {}

    def _theme_scale(self, theme: str, side: int, src: int) -> float:
        key = (theme, side)
        if key not in self._scale:
            got = _image(self._env, theme, "left_ptr", src)
            box = _bbox(got[0]) if got else None
            tall = max(box[2] - box[0], box[3] - box[1]) if box else src
            self._scale[key] = 0.8 * side / max(1, tall)
        return self._scale[key]

    def requestImage(self, ident: str, size: QSize, requested: QSize) -> QImage:  # noqa: N802
        theme, _, shape = ident.partition("/")
        shape = shape.split("?", 1)[0]
        if theme == cursors.KEEP and "?" in ident:
            self._scale = {k: v for k, v in self._scale.items() if k[0] != theme}
        side = max(requested.width(), requested.height()) if requested.isValid() else 64
        side = side if side > 0 else 64
        out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
        out.fill(Qt.GlobalColor.transparent)
        src = 64   # big enough to stay sharp when scaled down
        got = _image(self._env, theme, shape, src) if shape in cursors.PREVIEW_NAMES else None
        box = _bbox(got[0]) if got else None
        if got is not None and box is not None:
            k = self._theme_scale(theme, side, src)
            x0, y0, x1, y1 = box
            w, h = (x1 - x0) * k, (y1 - y0) * k
            fit = min(1.0, side / max(w, h))     # a wide busy ring still fits the square
            w, h = round(w * fit), round(h * fit)
            part = got[0].copy(x0, y0, x1 - x0, y1 - y0).scaled(
                max(1, w), max(1, h), Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            p = QPainter(out)
            p.drawImage((side - w) // 2, (side - h) // 2, part)
            p.end()
        if size is not None:
            size.setWidth(side)
            size.setHeight(side)
        return out


class CursorPicker(QObject):
    changed = Signal()

    def __init__(self, env: Env | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._env = env or Env()
        self._trying = False

    @Property("QVariantList", notify=changed)
    def styles(self) -> list[dict]:
        return [{"id": s.id, "name": s.name, "blurb": s.blurb, "credit": s.credit,
                 "fun": s.fun, "installed": cursors.theme_dir(self._env, s.id) is not None}
                for s in cursors.STYLES]

    @Property(str, notify=changed)
    def ownName(self) -> str:
        """The name of the pointer the desktop uses now, for the "Keep mine" tile."""
        theme = cursors.current_theme(self._env)
        for s in cursors.STYLES:
            if s.id == theme:
                return s.name
        root = cursors.theme_dir(self._env, theme)
        if root is not None:
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(root / "index.theme", encoding="utf-8")
                name = cp.get("Icon Theme", "Name", fallback="").strip()
            except (configparser.Error, OSError, UnicodeDecodeError):
                name = ""
            if name:
                return name[:40]
        return theme[:40]

    @Slot()
    def refresh(self) -> None:
        self.changed.emit()

    @Slot(str)
    def tryOn(self, theme: str) -> None:
        """Show this style on the app's own pointer while it is over the picker; "" stops."""
        app = QGuiApplication.instance()
        if app is None:
            return
        if self._trying:
            QGuiApplication.restoreOverrideCursor()
            self._trying = False
        if not theme:
            return
        size = 24
        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen is not None else 1.0
        got = _image(self._env, theme, "left_ptr", round(size * dpr))
        if got is None:
            return
        img, xh, yh = got
        pm = QPixmap.fromImage(img)
        ratio = max(1.0, img.width() / size)    # a 48 px picture is a 24 px pointer at 200 %
        pm.setDevicePixelRatio(ratio)
        QGuiApplication.setOverrideCursor(QCursor(pm, round(xh / ratio), round(yh / ratio)))
        self._trying = True
