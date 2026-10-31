"""The bridge between the QML customizer and the engine.

Backend owns the Settings being edited, turns them into Tokens on every
change (so the preview follows the slider without a round trip to disk) and
runs everything slow (target detection, planning, apply, revert) on worker
threads so the window never stalls.
"""

from __future__ import annotations

import ast
import configparser
import os
from collections.abc import Callable
from dataclasses import asdict, fields, replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QProcess, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QGuiApplication, QIcon

from .. import APP_ID, palette
from .. import settings as settings_mod
from ..color import Color
from ..env import Env
from ..settings import GNOME_ACCENTS, PRESETS, Settings

GROUP_ORDER = ("Desktop", "Panel", "Apps", "Terminal", "My apps")

# The windows the preview opens, so their dock icons get a "running" dot.
RUNNING_APPS = ("org.gnome.Nautilus", "org.gnome.Ptyxis")

FALLBACK_DOCK = ("org.gnome.Nautilus.desktop", "org.gnome.Ptyxis.desktop")


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


class Backend(QObject):
    settingsChanged = Signal()
    tokensChanged = Signal()
    previewChanged = Signal()
    uiChanged = Signal()
    targetsChanged = Signal()
    busyChanged = Signal()
    progressChanged = Signal()
    savedChanged = Signal()
    planReady = Signal("QVariantList")
    applyFinished = Signal("QVariantList")
    revertFinished = Signal("QVariantList")
    failed = Signal(str)
    headerNoteChanged = Signal()

    def __init__(self, *, env: Env | None = None, engine_factory: Callable[[], Any] | None = None,
                 settings_path: Path | None = None, ui_dark: bool | None = None,
                 start: bool = True, parent: QObject | None = None):
        super().__init__(parent)
        self._env = env or Env()
        self._engine_factory = engine_factory or self._default_engine
        self._engine: Any = None
        self._path = settings_path
        self._saved = settings_mod.load(settings_path)
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
        self._pending_apply = False
        # Set when the last Apply or Restore changed the header bars, so the card can
        # offer to restart Files (it keeps running with the old style sheet).
        self._header_note = ""
        self._terminal_pal = ""
        self._motion_state = {"animations": True, "dtpHover": False}
        self._lost: list[str] = []         # targets whose applied files something else replaced
        # The glass extension follows its config file live, so once it runs the
        # desktop can follow the sliders before Apply.
        self._glass_live = False
        self._live_timer = QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(120)
        self._live_timer.timeout.connect(lambda: self._write_live_glass(self._s))
        self._wallpaper = self._find_wallpaper()
        self._dock = self._find_dock()
        self._rebuild_tokens()
        if start:
            self.refreshTargets()
            self._watch_scheme()

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
                name, url = "Liquid Glass", self._own_icon_url()
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
        if self._glass_live:
            self._live_timer.start()

    def _write_live_glass(self, s: Settings) -> None:
        if not self._glass_live:
            return
        from ..engine import atomic_write
        from ..render import glass as rg
        s = s.normalized()
        dark = s.scheme == "dark" or (s.scheme == "auto" and self._system_dark)
        t = palette.build(s, dark=dark, system_accent=self._system_accent)
        try:
            path = self._env.config / "liquid-glass/shell-glass.json"
            atomic_write(path, rg.render_config(s, t).encode())
        except OSError:
            pass   # the desktop just keeps its last look; Apply reports real problems

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
        # Unapplied changes shown live on the desktop go back to the saved look.
        self._live_timer.stop()
        if self._task is not None:
            self._task.wait(30000)    # let a running Apply or Restore finish first
        if self._glass_live and self._s != self._saved:
            self._write_live_glass(self._saved)
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
    glassPanel = _p("glass_panel", bool)
    glassMenus = _p("glass_menus", bool)
    glassOverview = _p("glass_overview", bool)
    glassSeeWindows = _p("glass_see_windows", bool)
    headerHeight = _p("header_height", int)
    headerOpacity = _p("header_opacity", float, -1.0)   # -1 means "same glass as the window"
    terminalColors = _p("terminal_colors", bool)
    terminalFollowsStyle = _p("terminal_follows_style", bool)
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
    startOnDesktop = _p("start_on_desktop", bool)
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
        return self._s != self._saved.normalized()

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

    @Slot(str, result=bool)
    def isColor(self, value: str) -> bool:
        return settings_mod._is_hex(value)

    # ---- tokens -------------------------------------------------------------------
    def _get_tokens(self) -> dict:
        return self._maps[0] if self._preview_dark else self._maps[1]

    tokens = Property("QVariantMap", _get_tokens, notify=tokensChanged)
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

    @Property(int, notify=targetsChanged)
    def activeTargetCount(self) -> int:
        return sum(1 for t in self._targets if t["available"] and self._s.target_enabled(t["id"]))

    @Property(bool, notify=targetsChanged)
    def hasBackup(self) -> bool:
        return self._has_backup

    @Property(str, notify=targetsChanged)
    def lostNote(self) -> str:
        """One line when another app (a theme update, say) replaced files Apply wrote, or ""."""
        if not self._lost:
            return ""
        what = self._lost[0] if len(self._lost) == 1 else ", ".join(self._lost[:-1]) + " and " + self._lost[-1]
        return f"Another app replaced the Liquid Glass look for {what}. Apply again to bring it back."

    @Slot(str, bool)
    def setTargetEnabled(self, target_id: str, on: bool) -> None:
        if self._s.target_enabled(target_id) == bool(on):
            return
        targets = dict(self._s.targets)
        targets[target_id] = bool(on)
        self._s = replace(self._s, targets=targets)
        self.settingsChanged.emit()
        self.targetsChanged.emit()

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
                    lost, self._motion_env(engine))
        self._run("detect", job, self._targets_done, show_busy=False)

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
            if env.extension_path("dash-to-panel@jderose9.github.com") is not None:
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
             self._motion_state) = out
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
    @Property(bool, notify=busyChanged)
    def busy(self) -> bool:
        return bool(self._busy)

    @Property(str, notify=busyChanged)
    def busyKind(self) -> str:
        return self._busy

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
        if self._pending_apply and self._task is None:
            self._pending_apply = False
            self.apply()

    @Slot(float, str)
    def _on_progress(self, f: float, text: str) -> None:
        self._progress, self._progress_text = f, text
        self.progressChanged.emit()

    @Slot()
    def requestPlan(self) -> None:
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
            self._pending_apply = True
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
            results = []
            for i, t in enumerate(ts):
                report(i / len(ts), t.name)
                results += engine.apply(s, only={t.id})
            report(1.0, "Done")
            return results, self._backup_exists(engine)

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
        self._run("apply", job, done)

    @Slot()
    def revert(self) -> None:
        # From here on the extension's config is the engine's to remove; stop writing it.
        self._live_timer.stop()
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
    def liquidGlassPalette(self) -> str:
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
            self.failed.emit("Could not restart Files. Close all Files windows and log out and back in instead.")
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
