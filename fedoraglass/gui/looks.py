"""Saved looks: the appearance settings under a name, kept, shared and picked again.

A look holds only how the desktop looks (colours, glass, the panel and windows, motion,
the lock screen's look, the pointer), never what belongs to this PC or this person: which
apps are themed, what happens on removal, starting on the desktop, glass quality (it
depends on the graphics card), opt-ins that change other apps' own settings, and what the
lock screen says about its owner (the message, the weather and its place, the greeting).

Saved looks live in ~/.config/liquid-glass/looks/<slug>.json, private, written atomically.
A look file from somewhere else is untrusted: it is read only up to LOOK_MAX bytes, must be
a JSON object of this format, and only known keys are taken, each through
Settings.normalized(), so nothing in it can do more than moving a slider can.
No Qt in here: the Backend calls it, and the tests run it without PySide6.
"""

from __future__ import annotations

import json
import os
import re
import stat
import unicodedata
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Callable

from .. import settings as settings_mod
from ..settings import Settings

FORMAT = "fedora-glass-look"
VERSION = 1
LOOK_MAX = 64 * 1024
NAME_MAX = 40
LIST_MAX = 200          # looks shown; a folder with more is someone else's mess, not a list

# The settings a look carries. A list of what is in, not of what is out: a setting added
# later stays the user's own until someone decides it is part of a look.
LOOK_KEYS = (
    "frost", "scheme", "accent", "tint", "tint_strength", "radius", "highlight", "opacity", "blur",
    "reduce_transparency", "panel_style", "panel_margin", "blur_app_windows", "terminal_opacity",
    "refraction", "dispersion", "vibrancy", "bleed", "pointer_light", "liquid_motion", "menu_grow",
    "glass_panel", "glass_menus", "glass_overview", "glass_see_windows", "parts",
    "header_height", "header_opacity", "motion", "hover_glide",
    "lock_glass", "lock_blur", "lock_dim", "lock_tint", "lock_card", "lock_clock", "lock_clock_position",
    "lock_slide", "lock_slide_ms", "lock_bounce", "lock_widget_battery", "lock_widget_style",
    "cursor_theme", "cursor_size",
    "tint_from_wallpaper", "accent_from_wallpaper",
)


class LookError(Exception):
    """A look file that can't be used; the message is for the user."""


def looks_dir(settings_path: Path | None = None) -> Path:
    return (settings_path or settings_mod.settings_path()).parent / "looks"


def clean_name(raw: object) -> str:
    """A look's name: plain text on one line, at most NAME_MAX characters."""
    if not isinstance(raw, str):
        return ""
    return settings_mod.clean_message(raw)[:NAME_MAX].strip()


def slug(name: str) -> str:
    """The file name for a look's name: lower-case letters, digits and dashes."""
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-")
    return text or "look"


def pick(s: Settings) -> dict:
    """The look part of these settings, as it is written to a file."""
    d = asdict(s.normalized())
    return {k: d[k] for k in LOOK_KEYS}


def same_look(a: Settings, b: Settings) -> bool:
    na, nb = a.normalized(), b.normalized()
    da = pick(na)
    db = pick(nb)
    # Motion as it plays: a missing event is its default.
    da["motion"] = {ev: na.motion_for(ev) for ev in settings_mod.MOTION_EVENTS}
    db["motion"] = {ev: nb.motion_for(ev) for ev in settings_mod.MOTION_EVENTS}
    for k in da:
        x, y = da[k], db[k]
        if isinstance(x, float) or isinstance(y, float):
            if x is None or y is None or abs(float(x) - float(y)) > 0.0005:
                return False
        elif x != y:
            return False
    return True


def apply_look(current: Settings, look: dict, cursor_installed: Callable[[str], bool] = lambda _id: True) -> Settings:
    """`current` with the look's settings. Every value goes through Settings.normalized(),
    one at a time, so a bad value costs only that setting (it stays as it is). A pointer
    style this PC doesn't have keeps the user's own pointer."""
    known = {f.name for f in fields(Settings)}
    s = replace(current.normalized(), targets=dict(current.targets))
    for k in LOOK_KEYS:
        if k not in look or k not in known:
            continue
        v = look[k]
        if k == "cursor_theme" and v != "keep" and not cursor_installed(str(v)):
            continue
        try:
            trial = replace(s, **{k: v}).normalized()
        except (TypeError, ValueError, OverflowError, RecursionError):
            continue
        s = trial
    if not s.tint_from_wallpaper:
        s.tint_own = s.accent_own = ""
    return s


def look_data(name: str, s: Settings) -> dict:
    return {"format": FORMAT, "version": VERSION, "name": clean_name(name), "settings": pick(s)}


def parse(raw: bytes) -> tuple[str, dict]:
    """(name, settings) from the bytes of a look file. Raises LookError with plain words."""
    if len(raw) > LOOK_MAX:
        raise LookError(f"This file is too big to be a look (looks are under {LOOK_MAX // 1024} KB).")
    try:
        data = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise LookError("This file isn't a look: it isn't text.") from None
    except (ValueError, RecursionError):
        raise LookError("This file isn't a look: it isn't readable JSON.") from None
    if not isinstance(data, dict):
        raise LookError("This file isn't a look: it holds no settings.")
    if data.get("format") != FORMAT:
        raise LookError("This file isn't a Fedora Glass look.")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise LookError("This look file has no version, so it can't be read safely.")
    values = data.get("settings")
    if not isinstance(values, dict):
        raise LookError("This look file holds no settings.")
    # Only known keys; a newer version's extra settings are left out.
    values = {k: values[k] for k in LOOK_KEYS if k in values}
    if not values:
        raise LookError("This look file holds none of the settings this version knows.")
    name = clean_name(data.get("name")) or "Imported look"
    return name, values


def read_file(path: Path) -> tuple[str, dict]:
    """A look file picked by the user: at most LOOK_MAX bytes are read, never a device or a pipe."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)     # a pipe must not hang the app
    except FileNotFoundError:
        raise LookError("That file isn't there any more.") from None
    except OSError as e:
        raise LookError(f"That file can't be opened ({e.strerror or e}).") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise LookError("That isn't a file a look can be read from.")
        with os.fdopen(fd, "rb", closefd=False) as f:
            raw = f.read(LOOK_MAX + 1)
    except OSError as e:
        raise LookError(f"That file can't be read ({e.strerror or e}).") from None
    finally:
        os.close(fd)
    return parse(raw)


class Library:
    """The saved looks in one folder."""

    def __init__(self, folder: Path):
        self.folder = folder

    def _file(self, look_id: str) -> Path | None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,47}", look_id or ""):
            return None
        return self.folder / f"{look_id}.json"

    def list(self) -> list[dict]:
        """[{"id", "name", "settings"}], by name. Files that aren't looks are left out."""
        out = []
        try:
            entries = sorted(p for p in self.folder.iterdir() if p.suffix == ".json")[:LIST_MAX]
        except OSError:
            return []
        for p in entries:
            if self._file(p.stem) != p:
                continue
            try:
                if p.is_symlink() or not p.is_file():
                    continue
                name, values = parse(p.read_bytes()[:LOOK_MAX + 1])
            except (OSError, LookError):
                continue
            out.append({"id": p.stem, "name": name, "settings": values})
        out.sort(key=lambda d: (d["name"].casefold(), d["id"]))
        return out

    def get(self, look_id: str) -> dict | None:
        return next((d for d in self.list() if d["id"] == look_id), None)

    def _free_id(self, name: str, keep: str = "") -> str:
        base = slug(name)
        taken = {p.stem for p in self.folder.glob("*.json")} - {keep}
        if base not in taken:
            return base
        n = 2
        while f"{base[:44]}-{n}" in taken:
            n += 1
        return f"{base[:44]}-{n}"

    def _write(self, look_id: str, name: str, values: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        os.chmod(self.folder, 0o700)
        data = {"format": FORMAT, "version": VERSION, "name": name, "settings": values}
        settings_mod._write(self.folder / f"{look_id}.json", json.dumps(data, indent=2).encode("utf-8") + b"\n")

    def save(self, name: str, s: Settings) -> str:
        name = clean_name(name)
        if not name:
            raise LookError("Give the look a name.")
        look_id = self._free_id(name)
        self._write(look_id, name, pick(s))
        return look_id

    def add(self, name: str, values: dict) -> str:
        """An imported look, with its values made safe: through normalized(), on the defaults."""
        clean = pick(apply_look(Settings(), values))
        look_id = self._free_id(name)
        self._write(look_id, clean_name(name) or "Imported look", clean)
        return look_id

    def rename(self, look_id: str, name: str) -> str:
        name = clean_name(name)
        if not name:
            raise LookError("Give the look a name.")
        look = self.get(look_id)
        if look is None:
            raise LookError("That look isn't there any more.")
        new_id = self._free_id(name, keep=look_id)
        self._write(new_id, name, look["settings"])
        if new_id != look_id:
            self.delete(look_id)
        return new_id

    def delete(self, look_id: str) -> None:
        p = self._file(look_id)
        if p is None:
            return
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    def export(self, look_id: str, dest: Path) -> None:
        look = self.get(look_id)
        if look is None:
            raise LookError("That look isn't there any more.")
        data = {"format": FORMAT, "version": VERSION, "name": look["name"], "settings": look["settings"]}
        try:
            settings_mod._write(dest, json.dumps(data, indent=2).encode("utf-8") + b"\n")
            os.chmod(dest, 0o644)    # a file to share: readable, like any document
        except OSError as e:
            raise LookError(f"The look couldn't be saved there ({e.strerror or e}).") from None
