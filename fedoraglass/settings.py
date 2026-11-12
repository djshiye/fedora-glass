"""User settings: what the customizer edits and every renderer reads.

Stored as JSON in ~/.config/liquid-glass/settings.json. Missing keys fall back to
defaults, so old files keep working. Keys a newer version wrote don't change what this
version does, and are written back on save, so going back a version loses nothing.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import math
import os
import re
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import NamedTuple

from .i18n import _
from .cursors import SIZES as CURSOR_SIZES, STYLE_IDS as CURSOR_STYLE_IDS

# GNOME's own accent colours (Settings > Appearance), so "system" matches the desktop.
GNOME_ACCENTS = {
    "blue": "#3584e4", "teal": "#2190a4", "green": "#3a944a", "yellow": "#c88800",
    "orange": "#ed5b00", "red": "#e62d42", "pink": "#d56199", "purple": "#9141ac",
    "slate": "#6f8396",
}

SCHEMES = ("auto", "dark", "light")
# How much the shell extension draws: auto steps down by itself when frames drop.
GLASS_QUALITIES = ("auto", "full", "lighter", "lightest")
PANEL_STYLES = ("floating", "docked")
# Header bar height limits: below 36 px the buttons no longer fit, above 64 px it is wasted space.
HEADER_MIN, HEADER_MAX = 36, 64
HEADER_OPACITY_MIN = 0.10  # never fully clear, so titles stay readable

# Window and panel animations: which one plays for each event, how lively it is
# (intensity 0..1) and how fast (speed 0.5..2). The extension's curves.js holds the
# same lists. "gnome" leaves an event to GNOME's own animation; "off" makes it instant.
MOTION_EVENTS = ("open", "minimize", "close", "launch", "hover")
MOTION_PRESETS = {
    "open": ("gnome", "spring", "bounce", "jelly", "genie", "scalefade", "off"),
    "minimize": ("gnome", "spring", "bounce", "jelly", "genie", "scalefade", "off"),
    "close": ("gnome", "scalefade", "spring", "genie", "off"),
    "launch": ("bounce", "spring", "jelly", "off"),
    "hover": ("spring", "bounce", "jelly", "scalefade", "off"),
}
MOTION_DEFAULTS = {
    "open": {"preset": "spring", "intensity": 0.5, "speed": 1.0},
    "minimize": {"preset": "genie", "intensity": 0.5, "speed": 1.0},
    "close": {"preset": "scalefade", "intensity": 0.5, "speed": 1.0},
    "launch": {"preset": "bounce", "intensity": 0.5, "speed": 1.0},
    "hover": {"preset": "spring", "intensity": 0.5, "speed": 1.0},
}
SPEED_MIN, SPEED_MAX = 0.5, 2.0

# Motion styles: one choice that sets every animation at once (the Motion page's tiles).
# Each sets the style and strength of all five; the speed is the user's own and stays.
def _style(open_, minimize, close, launch, hover, i):
    return {"open": (open_, i), "minimize": (minimize, i), "close": (close, i),
            "launch": (launch, i), "hover": (hover, i)}


MOTION_STYLES = {
    "off": _style("off", "off", "off", "off", "off", 0.5),
    "calm": _style("scalefade", "scalefade", "scalefade", "spring", "scalefade", 0.3),
    "gnome": _style("gnome", "gnome", "gnome", "off", "off", 0.5),
    "lively": {ev: (MOTION_DEFAULTS[ev]["preset"], MOTION_DEFAULTS[ev]["intensity"]) for ev in MOTION_EVENTS},
    "playful": _style("bounce", "jelly", "genie", "bounce", "jelly", 0.75),
}


def motion_style_of(motion: dict[str, dict]) -> str:
    """The motion style these animations match, ignoring speed, or "custom"."""
    for name, style in MOTION_STYLES.items():
        if all(motion[ev]["preset"] == p and (p == "off" or abs(float(motion[ev]["intensity"]) - i) < 0.005)
               for ev, (p, i) in style.items()):
            return name
    return "custom"

# The parts of the desktop that can differ from the global look, and the
# values each may override (a missing key follows the global setting).
PARTS = ("panel", "arcmenu", "quicksettings", "calendar", "overview", "windows", "terminal")
PART_KEYS = ("tint", "tint_strength", "radius", "frost", "refraction", "bleed", "reflections")


@dataclass
class Settings:
    # The headline control: 0 = liquid (clear, sharp, bright rim light),
    # 1 = frosted (milky, heavily blurred, quiet edges).
    frost: float = 0.45
    scheme: str = "auto"            # auto follows GNOME's dark/light style
    accent: str = "system"          # "system", a GNOME accent name, or "#rrggbb"
    tint: str = "#8fa8c8"           # colour the glass leans towards
    tint_strength: float = 0.06     # 0..1
    radius: int = 18                # base corner radius in px
    highlight: float = 0.7          # specular rim light strength, 0..1
    # Fine-tune overrides; None means "follow the frost slider".
    opacity: float | None = None    # 0..1, how solid chrome surfaces are
    blur: int | None = None         # blur radius in px
    reduce_transparency: bool = False  # accessibility: near-opaque everything

    glass_quality: str = "auto"     # see GLASS_QUALITIES
    panel_style: str = "floating"   # Dash to Panel: floating pill or edge-docked
    panel_margin: int = 8
    blur_app_windows: bool = True   # glass behind translucent app windows
    terminal_opacity: float | None = None

    # The Fedora Glass Shell extension: the lens along the edge of the panel and menus.
    refraction: float = 0.6         # 0..1, how strongly the rim bends what's behind
    dispersion: float = 0.3         # 0..1, rainbow split along the rim
    vibrancy: float = 0.85          # 0..1, how much colour shows through
    bleed: float = 0.6              # 0..1, how much icon and text colours light up the glass around them
    pointer_light: float = 0.5      # 0..1, how far the light on the glass turns towards the pointer
    liquid_motion: bool = True      # glass springs a little when pressed and when a menu opens
    liquid_strength: float = 0.4    # 0..1, how far the glass gives under a press (0.4: the original feel)
    menu_grow: bool = True          # menus grow out of the button that opened them, and flow back on close
    glass_panel: bool = True
    glass_menus: bool = True        # menus, quick settings, calendar, ArcMenu, Spawn
    glass_overview: bool = True     # blurred wallpaper behind the overview
    glass_see_windows: bool = True  # panel and menus show the windows behind them, not just the wallpaper

    # Desktop behaviour, done by the same Shell extension.
    # Log in to the desktop, not the Activities overview. None (not chosen yet) follows the
    # desktop: on with Dash to Panel, whose users start on the desktop anyway; off on GNOME's
    # own desktop, which opens Activities at login (see start_on_desktop_for).
    start_on_desktop: bool | None = None
    overview_off: bool = False      # Activities never opens: no hot corner, Super key or swipe

    # When the app is removed (`dnf remove fedora-glass`), put the original look back
    # first, as Restore original does. Off: the look stays as it is after removal.
    undo_on_remove: bool = True

    # Per-part overrides: {"panel": {"tint": "#rrggbb", "radius": 12}, ...}.
    # Parts: panel, arcmenu, quicksettings, calendar (and notifications), overview (dash and
    # overview), windows, terminal. Keys: tint, tint_strength (0..1), radius (0..32 px),
    # frost (0..1), refraction (0..1), bleed (0..1), reflections (0..1, edge reflections).
    parts: dict[str, dict] = field(default_factory=dict)

    # Target id -> enabled. Missing ids default to enabled, except OPT_IN_TARGETS.
    targets: dict[str, bool] = field(default_factory=dict)

    # Window header bars in GTK 3, GTK 4 and libadwaita apps.
    header_height: int = 47                 # px; 47 is GNOME's own height
    header_opacity: float | None = None     # how solid, 0..1; None = the same glass as the window
    # Switch Ptyxis profiles to the Fedora Glass palette (it carries the glass top bar).
    # Off unless the user opts in, so their own terminal colours are never replaced.
    terminal_colors: bool = False
    # Ptyxis has its own light/dark switch, set to dark out of the box. Off unless the
    # user opts in: then Ptyxis follows GNOME's style; off again brings their own value back.
    terminal_follows_style: bool = False
    # Qt apps' own title bars have fixed colours that no theme can reach. On, native Qt
    # apps start through XWayland when they can, so GNOME draws their title bar with
    # the same glass header as GTK apps. Off unless the user opts in: it can make Qt
    # apps a little soft with fractional scaling. Flatpak apps are left alone.
    qt_gnome_titlebars: bool = False

    # Animations, per event: {"open": {"preset": "spring", "intensity": 0.5, "speed": 1.0}, ...}.
    # A missing event or key uses MOTION_DEFAULTS.
    motion: dict[str, dict] = field(default_factory=dict)
    # Dash to Panel's own "Animate hovering app icons" is switched off so ours can run.
    # Only when the user asks; Restore original brings their setting back.
    motion_dtp_hover_off: bool = False
    # One hover highlight that glides from icon to icon along the Dash to Panel taskbar,
    # in place of Dash to Panel's own highlight on each icon.
    hover_glide: bool = True

    # The glass lock screen, drawn by the same Shell extension. Only the wallpaper shows
    # through it; GNOME's own clock, password prompt and notifications stay as they are.
    lock_glass: bool = True
    lock_blur: int = 60                 # px of frost on the sheet, 10..100
    lock_dim: float = 0.28              # 0..0.65, how much darker the sheet is than the wallpaper
    lock_tint: float = 0.2              # 0..1, how much of the glass tint colours the sheet
    lock_card: bool = True              # a glass card behind the password prompt
    lock_clock: str = "bold"            # gnome, bold or thin
    lock_clock_position: str = "gnome"  # gnome (upper third), top or middle
    lock_slide: str = "spring"          # how the sheet leaves on unlock: gnome, smooth or spring
    lock_slide_ms: int = 450            # 250..1200
    lock_bounce: float = 0.2            # 0..1, spring only
    # Widgets on the lock screen. Only the battery is on by default: it says nothing
    # about the owner. Weather, its place name, the greeting and the message are opt-in.
    lock_widget_battery: bool = True    # laptops only; a PC without a battery shows nothing
    lock_widget_weather: bool = False   # GNOME Weather's current weather for the place set there
    lock_weather_place: bool = False    # also name that place
    lock_greeting: bool = False         # "Good morning" above the clock
    lock_message: str = ""              # the owner's own words under the clock, plain text
    lock_widget_style: str = "chips"    # chips (small glass panes) or plain (text only)
    # Hide GNOME's notifications and music controls on the lock screen (only hidden,
    # GNOME's own notification settings are not changed).
    lock_hide_notifications: bool = False

    # The mouse pointer: "keep" leaves the user's own; otherwise one of cursors.STYLE_IDS,
    # set on Apply (Restore original brings theirs back). Size 0 leaves their own size.
    cursor_theme: str = "keep"
    cursor_size: int = 0

    # ---- Shell features: lighter glass on battery, apps without glass, the Quick Settings switch ----
    # On battery or in Power Saver, the glass draws at most at the lighter level (never
    # heavier than glass_quality or auto picked); back on mains it goes back.
    lighter_on_battery: bool = True
    # The user's own apps whose windows get no glass, as the ids the extension matches a
    # window by (desktop id without ".desktop", WM class, app id). The built-in ones
    # (render/glass.py WINDOW_SKIP and windows.js NO_GLASS) always apply on top.
    no_glass_apps: list[str] = field(default_factory=list)
    # A "Glass" tile in GNOME's Quick Settings that pauses all the glass until the next login.
    quick_toggle: bool = True
    # ---- feature stream "looks": the glass tint (and accent) from the wallpaper ----------
    # The app works the colour out of the wallpaper when Apply is pressed and writes it into
    # `tint` (and `accent`), so the engine, the command line and the watcher need no image
    # code. These say to do so, and what the user had picked before, to put back when off.
    tint_from_wallpaper: bool = False
    accent_from_wallpaper: bool = False
    tint_own: str = ""                      # "#rrggbb" or "" (nothing to put back)
    accent_own: str = ""                    # an accent value, or ""
    # Which picture the colours were last taken from ("<path>|<mtime_ns>|<size>"), so the
    # app can say when the wallpaper changed since.
    wallpaper_match: str = ""

    def motion_for(self, event: str) -> dict:
        return {**MOTION_DEFAULTS[event], **self.motion.get(event, {})}

    def target_enabled(self, target_id: str) -> bool:
        return self.targets.get(target_id, target_default(target_id))

    # ---- validation ---------------------------------------------------
    def start_on_desktop_for(self, has_dash_to_panel: bool) -> bool:
        """Whether GNOME starts on the desktop, with the default following the desktop."""
        return has_dash_to_panel if self.start_on_desktop is None else bool(self.start_on_desktop)

    def normalized(self) -> "Settings":
        s = Settings(**asdict(self))
        s.frost = _clamp(float(s.frost))
        s.tint_strength = _clamp(float(s.tint_strength))
        s.highlight = _clamp(float(s.highlight))
        s.refraction = _clamp(float(s.refraction))
        s.dispersion = _clamp(float(s.dispersion))
        s.vibrancy = _clamp(float(s.vibrancy))
        s.bleed = _clamp(float(s.bleed), Settings.bleed)
        s.pointer_light = _clamp(float(s.pointer_light), Settings.pointer_light)
        s.liquid_strength = _clamp(float(s.liquid_strength), Settings.liquid_strength)
        for k in ("liquid_motion", "menu_grow", "hover_glide"):
            setattr(s, k, _bool(getattr(s, k), getattr(Settings, k)))
        s.radius = _int(s.radius, 0, 32, Settings.radius)
        s.panel_margin = _int(s.panel_margin, 0, 32, Settings.panel_margin)
        for k in ("blur_app_windows", "reduce_transparency", "glass_panel", "glass_menus",
                  "glass_overview", "glass_see_windows", "terminal_colors", "terminal_follows_style", "qt_gnome_titlebars",
                  "overview_off"):
            setattr(s, k, _bool(getattr(s, k), getattr(Settings, k)))
        if s.start_on_desktop is not None:
            s.start_on_desktop = _bool(s.start_on_desktop, True)
        if s.opacity is not None:
            s.opacity = _clamp(float(s.opacity), 0.6)
        if s.blur is not None:
            b = float(s.blur)
            s.blur = int(min(100, max(0, b))) if math.isfinite(b) else None
        if s.terminal_opacity is not None:
            t = float(s.terminal_opacity)
            s.terminal_opacity = min(1.0, max(0.3, t)) if math.isfinite(t) else None
        if s.scheme not in SCHEMES:
            s.scheme = "auto"
        if s.glass_quality not in GLASS_QUALITIES:
            s.glass_quality = "auto"
        if s.panel_style not in PANEL_STYLES:
            s.panel_style = "floating"
        if not (s.accent == "system" or s.accent in GNOME_ACCENTS or _is_hex(s.accent)):
            s.accent = "system"
        if not _is_hex(s.tint):
            s.tint = Settings.tint
        s.parts = _clean_parts(s.parts)
        s.motion = _clean_motion(s.motion)
        s.targets = {str(k): _bool(v, True) for k, v in dict(s.targets).items()}
        s.header_height = _int(s.header_height, HEADER_MIN, HEADER_MAX, Settings.header_height)
        for k in ("lock_glass", "lock_card", "undo_on_remove"):
            setattr(s, k, _bool(getattr(s, k), getattr(Settings, k)))
        s.lock_blur = _int(s.lock_blur, 10, 100, Settings.lock_blur)
        s.lock_dim = min(0.65, _clamp(float(s.lock_dim), Settings.lock_dim))
        s.lock_tint = _clamp(float(s.lock_tint), Settings.lock_tint)
        s.lock_slide_ms = _int(s.lock_slide_ms, 250, 1200, Settings.lock_slide_ms)
        s.lock_bounce = _clamp(float(s.lock_bounce), Settings.lock_bounce)
        for k in ("lock_widget_battery", "lock_widget_weather", "lock_weather_place", "lock_greeting",
                  "lock_hide_notifications"):
            # Only a real true switches one on: "false" typed by hand must not show the weather.
            v = getattr(s, k)
            setattr(s, k, v if isinstance(v, bool) else getattr(Settings, k))
        s.lock_message = clean_message(s.lock_message)
        for k, choices in LOCK_CHOICES.items():
            if getattr(s, k) not in choices:
                setattr(s, k, getattr(Settings, k))
        if s.cursor_theme != "keep" and s.cursor_theme not in CURSOR_STYLE_IDS:
            s.cursor_theme = "keep"
        # 24.0 (a hand edit, another tool's JSON) equals 24 but would reach gsettings as
        # "24.0", which an int key refuses on every Apply.
        size = s.cursor_size
        if isinstance(size, float) and size.is_integer():
            size = int(size)
        s.cursor_size = size if type(size) is int and size in CURSOR_SIZES else 0
        if s.header_opacity is not None:
            h = float(s.header_opacity)
            s.header_opacity = min(1.0, max(HEADER_OPACITY_MIN, h)) if math.isfinite(h) else None
        # ---- Firefox theme (opt-in parts) ----
        # Only a real true turns an opt-in part on: "yes" typed by hand, or a damaged
        # value, must not change files in another app's profile.
        raw = dict(self.targets) if isinstance(self.targets, dict) else {}
        for k in OPT_IN_TARGETS & set(s.targets):
            s.targets[k] = raw.get(k) is True
        # ---- Shell features (lighter glass on battery, apps without glass, Quick Settings switch) ----
        for k in ("lighter_on_battery", "quick_toggle"):
            setattr(s, k, _bool(getattr(s, k), getattr(Settings, k)))
        s.no_glass_apps = clean_app_ids(s.no_glass_apps)
        # ---- feature stream "looks": colours from the wallpaper ----
        for k in ("tint_from_wallpaper", "accent_from_wallpaper"):
            setattr(s, k, _bool(getattr(s, k), False))
        s.tint_own = s.tint_own if _is_hex(s.tint_own) else ""
        if not (s.accent_own in ("", "system") or s.accent_own in GNOME_ACCENTS or _is_hex(s.accent_own)):
            s.accent_own = ""
        s.wallpaper_match = _CONTROL.sub("", s.wallpaper_match)[:4096] if isinstance(s.wallpaper_match, str) else ""
        return s


# ---- Firefox theme (opt-in parts) ----------------------------------------------------
# Parts that are off until the user turns them on in the Apps page: they change files in
# another app's own profile folders, which nobody should find changed without asking.
# A new id, not Firefox's old "firefox" row: an older version stored that one as on when
# it was switched off and on again, and that must not count as asking for this.
OPT_IN_TARGETS = frozenset({"firefox-theme"})


def target_default(target_id: str) -> bool:
    """Whether a part is on when the user hasn't switched it either way."""
    return target_id not in OPT_IN_TARGETS


LOCK_CHOICES = {"lock_clock": ("gnome", "bold", "thin"), "lock_clock_position": ("gnome", "top", "middle"),
                "lock_slide": ("gnome", "smooth", "spring"), "lock_widget_style": ("chips", "plain")}

LOCK_MESSAGE_MAX = 120
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def clean_message(raw: object) -> str:
    """The lock screen message: plain text, one paragraph, at most LOCK_MESSAGE_MAX characters."""
    if not isinstance(raw, str):
        return ""
    text = " ".join(_CONTROL.sub(" ", raw).split())
    return text[:LOCK_MESSAGE_MAX].strip()


# The user's apps without window glass: how many ids, and how long each may be. The
# extension (config.js) takes at most 200 ids of under 200 characters, built-in ones included.
NO_GLASS_APPS_MAX = 150
APP_ID_MAX = 199


def clean_app_ids(raw: object) -> list[str]:
    """App ids as the extension compares them with a window's (whole ids, any case): strings with no
    control characters, trimmed, 1..APP_ID_MAX long, each once, at most NO_GLASS_APPS_MAX."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    for v in raw:
        if not isinstance(v, str):
            continue
        v = v.strip()
        if not v or len(v) > APP_ID_MAX or _CONTROL.search(v) or v in out:
            continue
        out.append(v)
        if len(out) >= NO_GLASS_APPS_MAX:
            break
    return out


def _clean_parts(raw: object) -> dict[str, dict]:
    """Keep only known parts and keys, with every value clamped; bad values are dropped
    (so that key follows the global setting again)."""
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for part in PARTS:
        src = raw.get(part)
        if not isinstance(src, dict):
            continue
        clean: dict[str, object] = {}
        for key in PART_KEYS:
            v = src.get(key)
            if v is None:
                continue
            if key == "tint":
                if _is_hex(v):
                    clean[key] = v
            elif key == "radius":
                r = _int(v, 0, 32, -1)
                if r >= 0:
                    clean[key] = r
            else:
                try:
                    f = float(v)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if math.isfinite(f):
                    clean[key] = _clamp(f)
        if clean:
            out[part] = clean
    return out


def _clean_motion(raw: object) -> dict[str, dict]:
    """Keep only known events and preset names, with intensity and speed clamped.
    Values equal to the default are kept too, so a choice survives a change of default."""
    out: dict[str, dict] = {}
    if not isinstance(raw, dict):
        return out
    for ev in MOTION_EVENTS:
        src = raw.get(ev)
        if not isinstance(src, dict):
            continue
        clean: dict[str, object] = {}
        if src.get("preset") in MOTION_PRESETS[ev]:
            clean["preset"] = src["preset"]
        for key, lo, hi in (("intensity", 0.0, 1.0), ("speed", SPEED_MIN, SPEED_MAX)):
            try:
                f = float(src[key])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(f):
                clean[key] = round(min(hi, max(lo, f)), 3)
        if clean:
            out[ev] = clean
    return out


_TRUE, _FALSE = ("true", "1", "yes", "on"), ("false", "0", "no", "off")


def _bool(v: object, default: bool) -> bool:
    """A switch from a hand-edited file: bool() would count the string "false" as on.
    Words and 0/1 are read as meant; anything else is the switch's default."""
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    if isinstance(v, str):
        w = v.strip().lower()
        if w in _TRUE:
            return True
        if w in _FALSE:
            return False
    return default


def _clamp(x: float, default: float = 0.5) -> float:
    if not math.isfinite(x):
        return default
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _int(v: object, lo: int, hi: int, default: int) -> int:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return int(min(hi, max(lo, f))) if math.isfinite(f) else default


def _is_hex(v: object) -> bool:
    if not isinstance(v, str) or not v.startswith("#") or len(v) not in (4, 7):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in v[1:])


# ---- presets ----------------------------------------------------------
PRESETS: dict[str, dict] = {
    "Liquid": {"frost": 0.0, "highlight": 0.9, "tint_strength": 0.04},
    # Apple's two glasses: clear (almost no blur or tint; text keeps a soft shade of its
    # own) and frosted (a heavy but not foggy blur, a milky or smoky tint).
    "Clear": {"frost": 0.1, "blur": 2, "highlight": 0.85, "tint_strength": 0.03},
    "Balanced": {"frost": 0.45, "highlight": 0.7, "tint_strength": 0.06},
    "Frosted": {"frost": 0.8, "blur": 26, "highlight": 0.45, "tint_strength": 0.09},
    "Solid": {"frost": 1.0, "highlight": 0.3, "tint_strength": 0.1, "opacity": 0.92},
}


def apply_preset(s: Settings, name: str) -> Settings:
    data = asdict(s)
    data.update({"opacity": None, "blur": None})
    data.update(PRESETS[name])
    return Settings(**data).normalized()


# ---- storage ------------------------------------------------------------
def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "liquid-glass"


def settings_path() -> Path:
    return config_dir() / "settings.json"


def _sibling(path: Path, suffix: str) -> Path:
    return path.with_name(path.name + suffix)


class Loaded(NamedTuple):
    """What load_checked() found. `problem`: why the file could not be used, for the user,
    or None. `usable`: whether these settings are the user's own (their file, its last good
    copy, or no file at all); False means only defaults stand in for a file that is damaged,
    and nothing should be applied by itself from them."""
    settings: Settings
    problem: str | None
    usable: bool


def _parse(raw: bytes) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"))
    except RecursionError as err:
        # Nested thousands deep: no settings file of ours, and damaged like any other.
        raise ValueError("not a Fedora Glass settings file") from err
    if not isinstance(data, dict):
        raise ValueError("not a Fedora Glass settings file")
    return data


def _read(path: Path) -> dict | None:
    """The file's settings, or None when there is no file. Raises OSError or ValueError
    when it is there but can't be read or isn't settings."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    return _parse(raw)


@contextlib.contextmanager
def _locked(path: Path) -> Iterator[None]:
    """One writer of settings.json at a time: save() and the step that moves a damaged file
    aside (the app and the watcher both do that). Plain reads don't take it."""
    fd = os.open(path.with_name(f".{path.name}.lock"), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def load_checked(path: Path | None = None, *, fix: bool = True, _tries: int = 3) -> Loaded:
    """Load the settings and say whether they can be trusted.

    A missing file is the defaults (a first start). A file that is there but damaged (a
    power cut mid-write, a bad hand edit) is never quietly taken for the defaults: the
    watcher would then apply them over the user's look. It is moved aside as
    settings.json.damaged (only the latest is kept) and the last good copy that save()
    keeps (settings.json.bak) takes its place, when that one reads.
    `fix=False` only reads (the last good copy, when there is one) and moves or writes
    nothing: for commands that just look (status, plan) and for the package removal."""
    path = path or settings_path()
    damaged = _sibling(path, ".damaged")
    blob = None
    try:
        blob = path.read_bytes()
        raw = _parse(blob)
    except FileNotFoundError:
        if damaged.exists():
            # Damaged earlier and nothing saved since: still no file of the user's to go on.
            return Loaded(_stand_in(path), damage_notice(path), False)
        return Loaded(Settings(), None, True)
    except (OSError, ValueError) as err:
        problem: Exception = err
    else:
        return Loaded(_from_dict(raw), None, True)
    if fix and isinstance(problem, ValueError):
        # Readable but not settings: set it aside, so a later save can't lose it and a
        # copy is there to look at. A read error (EIO, no permission) moves nothing.
        try:
            with _locked(path):
                try:
                    now = path.read_bytes()
                except OSError:
                    now = None
                if now != blob:
                    # The app saved a good file since it was read: that one must not go.
                    raise _ReadAgain
                os.replace(path, damaged)
                os.utime(damaged)       # when it was found, for damage_notice()
                good = _good_copy(path)
                if good is not None:
                    _write(path, json.dumps(good, indent=2).encode() + b"\n")
                    os.utime(damaged)   # newer than the copy put back: the notice stays until a save
        except _ReadAgain:
            if _tries > 0:
                return load_checked(path, fix=fix, _tries=_tries - 1)
        except OSError:
            pass
    good = _good_copy(path)
    if good is not None:
        return Loaded(_from_dict(good), f"Your settings file {path} could not be read ({problem}), so the last good "
                                        "copy of it is used." + _kept(damaged), True)
    return Loaded(_stand_in(path), f"Your settings file {path} could not be read ({problem}), and there is "
                              "no good copy of it. Fedora Glass shows its defaults and changes nothing by "
                              "itself until you press Apply." + _kept(damaged), False)


class _ReadAgain(Exception):
    pass


def _good_copy(path: Path) -> dict | None:
    try:
        return _read(_sibling(path, ".bak"))
    except (OSError, ValueError):
        return None


def _on_remove_path(path: Path) -> Path:
    return _sibling(path, ".on-remove")


def _stand_in(path: Path) -> Settings:
    """The defaults that stand in for a damaged file, with the one choice the app saves
    on its own meanwhile: "Remove only" (see save_undo_on_remove)."""
    try:
        raw = json.loads(_on_remove_path(path).read_bytes().decode("utf-8"))
    except (OSError, ValueError):
        raw = None
    on = raw.get("undo_on_remove") if isinstance(raw, dict) else None
    return Settings(undo_on_remove=on) if isinstance(on, bool) else Settings()


def save_undo_on_remove(on: bool, path: Path | None = None) -> None:
    """Keep "Remove only" while settings.json is damaged with no good copy. Only an Apply
    may write settings.json then: anything else would write the defaults that stand in for
    it, and the watcher would take those for the user's own and apply them. Removing the
    package still finds the choice: load_checked() reads it back for as long as the file
    stays unusable, and an Apply saves it in settings.json with the rest."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(_on_remove_path(path), json.dumps({"undo_on_remove": bool(on)}).encode() + b"\n")


def read_raw(path: Path | None = None) -> bytes | None:
    """settings.json as it is now, or None when there is none (for put_back)."""
    try:
        return (path or settings_path()).read_bytes()
    except FileNotFoundError:
        return None


def put_back(before: bytes | None, path: Path | None = None) -> None:
    """settings.json as read_raw() found it (none: no file), after an Apply that stopped.
    Unlike save(), the last good copy (.bak) is left alone: it must never become the look
    that failed."""
    path = path or settings_path()
    with _locked(path):
        if before is None:
            path.unlink(missing_ok=True)
        else:
            _write(path, before)


def _kept(damaged: Path) -> str:
    return f" The damaged file is kept as {damaged}." if damaged.exists() else ""


def load(path: Path | None = None, *, fix: bool = True) -> Settings:
    return load_checked(path, fix=fix).settings


def damage_notice(path: Path | None = None) -> str | None:
    """For the app: a line to show while the settings were found damaged and nothing has
    been saved since (the damaged copy is newer than settings.json, or there is no
    settings.json), else None."""
    path = path or settings_path()
    damaged = _sibling(path, ".damaged")
    try:
        found = damaged.stat().st_mtime_ns
    except OSError:
        return None
    try:
        if path.stat().st_mtime_ns > found:
            return None     # saved again since: the user has their settings back
        recovered = True    # the last good copy was put back in its place
    except FileNotFoundError:
        recovered = False
    except OSError:
        return None
    if recovered:
        return _("Your settings file was damaged, so its last good copy was used. The damaged "
                 "file is kept as {path}.").format(path=damaged)
    return _("Your settings file was damaged and there was no good copy, so these are the "
             "defaults. The damaged file is kept as {path}.").format(path=damaged)


def _from_dict(raw: dict) -> Settings:
    known = {f.name for f in fields(Settings)}
    data = {k: v for k, v in raw.items() if k in known}
    try:
        return Settings(**data).normalized()
    except (TypeError, ValueError, OverflowError):
        pass
    # One damaged value (a hand edit, a half-written file) costs only that setting, not all
    # of them: the next Apply would otherwise save the defaults over the user's choices.
    good: dict = {}
    for k, v in data.items():
        try:
            Settings(**{**good, k: v}).normalized()
        except (TypeError, ValueError, OverflowError):
            continue
        good[k] = v
    return Settings(**good).normalized()


# Choices a newer version may have more of. A value this version doesn't know reads as the
# setting's default (see normalized), and while the user leaves it at that default, save()
# writes the newer version's value back, so going back to an older version and forward
# again doesn't lose it.
CHOICE_KEYS = ("scheme", "glass_quality", "panel_style", "accent", "cursor_theme", "cursor_size", *LOCK_CHOICES)


def _keep_newer(out: dict, before: dict) -> dict:
    """`out` (what this version saves) with what `before` (the file on disk) holds that
    this version doesn't know: settings added by a newer version, and their new choices."""
    known = {f.name for f in fields(Settings)}
    for k, v in before.items():
        if k not in known:
            out[k] = v
    for k in CHOICE_KEYS:
        if k not in before:
            continue
        raw, default = before[k], getattr(Settings, k)
        try:
            read_as = getattr(Settings(**{k: raw}).normalized(), k)
        except (TypeError, ValueError, OverflowError):
            continue
        if isinstance(raw, (str, int)) and not isinstance(raw, bool) and raw != default and \
                read_as == default and out.get(k) == default:
            out[k] = raw
    for k, names, subkeys in (("parts", PARTS, PART_KEYS), ("motion", MOTION_EVENTS, ("preset", "intensity", "speed"))):
        old = before.get(k)
        if not isinstance(old, dict):
            continue
        new = out.setdefault(k, {})
        for name, sub in old.items():
            if name not in names:
                new[name] = sub             # a part or an event this version doesn't have
                continue
            if not isinstance(sub, dict):
                continue
            mine = new.get(name, {})
            extra = {sk: sv for sk, sv in sub.items() if sk not in subkeys}
            if k == "motion" and "preset" in sub and "preset" not in mine and \
                    sub["preset"] not in MOTION_PRESETS[name]:
                extra["preset"] = sub["preset"]   # a newer animation, still unchosen here
            if extra:
                new[name] = {**mine, **extra}
    return out


def _write(path: Path, data: bytes) -> None:
    """Write via a fresh, exclusively created temp file (a planted symlink can't redirect
    the write), private, flushed to disk before and after the rename: a power cut must
    never leave an empty settings file."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        dfd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(dfd)
    except OSError:
        pass
    finally:
        os.close(dfd)


def save(s: Settings, path: Path | None = None, *, backup: bool = True) -> Path:
    """`backup`: keep the file as it was as settings.json.bak. False while an Apply runs or
    after it stopped: the file then holds a look that isn't applied yet (or failed), and
    .bak must stay the last one that was."""
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _locked(path):
        try:
            before = path.read_bytes()
            old = _parse(before)
        except (OSError, ValueError):
            before, old = None, {}
        out = _keep_newer(asdict(s.normalized()), old)
        if before is not None and backup:
            # The file as it was, good, kept for the day settings.json itself is found damaged.
            _write(_sibling(path, ".bak"), before)
        _write(path, json.dumps(out, indent=2).encode("utf-8") + b"\n")
    return path


# ---- feature stream "looks": the look before the last Apply ---------------------------
# Before each Apply that changes the look, the look applied until then is kept as
# settings.previous.json, so About and restore can go back one Apply (and forward again:
# going back is an Apply too, which keeps the look it replaced). Written like
# settings.json (private, atomic), and never touches settings.json, .bak or .damaged.
PREVIOUS_MAX = 256 * 1024


class Previous(NamedTuple):
    settings: Settings
    applied_at: float     # when that look was applied (seconds since the epoch), 0 if not known
    forward: bool         # True: it is the look the user went back from


def previous_path(path: Path | None = None) -> Path:
    return (path or settings_path()).with_name("settings.previous.json")


def save_previous(s: Settings, applied_at: float, forward: bool = False, path: Path | None = None) -> Path:
    out = previous_path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "applied_at": float(applied_at) if math.isfinite(applied_at) else 0.0,
            "forward": bool(forward), "settings": asdict(s.normalized())}
    _write(out, json.dumps(data, indent=2).encode("utf-8") + b"\n")
    return out


def load_previous(path: Path | None = None) -> Previous | None:
    """The look before the last Apply, or None when there is none (or it can't be read)."""
    p = previous_path(path)
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > PREVIOUS_MAX:
            return None
        data = _parse(p.read_bytes())
    except (OSError, ValueError, RecursionError):
        return None
    raw = data.get("settings")
    if not isinstance(raw, dict):
        return None
    when = data.get("applied_at")
    when = float(when) if isinstance(when, (int, float)) and not isinstance(when, bool) and \
        math.isfinite(float(when)) and when > 0 else 0.0
    return Previous(_from_dict(raw), when, data.get("forward") is True)
