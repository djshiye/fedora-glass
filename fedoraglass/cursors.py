"""The mouse pointer (cursor) styles that come with Fedora Glass.

The themes themselves are installed by the package into /usr/share/icons/<id> (or by
install.sh into ~/.local/share/icons/<id>), built from pinned upstream sources by
packaging/cursors/build.py. Choosing one changes nothing until Apply, which only sets
GNOME's cursor-theme (and, if asked, cursor-size) key; Restore original puts the user's
own pointer back.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .env import Env

IFACE = "org.gnome.desktop.interface"
KEEP = "keep"           # leave the user's own pointer as it is
SIZES = (0, 24, 32, 48)  # 0 = leave the user's own size as it is


@dataclass(frozen=True)
class CursorStyle:
    id: str             # folder name in the icon path, and the cursor-theme value
    name: str
    blurb: str
    credit: str         # who made it, and its licence


STYLES: tuple[CursorStyle, ...] = (
    CursorStyle("fedora-glass-light", "Glass Light", "Frosted glass, dark rim",
                "Fedora Glass, from Bibata by Abdulkaiz Khatri · GPL-3.0"),
    CursorStyle("fedora-glass-dark", "Glass Dark", "Smoked glass, light rim",
                "Fedora Glass, from Bibata by Abdulkaiz Khatri · GPL-3.0"),
    CursorStyle("fedora-glass-bibata-ice", "Bibata Ice", "Rounded, white",
                "Bibata by Abdulkaiz Khatri · GPL-3.0"),
    CursorStyle("fedora-glass-bibata-classic", "Bibata Classic", "Rounded, black",
                "Bibata by Abdulkaiz Khatri · GPL-3.0"),
    CursorStyle("fedora-glass-whitesur", "WhiteSur", "Like macOS",
                "WhiteSur by Vince Liuice · GPL-3.0"),
)
STYLE_IDS = tuple(s.id for s in STYLES)

# The pictures in the picker (first frame of each): arrow, link hand, text beam, busy.
PREVIEW_NAMES = ("left_ptr", "hand2", "xterm", "left_ptr_watch")
# Other names the same shapes go by in other themes, for the user's own pointer.
_ALIASES = {
    "left_ptr": ("default", "arrow", "top_left_arrow"),
    "hand2": ("pointer", "hand1", "hand", "pointing_hand"),
    "xterm": ("text", "ibeam"),
    "left_ptr_watch": ("progress", "half-busy", "wait", "watch"),
}
_PREVIEWS = Path(__file__).resolve().parent / "data/cursors"


def icon_dirs(env: "Env") -> list[Path]:
    """Where cursor themes are looked for, in GNOME's order."""
    return [env.data / "icons", env.home / ".icons", Path("/usr/local/share/icons"), Path("/usr/share/icons")]


def theme_dir(env: "Env", theme: str) -> Path | None:
    if not theme or "/" in theme or theme.startswith("."):
        return None
    for d in icon_dirs(env):
        if (d / theme / "cursors").is_dir():
            return d / theme
    return None


def _inherits(theme_root: Path) -> list[str]:
    try:
        text = (theme_root / "index.theme").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for line in text.splitlines():
        if line.strip().lower().startswith("inherits="):
            return [t.strip() for t in line.split("=", 1)[1].split(",") if t.strip()]
    return []


def find_cursor(env: "Env", theme: str, name: str, _seen: set | None = None) -> Path | None:
    """The file for one pointer shape in a theme, following the theme's Inherits= line."""
    seen = _seen if _seen is not None else set()
    if theme in seen or len(seen) > 8:
        return None
    seen.add(theme)
    root = theme_dir(env, theme)
    names = (name, *_ALIASES.get(name, ()))
    if root is not None:
        for n in names:
            p = root / "cursors" / n
            if p.is_file():
                return p
        for parent in _inherits(root):
            if (found := find_cursor(env, parent, name, seen)) is not None:
                return found
    elif theme != "Adwaita":
        return find_cursor(env, "Adwaita", name, seen)
    return None


@dataclass
class CursorImage:
    size: int
    width: int
    height: int
    xhot: int
    yhot: int
    argb: bytes          # premultiplied ARGB32, little endian (Qt's Format_ARGB32_Premultiplied)


_IMAGE = 0xFFFD0002
_MAX_BYTES = 16 * 1024 * 1024


def read_xcursor(path: Path, want: int) -> CursorImage | None:
    """The first frame nearest `want` px from an Xcursor file; None if it is not one.
    Reads untrusted files (any theme the user has), so every offset is checked."""
    try:
        with open(path, "rb") as f:
            b = f.read(_MAX_BYTES + 1)
    except OSError:
        return None
    if len(b) > _MAX_BYTES or len(b) < 16 or b[:4] != b"Xcur":
        return None
    hsize, _, ntoc = struct.unpack_from("<III", b, 4)
    if ntoc > 4096 or hsize + 12 * ntoc > len(b):
        return None
    imgs = []
    for i in range(ntoc):
        typ, sub, pos = struct.unpack_from("<III", b, hsize + 12 * i)
        if typ == _IMAGE and pos + 36 <= len(b):
            imgs.append((sub, pos))
    if not imgs:
        return None
    best = min({s for s, _ in imgs}, key=lambda s: (abs(s - want), -s))
    pos = next(p for s, p in imgs if s == best)
    _, typ, _, _, w, h, xh, yh, _ = struct.unpack_from("<9I", b, pos)
    if typ != _IMAGE or not (0 < w <= 0x7FFF and 0 < h <= 0x7FFF) or pos + 36 + w * h * 4 > len(b):
        return None
    return CursorImage(best, w, h, min(xh, w - 1), min(yh, h - 1), b[pos + 36:pos + 36 + w * h * 4])


def preview_png(style_id: str, name: str) -> Path | None:
    """The picture that comes with the app, for a style whose files are not installed."""
    p = _PREVIEWS / style_id / f"{name}.png"
    return p if style_id in STYLE_IDS and name in PREVIEW_NAMES and p.is_file() else None


def current_theme(env: "Env") -> str:
    raw = env.gsettings_get(IFACE, "cursor-theme") or "'Adwaita'"
    return raw.strip().strip("'\"") or "Adwaita"
