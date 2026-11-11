"""The bridge between the QML customizer and the engine.

Backend owns the Settings being edited, turns them into Tokens on every
change (so the preview follows the slider without a round trip to disk) and
runs everything slow (target detection, planning, apply, revert) on worker
threads so the window never stalls.
"""

from __future__ import annotations

import ast
import configparser
import json
import os
import re
import secrets
import stat
import time
from collections.abc import Callable
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QFileSystemWatcher, QObject, QProcess, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QIcon

from .. import APP_ID, cursors, distro, login_screen, palette
from .. import settings as settings_mod
from . import changes as changes_mod
from . import looks as looks_mod
from . import wallcolour
from ..color import Color
from ..env import Env
from .. import i18n
from ..i18n import _, N_, gettext as tr
from ..settings import GNOME_ACCENTS, PRESETS, Settings

GROUP_ORDER = (N_("Desktop"), N_("Panel"), N_("Apps"), N_("Terminal"), N_("My apps"))   # also the groups the targets are in

# A detection detail that holds one command that installs the missing part.
_INSTALL_CMD = re.compile(r"\b(?:sudo \S+ install|flatpak install|pacman -S)\b")


def _join_names(names: list[str]) -> str:
    """"A", "A and B", "A, B and C", in the language of the app."""
    if len(names) == 1:
        return names[0]
    return _("{start} and {last}").format(start=", ".join(names[:-1]), last=names[-1])


def _group_rank(group: str) -> tuple[int, str]:
    return (GROUP_ORDER.index(group) if group in GROUP_ORDER else 99, group)


def _missing_text(t: dict) -> dict:
    """For a part that is not installed: a calm one-line `reason`, or an `install` hint when
    a single command fixes it. "Dash to Panel is not installed (pkg)" reads "Not installed
    (pkg)" under its name. Both are "" for an installed part."""
    if t["available"]:
        return {"reason": "", "install": ""}
    detail = (t.get("detail") or "").strip()
    if _INSTALL_CMD.search(detail):
        return {"reason": "", "install": detail}
    lead = _("{name} is not installed").format(name=t["name"])
    if not detail or detail == lead:
        return {"reason": _("Not installed"), "install": ""}
    if detail.startswith(lead + " "):
        return {"reason": _("Not installed") + detail[len(lead):], "install": ""}
    return {"reason": detail, "install": ""}

# The windows the preview opens, so their dock icons get a "running" dot.
RUNNING_APPS = ("org.gnome.Nautilus", "org.gnome.Ptyxis")

DOCK_EXTENSIONS = ("dash-to-dock@micxgx.gmail.com", "ubuntu-dock@ubuntu.com")
MENU_EXTENSIONS = ("arcmenu@arcmenu.com", "spawn@djshiye.github.io")
DASH_TO_PANEL = "dash-to-panel@jderose9.github.com"
EXTENSION_NAMES = {"dash-to-dock@micxgx.gmail.com": "Dash to Dock", "ubuntu-dock@ubuntu.com": "Ubuntu Dock",
                   "arcmenu@arcmenu.com": "ArcMenu", "spawn@djshiye.github.io": "Spawn"}
FALLBACK_DOCK = ("org.gnome.Nautilus.desktop", "org.gnome.Ptyxis.desktop")


def _has_battery(root: Path) -> bool:
    """A system battery, not a wireless mouse's or a headset's (their scope is "Device")."""
    try:
        for d in root.iterdir():
            try:
                kind = (d / "type").read_text().strip()
                scope = (d / "scope").read_text().strip() if (d / "scope").exists() else ""
            except OSError:
                continue
            if kind == "Battery" and scope != "Device":
                return True
    except OSError:
        pass
    return False


def _average_luma(path: str) -> float:
    """The wallpaper's mean linear luminance, decoded small so it costs a few milliseconds."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QImageReader
    r = QImageReader(path)
    r.setScaledSize(QSize(24, 24))
    img = r.read()
    if img.isNull():
        return 0.2

    def lin(v: int) -> float:
        c = v / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    total = n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            total += 0.2126 * lin(c.red()) + 0.7152 * lin(c.green()) + 0.0722 * lin(c.blue())
            n += 1
    return round(total / n, 4) if n else 0.2


def qcolor(c: Color) -> QColor:
    return QColor.fromRgbF(c.r, c.g, c.b, c.a)


def _qvalue(v: Any) -> Any:
    if isinstance(v, Color):
        return qcolor(v)
    if isinstance(v, dict):
        return {k: _qvalue(x) for k, x in v.items()}
    return v


def tokens_map(t: palette.Tokens) -> dict[str, Any]:
    """Tokens as QML sees them: colours become QColor, the rest stays as is."""
    return {k: _qvalue(v) for k, v in t.__dict__.items()}


class _Task(QThread):
    """Runs one function off the GUI thread; `report(fraction, text)` feeds progress."""

    progressed = Signal(float, str)
    finishedWith = Signal(object)

    def __init__(self, fn: Callable[[Callable[[float, str], None]], Any], parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            out = self._fn(lambda f, text: self.progressed.emit(float(f), str(text)))
        except Exception as e:  # surfaced to the user instead of dying silently in a thread
            out = e
        self.finishedWith.emit(out)


def _parse_strv(text: str | None) -> list[str]:
    if not text:
        return []
    text = text.strip()
    if text.startswith("@as"):
        text = text[3:].strip()
    try:
        v = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return [str(x) for x in v] if isinstance(v, list) else []


def _desktop_entry(env: Env, desktop_id: str) -> tuple[str, str] | None:
    """(name, icon) from an installed .desktop file, searched like the Shell does."""
    dirs = [env.data / "applications", env.data / "flatpak/exports/share/applications",
            Path("/var/lib/flatpak/exports/share/applications")]
    dirs += [Path(d) / "applications" for d in
             (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
    stem = desktop_id.removesuffix(".desktop")
    for d in dirs:
        p = d / desktop_id
        if not p.is_file():
            continue
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read(p, encoding="utf-8")
            sec = cp["Desktop Entry"]
        except (configparser.Error, KeyError, OSError, UnicodeDecodeError):
            continue
        return sec.get("Name", stem), sec.get("Icon", stem)
    return None


def _app_dirs(env: Env) -> list[Path]:
    """Where .desktop files live, in the order the Shell looks (the first one found wins)."""
    dirs = [env.data / "applications", env.data / "flatpak/exports/share/applications",
            Path("/var/lib/flatpak/exports/share/applications")]
    dirs += [Path(d) / "applications" for d in
             (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if d]
    return dirs


def installed_apps(env: Env) -> list[dict]:
    """Apps people can open (their .desktop files, without hidden ones), sorted by name:
    {"id": desktop id, "name", "icon": the Icon= value, "ids": the ids a window of the app
    carries that the extension matches (the desktop id without ".desktop", and its
    StartupWMClass when that differs)}. Reads files: call it off the UI thread."""
    seen: set[str] = set()
    out: list[dict] = []
    for d in _app_dirs(env):
        try:
            files = sorted(d.glob("*.desktop"))
        except OSError:
            continue
        for p in files:
            if p.name in seen:
                continue
            seen.add(p.name)       # hidden or broken here hides it in the dirs after, as in the Shell
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(p, encoding="utf-8")
                sec = cp["Desktop Entry"]
            except (configparser.Error, KeyError, OSError, UnicodeDecodeError):
                continue
            if sec.get("Type", "Application") != "Application" or \
                    sec.get("NoDisplay", "").lower() == "true" or sec.get("Hidden", "").lower() == "true":
                continue
            stem = p.name.removesuffix(".desktop")
            ids = [stem]
            wm = (sec.get("StartupWMClass") or "").strip()
            if wm and wm != stem:
                ids.append(wm)
            ids = settings_mod.clean_app_ids(ids)
            if not ids:
                continue
            name = ""
            lang = i18n.language()
            for code in ([lang, lang.split("_")[0]] if lang else []):
                name = (sec.get(f"Name[{code}]") or "").strip()    # the app's name in our language
                if name:
                    break
            out.append({"id": p.name, "name": name or (sec.get("Name") or stem).strip() or stem,
                        "icon": (sec.get("Icon") or "").strip(), "ids": ids})
    out.sort(key=lambda a: (a["name"].casefold(), a["id"]))
    return out


# Saved the moment it is switched (removing the package reads it), so never "not applied yet".
_SAVED_AT_ONCE = ("undo_on_remove",)
# Bookkeeping that follows other settings (the wallpaper match): never a change of its own.
_BOOKKEEPING = ("tint_own", "accent_own", "wallpaper_match")


def _effective(s: Settings, has_dash_to_panel: bool = True) -> dict:
    """What a Settings really does, so a switch flipped off and on again, or a motion picked and
    then set back to its default, doesn't count as an unapplied change. "Start on the desktop"
    not chosen yet (None) is what Apply decides for this desktop."""
    d = asdict(s)
    d["targets"] = sorted(k for k, v in s.targets.items() if v != settings_mod.target_default(k))
    d["motion"] = {ev: s.motion_for(ev) for ev in settings_mod.MOTION_EVENTS}
    d["start_on_desktop"] = s.start_on_desktop_for(has_dash_to_panel)
    for k in (*_SAVED_AT_ONCE, *_BOOKKEEPING):
        d.pop(k, None)
    return d


def _weather_state(env: Env) -> str:
    """Whether GNOME's own weather (the one the lock screen shows) has anything to say:
    "ready", "no-app" (GNOME Weather isn't installed) or "no-place" (no place chosen in it).
    The Shell's weather needs the Weather app, and either places from it or automatic
    location with Location Services on."""
    try:
        if _desktop_entry(env, "org.gnome.Weather.desktop") is None:
            return "no-app"
        places = (env.gsettings_get("org.gnome.shell.weather", "locations") or "").strip()
        if places and places not in ("@av []", "[]"):
            return "ready"
        auto = (env.gsettings_get("org.gnome.shell.weather", "automatic-location") or "").strip() == "true"
        located = (env.gsettings_get("org.gnome.system.location", "enabled") or "").strip() == "true"
        return "ready" if auto and located else "no-place"
    except Exception:
        return "ready"     # can't tell: don't claim it won't work


class Backend(QObject):
    settingsChanged = Signal()
    tokensChanged = Signal()
    previewChanged = Signal()
    uiChanged = Signal()
    targetsChanged = Signal()
    # Only which parts are switched on: the Apps page keeps its rows (focus, open notes)
    # when one is flipped, instead of building every row again as targetsChanged does.
    targetStatesChanged = Signal()
    weatherChanged = Signal()
    wallpaperChanged = Signal()
    damageNoteChanged = Signal()
    wallpaperLumaChanged = Signal()
    busyChanged = Signal()
    progressChanged = Signal()
    savedChanged = Signal()
    planReady = Signal("QVariantList")
    applyFinished = Signal("QVariantList")
    revertFinished = Signal("QVariantList")
    failed = Signal(str)
    headerNoteChanged = Signal()
    loginGlassChanged = Signal()
    safeModeChanged = Signal()
    speedChanged = Signal()
    removingChanged = Signal()
    removeFinished = Signal(bool)
    noticed = Signal(str)       # a short "done" message for a toast
    restartNeededChanged = Signal()
    partialChanged = Signal()
    installedAppsChanged = Signal()     # the app picker's list (apps without glass)
    noGlassAppsChanged = Signal()       # the rows of apps without glass
    # Feature stream "looks": saved looks, the look before the last Apply, wallpaper colours.
    looksChanged = Signal()
    lookProblem = Signal(str)       # a look that couldn't be saved, read or written, in plain words
    previousChanged = Signal()
    wallpaperMatchChanged = Signal()

    def __init__(self, *, env: Env | None = None, engine_factory: Callable[[], Any] | None = None,
                 settings_path: Path | None = None, ui_dark: bool | None = None,
                 start: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        self._env = env or Env()
        self._engine_factory = engine_factory or self._default_engine
        self._engine: Any = None
        self._path = settings_path
        loaded = settings_mod.load_checked(settings_path)
        self._saved = loaded.settings
        # False: settings.json is damaged with no good copy, and _saved is only the defaults
        # standing in for it. Then nothing but an Apply that runs to the end writes
        # settings.json: a file of defaults would read as the user's own again, and the
        # watcher would apply it at the next dark/light switch, without anyone pressing Apply.
        self._usable = loaded.usable
        # First run: no saved settings and the welcome never dismissed. Asked once, at start.
        self._first_run = not self._settings_file().exists() and not self._welcome_marker().exists()
        self._s = replace(self._saved, targets=dict(self._saved.targets))
        # The last look that applied with no part failing: Undo goes back to it after an
        # Apply that only partly worked (_saved is then that partly applied look).
        self._good = self._saved
        # settings.json was damaged and set aside at load: said until the next save.
        self._damage = self._read_damage()
        self._partial: list[dict] = []     # the results of an Apply where some parts failed
        self._applying: Settings | None = None     # the look an Apply in progress writes
        self._ui_override = ui_dark
        self._system_dark = self._env.prefers_dark() if ui_dark is None else ui_dark
        self._system_accent = self._env.system_accent()
        self._preview_dark = self._effective_dark()
        self._targets: list[dict] = []
        self._targets_ready = False
        self._busy = ""
        self._progress = 0.0
        self._progress_text = ""
        self._has_backup = False
        self._task: _Task | None = None
        self._task_done: Callable[[Any], None] = lambda out: None
        self._task_busy = False
        self._monitor: QProcess | None = None
        # Apply, Restore or Review asked for while the app was still busy in the
        # background (checking the system after a start or an Apply): runs right after.
        self._pending_action: str | None = None
        # Set when the last Apply or Restore changed the header bars, so the card can
        # offer to restart Files (it keeps running with the old style sheet).
        self._header_note = ""
        # Glass on the login screen (opt in, needs the password): off, on, undone, busy
        # or unavailable, and a sentence about the last change.
        self._login_proc: QProcess | None = None
        self._login_note = ""
        self._login_failed = False     # the last login screen step ended in an error (not a cancel)
        self._login_state = self._read_login_state()
        # Removing the app (Restore original, then dnf remove through pkexec).
        self._remove_proc: QProcess | None = None
        self._removing = False
        # The package this app came from: asked of the package manager (up to 10 s) on the
        # first system check, off the UI thread, not before the window shows. None: not known yet.
        self._remove_package: str | None = None
        self._terminal_pal = ""
        self._motion_state = {"animations": True, "dtpHover": False}
        self._has_dock = False      # Dash to Dock or Ubuntu Dock switched on (the preview draws it)
        self._has_menu = False      # ArcMenu or Spawn switched on
        self._has_dtp = False       # Dash to Panel switched on
        self._problem = ("", "", "")       # what keeps the glass from running (see glassProblem)
        self._leftovers: list = []         # an old source install's files that override the package
        self._dock_name = self._menu_name = ""     # which of them, for the welcome's "Found on this PC"
        # Applied, but the glass (or a Shell part waiting for it) only starts after a restart.
        self._restart_needed = False
        # "Apply and lock" on the Lock and login page: lock once this Apply finishes well.
        self._lock_after_apply = False
        self._lost: list[str] = []         # targets whose applied files something else replaced
        # Whether the glass extension is running. The desktop only changes on Apply:
        # moving a slider changes the preview in this window, never the desktop.
        self._glass_live = False
        # Safe mode: the extension turned the glass off after it kept failing.
        self._safe = self._read_safe_mode()
        self._safe_timer = QTimer(self)
        self._safe_timer.setInterval(3000)
        self._safe_timer.timeout.connect(self._poll_safe_mode)
        # Speed: what the extension reports, and the check the user can ask for.
        self._speed_status: dict = {}
        self._speed_state = "idle"
        self._speed_result: dict = {}
        self._speed_id = ""
        self._speed_deadline = 0.0
        self._speed_poll = QTimer(self)
        self._speed_poll.setInterval(500)
        self._speed_poll.timeout.connect(self._poll_speed)
        self._speed_watch = QFileSystemWatcher(self)
        self._speed_watch.fileChanged.connect(self._on_speed_file)
        self._speed_watch.directoryChanged.connect(self._on_speed_file)
        # Apps without glass: the installed apps, read off the UI thread when first wanted.
        self._apps: list[dict] = []
        self._apps_state = "idle"           # idle, loading or ready
        self._apps_task: _Task | None = None
        self.settingsChanged.connect(self.noGlassAppsChanged)
        self.installedAppsChanged.connect(self.noGlassAppsChanged)
        # GNOME's two wallpapers (picture-uri for light, picture-uri-dark for dark), as file URLs.
        self._wallpapers = self._read_wallpapers()
        self._wall_monitor: QProcess | None = None
        self._lumas: dict[str, float] = {}       # wallpaper URL -> how bright it is, worked out off the UI thread
        self._luma_tasks: dict[str, _Task] = {}
        self._power_supply = Path("/sys/class/power_supply")
        self._dock = self._find_dock()
        self._init_looks()
        self._rebuild_tokens()
        self.targetsChanged.connect(self.targetStatesChanged)
        # The preview's Light/Dark pill and GNOME's own style pick the wallpaper.
        self.savedChanged.connect(self._refresh_damage)
        self.previewChanged.connect(self.wallpaperChanged)
        self.uiChanged.connect(self.wallpaperChanged)
        self.wallpaperChanged.connect(self.wallpaperLumaChanged)
        if start:
            self.refreshTargets()
            self._watch_scheme()
            self._watch_wallpaper()
            self._safe_timer.start()
            self._start_speed_watch()

    # ---- damaged settings ----------------------------------------------------------
    def _read_damage(self) -> str:
        # settings.damage_notice is newer than some engines this app runs with.
        notice = getattr(settings_mod, "damage_notice", lambda path=None: None)
        try:
            return notice(self._path) or ""
        except Exception:  # noqa: BLE001 (a note that can't be read is no note)
            return ""

    @Slot()
    def _refresh_damage(self) -> None:
        note = self._read_damage()
        if note != self._damage:
            self._damage = note
            self.damageNoteChanged.emit()

    @Property(str, notify=damageNoteChanged)
    def damageNote(self) -> str:
        """One plain line when settings.json was damaged and set aside, or ""."""
        return self._damage

    # ---- safe mode ---------------------------------------------------------------
    def _read_safe_mode(self) -> dict:
        """The extension's safe mode state, or {} when the glass runs normally. Only small,
        well-formed files from this user count."""
        path = self._env.cache / "liquid-glass/safe-mode.json"
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024:
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict) or data.get("tripped") is not True:
            return {}
        reason = data.get("reason") if data.get("reason") in ("errors", "restarts", "start") else "errors"
        return {"reason": reason, "resetId": str(data.get("resetId", ""))[:16]}

    def _poll_safe_mode(self) -> None:
        state = self._read_safe_mode()
        if state != self._safe:
            self._safe = state
            self.safeModeChanged.emit()

    @Property(bool, notify=safeModeChanged)
    def safeMode(self) -> bool:
        return bool(self._safe)

    @Property(str, notify=safeModeChanged)
    def safeModeNote(self) -> str:
        reason = self._safe.get("reason", "")
        if reason == "restarts":
            return _("Glass is paused because GNOME Shell restarted twice right after starting it. Your desktop works as usual.")
        if reason == "start":
            return _("Glass is paused because it could not start. Your desktop works as usual.")
        return _("Glass is paused because it hit errors. Your desktop works as usual.")

    @Slot()
    def resumeGlass(self) -> None:
        """Ask the extension to turn the glass back on (it watches this file)."""
        d = self._env.config / "liquid-glass"
        try:
            d.mkdir(parents=True, exist_ok=True)
            tmp = d / ".safe-mode-reset.json.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"id": secrets.token_hex(8)}, f)
            os.replace(tmp, d / "safe-mode-reset.json")
        except OSError:
            return
        QTimer.singleShot(800, self, self._poll_safe_mode)   # dropped if this object goes first

    # ---- helpers -----------------------------------------------------------------
    @staticmethod
    def _default_engine() -> Any:
        from ..engine import Engine
        return Engine()

    def _engine_obj(self) -> Any:
        if self._engine is None:
            self._engine = self._engine_factory()
        return self._engine

    def _effective_dark(self) -> bool:
        if self._s.scheme == "auto":
            return self._system_dark
        return self._s.scheme == "dark"

    @staticmethod
    def _wallpaper_url(value: str | None) -> str:
        """A picture-uri value as gsettings prints it, as a file URL ("" for none or no file)."""
        v = (value or "").strip().strip("'")
        if not v.startswith("file://"):
            return ""
        from urllib.parse import unquote, urlparse
        p = Path(unquote(urlparse(v).path))
        return QUrl.fromLocalFile(str(p)).toString() if p.is_file() else ""

    def _read_wallpapers(self) -> dict[str, str]:
        out = {}
        for mode, key in (("light", "picture-uri"), ("dark", "picture-uri-dark")):
            try:
                out[mode] = self._wallpaper_url(self._env.gsettings_get("org.gnome.desktop.background", key))
            except Exception:
                out[mode] = ""
        return out

    def _wallpaper_for(self, dark: bool) -> str:
        """GNOME shows picture-uri-dark in dark style; without one, picture-uri."""
        first, other = ("dark", "light") if dark else ("light", "dark")
        return self._wallpapers.get(first) or self._wallpapers.get(other) or ""

    def _watch_wallpaper(self) -> None:
        """Follow a wallpaper change while the app is open."""
        if not self._env.which("gsettings"):
            return
        p = QProcess(self)
        p.readyReadStandardOutput.connect(self._on_wallpaper_output)
        p.start("gsettings", ["monitor", "org.gnome.desktop.background"])
        self._wall_monitor = p

    def _on_wallpaper_output(self) -> None:
        if self._wall_monitor is not None:
            self._wallpaper_lines(bytes(self._wall_monitor.readAllStandardOutput()).decode(errors="replace"))

    def _wallpaper_lines(self, text: str) -> None:
        """`gsettings monitor` lines ("picture-uri-dark: 'file:///…'"): take the new pictures."""
        keys = {"picture-uri": "light", "picture-uri-dark": "dark"}
        changed = False
        for line in text.splitlines():
            key, sep, value = line.partition(":")
            mode = keys.get(key.strip())
            if not sep or mode is None:
                continue
            url = self._wallpaper_url(value)
            if url != self._wallpapers.get(mode):
                self._wallpapers[mode] = url
                changed = True
        if changed:
            self.wallpaperChanged.emit()

    def _find_dock(self) -> list[dict]:
        """The real dock: installed favourites, then the apps the preview shows running."""
        try:
            favs = _parse_strv(self._env.gsettings_get("org.gnome.shell", "favorite-apps"))
        except Exception:
            favs = []
        ids = [d for d in favs if _desktop_entry(self._env, d)] or list(FALLBACK_DOCK)
        for app in RUNNING_APPS + (APP_ID,):
            if f"{app}.desktop" not in ids:
                ids.append(f"{app}.desktop")
        out = []
        for did in ids[:10]:
            stem = did.removesuffix(".desktop")
            name, icon = _desktop_entry(self._env, did) or (stem.split(".")[-1], stem)
            if stem == APP_ID:
                name, url = "Fedora Glass", self._own_icon_url()
            elif icon.startswith("/"):
                url = QUrl.fromLocalFile(icon).toString() if Path(icon).is_file() else ""
            else:
                url = f"image://lgicon/{icon}" if QIcon.hasThemeIcon(icon) else ""
            out.append({"id": did, "name": name, "icon": url,
                        "running": stem in RUNNING_APPS or stem == APP_ID})
        return out

    @staticmethod
    def _own_icon_url() -> str:
        from .app import find_icon
        p = find_icon()
        return QUrl.fromLocalFile(str(p)).toString() if p else ""

    def _rebuild_tokens(self) -> None:
        s = self._s
        dark_t = palette.build(s, dark=True, system_accent=self._system_accent)
        light_t = palette.build(s, dark=False, system_accent=self._system_accent)
        auto = replace(s, opacity=None, blur=None, terminal_opacity=None)
        a = palette.build(auto, dark=self._preview_dark, system_accent=self._system_accent)
        auto_values = {"opacity": round(a.chrome.a, 2), "blur": a.blur_radius,
                       "terminal_opacity": a.terminal_opacity}
        # Most settings (the lock screen, motion, the pointer...) don't touch the colours:
        # then nothing that reads the tokens (the whole preview) has to be worked out again.
        key = (dark_t, light_t, auto_values, self._preview_dark)
        if key == getattr(self, "_tokens_key", None):
            return
        self._tokens_key = key
        self._dark_t, self._light_t, self._auto = dark_t, light_t, auto_values
        self._maps = (tokens_map(dark_t), tokens_map(light_t))
        self.tokensChanged.emit()

    def _changed(self) -> None:
        self._rebuild_tokens()
        self.settingsChanged.emit()

    def _set(self, name: str, value: Any) -> None:
        if getattr(self._s, name) == value:
            return
        extra = self._hand_picked(name)
        try:
            s = replace(self._s, **{name: value, **extra}).normalized()
        except (TypeError, ValueError):
            return
        if s == self._s:
            return
        self._s = s
        if name == "scheme" and self._effective_dark() != self._preview_dark:
            self._preview_dark = self._effective_dark()   # show the style just picked
            self.previewChanged.emit()
        self._changed()
        if name == "scheme":
            self._match_wallpaper()     # light and dark can have their own pictures

    def _watch_scheme(self) -> None:
        """Follow GNOME's dark/light switch while the app is open."""
        if self._ui_override is not None or not self._env.which("gsettings"):
            return
        p = QProcess(self)
        p.readyReadStandardOutput.connect(self._on_scheme_output)
        p.start("gsettings", ["monitor", "org.gnome.desktop.interface", "color-scheme"])
        self._monitor = p
        app = QGuiApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def _on_scheme_output(self) -> None:
        if self._monitor is None:
            return
        text = bytes(self._monitor.readAllStandardOutput()).decode(errors="replace")
        if "color-scheme" not in text:
            return
        dark = "dark" in text.splitlines()[-1]
        if dark != self._system_dark:
            preview_followed = self._preview_dark == self._effective_dark()
            self._system_dark = dark
            if preview_followed:
                self._preview_dark = self._effective_dark()
                self.previewChanged.emit()
                self._rebuild_tokens()
            self.uiChanged.emit()

    @Slot()
    def shutdown(self) -> None:
        self._speed_poll.stop()
        self._speed_watch.removePaths(self._speed_watch.files() + self._speed_watch.directories())
        if self._task is not None:
            self._task.wait(30000)    # let a running Apply or Restore finish first
        for name in ("_monitor", "_wall_monitor"):
            proc = getattr(self, name)
            if proc is not None:
                proc.kill()
                proc.waitForFinished(500)
                setattr(self, name, None)
        for t in [*self._luma_tasks.values(), getattr(self, "_weather_task", None), self._apps_task]:
            if t is not None:
                t.wait(2000)

    # ---- settings properties ---------------------------------------------------
    def _p(name: str, typ: type, none: Any = None, notify=settingsChanged):  # noqa: N805
        def get(self):
            v = getattr(self._s, name)
            return none if v is None else v

        def put(self, v):
            if none is not None and v is not None and v < 0:
                v = None
            elif typ is int and v is not None:
                v = int(round(v))
            self._set(name, v)
        return Property(typ, get, put, notify=notify)

    frost = _p("frost", float)
    scheme = _p("scheme", str)
    accent = _p("accent", str)
    tint = _p("tint", str)
    tintStrength = _p("tint_strength", float)
    radius = _p("radius", int)
    highlight = _p("highlight", float)
    opacity = _p("opacity", float, -1.0)          # -1 means "follow the slider"
    blur = _p("blur", int, -1)
    reduceTransparency = _p("reduce_transparency", bool)
    panelStyle = _p("panel_style", str)
    panelMargin = _p("panel_margin", int)
    blurAppWindows = _p("blur_app_windows", bool)
    terminalOpacity = _p("terminal_opacity", float, -1.0)
    refraction = _p("refraction", float)
    dispersion = _p("dispersion", float)
    vibrancy = _p("vibrancy", float)
    bleed = _p("bleed", float)
    pointerLight = _p("pointer_light", float)
    liquidMotion = _p("liquid_motion", bool)
    menuGrow = _p("menu_grow", bool)
    glassPanel = _p("glass_panel", bool)
    glassMenus = _p("glass_menus", bool)
    glassOverview = _p("glass_overview", bool)
    glassQuality = _p("glass_quality", str)
    glassSeeWindows = _p("glass_see_windows", bool)
    headerHeight = _p("header_height", int)
    headerOpacity = _p("header_opacity", float, -1.0)   # -1 means "same glass as the window"
    terminalColors = _p("terminal_colors", bool)
    terminalFollowsStyle = _p("terminal_follows_style", bool)
    qtGnomeTitlebars = _p("qt_gnome_titlebars", bool)
    lockGlass = _p("lock_glass", bool)
    lockBlur = _p("lock_blur", int)
    lockDim = _p("lock_dim", float)
    lockTint = _p("lock_tint", float)
    lockCard = _p("lock_card", bool)
    lockClock = _p("lock_clock", str)
    lockClockPosition = _p("lock_clock_position", str)
    lockSlide = _p("lock_slide", str)
    lockSlideMs = _p("lock_slide_ms", int)
    lockBounce = _p("lock_bounce", float)
    lockWidgetBattery = _p("lock_widget_battery", bool)
    lockWidgetWeather = _p("lock_widget_weather", bool)
    lockWeatherPlace = _p("lock_weather_place", bool)
    lockGreeting = _p("lock_greeting", bool)
    lockMessage = _p("lock_message", str)
    lockWidgetStyle = _p("lock_widget_style", str)
    lockHideNotifications = _p("lock_hide_notifications", bool)
    cursorTheme = _p("cursor_theme", str)
    cursorSize = _p("cursor_size", int)
    def _get_start_on_desktop(self) -> bool:
        # Not chosen yet: as Apply will decide it for this desktop (Settings.start_on_desktop_for).
        return self._s.start_on_desktop_for(self.hasDashToPanel)

    def _set_start_on_desktop(self, v: bool) -> None:
        self._set("start_on_desktop", bool(v))

    startOnDesktop = Property(bool, _get_start_on_desktop, _set_start_on_desktop, notify=settingsChanged)
    overviewOff = _p("overview_off", bool)
    motionDtpHoverOff = _p("motion_dtp_hover_off", bool)
    hoverGlide = _p("hover_glide", bool)
    # ---- Shell features: lighter glass on battery, the Quick Settings switch ----
    lighterOnBattery = _p("lighter_on_battery", bool)
    quickToggle = _p("quick_toggle", bool)
    del _p

    # ---- animations ----------------------------------------------------------------
    # Per event (open, minimize, close, launch, hover): {"preset", "intensity", "speed"}.
    @Property("QVariantMap", notify=settingsChanged)
    def motion(self) -> dict:
        return {ev: self._s.motion_for(ev) for ev in settings_mod.MOTION_EVENTS}

    @Property("QVariantMap", constant=True)
    def motionPresets(self) -> dict:
        return {ev: list(p) for ev, p in settings_mod.MOTION_PRESETS.items()}

    @Property("QVariantMap", constant=True)
    def motionDefaults(self) -> dict:
        return {ev: dict(v) for ev, v in settings_mod.MOTION_DEFAULTS.items()}

    @Slot(str, str, "QVariant")
    def setMotion(self, event: str, key: str, value: Any) -> None:
        if event not in settings_mod.MOTION_EVENTS or key not in ("preset", "intensity", "speed"):
            return
        motion = {ev: dict(v) for ev, v in self._s.motion.items()}
        motion.setdefault(event, {})[key] = value
        self._set("motion", settings_mod._clean_motion(motion))

    @Property("QVariantList", constant=True)
    def motionStyles(self) -> list[dict]:
        return [
            {"id": "off", "label": _("Off"), "tip": _("No animations: everything happens at once")},
            {"id": "calm", "label": _("Calm"), "tip": _("Quick, gentle zooms and fades. Nothing bounces.")},
            {"id": "gnome", "label": _("GNOME"), "tip": _("GNOME's own animations, as they come")},
            {"id": "lively", "label": _("Lively"), "tip": _("Springy windows, a genie into the taskbar and a bouncing app icon (the default)")},
            {"id": "playful", "label": _("Playful"), "tip": _("Bouncy, jelly-like and fun")},
        ]

    @Property(str, notify=settingsChanged)
    def motionStyle(self) -> str:
        """The motion style the animations match ("custom" when set one by one)."""
        return settings_mod.motion_style_of({ev: self._s.motion_for(ev) for ev in settings_mod.MOTION_EVENTS})

    @Slot(str)
    def setMotionStyle(self, name: str) -> None:
        style = settings_mod.MOTION_STYLES.get(name)
        if style is None:
            return
        motion = {}
        for ev, (preset, intensity) in style.items():
            speed = self._s.motion_for(ev)["speed"]
            motion[ev] = {"preset": preset, "intensity": intensity, "speed": speed}
        self._set("motion", settings_mod._clean_motion(motion))

    @Property(float, notify=settingsChanged)
    def motionSpeed(self) -> float:
        """One speed for every animation: the open animation's, which the slider sets for all."""
        return float(self._s.motion_for("open")["speed"])

    @motionSpeed.setter
    def motionSpeed(self, value: float) -> None:
        v = max(settings_mod.SPEED_MIN, min(settings_mod.SPEED_MAX, float(value)))
        motion = {ev: {**self._s.motion_for(ev), "speed": v} for ev in settings_mod.MOTION_EVENTS}
        self._set("motion", settings_mod._clean_motion(motion))

    @Slot()
    def resetMotion(self) -> None:
        self._set("motion", {})

    @Property(bool, notify=settingsChanged)
    def motionIsDefault(self) -> bool:
        return all(self._s.motion_for(ev) == settings_mod.MOTION_DEFAULTS[ev] for ev in settings_mod.MOTION_EVENTS)

    @Property(bool, notify=targetsChanged)
    def systemAnimations(self) -> bool:
        """GNOME's Reduce animation is off (animations play)."""
        return bool(self._motion_state.get("animations", True))

    @Property(bool, notify=targetsChanged)
    def dtpHoverAnimates(self) -> bool:
        """Dash to Panel's own "Animate hovering app icons" is on, as the desktop has it now."""
        return bool(self._motion_state.get("dtpHover", False))

    # ---- per-part overrides ------------------------------------------------------
    # A part (panel, arcmenu, ...) can override tint, tint_strength, radius, frost, refraction,
    # bleed and reflections; a key it doesn't set follows the global setting.
    @Property("QStringList", constant=True)
    def partNames(self) -> list[str]:
        return list(settings_mod.PARTS)

    @Property("QVariantMap", notify=settingsChanged)
    def parts(self) -> dict:
        return {k: dict(v) for k, v in self._s.parts.items()}

    @Slot(str, str, result=bool)
    def hasPart(self, part: str, key: str) -> bool:
        return key in self._s.parts.get(part, {})

    @Slot(str, str, result="QVariant")
    def partValue(self, part: str, key: str) -> Any:
        """The part's own value, or the global one when it follows the global setting."""
        own = self._s.parts.get(part, {})
        if key in own:
            return own[key]
        return getattr(self._s, "highlight" if key == "reflections" else key)

    @Slot(str, str, "QVariant")
    def setPart(self, part: str, key: str, value: Any) -> None:
        if part not in settings_mod.PARTS or key not in settings_mod.PART_KEYS:
            return
        parts = {p: dict(v) for p, v in self._s.parts.items()}
        parts.setdefault(part, {})[key] = value
        self._set_parts(parts)

    @Slot(str, str)
    def clearPart(self, part: str, key: str) -> None:
        parts = {p: dict(v) for p, v in self._s.parts.items()}
        parts.get(part, {}).pop(key, None)
        self._set_parts(parts)

    # ---- speed -------------------------------------------------------------------
    def _speed_status_path(self) -> Path:
        return self._env.cache / "liquid-glass/speed.json"

    def _read_speed_status(self) -> dict:
        """The extension's status file, read defensively: anything odd counts as no status."""
        path = self._speed_status_path()
        try:
            st = os.lstat(path)
            if not stat.S_ISREG(st.st_mode) or st.st_size > 64 * 1024:
                return {}
            with open(path, "rb") as f:
                data = json.loads(f.read(64 * 1024 + 1))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _check_of(self, status: dict) -> dict:
        c = status.get("check")
        return c if isinstance(c, dict) else {}

    def _start_speed_watch(self) -> None:
        self._speed_status = self._read_speed_status()
        # The last finished check shows again when the app opens, also when a later
        # check stopped short ('lastDone' keeps the finished one).
        c = self._check_of(self._speed_status)
        if c.get("state") != "done" and isinstance(self._speed_status.get("lastDone"), dict):
            c = self._speed_status["lastDone"]
        if c.get("state") == "done" and isinstance(c.get("phases"), list) and c["phases"]:
            self._speed_result = c
            self._speed_state = "done"
        self._rewatch_speed()
        self.speedChanged.emit()

    def _rewatch_speed(self) -> None:
        path = self._speed_status_path()
        if str(path.parent) not in self._speed_watch.directories() and path.parent.is_dir():
            self._speed_watch.addPath(str(path.parent))
        if str(path) not in self._speed_watch.files() and path.exists():
            self._speed_watch.addPath(str(path))     # an atomic replace drops it, so add it again

    def _on_speed_file(self, _path: str = "") -> None:
        self._rewatch_speed()
        self._speed_status = self._read_speed_status()
        self.speedChanged.emit()

    def _poll_speed(self) -> None:
        status = self._read_speed_status()
        self._speed_status = status
        c = self._check_of(status)
        if c.get("id") == self._speed_id and c.get("state") in ("done", "failed"):
            self._speed_poll.stop()
            self._speed_result = c
            self._speed_state = c["state"]
        elif time.monotonic() > self._speed_deadline:
            self._speed_poll.stop()
            self._speed_result = {}
            self._speed_state = "noanswer"
        self.speedChanged.emit()

    @Slot()
    def checkSpeed(self) -> None:
        if self._speed_state == "running":
            return
        self._speed_result = {}
        if not self._glass_live:
            self._speed_state = "noanswer"
            self.speedChanged.emit()
            return
        from ..engine import atomic_write
        self._speed_id = secrets.token_hex(8)
        try:
            atomic_write(self._env.config / "liquid-glass/speed-check.json",
                         json.dumps({"id": self._speed_id}).encode())
        except OSError:
            self._speed_state = "noanswer"
            self.speedChanged.emit()
            return
        self._speed_state = "running"
        self._speed_deadline = time.monotonic() + 45
        self._speed_poll.start()
        self.speedChanged.emit()

    @Slot(str)
    def useQuality(self, level: str) -> None:
        if level in settings_mod.GLASS_QUALITIES:
            self._set("glass_quality", level)

    def _get_speed_level(self) -> str:
        v = self._speed_status.get("level")
        return v if v in ("full", "lighter", "lightest") else ""

    def _get_speed_reason(self) -> str:
        v = self._speed_status.get("reason")
        return v if v in ("setting", "slow", "retry", "check", "battery") else ""

    def _get_speed_power(self) -> str:
        """Why the glass is lighter than set: "battery" (on battery) or "saver" (Power Saver
        is on), when the extension says so (speed.js); else ""."""
        v = self._speed_status.get("power")
        return v if self._get_speed_reason() == "battery" and v in ("battery", "saver") else ""

    def _get_speed_drag(self) -> str:
        """The last window drag the desktop timed (speed.js writes it at the end of a drag), in
        words: how smooth dragging really is on this PC, with no check to run. "" when none yet.
        Its times are the gaps between frames, so 1000 / median is the frame rate (never more
        than the screen's refresh rate)."""
        d = self._speed_status.get("drag")
        if not isinstance(d, dict):
            return ""
        try:
            median, p95 = float(d["median_ms"]), float(d["p95_ms"])
            hz, windows = float(d.get("refresh") or 60), int(d.get("windows") or 0)
        except (KeyError, TypeError, ValueError):
            return ""
        if not (0 < median < 10_000 and 0 < p95 < 10_000 and 1 < hz < 1000):
            return ""
        fps = min(hz, 1000 / median)
        smooth, uneven = p95 <= 1.5 * 1000 / hz, fps >= 0.6 * hz
        n = round(fps)
        if windows > 1:
            if smooth:
                return _("Last window drag with {windows} windows open: about {fps} frames a second, smooth.").format(windows=windows, fps=n)
            if uneven:
                return _("Last window drag with {windows} windows open: about {fps} frames a second, a little uneven.").format(windows=windows, fps=n)
            return _("Last window drag with {windows} windows open: about {fps} frames a second, slow.").format(windows=windows, fps=n)
        if smooth:
            return _("Last window drag: about {fps} frames a second, smooth.").format(fps=n)
        if uneven:
            return _("Last window drag: about {fps} frames a second, a little uneven.").format(fps=n)
        return _("Last window drag: about {fps} frames a second, slow.").format(fps=n)

    def _get_speed_state(self) -> str:
        return self._speed_state

    def _get_speed_result(self) -> dict:
        return dict(self._speed_result)

    speedLevel = Property(str, _get_speed_level, notify=speedChanged)
    speedReason = Property(str, _get_speed_reason, notify=speedChanged)
    speedPower = Property(str, _get_speed_power, notify=speedChanged)
    speedDrag = Property(str, _get_speed_drag, notify=speedChanged)
    speedState = Property(str, _get_speed_state, notify=speedChanged)
    speedResult = Property("QVariantMap", _get_speed_result, notify=speedChanged)

    @Slot(str)
    def resetPart(self, part: str) -> None:
        parts = {p: dict(v) for p, v in self._s.parts.items()}
        parts.pop(part, None)
        self._set_parts(parts)

    def _set_parts(self, parts: dict) -> None:
        self._set("parts", parts)

    @Property(bool, notify=targetsChanged)
    def glassLive(self) -> bool:
        return self._glass_live

    def _get_auto(self) -> dict:
        return dict(self._auto)

    autoValues = Property("QVariantMap", _get_auto, notify=tokensChanged)

    @Property(bool, notify=settingsChanged)
    def dirty(self) -> bool:
        dtp = self.hasDashToPanel
        return _effective(self._s, dtp) != _effective(self._saved.normalized(), dtp)

    @Property(int, notify=settingsChanged)
    def changeCount(self) -> int:
        """How many settings differ from the look applied last (the footer says "3 changes
        not applied yet"): as many as See changes lists, so the two never disagree."""
        return len(self._change_rows()) if self.dirty else 0

    @Property(str, notify=settingsChanged)
    def activePreset(self) -> str:
        for name, values in PRESETS.items():
            want = {"opacity": None, "blur": None, **values}
            if all(_close(getattr(self._s, k), v) for k, v in want.items()):
                return name
        return ""

    @Property("QStringList", constant=True)
    def presets(self) -> list[str]:
        return list(PRESETS)

    # The preset tiles, the ticks on the frost slider and the name beside it all come from
    # settings.PRESETS, so they can't disagree (Clear was 0.1 there and 0.25 in the window).
    @Property("QVariantMap", constant=True)
    def presetFrost(self) -> dict:
        return {name: float(v["frost"]) for name, v in PRESETS.items()}

    @Property("QVariantList", constant=True)
    def frostTicks(self) -> list[dict]:
        return [{"value": float(v["frost"]), "label": name} for name, v in PRESETS.items()]

    @Slot(float, result=str)
    def frostName(self, frost: float) -> str:
        """The preset whose frost is nearest (the one the slider sits closest to)."""
        return min(PRESETS, key=lambda name: (abs(PRESETS[name]["frost"] - frost), PRESETS[name]["frost"]))

    @Property("QVariantList", constant=True)
    def accents(self) -> list[dict]:
        return [{"id": k, "color": v, "label": changes_mod._accent_name(k)} for k, v in GNOME_ACCENTS.items()]

    @Property(str, constant=True)
    def systemAccent(self) -> str:
        return self._system_accent or "blue"

    @Slot(str)
    def applyPreset(self, name: str) -> None:
        if name not in PRESETS:
            return
        s = settings_mod.apply_preset(self._s, name)
        s.targets = dict(self._s.targets)
        if s != self._s:
            self._s = s
            self._changed()

    def _all_reset(self) -> Settings:
        """Every setting at its default but this PC's own choices: which apps get the look,
        what happens on removal, and the apps without glass (the list picked on this PC,
        kept like the apps that get the look; its card's Reset still empties it)."""
        return Settings(targets=dict(self._s.targets), undo_on_remove=self._s.undo_on_remove,
                        no_glass_apps=list(self._s.no_glass_apps))

    @Property(bool, notify=settingsChanged)
    def canResetAll(self) -> bool:
        """Whether Reset all would change anything (the apps picked stay, so not always
        when changedFromDefault lists something)."""
        dtp = self.hasDashToPanel
        return _effective(self._all_reset(), dtp) != _effective(self._s, dtp)

    @Slot()
    def resetDefaults(self) -> None:
        s = self._all_reset()
        if s != self._s:
            was_dark = self._effective_dark()
            self._s = s
            if self._effective_dark() != was_dark:
                self._preview_dark = self._effective_dark()
                self.previewChanged.emit()
            self._changed()

    # ---- defaults, one setting or one card at a time ------------------------------------
    # Every slider shows where its default is and every card can go back to its defaults,
    # so no change is a one-way street. Names are the Settings field names (snake_case).
    @Property("QVariantMap", constant=True)
    def defaults(self) -> dict:
        """Each setting's default by its Settings name; an "automatic" one (None) is -1, as
        the QML sliders mean it."""
        out = {}
        for f in fields(Settings):
            v = getattr(Settings(), f.name)
            if f.name in ("parts", "targets", "motion"):
                continue
            out[f.name] = -1 if v is None else v
        return out

    @Property("QStringList", notify=settingsChanged)
    def changedFromDefault(self) -> list[str]:
        """The settings (Settings names) that differ from their defaults; the app's choice
        of apps (targets) isn't a look setting and is never listed."""
        dtp = self.hasDashToPanel
        d, now = _effective(Settings(), dtp), _effective(self._s, dtp)
        return [f.name for f in fields(Settings) if f.name in now and f.name != "targets" and now[f.name] != d[f.name]]

    @Slot("QStringList")
    def resetSettings(self, names: list[str]) -> None:
        """Put these settings back to their defaults (Apply then uses them)."""
        known = {f.name for f in fields(Settings)} - {"targets", *_SAVED_AT_ONCE}
        values = {n: getattr(Settings(), n) for n in names if n in known}
        if not values:
            return
        s = replace(self._s, **values).normalized()
        if s == self._s:
            return
        was_dark = self._effective_dark()
        self._s = s
        if self._effective_dark() != was_dark:
            self._preview_dark = self._effective_dark()
            self.previewChanged.emit()
        self._changed()

    @Slot()
    def discardChanges(self) -> None:
        """Undo: back to the look applied last. After an Apply where some parts failed (nothing
        changed since), back to the last look that applied fully, to apply again."""
        back = self._saved if self.dirty or not self._partial else self._good
        self._s = replace(back, targets=dict(back.targets), undo_on_remove=self._saved.undo_on_remove)
        self._preview_dark = self._effective_dark()
        self.previewChanged.emit()
        self._changed()
        self.targetStatesChanged.emit()   # the app switches and the glass edges follow the saved state

    @Slot(str, result=bool)
    def isColor(self, value: str) -> bool:
        return settings_mod._is_hex(value)

    # ---- tokens -------------------------------------------------------------------
    def _get_tokens(self) -> dict:
        return self._maps[0] if self._preview_dark else self._maps[1]

    tokens = Property("QVariantMap", _get_tokens, notify=tokensChanged)

    def _get_terminal_palettes(self) -> dict:
        """The Ptyxis colours Fedora Glass writes (render/terminal.py), for the preview."""
        from ..render import terminal as rt
        out = {}
        for name, t in (("dark", self._dark_t), ("light", self._light_t)):
            p = rt.derive(t)
            out[name] = {"bg": qcolor(p.bg), "fg": qcolor(p.fg), "green": qcolor(p.ansi[2]),
                         "blue": qcolor(p.ansi[4]), "yellow": qcolor(p.ansi[3]), "dim": qcolor(p.dim),
                         "cursor": qcolor(p.cursor)}
        return out

    terminalPalettes = Property("QVariantMap", _get_terminal_palettes, notify=tokensChanged)
    darkTokens = Property("QVariantMap", lambda self: self._maps[0], notify=tokensChanged)
    lightTokens = Property("QVariantMap", lambda self: self._maps[1], notify=tokensChanged)

    def _get_preview_dark(self) -> bool:
        return self._preview_dark

    def _set_preview_dark(self, v: bool) -> None:
        if bool(v) != self._preview_dark:
            self._preview_dark = bool(v)
            self.previewChanged.emit()
            self._rebuild_tokens()

    previewDark = Property(bool, _get_preview_dark, _set_preview_dark, notify=previewChanged)

    # ---- the app's own look ------------------------------------------------------
    @Property(bool, notify=uiChanged)
    def uiDark(self) -> bool:
        return self._system_dark

    @Property(QColor, notify=tokensChanged)
    def uiAccent(self) -> QColor:
        return qcolor(palette.resolve_accent(self._s, self._system_accent))

    @Property(QColor, notify=tokensChanged)
    def uiAccentFg(self) -> QColor:
        return qcolor(self._dark_t.accent_fg)

    @Slot(str, result=str)
    def iconUrl(self, name: str) -> str:
        return f"image://lgicon/{name}" if name and QIcon.hasThemeIcon(name) else ""

    @Property(str, notify=wallpaperChanged)
    def wallpaper(self) -> str:
        """The wallpaper the preview shows: the dark one when the preview is dark."""
        return self._wallpaper_for(self._preview_dark)

    @Property(str, notify=wallpaperChanged)
    def appWallpaper(self) -> str:
        """The wallpaper behind this window's own glass: the one GNOME shows now."""
        return self._wallpaper_for(self._system_dark)

    @Property(float, notify=wallpaperLumaChanged)
    def wallpaperLuma(self) -> float:
        """How bright the wallpaper is on average (0..1, linear), for the lock screen preview,
        which darkens a bright picture the way the lock glass's brightness ceiling does.
        Decoded on a worker thread: until it is known, an average dark wallpaper."""
        url = self.wallpaper
        if not url:
            return 0.2
        if url not in self._lumas and url not in self._luma_tasks:
            task = _Task(lambda _report: _average_luma(QUrl(url).toLocalFile()), self)
            # A bound slot of this object, so the result arrives queued on the GUI thread.
            task.finishedWith.connect(self._luma_done)
            self._luma_tasks[url] = task
            task.start()
        return self._lumas.get(url, 0.2)

    @Slot(object)
    def _luma_done(self, out: Any) -> None:
        task = self.sender()
        url = next((u for u, t in self._luma_tasks.items() if t is task), None)
        if url is None:
            return
        del self._luma_tasks[url]
        task.wait()
        task.deleteLater()
        self._lumas[url] = out if isinstance(out, float) else 0.2
        if url == self.wallpaper:
            self.wallpaperLumaChanged.emit()

    @Property(bool, constant=True)
    def hasBattery(self) -> bool:
        """Whether this PC has a battery of its own (a laptop), for the lock screen's battery widget."""
        return _has_battery(self._power_supply)

    WEATHER_EVERY = 30.0     # s: the window gaining focus looks again at most this often

    @Property(str, notify=weatherChanged)
    def weatherState(self) -> str:
        """For the lock screen's weather switch: "ready", "no-app" or "no-place". Until the
        first look (on a worker thread: three gsettings calls) "ready": don't claim it won't work."""
        if getattr(self, "_weather_state", None) is None:
            self._check_weather()
            return "ready"
        return self._weather_state

    @Slot()
    def refreshWeather(self) -> None:
        """Look again (the window just regained focus): GNOME Weather may have been installed
        or a place chosen meanwhile. Not more than once every WEATHER_EVERY seconds."""
        now = time.monotonic()
        if now - getattr(self, "_weather_at", -1e9) < self.WEATHER_EVERY:
            return
        self._weather_at = now
        self._check_weather()

    def _check_weather(self) -> None:
        if getattr(self, "_weather_task", None) is not None:
            return
        env = self._env
        task = _Task(lambda _report: _weather_state(env), self)
        task.finishedWith.connect(self._weather_done)     # bound: arrives on the GUI thread
        self._weather_task = task
        task.start()

    @Slot(object)
    def _weather_done(self, out: Any) -> None:
        task, self._weather_task = self._weather_task, None
        if task is not None:
            task.wait()
            task.deleteLater()
        new = out if isinstance(out, str) else "ready"
        if new != getattr(self, "_weather_state", None):
            self._weather_state = new
            self.weatherChanged.emit()

    @Property(int, constant=True)
    def lockMessageMax(self) -> int:
        return settings_mod.LOCK_MESSAGE_MAX

    @Slot()
    def lockScreenNow(self) -> None:
        """Lock the screen, so the lock screen can be seen as it is set now."""
        gdbus = self._env.which("gdbus")
        if gdbus:
            QProcess.startDetached(gdbus, ["call", "--session", "--dest", "org.gnome.ScreenSaver",
                                           "--object-path", "/org/gnome/ScreenSaver",
                                           "--method", "org.gnome.ScreenSaver.Lock"])

    @Property(str, constant=True)
    def userName(self) -> str:
        """Shown in the preview's terminal prompt and menu, like on the real desktop."""
        import getpass
        try:
            return getpass.getuser()
        except Exception:  # no passwd entry in some sandboxes
            return "user"

    @Property(str, constant=True)
    def version(self) -> str:
        """The app's version, for the About sheet."""
        from .. import __version__
        return __version__

    @Property(str, constant=True)
    def hostName(self) -> str:
        import socket
        return socket.gethostname().split(".")[0] or "fedora"

    @Property("QVariantList", constant=True)
    def dock(self) -> list[dict]:
        return self._dock

    # ---- targets -------------------------------------------------------------------
    def _target_items(self) -> list[dict]:
        """Every target to show, in group order, with its switch state. A part that only
        makes sense where it is installed (the author's own apps) is left out when missing."""
        items = [dict(t, enabled=self._s.target_enabled(t["id"]), **_missing_text(t))
                 for t in self._targets if t["available"] or not t.get("hideWhenMissing")]
        return sorted(items, key=lambda t: _group_rank(t["group"]))   # stable: keeps target order

    @staticmethod
    def _grouped(items: list[dict]) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for t in items:
            groups.setdefault(t["group"], []).append(t)
        return [{"group": g, "items": v} for g, v in groups.items()]

    @Property("QVariantList", notify=targetsChanged)
    def targets(self) -> list[dict]:
        return self._grouped(self._target_items())

    @Property("QVariantList", notify=targetsChanged)
    def installedTargets(self) -> list[dict]:
        """The groups of parts found on this PC, each with only those parts; empty groups go."""
        return self._grouped([t for t in self._target_items() if t["available"]])

    @Property("QVariantList", notify=targetsChanged)
    def missingTargets(self) -> list[dict]:
        """Parts not installed here, flat and in group order, for the folded list."""
        return [t for t in self._target_items() if not t["available"]]

    @Property(bool, notify=targetsChanged)
    def targetsReady(self) -> bool:
        return self._targets_ready

    @Property(bool, notify=targetsChanged)
    def hasDashToPanel(self) -> bool:
        """Dash to Panel is installed and switched on (one only installed is stock GNOME's
        top bar). Until the targets are known, yes: the panel settings stay put rather
        than flash away and back."""
        if not self._targets_ready:
            return True
        return self._has_dtp

    @Property(bool, notify=targetsChanged)
    def hasDock(self) -> bool:
        """Dash to Dock or Ubuntu Dock is on: the preview shows a dock along the bottom."""
        return self._has_dock

    @Property(bool, notify=targetsChanged)
    def hasStartMenu(self) -> bool:
        """ArcMenu or Spawn is installed and switched on (yes until the targets are known,
        as above). One that is only installed is not part of the desktop."""
        if not self._targets_ready:
            return True
        return self._has_menu

    @Property(int, notify=targetStatesChanged)
    def activeTargetCount(self) -> int:
        return sum(1 for t in self._targets if t["available"] and self._s.target_enabled(t["id"]))

    # ---- first run -------------------------------------------------------
    def _settings_file(self) -> Path:
        return self._path or settings_mod.settings_path()

    def _welcome_marker(self) -> Path:
        return self._settings_file().parent / "welcome-seen"

    @Property(bool, constant=True)
    def firstRun(self) -> bool:
        return self._first_run

    @Slot()
    def dismissWelcome(self) -> None:
        """Remember that the welcome was seen, so it never shows again."""
        marker = self._welcome_marker()
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            # O_NOFOLLOW: a planted symlink can't make this touch some other file.
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        except OSError:
            pass    # worst case it shows again next time

    # ---- restart to finish -------------------------------------------------
    @Property(bool, notify=restartNeededChanged)
    def restartNeeded(self) -> bool:
        """The look is applied, but the glass only starts when the PC restarts: the glass
        part is applied and GNOME Shell isn't running it yet, or Shell parts still wait for it."""
        return self._restart_needed

    def _set_restart_needed(self, on: bool) -> None:
        on = bool(on)
        if on != self._restart_needed:
            self._restart_needed = on
            self.restartNeededChanged.emit()

    @staticmethod
    def _restart_state(engine: Any, glass_wanted: bool) -> tuple[bool, bool]:
        """(the glass runs now, a restart is needed to finish), read on a worker thread."""
        try:
            from ..engine import Backup, read_pending, restored_path
            from ..targets.shell import GlassEffects, glass_blocked
            changed = Backup(engine.env).targets_with_changes()
            if not changed or restored_path(engine.env).exists():
                return False, False
            glass_applied = "glass" in changed
            running = glass_applied and GlassEffects.running(engine.env)
            waiting = bool(read_pending())
            # A glass that can't start (extensions off, an unsupported GNOME, an error) is
            # not fixed by a restart: the note in the window says what is.
            restart = glass_wanted and ((glass_applied and not running) or waiting) and not glass_blocked(engine.env)
            return running, restart
        except Exception:
            return False, False

    def _detach(self, program: str, args: list[str]) -> bool:
        return bool(QProcess.startDetached(program, args))

    @Slot()
    def restartPC(self) -> None:
        """Open GNOME's own restart dialog: the user confirms there, nothing restarts without it."""
        path = self._env.which("gnome-session-quit")
        if not path or not self._detach(path, ["--reboot"]):
            self.failed.emit(_("Could not open the restart dialog. Restart your PC from the system menu instead."))

    @Slot()
    def applyAndLock(self) -> None:
        """Apply the unapplied changes, then lock the screen so they can be seen for real.
        Nothing to apply: just lock."""
        if not self.dirty:
            self.lockScreenNow()
            return
        self._lock_after_apply = True
        self.apply()

    def _lock_if_asked(self, results: list) -> None:
        """After "Apply and lock": lock, unless something failed or the glass needs a restart
        first (the lock screen would still show the old look)."""
        if not self._lock_after_apply:
            return
        self._lock_after_apply = False
        if not any(r.status == "failed" for r in results) and not self._restart_needed:
            self.lockScreenNow()

    @Property(str, notify=targetsChanged)
    def foundSummary(self) -> str:
        """What the desktop here is made of, in one line for the welcome ("" until known)."""
        if not self._targets_ready:
            return ""
        parts = ["Dash to Panel" if self.hasDashToPanel else _("GNOME's own top bar")]
        parts += [n for n in (self._dock_name, self._menu_name) if n]
        return _("Found on this PC: {list}.").format(list=_join_names(parts))

    @Property(bool, notify=targetsChanged)
    def hasBackup(self) -> bool:
        return self._has_backup

    @Property(str, notify=targetsChanged)
    def lostNote(self) -> str:
        """One line when another app (a theme update, say) replaced files Apply wrote, or ""."""
        if not self._lost:
            return ""
        return _("Another app replaced the Fedora Glass look for {what}. Apply again to bring it back.").format(
            what=_join_names(self._lost))

    @Slot(str, bool)
    def setTargetEnabled(self, target_id: str, on: bool) -> None:
        if self._s.target_enabled(target_id) == bool(on):
            return
        targets = dict(self._s.targets)
        targets[target_id] = bool(on)
        self._s = replace(self._s, targets=targets)
        self._rebuild_tokens()   # the glass target decides which edges the theme draws
        self.settingsChanged.emit()
        self.targetStatesChanged.emit()

    @Property("QVariantMap", notify=targetStatesChanged)
    def targetStates(self) -> dict:
        """Target id -> on, for the preview (a missing id is on). Parts that are off until
        the user turns them on are always listed, so a missing id stays "on"."""
        return {**{k: False for k in settings_mod.OPT_IN_TARGETS},
                **{k: bool(v) for k, v in self._s.targets.items()}}

    @Slot()
    def refreshTargets(self) -> None:
        s = self._s.normalized()
        glass_wanted = self._saved.target_enabled("glass")

        def job(report):
            engine = self._engine_obj()
            try:
                ctx = engine.context(s)
            except Exception:
                ctx = None
            out = []
            for t in engine.targets:
                try:
                    notes = list(t.live_notes(ctx)) if ctx is not None and hasattr(t, "live_notes") else list(t.notes or [])
                except Exception:
                    notes = list(t.notes or [])
                try:
                    det = t.detect(engine.env)
                    available, detail = bool(det.available), det.detail or ""
                except Exception as e:
                    available, detail = False, _("Could not check: {error}").format(error=e)
                out.append({"id": t.id, "name": tr(t.name), "group": t.group or "Apps",
                            "groupLabel": tr(t.group or "Apps"),
                            "summary": tr(t.summary), "notes": [tr(n) for n in notes],
                            "available": available, "detail": detail,
                            "hideWhenMissing": bool(getattr(t, "hide_when_missing", False)),
                            # Off until the user turns it on: off is its normal state, not a warning.
                            "optIn": t.id in settings_mod.OPT_IN_TARGETS})
            names = {t["id"]: t["name"] for t in out}
            lost = [names.get(tid, tid) for tid in self._overwritten(engine)]
            package = self._remove_package
            if package is None:
                try:
                    package = self._installed_package()
                except Exception:
                    package = ""
            return (out, self._backup_exists(engine), self._restart_state(engine, glass_wanted),
                    self._terminal_palette(engine), lost, self._motion_env(engine), self._extension_names(engine),
                    self._extensions_on(engine)[2], self._glass_problem(engine, s), self._find_leftovers(engine),
                    package)
        self._run("detect", job, self._targets_done, show_busy=False)

    @staticmethod
    def _extensions_on(engine: Any) -> tuple[bool, bool, bool]:
        """Whether a dock (Dash to Dock, Ubuntu Dock), a start menu (ArcMenu, Spawn) and
        Dash to Panel are installed and switched on: the same rule as Apply (Env.extension_on)."""
        dock, menu = Backend._extension_names(engine)
        try:
            dtp = engine.env.extension_on(DASH_TO_PANEL)
        except Exception:
            dtp = False
        return bool(dock), bool(menu), dtp

    @staticmethod
    def _extension_names(engine: Any) -> tuple[str, str]:
        """The dock and the start menu that are installed and switched on, by name ("" for none)."""
        try:
            env = engine.env
            def first_on(uuids: tuple[str, ...]) -> str:
                return next((EXTENSION_NAMES[u] for u in uuids if env.extension_on(u)), "")
            return first_on(DOCK_EXTENSIONS), first_on(MENU_EXTENSIONS)
        except Exception:
            return "", ""

    @staticmethod
    def _overwritten(engine: Any) -> list[str]:
        try:
            from ..engine import Backup
            return Backup(engine.env).overwritten()
        except Exception:
            return []

    @staticmethod
    def _glass_running(engine: Any) -> bool:
        """Applied, and already loaded by the Shell (new extensions load at login)."""
        try:
            from ..engine import Backup
            from ..targets.shell import GlassEffects
            return "glass" in Backup(engine.env).targets_with_changes() and GlassEffects.running(engine.env)
        except Exception:
            return False

    @staticmethod
    def _glass_problem(engine: Any, s: Settings) -> tuple[str, str, str]:
        try:
            from ..targets.shell import glass_problem
            return glass_problem(engine.env, wanted=s.target_enabled("glass"))
        except Exception:
            return "", "", ""

    @Property(str, notify=targetsChanged)
    def glassProblem(self) -> str:
        """Why the glass isn't running this version, when it is more than the first
        restart: "old" (an update waits for the restart), "off" (extensions switched off
        in GNOME), "out-of-date" (this GNOME isn't supported yet), "error", or ""."""
        return self._problem[0]

    @Property(bool, notify=targetsChanged)
    def glassBlocked(self) -> bool:
        """The glass won't start by itself, not even after a restart."""
        return self._problem[0] in ("off", "out-of-date", "error")

    @Property(str, notify=targetsChanged)
    def glassProblemNote(self) -> str:
        return self._problem[1]

    @Property(str, notify=targetsChanged)
    def glassProblemDetails(self) -> str:
        """What GNOME reports, for "Copy details" (may be empty)."""
        return self._problem[2]

    @Slot()
    def switchExtensionsOn(self) -> None:
        """GNOME's own Extensions switch, back on (only when the user clicks). The glass
        and the other extensions start right away; the parts Apply left as they were
        need Apply again."""
        r = self._env.gsettings_set("org.gnome.shell", "disable-user-extensions", "false")
        if not r.ok:
            self.failed.emit(_("Could not switch extensions on. Try the Extensions app instead."))
            return
        self.noticed.emit(_("Extensions are on again. Press Apply to finish your look."))
        self.refreshTargets()

    # ---- an old source install left behind (see leftovers.py) -----------------------
    @staticmethod
    def _find_leftovers(engine: Any) -> list:
        try:
            from .. import leftovers
            return leftovers.find(engine.env)
        except Exception:
            return []

    @Property(bool, notify=targetsChanged)
    def hasOldCopy(self) -> bool:
        """A copy installed with install.sh still starts at login instead of this package."""
        return bool(self._leftovers)

    @Slot()
    def cleanUpOldCopy(self) -> None:
        """Take away only that copy's launcher, menu entry and user service (only on this
        click), then start the package's own watcher."""
        if not self._leftovers or self._removing:
            return
        if self._task is not None:
            # The system check is still running: clean up as soon as it ends.
            self._pending_action = "cleanUpOldCopy"
            self.busyChanged.emit()
            return
        from .. import leftovers

        # systemctl can take up to 30 s per call: on a worker thread, never the UI's.
        def job(report):
            try:
                return leftovers.clean_up(self._engine_obj().env)
            except Exception as e:
                return [str(e)]

        def done(problems):
            if isinstance(problems, Exception):
                problems = [str(problems)]
            if problems:
                self.failed.emit(_("Could not clean up the old copy: {problem}").format(problem=problems[0]))
            else:
                self.noticed.emit(_("Old copy cleaned up. Fedora Glass now runs from the package only."))
            self.refreshTargets()
        self._run("cleanup", job, done)

    @Slot()
    def copyGlassDetails(self) -> None:
        text = self._problem[2] or self._problem[1]
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.noticed.emit(_("Error details copied"))

    @staticmethod
    def _motion_env(engine: Any) -> dict:
        """What the Motion card needs to say: whether GNOME's animations are on at all, and
        whether Dash to Panel animates its icons on hover itself (ours then stands down there)."""
        env = engine.env
        out = {"animations": True, "dtpHover": False}
        try:
            v = env.gsettings_get("org.gnome.desktop.interface", "enable-animations")
            out["animations"] = v != "false"
            from ..targets.shell import DashToPanel
            if env.extension_on(DASH_TO_PANEL):
                out["dtpHover"] = env.gsettings_get(DashToPanel.SCHEMA, "animate-appicon-hover") == "true"
        except Exception:
            pass
        return out

    @staticmethod
    def _terminal_palette(engine: Any) -> str:
        """The palette Ptyxis opens with, or "" when there is no Ptyxis profile to change."""
        try:
            from ..targets.terminal import Ptyxis
            t = next((t for t in engine.targets if isinstance(t, Ptyxis)), None)
            if t is None or not t.detect(engine.env).available:
                return ""
            return t.palette_in_use(engine.env) or ""
        except Exception:
            return ""

    def _targets_done(self, out: Any) -> None:
        dtp_before = self.hasDashToPanel
        if isinstance(out, Exception):
            self._targets, self._has_backup = [], False
            self.failed.emit(_("Could not load targets: {error}").format(error=out))
            restart = False
        else:
            (self._targets, self._has_backup, (self._glass_live, restart), self._terminal_pal, self._lost,
             self._motion_state, (self._dock_name, self._menu_name), self._has_dtp, self._problem,
             self._leftovers, package) = out
            if self._remove_package is None:
                self._remove_package = package
            self._has_dock, self._has_menu = bool(self._dock_name), bool(self._menu_name)
        self._targets_ready = True
        self.targetsChanged.emit()
        if self.hasDashToPanel != dtp_before:
            self.settingsChanged.emit()     # "start on the desktop" follows Dash to Panel until chosen
        self._set_restart_needed(restart)

    @staticmethod
    def _backup_exists(engine: Any) -> bool:
        try:
            from ..engine import Backup
            return bool(Backup(engine.env).targets_with_changes())
        except Exception:
            return False

    # ---- long-running work --------------------------------------------------------
    def _queued_kind(self) -> str:
        """The asked-for action waiting for the background check to end, as a busy kind."""
        return {"apply": "apply", "revert": "revert", "requestPlan": "plan",
                "cleanUpOldCopy": "cleanup"}.get(self._pending_action or "", "")

    # Removing the app (Restore original, then the package manager behind pkexec) counts
    # as busy from start to end: Apply, Restore or See changes would run over it.
    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return bool(self._busy or self._queued_kind() or self._removing)

    @Property(str, notify=busyChanged)
    def busyKind(self) -> str:
        return "remove" if self._removing else self._busy or self._queued_kind()

    @Property(float, notify=progressChanged)
    def progress(self) -> float:
        return self._progress

    @Property(str, notify=progressChanged)
    def progressText(self) -> str:
        return self._progress_text

    def _run(self, kind: str, fn, done, show_busy: bool = True) -> bool:
        if self._task is not None:
            return False
        task = _Task(fn, self)
        self._task, self._task_done, self._task_busy = task, done, show_busy
        if show_busy:
            self._busy = kind
            self._progress, self._progress_text = 0.0, ""
            self.busyChanged.emit()
            self.progressChanged.emit()
        # Bound slots of this object, so results arrive queued on the GUI thread.
        task.progressed.connect(self._on_progress)
        task.finishedWith.connect(self._on_task_done)
        task.start()
        return True

    @Slot(object)
    def _on_task_done(self, out: Any) -> None:
        task, done = self._task, self._task_done
        self._task = None
        if task is not None:
            task.wait()
            task.deleteLater()
        if self._task_busy:
            self._busy = ""
            self.busyChanged.emit()
        done(out)
        if self._pending_action and self._task is None:
            name, self._pending_action = self._pending_action, None
            self.busyChanged.emit()
            getattr(self, name)()

    @Slot(float, str)
    def _on_progress(self, f: float, text: str) -> None:
        self._progress, self._progress_text = f, text
        self.progressChanged.emit()

    @Slot()
    def requestPlan(self) -> None:
        if self._removing:
            return
        if self._task is not None:
            self._pending_action = self._pending_action or "requestPlan"
            self.busyChanged.emit()
            return
        s = self._s.normalized()

        def job(report):
            engine = self._engine_obj()
            names = {t.id: tr(t.name) for t in engine.targets}
            plain = {t.id: tr(getattr(t, "plain", "") or "") for t in engine.targets}
            home = str(engine.env.home)
            report(0.1, _("Planning"))
            plan = engine.plan(s)
            return [{"id": tid, "name": names.get(tid, tid), "plain": plain.get(tid, ""),
                     "actions": [{"kind": type(a).__name__, "text": _tilde(a.describe(), home)} for a in actions]}
                    for tid, actions in plan.items()]

        def done(out):
            if isinstance(out, Exception):
                self.failed.emit(_("Could not work out the changes: {error}").format(error=out))
            else:
                self.planReady.emit(out)
        self._run("plan", job, done)

    @Slot()
    def apply(self) -> None:
        if self._removing:
            self._lock_after_apply = False
            return
        if self._task is not None:
            # Still checking the system in the background: apply as soon as that ends.
            self._pending_action = "apply"
            self.busyChanged.emit()
            return
        # "Match my wallpaper": the colour is taken again now, from the picture shown now.
        # Not known yet: worked out on a worker thread first, then Apply goes on.
        if not self._take_wallpaper_colours():
            return
        s = self._s.normalized()
        header_changed = _header_key(s) != _header_key(self._saved)
        # The look applied until now, kept as the one to go back to once this Apply ends.
        was_applied, was_at, step = self._saved, self._saved_at, self._apply_step
        self._apply_step = ""
        # Saved first, so a settings folder that can't be written stops Apply before the
        # desktop changes. The look counts as applied (_saved) only once Apply ends.
        try:
            before = settings_mod.read_raw(self._path)
        except OSError:
            before = False      # can't be read: an Apply that stops leaves the file as it is then
        try:
            settings_mod.save(s, self._path)
        except OSError as e:
            self._lock_after_apply = False
            self.failed.emit(_("Could not save settings: {error}").format(error=e))
            return
        self._applying = s
        glass_wanted = s.target_enabled("glass")

        def job(report):
            engine = self._engine_obj()
            ts = list(engine.targets)
            if not ts:
                report(0.5, _("Writing tokens"))
                return [], self._backup_exists(engine), self._restart_state(engine, glass_wanted)
            results = {}
            for i, t in enumerate(ts):
                report(i / len(ts), tr(t.name))
                # Switching the glass on can finish parts that waited for it a step
                # earlier (the Shell theme): the latest result for a part counts.
                for r in engine.apply(s, only={t.id}):
                    results[r.target] = r
            report(1.0, _("Done"))
            return list(results.values()), self._backup_exists(engine), self._restart_state(engine, glass_wanted)

        def done(out):
            # "Remove only" (undoOnRemove) may have been switched while Apply ran: it is saved at once.
            uor = self._saved.undo_on_remove
            self._applying = None
            if isinstance(out, Exception):
                self._lock_after_apply = False
                # Stopped part way: the changes stay unapplied (dirty, Undo, the close guard),
                # and settings.json goes back to the look applied last, since the watcher
                # applies that file again whenever GNOME flips between dark and light.
                # Not a save: that would make .bak the look that just failed. While the
                # file was damaged (_usable False) it goes back to exactly what it was, so the
                # defaults never land in it.
                try:
                    if self._usable:
                        settings_mod.save(self._saved, self._path, backup=False)
                    elif before is not False:
                        settings_mod.put_back(before, self._path)
                except OSError:
                    pass
                self._refresh_damage()
                self.failed.emit(_("Apply stopped: {error}").format(error=out))
                return
            results, self._has_backup, (self._glass_live, restart) = out
            self._saved = replace(s, undo_on_remove=uor)
            self._usable = True         # settings.json is the look the user applied now
            self._keep_previous(was_applied, was_at, step)
            from ..engine import WAITING
            rows = [{"id": r.target, "name": r.name, "status": r.status, "message": r.message,
                     "restart": r.status == "info" and r.message == tr(WAITING)} for r in results]
            # Some parts failed: the rest is applied, and settings.json is that look (the
            # watcher keeps it), but Undo goes back to the last look that applied fully.
            if any(r["status"] == "failed" for r in rows):
                self._partial = rows
            else:
                self._partial = []
                self._good = self._saved
            self.settingsChanged.emit()
            self.savedChanged.emit()
            self.partialChanged.emit()
            self._set_restart_needed(restart)    # before applyFinished: the results sheet reads it
            self.targetsChanged.emit()
            self.refreshTargets()          # the glass may be live now, and notes change
            if header_changed:
                self._set_header_note("pending")
            # Apply brings the login screen along when its glass is on: new colours, or the
            # rules of a newer Fedora Glass. It changes a system file, so this asks for the
            # password. Started before applyFinished, so "Apply and close" sees it running
            # and waits for it.
            self._login_state = self._read_login_state()
            if self._login_stale(self._saved):
                self._run_login(["apply", *self.login_values(self._saved)],
                                _("The login screen has your new look. You'll see it the next time you restart your PC."))
            else:
                self.loginGlassChanged.emit()
            self.applyFinished.emit(rows)
            self._lock_if_asked(results)
        self._run("apply", job, done)

    @Slot()
    def revert(self) -> None:
        if self._removing:
            return
        if self._task is not None:
            # Right after an Apply the app re-checks the system: restore once that ends
            # (1.5.3 dropped the click without a word).
            self._pending_action = "revert"
            self.busyChanged.emit()
            return
        # From here on the extension's config is the engine's to remove; stop writing it.
        self._glass_live = False
        header_changed = _header_key(self._saved) != _header_key(Settings())

        def job(report):
            engine = self._engine_obj()
            report(0.3, _("Restoring"))
            problems = engine.revert()
            return list(problems), self._backup_exists(engine)

        def done(out):
            if isinstance(out, Exception):
                self.failed.emit(_("Restore stopped: {error}").format(error=out))
                return
            problems, self._has_backup = out
            self._glass_live = False
            self._lost = []
            self._set_partial([])
            self.targetsChanged.emit()
            self._set_restart_needed(False)
            if header_changed:
                self._set_header_note("pending")
            self.revertFinished.emit(problems)
        self._run("revert", job, done)

    # ---- an Apply where some parts failed ------------------------------------------
    def _set_partial(self, rows: list[dict]) -> None:
        if rows != self._partial:
            self._partial = rows
            self.partialChanged.emit()

    @Property(int, notify=partialChanged)
    def partlyApplied(self) -> int:
        """How many parts failed in the last Apply (0: it applied fully, or nothing was applied)."""
        return sum(1 for r in self._partial if r["status"] == "failed")

    @Property("QVariantList", notify=partialChanged)
    def partialResults(self) -> list[dict]:
        """That Apply's results, for the results sheet the footer opens."""
        return list(self._partial)

    # ---- header bars: Files keeps the old style sheet until it restarts -------------
    def _set_header_note(self, state: str) -> None:
        if state != self._header_note:
            self._header_note = state
            self.headerNoteChanged.emit()

    @Property(str, notify=headerNoteChanged)
    def headerNote(self) -> str:
        """Empty (nothing to say), "pending" (Files still shows the old bars) or "restarted"."""
        return self._header_note

    @Property(str, notify=targetsChanged)
    def terminalPalette(self) -> str:
        """The colour palette Terminal (Ptyxis) uses now, "" if there is no profile."""
        return self._terminal_pal

    @Property(str, constant=True)
    def fedoraGlassPalette(self) -> str:
        from ..render.terminal import PTYXIS_PALETTE_NAME
        return PTYXIS_PALETTE_NAME

    @Property(bool, constant=True)
    def canRestartFiles(self) -> bool:
        return bool(self._env.which("nautilus"))

    @Slot(result=bool)
    def restartFiles(self) -> bool:
        """Quit Files (`nautilus -q`) so it starts with the new header bars next time.

        Only ever on the user's click: open Files windows close. Terminal is never touched,
        since quitting it would end running shells."""
        path = self._env.which("nautilus")
        if not path or not QProcess.startDetached(path, ["-q"]):
            self.failed.emit(_("Could not restart Files. Close all Files windows, or restart your PC instead."))
            return False
        self._set_header_note("restarted")
        return True

    @Slot(result=bool)
    def waitIdle(self) -> bool:
        """For tests and the screenshot mode: block until background work ends."""
        from PySide6.QtCore import QCoreApplication, QElapsedTimer
        timer = QElapsedTimer()
        timer.start()
        while self._task is not None and timer.elapsed() < 30000:
            QCoreApplication.processEvents()
            QThread.msleep(5)
        return self._task is None

    # ---- glass on the login screen -------------------------------------------------
    LOGIN_HELPER = Path("/usr/libexec/liquid-glass-login-screen")
    PKEXEC = Path("/usr/bin/pkexec")

    def _login_available(self) -> bool:
        """Only offered when the package put a root-owned helper in place: pkexec
        would run whatever is at that path as root."""
        for p in (self.LOGIN_HELPER, self.PKEXEC):
            try:
                st = p.stat()
            except OSError:
                return False
            if st.st_uid != 0 or st.st_mode & 0o022:
                return False
        return True

    def _read_login_state(self) -> str:
        if not self._login_available():
            return "unavailable"
        try:
            return login_screen.status()
        except Exception:  # noqa: BLE001 (a status read never stops the app)
            return "off"

    @Property(str, notify=loginGlassChanged)
    def loginGlass(self) -> str:
        return "busy" if self._login_proc is not None else self._login_state

    @Property(str, notify=loginGlassChanged)
    def loginGlassNote(self) -> str:
        return self._login_note

    @Property(bool, notify=loginGlassChanged)
    def loginGlassFailed(self) -> bool:
        """The last login screen step went wrong (a closed password dialog doesn't count)."""
        return self._login_failed

    def _login_stale(self, s: Settings | None = None) -> bool:
        """Glass is on the login screen, but not the look Apply gives now: other colours,
        or the rules of an older Fedora Glass (1.5.7 made the password prompt compact)."""
        if self._login_state != "on":
            return False
        try:
            return not login_screen.up_to_date(*self.login_values(s))
        except Exception:  # noqa: BLE001 (a status read never stops the app)
            return False

    @Property(bool, notify=loginGlassChanged)
    def loginGlassStale(self) -> bool:
        return self._login_proc is None and self._login_stale(self._saved)

    def login_values(self, s: Settings | None = None) -> list[str]:
        """The three values the helper takes: accent, tint and frost from the current look
        (or from s, such as the look just applied)."""
        s = (self._s if s is None else s).normalized()
        dark = self._dark_t if s == self._s.normalized() else palette.build(s, dark=True, system_accent=self._system_accent)
        return [dark.accent.hex6, Color.hex(s.tint).hex6, f"{s.frost:.3f}"]

    @Property(bool, notify=settingsChanged)
    def loginGlassBehind(self) -> bool:
        """Unapplied changes would change the login screen's colours or frost: its button
        uses the look applied last, so the card says so."""
        try:
            return self.login_values(self._s) != self.login_values(self._saved)
        except Exception:  # noqa: BLE001 (a colour that can't be read: say nothing)
            return False

    @Slot()
    def turnOnLoginGlass(self) -> None:
        # The applied look, as Apply keeps it: the desktop doesn't have unapplied slider
        # values either, and loginGlassStale compares with this one.
        self._run_login(["apply", *self.login_values(self._saved)],
                        _("Glass is on the login screen. You'll see it the next time you restart your PC."))

    @Slot()
    def turnOffLoginGlass(self) -> None:
        self._run_login(["undo"], _("The normal login screen is back."))

    def _run_login(self, args: list[str], done: str) -> None:
        if self._login_proc is not None or not self._login_available():
            return
        p = QProcess(self)
        p.setProgram(str(self.PKEXEC))
        p.setArguments([str(self.LOGIN_HELPER), *args])
        p.finished.connect(lambda code, _status: self._login_finished(p, code, done))
        p.errorOccurred.connect(lambda _e: self._login_finished(p, -1, done))
        self._login_proc = p
        self._login_note = ""
        self._login_failed = False
        self.loginGlassChanged.emit()
        p.start()

    def _login_finished(self, p: QProcess, code: int, done: str) -> None:
        if self._login_proc is not p:
            return
        err = bytes(p.readAllStandardError()).decode(errors="replace").strip()
        self._login_proc = None
        p.deleteLater()
        if code == 0:
            self._login_note = done
        elif code in (126, 127):          # pkexec: the password dialog was closed or refused
            self._login_note = _("Not changed: the password wasn't given.")
        else:
            self._login_failed = True
            first = err.splitlines()[-1] if err else _("the helper didn't finish")
            self._login_note = first if first.startswith("Nothing was changed") else _("Nothing was changed: {reason}").format(reason=first)
        self._login_state = self._read_login_state()
        self.loginGlassChanged.emit()

    # ---- removing the app --------------------------------------------------------
    @Property(bool, notify=settingsChanged)
    def undoOnRemove(self) -> bool:
        return self._s.undo_on_remove

    @undoOnRemove.setter
    def undoOnRemove(self, on: bool) -> None:
        """Saved straight away, without Apply: removing the package reads it from the saved settings."""
        on = bool(on)
        if self._s.undo_on_remove == on and self._saved.undo_on_remove == on:
            return
        saved = replace(self._saved, undo_on_remove=on)
        # While Apply runs, settings.json holds the look it applies: keep that one, and keep
        # .bak the look applied before it (the Apply may still fail).
        on_disk = replace(self._applying, undo_on_remove=on) if self._applying is not None else saved
        try:
            if self._usable or self._applying is not None:
                settings_mod.save(on_disk, self._path, backup=self._applying is None)
            if not self._usable:
                # Damaged settings.json: only Apply writes it (see _usable). The choice is
                # kept beside it, where removing the package reads it.
                settings_mod.save_undo_on_remove(on, self._path)
        except OSError as e:
            self.failed.emit(_("Could not save settings: {error}").format(error=e))
            return
        if self._applying is not None:
            self._applying = on_disk
        self._saved = saved
        self._good = replace(self._good, undo_on_remove=on)
        self._s = replace(self._s, undo_on_remove=on)
        self.settingsChanged.emit()
        self.savedChanged.emit()

    APP_DIR = Path("/usr/share/fedora-glass")

    def _installed_package(self) -> str:
        """The package this app came from ("fedora-glass", or "liquid-glass" before the
        second dnf upgrade), or "" when it runs from anywhere else (a source install, tests).
        Asked of this Linux's own package tool: rpm, dpkg or pacman."""
        d = distro.current()
        if not d.manager:
            return ""
        try:
            if not Path(__file__).resolve().is_relative_to(self.APP_DIR):
                return ""
            for p in (Path(d.manager), self.PKEXEC):
                st = p.stat()
                if st.st_uid != 0 or st.st_mode & 0o022:
                    return ""
        except OSError:
            return ""
        r = self._env.run([*d.owner_cmd, str(self.APP_DIR)], timeout=10)
        # rpm and pacman print the name; dpkg-query prints "name: path".
        name = r.out.strip().split(":")[0].strip() if r.ok else ""
        return name if name in ("fedora-glass", "liquid-glass") else ""

    @Property(str, constant=True)
    def removeCommand(self) -> str:
        """The terminal command that removes the app here (shown in a tip)."""
        return distro.current().remove_command()

    @Property(bool, notify=targetsChanged)
    def canRemoveApp(self) -> bool:
        return bool(self._remove_package)

    @Property(bool, notify=removingChanged)
    def removing(self) -> bool:
        return self._removing

    def _set_removing(self, on: bool) -> None:
        if on != self._removing:
            self._removing = on
            self.removingChanged.emit()
            self.busyChanged.emit()

    @Slot()
    def removeApp(self) -> None:
        """Restore original first (so problems show here, with the app still installed),
        then remove the package: pkexec asks for the password."""
        if self._task is not None or self._removing or not self._remove_package:
            return
        self._set_removing(True)
        self._glass_live = False

        def job(report):
            engine = self._engine_obj()
            report(0.3, _("Restoring"))
            problems = engine.revert()
            return list(problems), self._backup_exists(engine)

        def done(out):
            if isinstance(out, Exception):
                self._set_removing(False)
                self.failed.emit(_("Restore stopped, so Fedora Glass was not removed: {error}").format(error=out))
                return
            problems, self._has_backup = out
            self._lost = []
            self._set_partial([])
            self.targetsChanged.emit()
            self._set_restart_needed(False)
            if problems:
                self._set_removing(False)
                self.revertFinished.emit(problems)      # shows what could not be restored
                return
            proc = QProcess(self)
            proc.setProgram(str(self.PKEXEC))
            d = distro.current()
            proc.setArguments([d.manager, *d.remove_args, self._remove_package])
            proc.finished.connect(lambda code, _status: self._remove_done(proc, code))
            proc.errorOccurred.connect(lambda _e: self._remove_done(proc, -1))
            self._remove_proc = proc
            proc.start()
        self._run("revert", job, done)

    def _remove_done(self, p: QProcess, code: int) -> None:
        if self._remove_proc is not p:
            return
        err = bytes(p.readAllStandardError()).decode(errors="replace").strip()
        self._remove_proc = None
        p.deleteLater()
        self._set_removing(False)
        if code == 0:
            self.removeFinished.emit(True)
            return
        if code in (126, 127):
            self.failed.emit(_("Your original look is back, but Fedora Glass was not removed: the password wasn't given."))
        else:
            last = err.splitlines()[-1] if err else _("{tool} did not finish").format(tool=distro.current().tool_name)
            self.failed.emit(_("Your original look is back, but removing Fedora Glass failed: {reason}").format(reason=last))
        self.removeFinished.emit(False)

    # ---- Shell features: apps without glass -----------------------------------------------
    # The user's own list of apps whose windows get no glass (Settings.no_glass_apps holds the
    # ids the extension matches), shown one row per app with its icon and name.
    def _app_icon(self, icon: str) -> str:
        if not icon:
            return ""
        if icon.startswith("/"):
            return QUrl.fromLocalFile(icon).toString() if Path(icon).is_file() else ""
        return f"image://lgicon/{icon}" if QIcon.hasThemeIcon(icon) else ""

    @Slot()
    def refreshInstalledApps(self) -> None:
        """Read the installed apps again (the picker opens with apps installed since), off the UI thread."""
        if self._apps_task is not None:
            return
        if self._apps_state == "idle":
            self._apps_state = "loading"
            self.installedAppsChanged.emit()
        env = self._env
        task = _Task(lambda _report: installed_apps(env), self)
        task.finishedWith.connect(self._apps_done)
        self._apps_task = task
        task.start()

    @Slot(object)
    def _apps_done(self, out: Any) -> None:
        task, self._apps_task = self._apps_task, None
        if task is not None:
            task.wait()
            task.deleteLater()
        apps = out if isinstance(out, list) else []
        from ..render.glass import always_without_glass
        self._apps = [{**a, "iconUrl": self._app_icon(a["icon"]),
                       "builtIn": any(always_without_glass(i) for i in a["ids"])} for a in apps]
        self._apps_state = "ready"
        self.installedAppsChanged.emit()     # the rows can show names and icons now

    @Property(bool, notify=installedAppsChanged)
    def installedAppsReady(self) -> bool:
        return self._apps_state == "ready"

    def _app_of(self) -> dict[str, dict]:
        """Installed apps by each id their windows carry, in lower case: the extension
        compares ids without regard to case, so "CODE" typed into the file is Code's."""
        index: dict[str, dict] = {}
        for a in self._apps:
            for i in a["ids"]:
                index.setdefault(i.casefold(), a)
        return index

    @Property("QVariantList", notify=installedAppsChanged)
    def installedApps(self) -> list[dict]:
        """For the picker: every installed app, and whether it is always without glass anyway
        ("builtIn"). Whether it is on the list is noGlassApps' (a row keyed by its id), so
        picking one doesn't build the picker's list again (it would jump back to the top)."""
        return [{"id": a["id"], "name": a["name"], "icon": a["iconUrl"], "builtIn": a["builtIn"]} for a in self._apps]

    def _get_no_glass_apps(self) -> list[dict]:
        """The user's apps without glass, one row per app in the order added: {"key", "name",
        "icon", "ids"}. An id no installed app has (removed since, or typed into the
        settings file) is a row of its own, named by the id."""
        index = self._app_of()
        rows: list[dict] = []
        by_key: dict[str, dict] = {}
        for i in self._s.no_glass_apps:
            a = index.get(i.casefold())
            key = a["id"] if a else i
            if key in by_key:
                by_key[key]["ids"].append(i)
                continue
            row = {"key": key, "name": a["name"] if a else i, "icon": a["iconUrl"] if a else "", "ids": [i]}
            by_key[key] = row
            rows.append(row)
        return rows

    noGlassApps = Property("QVariantList", _get_no_glass_apps, notify=noGlassAppsChanged)

    def _set_no_glass(self, ids: list[str]) -> None:
        self._set("no_glass_apps", settings_mod.clean_app_ids(ids))

    @Slot(str)
    def addNoGlassApp(self, desktop_id: str) -> None:
        """Add an installed app (by desktop id): every id its windows may carry."""
        app = next((a for a in self._apps if a["id"] == desktop_id), None)
        if app is None:
            return
        have = {i.casefold() for i in self._s.no_glass_apps}
        self._set_no_glass([*self._s.no_glass_apps, *(i for i in app["ids"] if i.casefold() not in have)])

    @Slot(str)
    def removeNoGlassApp(self, key: str) -> None:
        """Take a row off the list (its key from noGlassApps), with all of its ids. An
        installed app's key is its desktop id, so a row added as that app goes whole."""
        row = next((r for r in self._get_no_glass_apps() if r["key"] == key), None)
        app = next((a for a in self._apps if a["id"] == key), None)
        drop = {i.casefold() for i in [*(row["ids"] if row else []), *(app["ids"] if app else [])]}
        if drop:
            self._set_no_glass([i for i in self._s.no_glass_apps if i.casefold() not in drop])

    @Slot(str)
    def toggleNoGlassApp(self, desktop_id: str) -> None:
        """The picker's rows: on the list, off it; off, on it."""
        app = next((a for a in self._apps if a["id"] == desktop_id), None)
        if app is None:
            return
        have = {i.casefold() for i in self._s.no_glass_apps}
        if any(i.casefold() in have for i in app["ids"]):
            self.removeNoGlassApp(desktop_id)
        else:
            self.addNoGlassApp(desktop_id)

    @Property(str, constant=True)
    def noGlassBuiltIn(self) -> str:
        """The apps the extension always leaves without glass, in words."""
        return _("Steam and its games, video players (VLC, mpv, Videos, Celluloid, Clapper), RetroArch, "
                 "Firefox, Brave, Discord, Slack, Zoom, Visual Studio Code, Obsidian, LibreOffice and "
                 "Prism Launcher, and a few more. They draw their own solid windows, so glass behind them would only cost speed.")

    # =================================================================================
    # Feature stream "looks": saved looks, plain-language changes, one Apply back, and
    # colours from the wallpaper. Kept together here so merges stay easy.
    # =================================================================================
    def _init_looks(self) -> None:
        self._library = looks_mod.Library(looks_mod.looks_dir(self._path))
        self._looks: list[dict] | None = None       # read when first asked for, then kept
        self._look_values: dict[str, dict] = {}     # each look's values, normalized once
        self._cursors_here: dict[str, bool] = {}    # pointer style -> installed here
        # When the look applied last was applied: settings.json's time, or 0 for none yet.
        try:
            self._saved_at = self._settings_file().stat().st_mtime
        except OSError:
            self._saved_at = 0.0
        self._previous = settings_mod.load_previous(self._path)
        self._apply_step = ""          # "back" or "forward" while that Apply is on its way
        # Wallpaper colours: picture path -> {"key", "tint", "accent"}, worked out off the UI thread.
        self._wall_colours: dict[str, dict] = {}
        self._wall_tasks: dict[str, _Task] = {}
        self._matching = False         # the app itself is setting the tint or accent
        self.wallpaperChanged.connect(self.wallpaperMatchChanged)
        self.savedChanged.connect(self.wallpaperMatchChanged)

    # ---- saved looks ------------------------------------------------------------------
    def _look_list(self) -> list[dict]:
        if self._looks is None:
            self._looks = self._library.list()
            # Normalized once here: activeLook is read on every slider tick.
            self._look_values = {x["id"]: looks_mod.look_values(x["settings"], self._cursor_installed)
                                 for x in self._looks}
        return self._looks

    def _looks_changed(self) -> None:
        self._looks = None
        self._cursors_here = {}      # a pointer style may have been installed since
        self.looksChanged.emit()

    def _cursor_installed(self, style: str) -> bool:
        if style not in self._cursors_here:
            try:
                self._cursors_here[style] = cursors.theme_dir(self._env, style) is not None
            except Exception:
                self._cursors_here[style] = False
        return self._cursors_here[style]

    @Property("QVariantList", notify=looksChanged)
    def savedLooks(self) -> list[dict]:
        """The user's own looks, by name: {"id", "name", "tint", "accent", "frost"}, the
        colours as they show on the tile."""
        out = []
        for look in self._look_list():
            s = looks_mod.apply_look(Settings(), look["settings"])
            out.append({"id": look["id"], "name": look["name"], "tint": s.tint, "frost": s.frost,
                        "accent": qcolor(palette.resolve_accent(s, self._system_accent)).name()})
        return out

    def _get_active_look(self) -> str:
        for look in self._look_list():
            if looks_mod.holds(self._look_values[look["id"]], self._s):
                return look["id"]
        return ""

    activeLook = Property(str, _get_active_look, notify=settingsChanged)

    def _with_look(self, values: dict) -> Settings:
        s = looks_mod.apply_look(self._s, values, self._cursor_installed)
        if s.tint_from_wallpaper and not self._s.tint_from_wallpaper:
            s.tint_own = self._s.tint
        if s.accent_from_wallpaper and not self._s.accent_from_wallpaper:
            s.accent_own = self._s.accent
        if not s.tint_from_wallpaper:
            s.tint_own = ""
        if not s.accent_from_wallpaper:
            s.accent_own = ""
        return s

    @Slot(str)
    def useLook(self, look_id: str) -> None:
        """Put a saved look in the editor (Apply then uses it), as a preset tile does."""
        look = next((x for x in self._look_list() if x["id"] == look_id), None)
        if look is None:
            self._looks_changed()
            return
        self._replace_editor(self._with_look(look["settings"]))
        self._match_wallpaper()
        # Selected even when the look is what the editor holds already.
        self.settingsChanged.emit()

    def _replace_editor(self, s: Settings) -> None:
        if s == self._s:
            return
        was_dark = self._effective_dark()
        self._s = s
        if self._effective_dark() != was_dark:
            self._preview_dark = self._effective_dark()
            self.previewChanged.emit()
        self._changed()
        self.targetStatesChanged.emit()

    @Slot(result=str)
    def suggestLookName(self) -> str:
        names = {x["name"].casefold() for x in self._look_list()}
        n = 1
        while (_("My look {n}").format(n=n) if n > 1 else _("My look")).casefold() in names:
            n += 1
        return _("My look {n}").format(n=n) if n > 1 else _("My look")

    @Slot(str, result=str)
    def saveLook(self, name: str) -> str:
        """Keep the editor's look under this name; its id, or "" (lookProblem says why)."""
        try:
            look_id = self._library.save(name, self._s)
        except looks_mod.LookError as e:
            self.lookProblem.emit(str(e))
            return ""
        except OSError as e:
            self.lookProblem.emit(_("The look couldn't be saved: {reason}").format(reason=e.strerror or e))
            return ""
        self._looks_changed()
        self.settingsChanged.emit()     # it is the active look now
        self.noticed.emit(_("Saved “{name}”").format(name=looks_mod.clean_name(name)))
        return look_id

    @Slot(str, str, result=str)
    def renameLook(self, look_id: str, name: str) -> str:
        try:
            new_id = self._library.rename(look_id, name)
        except looks_mod.LookError as e:
            self.lookProblem.emit(str(e))
            return ""
        except OSError as e:
            self.lookProblem.emit(_("The look couldn't be renamed: {reason}").format(reason=e.strerror or e))
            return ""
        self._looks_changed()
        self.settingsChanged.emit()
        return new_id

    @Slot(str)
    def deleteLook(self, look_id: str) -> None:
        look = next((x for x in self._look_list() if x["id"] == look_id), None)
        try:
            self._library.delete(look_id)
        except OSError as e:
            self.lookProblem.emit(_("The look couldn't be deleted: {reason}").format(reason=e.strerror or e))
            return
        self._looks_changed()
        self.settingsChanged.emit()
        if look is not None:
            self.noticed.emit(_("Deleted “{name}”").format(name=look["name"]))

    @Slot(str, result=str)
    def lookFileName(self, look_id: str) -> str:
        return f"{look_id or 'look'}.json"

    @Property(str, constant=True)
    def looksFolder(self) -> str:
        """Where the file dialogs start: Documents when there is one, else the home folder."""
        docs = self._env.home / "Documents"
        return QUrl.fromLocalFile(str(docs if docs.is_dir() else self._env.home)).toString()

    @staticmethod
    def _local(url: Any) -> Path | None:
        u = url if isinstance(url, QUrl) else QUrl(str(url))
        if not u.isValid() or not u.isLocalFile():
            text = str(url)
            return Path(text) if text.startswith("/") else None
        return Path(u.toLocalFile())

    @Slot(str, "QVariant", result=bool)
    def exportLook(self, look_id: str, url: Any) -> bool:
        dest = self._local(url)
        if dest is None:
            self.lookProblem.emit(_("Pick a file on this PC to save the look in."))
            return False
        # The dialog adds ".json" itself (defaultSuffix) and asks before it replaces a file,
        # so the name it gives is the one to use: adding ".json" here could replace another
        # file nobody was asked about (foo.txt confirmed, foo.txt.json replaced). Only a bare
        # name (a dialog that doesn't add it) gets ".json", and only when that is no file yet.
        if not dest.suffix:
            named = dest.with_name(dest.name + ".json")
            if not os.path.lexists(named):
                dest = named
        try:
            self._library.export(look_id, dest)
        except looks_mod.LookError as e:
            self.lookProblem.emit(str(e))
            return False
        self.noticed.emit(_("Saved as {path}").format(path=_tilde(str(dest), str(self._env.home))))
        return True

    @Slot("QVariant", result=str)
    def importLook(self, url: Any) -> str:
        """Add a look from a file (someone else's, perhaps): it only becomes a tile; picking
        it puts it in the editor. Its id, or "" (lookProblem says why)."""
        src = self._local(url)
        if src is None:
            self.lookProblem.emit(_("Pick a look file on this PC."))
            return ""
        try:
            name, values = looks_mod.read_file(src)
            look_id = self._library.add(name, values)
        except looks_mod.LookError as e:
            self.lookProblem.emit(str(e))
            return ""
        except OSError as e:
            self.lookProblem.emit(_("The look couldn't be added: {reason}").format(reason=e.strerror or e))
            return ""
        self._looks_changed()
        added = next((x["name"] for x in self._look_list() if x["id"] == look_id), name)
        self.noticed.emit(_("Added “{name}”. Pick it to try it.").format(name=added))
        return look_id

    # ---- unapplied changes in plain words -------------------------------------------------
    def _change_rows(self) -> list[dict]:
        names = {t["id"]: t["name"] for t in self._targets}
        return changes_mod.change_rows(self._s, self._saved, has_dash_to_panel=self.hasDashToPanel,
                                       target_names=names, system_accent=self._system_accent or "blue")

    @Property("QVariantList", notify=settingsChanged)
    def changeList(self) -> list[dict]:
        """Every unapplied change: {"page", "name", "label", "before", "after", "key"}, in
        page order. "name" is the control to go to on that page ("" for none)."""
        return self._change_rows() if self.dirty else []

    @Property("QStringList", notify=settingsChanged)
    def changedPages(self) -> list[str]:
        """The pages that have unapplied changes (the sidebar puts a dot on each)."""
        out: list[str] = []
        for r in self.changeList:
            if r["page"] not in out:
                out.append(r["page"])
        return out

    # ---- one Apply back ----------------------------------------------------------------
    def _keep_previous(self, before: Settings, before_at: float, step: str) -> None:
        """After an Apply: the look applied until then becomes the one to go back to. Only a
        look that was applied counts (not the defaults of a first start), and only when
        this Apply changed it, so pressing Apply twice doesn't lose the way back."""
        now = time.time()
        applied_before = before_at > 0
        self._saved_at = now
        if not applied_before or _effective(before) == _effective(self._saved):
            return
        try:
            settings_mod.save_previous(before, before_at, forward=(step == "back"), path=self._path)
        except OSError:
            return      # the way back is a nicety: never a reason for Apply to fail
        self._previous = settings_mod.load_previous(self._path)
        self.previousChanged.emit()

    @Property(bool, notify=previousChanged)
    def hasPrevious(self) -> bool:
        return self._previous is not None

    @Property(bool, notify=previousChanged)
    def previousIsForward(self) -> bool:
        """The kept look is the one the user went back from: the button goes forward again."""
        return bool(self._previous and self._previous.forward)

    @Property(str, notify=previousChanged)
    def previousWhen(self) -> str:
        """When the kept look was applied, as people say it ("today at 14:05")."""
        if self._previous is None or self._previous.applied_at <= 0:
            return ""
        t = time.localtime(self._previous.applied_at)
        today = time.localtime()
        clock = time.strftime("%H:%M", t)
        if (t.tm_year, t.tm_yday) == (today.tm_year, today.tm_yday):
            return _("today at {time}").format(time=clock)
        yesterday = time.localtime(time.time() - 86400)
        if (t.tm_year, t.tm_yday) == (yesterday.tm_year, yesterday.tm_yday):
            return _("yesterday at {time}").format(time=clock)
        day = time.strftime("%d %B" if t.tm_year == today.tm_year else "%d %B %Y", t).lstrip("0")
        return _("on {day} at {time}").format(day=day, time=clock)

    @Slot()
    def goToPrevious(self) -> None:
        """Put the kept look in the editor and apply it: one click, then the usual results.
        That Apply keeps the look it replaces, so the button then offers the way forward."""
        p = self._previous
        if p is None or self._removing or self.busy:
            return      # (a background check still running is fine: Apply waits for it)
        s = replace(p.settings, targets=dict(p.settings.targets), undo_on_remove=self._saved.undo_on_remove)
        self._apply_step = "forward" if p.forward else "back"
        self._replace_editor(s)
        self.apply()

    # ---- colours from the wallpaper ----------------------------------------------------
    def _match_path(self, s: Settings | None = None, dark: bool | None = None) -> str:
        """The picture GNOME shows with this look's style (picture-uri-dark in dark)."""
        s = s or self._s
        if dark is None:
            dark = self._system_dark if s.scheme == "auto" else s.scheme == "dark"
        url = self._wallpaper_for(dark)
        return QUrl(url).toLocalFile() if url else ""

    def _known_colours(self, path: str) -> dict | None:
        c = self._wall_colours.get(path)
        return c if c is not None and c["key"] == wallcolour.picture_key(path) else None

    def _hand_picked(self, name: str) -> dict:
        """A tint or accent picked by hand while it matched the wallpaper: it stops matching."""
        if self._matching:
            return {}
        if name == "tint" and self._s.tint_from_wallpaper:
            return {"tint_from_wallpaper": False, "tint_own": ""}
        if name == "accent" and self._s.accent_from_wallpaper:
            return {"accent_from_wallpaper": False, "accent_own": ""}
        return {}

    def _use_colours(self, c: dict) -> None:
        """Put the wallpaper's colours in the editor, for the switches that are on."""
        values = {}
        if self._s.tint_from_wallpaper and c.get("tint"):
            values["tint"] = c["tint"]
        if self._s.accent_from_wallpaper and c.get("accent"):
            values["accent"] = c["accent"]
        if values:
            self._matching = True
            try:
                for k, v in values.items():
                    self._set(k, v)
            finally:
                self._matching = False

    def _match_wallpaper(self) -> None:
        """For the preview: take the wallpaper's colours now, or once they are worked out."""
        if not (self._s.tint_from_wallpaper or self._s.accent_from_wallpaper):
            return
        path = self._match_path()
        if not path:
            self.wallpaperMatchChanged.emit()
            return
        c = self._known_colours(path)
        if c is not None:
            self._use_colours(c)
            return
        if path in self._wall_tasks:
            return
        task = _Task(lambda _report: wallcolour.colours_of(path), self)
        task.finishedWith.connect(self._wall_colours_done)
        self._wall_tasks[path] = task
        self.wallpaperMatchChanged.emit()
        task.start()

    @Slot(object)
    def _wall_colours_done(self, out: Any) -> None:
        task = self.sender()
        path = next((p for p, t in self._wall_tasks.items() if t is task), None)
        if path is None:
            return
        del self._wall_tasks[path]
        task.wait()
        task.deleteLater()
        self._wall_colours[path] = out if isinstance(out, dict) else \
            {"key": wallcolour.picture_key(path), "tint": "", "accent": "", "unreadable": True}
        if path == self._match_path():
            self._use_colours(self._wall_colours[path])
        self.wallpaperMatchChanged.emit()

    def _take_wallpaper_colours(self) -> bool:
        """Before Apply: the colours of the picture shown now go into the look (and the
        picture is noted, to tell when it changes). False: they are being worked out, and
        Apply starts again once they are."""
        if not (self._s.tint_from_wallpaper or self._s.accent_from_wallpaper):
            return True
        path = self._match_path()
        if not path:
            return True     # no picture (a plain colour background): the colours stay as they are
        c = self._known_colours(path)
        if c is None:
            def done(out: Any) -> None:
                self._wall_colours[path] = out if isinstance(out, dict) else \
                    {"key": wallcolour.picture_key(path), "tint": "", "accent": "", "unreadable": True}
                self.wallpaperMatchChanged.emit()
                self.apply()

            def job(report):
                report(0.02, _("your wallpaper's colour"))
                return wallcolour.colours_of(path)
            if not self._run("apply", job, done):
                self._lock_after_apply = False
            return False
        self._use_colours(c)
        mark = c["key"] + ("|dark" if self._match_dark() else "|light")
        if mark != self._s.wallpaper_match:
            self._s = replace(self._s, wallpaper_match=mark)
        return True

    def _match_dark(self, s: Settings | None = None) -> bool:
        s = s or self._s
        return self._system_dark if s.scheme == "auto" else s.scheme == "dark"

    def _get_tint_from_wallpaper(self) -> bool:
        return self._s.tint_from_wallpaper

    def _set_tint_from_wallpaper(self, on: bool) -> None:
        self._set_matching("tint", bool(on))

    def _get_accent_from_wallpaper(self) -> bool:
        return self._s.accent_from_wallpaper

    def _set_accent_from_wallpaper(self, on: bool) -> None:
        self._set_matching("accent", bool(on))

    def _set_matching(self, what: str, on: bool) -> None:
        flag, own = f"{what}_from_wallpaper", f"{what}_own"
        if getattr(self._s, flag) == on:
            return
        if on:
            # What the user had, to put back when the switch goes off again.
            s = replace(self._s, **{flag: True, own: getattr(self._s, what)})
        else:
            back = getattr(self._s, own) or getattr(self._s, what)
            s = replace(self._s, **{flag: False, own: "", what: back})
        self._replace_editor(s.normalized())
        self._match_wallpaper()

    tintFromWallpaper = Property(bool, _get_tint_from_wallpaper, _set_tint_from_wallpaper, notify=settingsChanged)
    accentFromWallpaper = Property(bool, _get_accent_from_wallpaper, _set_accent_from_wallpaper, notify=settingsChanged)

    @Property(bool, notify=wallpaperMatchChanged)
    def wallpaperMatchBusy(self) -> bool:
        return self._match_path() in self._wall_tasks

    @Property(str, notify=wallpaperMatchChanged)
    def wallpaperMatchNote(self) -> str:
        """Why the colour can't follow the wallpaper here, or "" when it can."""
        if not (self._s.tint_from_wallpaper or self._s.accent_from_wallpaper):
            return ""
        path = self._match_path()
        if not path:
            return _("There's no wallpaper picture to take a colour from, so the colour stays as it is.")
        c = self._known_colours(path)
        if c is not None and c.get("unreadable"):
            return _("Fedora Glass can't read this wallpaper's picture, so the colour stays as it is.")
        if c is not None and not c["tint"]:
            return _("Your wallpaper has hardly any colour in it, so the colour stays as it is.")
        return ""

    @Property(bool, notify=wallpaperMatchChanged)
    def wallpaperChangedSince(self) -> bool:
        """The applied look follows the wallpaper, and the picture is not the one its
        colours came from: Apply takes them again."""
        saved = self._saved
        if not (saved.tint_from_wallpaper or saved.accent_from_wallpaper) or not saved.wallpaper_match:
            return False
        # The key notes which style's picture it was taken from ("|dark" / "|light"); 1.5.24
        # saved none, and those are compared with the picture of the style showing now.
        key, dark = saved.wallpaper_match, None
        for tag in ("|dark", "|light"):
            if key.endswith(tag):
                key, dark = key[:-len(tag)], tag == "|dark"
        return wallcolour.picture_key(self._match_path(saved, dark)) != key

    # ---- plumbing for tests ----------------------------------------------------------
    def settings(self) -> Settings:
        return self._s

    def settings_dict(self) -> dict:
        return asdict(self._s)


def _header_key(s: Settings) -> tuple:
    """What the header bar style sheet depends on, to tell when Apply changed it."""
    s = s.normalized()
    return (s.header_height, None if s.reduce_transparency else s.header_opacity)


def _tilde(text: str, home: str) -> str:
    """Show paths under the home folder as ~/…, the way people read them."""
    return text.replace(home.rstrip("/") + "/", "~/") if home and home != "/" else text


def _close(a: Any, b: Any) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(float(a) - float(b)) < 0.005
    return a == b


SETTING_FIELDS = tuple(f.name for f in fields(Settings))
