"""The app's side of "Match my wallpaper": pictures read with Qt.

The colour maths, the slideshow and picture keys, and the GdkPixbuf reader live in
fedoraglass/wallcolour.py, without Qt, so the `fedora-glass watch` service uses them too.
"""

from __future__ import annotations

from .. import wallcolour as _core
from ..wallcolour import (  # noqa: F401 - the app and its tests use them from here
    BUCKETS, SAMPLE, SLIDESHOW_MAX, as_accent, as_tint, dominant, follows, picture_key, picture_path,
    slideshow_picture,
)


def _pixbuf_pixels(path: str) -> list[tuple[int, int, int]] | None:
    return _core.pixbuf_pixels(path)


def read_pixels(path: str) -> list[tuple[int, int, int]] | None:
    """The picture, decoded small, or None when Qt can't decode it (a format without its
    plugin, a damaged file). Qt is only needed here (on the app's worker thread)."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImageReader
    r = QImageReader(path)
    size = r.size()
    if size.isValid() and size.width() > 0 and size.height() > 0:
        k = SAMPLE / max(size.width(), size.height())
        r.setScaledSize(QSize(max(1, round(size.width() * k)), max(1, round(size.height() * k))))
    else:
        r.setScaledSize(QSize(SAMPLE, SAMPLE))
    img = r.read()
    if img.isNull():
        return _pixbuf_pixels(path)      # e.g. .jxl, which Qt reads only with kimageformats
    out = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            out.append((c.red(), c.green(), c.blue()))
    return out


def colours_of(path: str) -> dict:
    """{"key", "tint", "accent", "unreadable"} for the picture at `path`, read with Qt
    (see fedoraglass.wallcolour.colours_of)."""
    return _core.colours_of(path, read_pixels)
