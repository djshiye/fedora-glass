"""A pleasant colour from the wallpaper, for "Match my wallpaper".

Shared by the app and the `fedora-glass watch` service, so it never needs Qt: the app reads
pictures with Qt (gui/wallcolour.py, on a worker thread), the watcher with GdkPixbuf
(pixbuf_pixels). The picture is read small (64 px). Near-black, near-white and grey
pixels say nothing about the picture's colour, so they are skipped; the rest are put in
hue buckets weighted by how saturated they are, and the fullest bucket wins. That colour is
then softened: a tint is a pale, gentle version of it (like the default #8fa8c8), an accent
a clear, readable one. A picture with no colour in it gives the default tint back.
The maths has no Qt in it, so the tests run it on plain pixels.

The watcher also uses `rematch` here: a look that follows the wallpaper takes the colours of
the picture GNOME shows now, the same way the app does at Apply.
"""

from __future__ import annotations

import colorsys
import os
from collections.abc import Callable, Iterable
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


SLIDESHOW_MAX = 256 * 1024


def slideshow_picture(path: str) -> str:
    """The first picture of a GNOME slideshow (.xml wallpaper), or "" when there is none.
    The file is read only up to SLIDESHOW_MAX bytes, and only a plain picture file is taken
    (never another slideshow)."""
    import xml.etree.ElementTree as ET
    try:
        with open(path, "rb") as f:
            data = f.read(SLIDESHOW_MAX + 1)
        if len(data) > SLIDESHOW_MAX:
            return ""
        root = ET.fromstring(data)
    except (OSError, ET.ParseError, ValueError):
        return ""
    def area(el) -> int:
        try:
            return int(el.get("width", 0)) * int(el.get("height", 0))
        except ValueError:
            return 0

    for el in root.iter():
        if el.tag == "file" and el.find("size") is not None:
            # <file><size width=.. height=..>/path</size>…</file>: the largest one
            sizes = [s for s in el.findall("size") if s.text and s.text.strip()]
            if not sizes:
                return ""
            pic = max(sizes, key=area).text.strip()
            if os.path.isabs(pic) and not pic.lower().endswith(".xml") and Path(pic).is_file():
                return pic
            return ""
        if el.tag in ("file", "from") and el.text:
            pic = el.text.strip()
            if os.path.isabs(pic) and not pic.lower().endswith(".xml") and Path(pic).is_file():
                return pic
            return ""
    return ""


def pixbuf_pixels(path: str) -> list[tuple[int, int, int]] | None:
    """The picture, decoded small through GdkPixbuf (GNOME's own loaders, .jxl among them),
    scaled down while it is decoded. None when GdkPixbuf isn't there or can't read it."""
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf, GLib
    except (ImportError, ValueError):
        return None
    try:
        info = GdkPixbuf.Pixbuf.get_file_info(path)
        w, h = (info[1], info[2]) if info and info[0] is not None else (0, 0)
        if w > 0 and h > 0:
            k = SAMPLE / max(w, h)
            w, h = max(1, round(w * k)), max(1, round(h * k))
        else:
            w = h = SAMPLE
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, w, h, True)
        if pb is None:
            return None
        width, height, stride, n = pb.get_width(), pb.get_height(), pb.get_rowstride(), pb.get_n_channels()
        data = bytes(pb.get_pixels())
    except (GLib.Error, OSError, ValueError, TypeError):
        return None
    if n < 3 or width <= 0 or height <= 0:
        return None
    out = []
    for y in range(height):
        row = y * stride
        for x in range(width):
            i = row + x * n
            out.append((data[i], data[i + 1], data[i + 2]))
    return out


def colours_of(path: str, read: Callable[[str], list[tuple[int, int, int]] | None] = pixbuf_pixels) -> dict:
    """{"key", "tint", "accent", "unreadable"} for the picture at `path`, decoded by `read`.
    Tint and accent are "" when there is no colour to take; "unreadable" says that was
    because the picture can't be read at all, not because it has hardly any colour."""
    key = picture_key(path)
    pic = path
    if key and path.lower().endswith(".xml"):
        pic = slideshow_picture(path)       # a slideshow: its first picture
    pixels = read(pic) if key and pic and Path(pic).is_file() else None
    if pixels is None:
        return {"key": key, "tint": "", "accent": "", "unreadable": True}
    rgb = dominant(pixels)
    if rgb is None:
        return {"key": key, "tint": "", "accent": "", "unreadable": False}
    return {"key": key, "tint": as_tint(rgb), "accent": as_accent(rgb), "unreadable": False}


# ---- following the wallpaper without the app (fedora-glass watch) -------------------------
BACKGROUND = "org.gnome.desktop.background"
PICTURE_KEYS = {"light": "picture-uri", "dark": "picture-uri-dark"}


def picture_path(value: str | None) -> str:
    """A picture-uri value as GSettings prints it ('file:///…'), as a local path; "" for none,
    another kind of URI, or a file that isn't there."""
    v = (value or "").strip().strip("'")
    if not v.startswith("file://"):
        return ""
    from urllib.parse import unquote, urlparse
    p = Path(unquote(urlparse(v).path))
    return str(p) if p.is_file() else ""


def wallpaper_path(env, dark: bool) -> str:
    """The picture GNOME shows in this style: picture-uri-dark in dark (picture-uri when it
    has none, or GNOME is older and has no such key), picture-uri in light."""
    order = ("dark", "light") if dark else ("light", "dark")
    for mode in order:
        try:
            path = picture_path(env.gsettings_get(BACKGROUND, PICTURE_KEYS[mode]))
        except Exception:  # noqa: BLE001 - a key that can't be read is no picture
            path = ""
        if path:
            return path
    return ""


def mark(key: str, dark: bool) -> str:
    """What settings.json keeps in wallpaper_match: the picture's key and its style."""
    return key + ("|dark" if dark else "|light")


def picture_of(match: str) -> str:
    """The picture's key in a wallpaper_match, without the style it was noted in (1.5.24
    noted none)."""
    for tag in ("|dark", "|light"):
        if match.endswith(tag):
            return match[:-len(tag)]
    return match


def follows(s) -> bool:
    """The look takes its tint or accent from the wallpaper."""
    return bool(getattr(s, "tint_from_wallpaper", False) or getattr(s, "accent_from_wallpaper", False))


def rematch(s, path: str, dark: bool, read: Callable[[str], list[tuple[int, int, int]] | None] = pixbuf_pixels):
    """The look `s` with the colours of the picture at `path` (shown in this style), as the
    app takes them at Apply: the tint and the accent whose switches are on, and the picture
    noted in wallpaper_match. None when there is nothing to change: the look doesn't follow
    the wallpaper, there is no picture, it is the picture the colours came from, or it can't
    be read (then the app still says the wallpaper changed, and its Apply can try)."""
    from dataclasses import replace
    if not follows(s) or not path:
        return None
    key = picture_key(path)
    if not key:
        return None
    m = mark(key, dark)
    if m == s.wallpaper_match or picture_of(s.wallpaper_match) == key:
        # The same picture, maybe noted in the other style (GNOME shows one picture in
        # both): its colours are the ones the look has, so it isn't decoded again and
        # settings.json isn't written for nothing at each dark/light switch.
        return None
    c = colours_of(path, read)
    if c.get("unreadable") or c.get("key") != key:
        return None
    values = {"wallpaper_match": m}
    if s.tint_from_wallpaper and c["tint"]:
        values["tint"] = c["tint"]
    if s.accent_from_wallpaper and c["accent"]:
        values["accent"] = c["accent"]
    return replace(s, **values)


def can_read_pictures() -> bool:
    """GdkPixbuf is there to decode pictures with (the watcher has no Qt)."""
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf  # noqa: F401
    except (ImportError, ValueError, AttributeError):
        return False
    return True
