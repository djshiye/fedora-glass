"""A pleasant colour from the wallpaper, for "Match my wallpaper".

The picture is read small (64 px) on a worker thread. Near-black, near-white and grey
pixels say nothing about the picture's colour, so they are skipped; the rest are put in
hue buckets weighted by how saturated they are, and the fullest bucket wins. That colour is
then softened: a tint is a pale, gentle version of it (like the default #8fa8c8), an accent
a clear, readable one. A picture with no colour in it gives the default tint back.
The maths has no Qt in it, so the tests run it on plain pixels.
"""

from __future__ import annotations

import colorsys
import os
from collections.abc import Iterable
from pathlib import Path

BUCKETS = 24
SAMPLE = 64


def dominant(pixels: Iterable[tuple[int, int, int]]) -> tuple[int, int, int] | None:
    """The picture's main colour as (r, g, b) 0..255, or None when it has no colour."""
    weight = [0.0] * BUCKETS
    sums = [[0.0, 0.0, 0.0] for _ in range(BUCKETS)]
    for r, g, b in pixels:
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        v = max(r, g, b) / 255
        if v < 0.14 or l > 0.9 or s < 0.18 or (max(r, g, b) - min(r, g, b)) < 24:
            continue        # near-black, near-white or grey
        w = s * s * (0.4 + v)   # saturated colour counts most
        i = int(h * BUCKETS) % BUCKETS
        weight[i] += w
        sums[i][0] += r * w
        sums[i][1] += g * w
        sums[i][2] += b * w
    # Neighbouring buckets belong together (a sunset's orange spans two).
    best = max(range(BUCKETS), key=lambda i: weight[i] + 0.5 * (weight[i - 1] + weight[(i + 1) % BUCKETS]))
    total = weight[best]
    if total <= 0:
        return None
    return tuple(int(round(c / total)) for c in sums[best])  # type: ignore[return-value]


def _hex(r: float, g: float, b: float) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, int(round(c * 255)))) for c in (r, g, b)))


def as_tint(rgb: tuple[int, int, int]) -> str:
    """A soft tint for the glass: the colour's hue, gentle saturation, light."""
    h, _l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return _hex(*colorsys.hls_to_rgb(h, 0.66, min(0.5, max(0.28, s * 0.6))))


def as_accent(rgb: tuple[int, int, int]) -> str:
    """An accent for buttons and highlights: the colour's hue, clear and mid-dark enough for
    white text on it."""
    h, _l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    # Yellow and green look lighter than blue at the same lightness: a little darker there.
    light = 0.42 if 0.1 < h < 0.45 else 0.5
    return _hex(*colorsys.hls_to_rgb(h, light, min(0.75, max(0.5, s))))


def picture_key(path: str) -> str:
    """Which picture this is, as it is now: its path, change time and size. "" when it isn't there."""
    if not path:
        return ""
    try:
        st = os.stat(path)
    except OSError:
        return ""
    return f"{path}|{st.st_mtime_ns}|{st.st_size}"


def read_pixels(path: str) -> list[tuple[int, int, int]]:
    """The picture, decoded small. Qt is only needed here (on the app's worker thread)."""
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
        return []
    out = []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            out.append((c.red(), c.green(), c.blue()))
    return out


def colours_of(path: str) -> dict:
    """{"key", "tint", "accent"} for the picture at `path`; tint and accent are "" when it
    has no colour to take (or can't be read)."""
    key = picture_key(path)
    rgb = dominant(read_pixels(path)) if key and Path(path).is_file() else None
    if rgb is None:
        return {"key": key, "tint": "", "accent": ""}
    return {"key": key, "tint": as_tint(rgb), "accent": as_accent(rgb)}
