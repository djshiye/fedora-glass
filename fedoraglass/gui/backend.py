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
import secrets
import stat
import time
from collections.abc import Callable
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QFileSystemWatcher, QObject, QProcess, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QIcon

from .. import APP_ID, distro, login_screen, palette
from .. import settings as settings_mod
from ..color import Color
from ..env import Env
from ..settings import GNOME_ACCENTS, PRESETS, Settings

GROUP_ORDER = ("Desktop", "Panel", "Apps", "Terminal", "My apps")

# The windows the preview opens, so their dock icons get a "running" dot.
RUNNING_APPS = ("org.gnome.Nautilus", "org.gnome.Ptyxis")

DOCK_EXTENSIONS = ("dash-to-dock@micxgx.gmail.com", "ubuntu-dock@ubuntu.com")
MENU_EXTENSIONS = ("arcmenu@arcmenu.com", "spawn@djshiye.github.io")
DASH_TO_PANEL = "dash-to-panel@jderose9.github.com"
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


def _effective(s: Settings) -> dict:
    """What a Settings really does, so a switch flipped off and on again, or a motion picked and
    then set back to its default, doesn't count as an unapplied change."""
    d = asdict(s)
    d["targets"] = sorted(k for k, v in s.targets.items() if not v)
    d["motion"] = {ev: s.motion_for(ev) for ev in settings_mod.MOTION_EVENTS}
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
    weatherChanged = Signal()
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

    def __init__(self, *, env: Env | None = None, engine_factory: Callable[[], Any] | None = None,
                 settings_path: Path | None = None, ui_dark: bool | None = None,
                 start: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        self._env = env or Env()
        self._engine_factory = engine_factory or self._default_engine
        self._engine: Any = None
        self._path = settings_path
        self._saved = settings_mod.load(settings_path)
        # First run: no saved settings and the welcome never dismissed. Asked once, at start.
        self._first_run = not self._settings_file().exists() and not self._welcome_marker().exists()
        self._s = replace(self._saved, targets=dict(self._saved.targets))
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
        self._login_state = self._read_login_state()
        # Removing the app (Restore original, then dnf remove through pkexec).
        self._remove_proc: QProcess | None = None
        self._removing = False
        self._remove_package = self._installed_package()
        self._terminal_pal = ""
        self._motion_state = {"animations": True, "dtpHover": False}
        self._has_dock = False      # Dash to Dock or Ubuntu Dock switched on (the preview draws it)
        self._has_menu = False      # ArcMenu or Spawn switched on
        self._has_dtp = False       # Dash to Panel switched on
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
        self._wallpaper = self._find_wallpaper()
        self._wallpaper_luma: float | None = None
        self._power_supply = Path("/sys/class/power_supply")
        self._dock = self._find_dock()
        self._rebuild_tokens()
        if start:
            self.refreshTargets()
            self._watch_scheme()
            self._safe_timer.start()
            self._start_speed_watch()

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
        why = {"restarts": "GNOME Shell restarted twice right after starting it",
               "start": "it could not start",
               "errors": "it hit errors"}.get(self._safe.get("reason", ""), "it hit errors")
        return f"Glass is paused because {why}. Your desktop works as usual."

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

    def _find_wallpaper(self) -> str:
        try:
            p = self._env.wallpaper()
        except Exception:
            p = None
        return QUrl.fromLocalFile(str(p)).toString() if p else ""

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
        self._dark_t = palette.build(s, dark=True, system_accent=self._system_accent)
        self._light_t = palette.build(s, dark=False, system_accent=self._system_accent)
        auto = replace(s, opacity=None, blur=None, terminal_opacity=None)
        a = palette.build(auto, dark=self._preview_dark, system_accent=self._system_accent)
        self._auto = {"opacity": round(a.chrome.a, 2), "blur": a.blur_radius,
                      "terminal_opacity": a.terminal_opacity}
        self._maps = (tokens_map(self._dark_t), tokens_map(self._light_t))
        self.tokensChanged.emit()

    def _changed(self) -> None:
        self._rebuild_tokens()
        self.settingsChanged.emit()

    def _set(self, name: str, value: Any) -> None:
        if getattr(self._s, name) == value:
            return
        try:
            s = replace(self._s, **{name: value}).normalized()
        except (TypeError, ValueError):
            return
        if s == self._s:
            return
        self._s = s
        if name == "scheme" and self._effective_dark() != self._preview_dark:
            self._preview_dark = self._effective_dark()   # show the style just picked
            self.previewChanged.emit()
        self._changed()

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
        if self._monitor is not None:
            self._monitor.kill()
            self._monitor.waitForFinished(500)
            self._monitor = None

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
    def _get_start_on_desktop(self) -> bool:
        # Not chosen yet: as Apply will decide it for this desktop (Settings.start_on_desktop_for).
        return self._s.start_on_desktop_for(self.hasDashToPanel)

    def _set_start_on_desktop(self, v: bool) -> None:
        self._set("start_on_desktop", bool(v))

    startOnDesktop = Property(bool, _get_start_on_desktop, _set_start_on_desktop, notify=settingsChanged)
    overviewOff = _p("overview_off", bool)
    motionDtpHoverOff = _p("motion_dtp_hover_off", bool)
    hoverGlide = _p("hover_glide", bool)
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
        return v if v in ("setting", "slow", "retry", "check") else ""

    def _get_speed_state(self) -> str:
        return self._speed_state

    def _get_speed_result(self) -> dict:
        return dict(self._speed_result)

    speedLevel = Property(str, _get_speed_level, notify=speedChanged)
    speedReason = Property(str, _get_speed_reason, notify=speedChanged)
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
        return _effective(self._s) != _effective(self._saved.normalized())

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

    @Property("QVariantList", constant=True)
    def accents(self) -> list[dict]:
        return [{"id": k, "color": v, "label": k.capitalize()} for k, v in GNOME_ACCENTS.items()]

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

    @Slot()
    def resetDefaults(self) -> None:
        s = Settings(targets=dict(self._s.targets))
        if s != self._s:
            was_dark = self._effective_dark()
            self._s = s
            if self._effective_dark() != was_dark:
                self._preview_dark = self._effective_dark()
                self.previewChanged.emit()
            self._changed()

    @Slot()
    def discardChanges(self) -> None:
        self._s = replace(self._saved, targets=dict(self._saved.targets))
        self._preview_dark = self._effective_dark()
        self.previewChanged.emit()
        self._changed()
        self.targetsChanged.emit()   # the app switches and the glass edges follow the saved state

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

    @Property(str, constant=True)
    def wallpaper(self) -> str:
        return self._wallpaper

    @Property(float, constant=True)
    def wallpaperLuma(self) -> float:
        """How bright the wallpaper is on average (0..1, linear), for the lock screen preview,
        which darkens a bright picture the way the lock glass's brightness ceiling does."""
        if self._wallpaper_luma is None:
            self._wallpaper_luma = _average_luma(QUrl(self._wallpaper).toLocalFile()) if self._wallpaper else 0.2
        return self._wallpaper_luma

    @Property(bool, constant=True)
    def hasBattery(self) -> bool:
        """Whether this PC has a battery of its own (a laptop), for the lock screen's battery widget."""
        return _has_battery(self._power_supply)

    @Property(str, notify=weatherChanged)
    def weatherState(self) -> str:
        """For the lock screen's weather switch: "ready", "no-app" or "no-place"."""
        if getattr(self, "_weather_state", None) is None:
            self._weather_state = _weather_state(self._env)
        return self._weather_state

    @Slot()
    def refreshWeather(self) -> None:
        """Look again (the window just regained focus): GNOME Weather may have been installed
        or a place chosen meanwhile."""
        new = _weather_state(self._env)
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
    def hostName(self) -> str:
        import socket
        return socket.gethostname().split(".")[0] or "fedora"

    @Property("QVariantList", constant=True)
    def dock(self) -> list[dict]:
        return self._dock

    # ---- targets -------------------------------------------------------------------
    @Property("QVariantList", notify=targetsChanged)
    def targets(self) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for t in self._targets:
            item = dict(t, enabled=self._s.target_enabled(t["id"]))
            groups.setdefault(t["group"], []).append(item)
        order = sorted(groups, key=lambda g: (GROUP_ORDER.index(g) if g in GROUP_ORDER else 99, g))
        return [{"group": g, "items": groups[g]} for g in order]

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

    @Property(int, notify=targetsChanged)
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

    @Property(bool, notify=targetsChanged)
    def hasBackup(self) -> bool:
        return self._has_backup

    @Property(str, notify=targetsChanged)
    def lostNote(self) -> str:
        """One line when another app (a theme update, say) replaced files Apply wrote, or ""."""
        if not self._lost:
            return ""
        what = self._lost[0] if len(self._lost) == 1 else ", ".join(self._lost[:-1]) + " and " + self._lost[-1]
        return f"Another app replaced the Fedora Glass look for {what}. Apply again to bring it back."

    @Slot(str, bool)
    def setTargetEnabled(self, target_id: str, on: bool) -> None:
        if self._s.target_enabled(target_id) == bool(on):
            return
        targets = dict(self._s.targets)
        targets[target_id] = bool(on)
        self._s = replace(self._s, targets=targets)
        self._rebuild_tokens()   # the glass target decides which edges the theme draws
        self.settingsChanged.emit()
        self.targetsChanged.emit()

    @Property("QVariantMap", notify=targetsChanged)
    def targetStates(self) -> dict:
        """Target id -> on, for the preview (a missing id is on)."""
        return {k: bool(v) for k, v in self._s.targets.items()}

    @Slot()
    def refreshTargets(self) -> None:
        s = self._s.normalized()

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
                    available, detail = False, f"Could not check: {e}"
                out.append({"id": t.id, "name": t.name, "group": t.group or "Apps",
                            "summary": t.summary, "notes": notes,
                            "available": available, "detail": detail})
            names = {t["id"]: t["name"] for t in out}
            lost = [names.get(tid, tid) for tid in self._overwritten(engine)]
            return (out, self._backup_exists(engine), self._glass_running(engine), self._terminal_palette(engine),
                    lost, self._motion_env(engine), self._extensions_on(engine))
        self._run("detect", job, self._targets_done, show_busy=False)

    @staticmethod
    def _extensions_on(engine: Any) -> tuple[bool, bool, bool]:
        """Whether a dock (Dash to Dock, Ubuntu Dock), a start menu (ArcMenu, Spawn) and
        Dash to Panel are installed and switched on: the same rule as Apply (Env.extension_on)."""
        try:
            env = engine.env
            def any_on(uuids: tuple[str, ...]) -> bool:
                return any(env.extension_on(u) for u in uuids)
            return any_on(DOCK_EXTENSIONS), any_on(MENU_EXTENSIONS), any_on((DASH_TO_PANEL,))
        except Exception:
            return False, False, False

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
        if isinstance(out, Exception):
            self._targets, self._has_backup = [], False
            self.failed.emit(f"Could not load targets: {out}")
        else:
            (self._targets, self._has_backup, self._glass_live, self._terminal_pal, self._lost,
             self._motion_state, (self._has_dock, self._has_menu, self._has_dtp)) = out
        self._targets_ready = True
        self.targetsChanged.emit()

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
        return {"apply": "apply", "revert": "revert", "requestPlan": "plan"}.get(self._pending_action or "", "")

    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return bool(self._busy or self._queued_kind())

    @Property(str, notify=busyChanged)
    def busyKind(self) -> str:
        return self._busy or self._queued_kind()

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
        if self._task is not None:
            self._pending_action = self._pending_action or "requestPlan"
            self.busyChanged.emit()
            return
        s = self._s.normalized()

        def job(report):
            engine = self._engine_obj()
            names = {t.id: t.name for t in engine.targets}
            home = str(engine.env.home)
            report(0.1, "Planning")
            plan = engine.plan(s)
            return [{"id": tid, "name": names.get(tid, tid),
                     "actions": [{"kind": type(a).__name__, "text": _tilde(a.describe(), home)} for a in actions]}
                    for tid, actions in plan.items()]

        def done(out):
            if isinstance(out, Exception):
                self.failed.emit(f"Could not work out the changes: {out}")
            else:
                self.planReady.emit(out)
        self._run("plan", job, done)

    @Slot()
    def apply(self) -> None:
        if self._task is not None:
            # Still checking the system in the background: apply as soon as that ends.
            self._pending_action = "apply"
            self.busyChanged.emit()
            return
        s = self._s.normalized()
        header_changed = _header_key(s) != _header_key(self._saved)
        try:
            settings_mod.save(s, self._path)
        except OSError as e:
            self.failed.emit(f"Could not save settings: {e}")
            return
        self._saved = s
        self.settingsChanged.emit()
        self.savedChanged.emit()

        def job(report):
            engine = self._engine_obj()
            ts = list(engine.targets)
            if not ts:
                report(0.5, "Writing tokens")
                return [], self._backup_exists(engine)
            results = {}
            for i, t in enumerate(ts):
                report(i / len(ts), t.name)
                # Switching the glass on can finish parts that waited for it a step
                # earlier (the Shell theme): the latest result for a part counts.
                for r in engine.apply(s, only={t.id}):
                    results[r.target] = r
            report(1.0, "Done")
            return list(results.values()), self._backup_exists(engine)

        def done(out):
            if isinstance(out, Exception):
                self.failed.emit(f"Apply stopped: {out}")
                return
            results, self._has_backup = out
            self.targetsChanged.emit()
            self.refreshTargets()          # the glass may be live now, and notes change
            if header_changed:
                self._set_header_note("pending")
            self.applyFinished.emit([{"id": r.target, "name": r.name, "status": r.status,
                                      "message": r.message} for r in results])
            # Apply brings the login screen along when its glass is on: new colours, or the
            # rules of a newer Fedora Glass. It changes a system file, so this asks for the password.
            self._login_state = self._read_login_state()
            if self._login_stale(s):
                self._run_login(["apply", *self.login_values(s)],
                                "The login screen has your new look. You'll see it the next time you restart your PC.")
            else:
                self.loginGlassChanged.emit()
        self._run("apply", job, done)

    @Slot()
    def revert(self) -> None:
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
            report(0.3, "Restoring")
            problems = engine.revert()
            return list(problems), self._backup_exists(engine)

        def done(out):
            if isinstance(out, Exception):
                self.failed.emit(f"Restore stopped: {out}")
                return
            problems, self._has_backup = out
            self._glass_live = False
            self._lost = []
            self.targetsChanged.emit()
            if header_changed:
                self._set_header_note("pending")
            self.revertFinished.emit(problems)
        self._run("revert", job, done)

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
            self.failed.emit("Could not restart Files. Close all Files windows, or restart your PC instead.")
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

    @Slot()
    def turnOnLoginGlass(self) -> None:
        self._run_login(["apply", *self.login_values()], "Glass is on the login screen. You'll see it the next time you restart your PC.")

    @Slot()
    def turnOffLoginGlass(self) -> None:
        self._run_login(["undo"], "The normal login screen is back.")

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
            self._login_note = "Not changed: the password wasn't given."
        else:
            first = err.splitlines()[-1] if err else "the helper didn't finish"
            self._login_note = first if first.startswith("Nothing was changed") else f"Nothing was changed: {first}"
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
        try:
            settings_mod.save(saved, self._path)
        except OSError as e:
            self.failed.emit(f"Could not save settings: {e}")
            return
        self._saved = saved
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

    @Property(bool, constant=True)
    def canRemoveApp(self) -> bool:
        return bool(self._remove_package)

    @Property(bool, notify=removingChanged)
    def removing(self) -> bool:
        return self._removing

    def _set_removing(self, on: bool) -> None:
        if on != self._removing:
            self._removing = on
            self.removingChanged.emit()

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
            report(0.3, "Restoring")
            problems = engine.revert()
            return list(problems), self._backup_exists(engine)

        def done(out):
            if isinstance(out, Exception):
                self._set_removing(False)
                self.failed.emit(f"Restore stopped, so Fedora Glass was not removed: {out}")
                return
            problems, self._has_backup = out
            self._lost = []
            self.targetsChanged.emit()
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
            self.failed.emit("Your original look is back, but Fedora Glass was not removed: the password wasn't given.")
        else:
            last = err.splitlines()[-1] if err else f"{distro.current().tool_name} did not finish"
            self.failed.emit(f"Your original look is back, but removing Fedora Glass failed: {last}")
        self.removeFinished.emit(False)

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
