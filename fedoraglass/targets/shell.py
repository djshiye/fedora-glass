"""GNOME Shell and its extensions: User Themes CSS, our glass extension, Dash to Panel, ArcMenu, Spawn."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from .. import distro
from ..env import Env
from ..render import glass as rg
from ..render import shell as rs
from .base import Action, Context, Detection, GReset, GSet, ListEdit, Target, WriteFile

USER_THEME = "user-theme@gnome-shell-extensions.gcampax.github.com"
BLUR = "blur-my-shell@aunetx"
DASH_TO_PANEL = "dash-to-panel@jderose9.github.com"
ARCMENU = "arcmenu@arcmenu.com"
SPAWN = "spawn@djshiye.github.io"
JUST_PERFECTION = "just-perfection-desktop@just-perfection"
THEME_NAME = "FedoraGlass"



def _need_extension(env: Env, uuid: str, label: str, package: str) -> Detection:
    if env.extension_path(uuid) is None:
        return Detection(False, f"{label} is not installed ({package})")
    return Detection(True)


def _need_extension_on(env: Env, uuid: str, label: str, package: str) -> Detection:
    """For an extension we theme but never switch on ourselves (Dash to Panel, ArcMenu,
    Spawn): one that is installed but switched off is not part of this desktop. Their
    look needs the glass behind it, as the Shell theme's does (see _waits_for_glass)."""
    # Extensions switched off altogether: said as such, not as "switched off" for each one.
    d = _waits_for_glass(env, _need_extension(env, uuid, label, package))
    if d.available and not env.extension_on(uuid):
        return Detection(False, f"{label} is installed but switched off")
    return d


def _gset(schema: str, values: dict[str, str]) -> list[Action]:
    return [GSet(schema, k, v) for k, v in values.items()]


@dataclass
class GnomeShell(Target):
    id: str = "shell"
    name: str = "GNOME Shell"
    plain: str = "Turns on the User Themes extension and selects the Fedora Glass theme for menus and pop-ups."
    waits_for_glass: bool = True
    group: str = "Desktop"
    summary: str = "Glass menus, quick settings, calendar, notifications, dialogs, OSD and overview, as a Shell theme."
    notes: list[str] = field(default_factory=lambda: [
        "Needs the User Themes extension (enabled automatically when installed).",
        "Surfaces are translucent; the glass behind them comes from Fedora Glass effects."])

    def detect(self, env: Env) -> Detection:
        det = _need_extension(env, USER_THEME, "User Themes", "gnome-shell-extension-user-theme")
        how = "" if det.available else distro.hint("user-theme")
        return Detection(False, f"Install the User Themes extension: {how}") if how else _waits_for_glass(env, det)

    def css_path(self, env: Env):
        return env.data / "themes" / THEME_NAME / "gnome-shell/gnome-shell.css"

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        css = rs.render_css(ctx.tokens)
        path = self.css_path(env)
        try:
            unchanged = path.read_text(encoding="utf-8") == css
        except OSError:
            unchanged = False
        acts: list[Action] = [WriteFile(path, css)]

        acts.append(ListEdit("org.gnome.shell", "enabled-extensions", add=(USER_THEME,)))
        acts.append(ListEdit("org.gnome.shell", "disabled-extensions", remove=(USER_THEME,)))

        schema = "org.gnome.shell.extensions.user-theme"
        if not unchanged and (env.gsettings_get(schema, "name") or "").strip("'") == THEME_NAME:
            # User Themes only reloads when the name changes, so bounce it to pick up new CSS.
            acts.append(GSet(schema, "name", "''"))
        acts.append(GSet(schema, "name", f"'{THEME_NAME}'"))
        return acts


@dataclass
class GlassEffects(Target):
    id: str = "glass"
    name: str = "Fedora Glass effects"
    plain: str = ("Installs the Fedora Glass extension for GNOME and turns it on. "
                  "It draws the live glass behind your panel, menus and overview.")
    group: str = "Desktop"
    summary: str = ("Real glass behind the panel or dock, menus, quick settings, app windows and the overview: "
                    "live blur, a refracting rim, rim light and a rainbow edge.")
    notes: list[str] = field(default_factory=lambda: [
        "Uses Fedora Glass's own GNOME Shell extension; Blur my Shell isn't needed."])

    BLUR_SCHEMA = "org.gnome.shell.extensions.blur-my-shell"
    # Blur my Shell parts that would draw a second blur over ours.
    BLUR_OVERLAP = ("panel", "popup", "overview", "appfolder", "applications", "dash-to-panel", "dash-to-dock")

    def detect(self, env: Env) -> Detection:
        if env.which("gnome-shell") is None:
            return Detection(False, "GNOME Shell is not installed")
        return Detection(True)

    def ext_dir(self, env: Env):
        return env.data / "gnome-shell/extensions" / rg.UUID

    def config_path(self, env: Env):
        return env.config / "liquid-glass/shell-glass.json"

    @staticmethod
    def resolved(ctx: Context):
        """The settings with "start on the desktop" decided for this desktop (see Settings)."""
        s = ctx.settings
        if s.start_on_desktop is not None:
            return s
        return replace(s, start_on_desktop=s.start_on_desktop_for(ctx.env.extension_on(DASH_TO_PANEL)))

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        d = self.ext_dir(env)
        acts: list[Action] = [WriteFile(d / name, text) for name, text in rg.extension_files().items()]
        acts.append(WriteFile(self.config_path(env), rg.render_config(self.resolved(ctx), ctx.tokens)))
        acts.append(ListEdit("org.gnome.shell", "enabled-extensions", add=(rg.UUID,)))
        acts.append(ListEdit("org.gnome.shell", "disabled-extensions", remove=(rg.UUID,)))
        # Blur my Shell keeps blurring until our glass is there to take over.
        if ctx.glass_running and env.extension_path(BLUR) is not None:
            acts += [GSet(f"{self.BLUR_SCHEMA}.{part}", "blur", "false") for part in self.BLUR_OVERLAP]
        acts += self._startup_actions(ctx)
        return acts

    # Dash to Panel and Just Perfection each have their own "start on the desktop" option, and
    # each would open the overview again if theirs said otherwise, so theirs follows ours.
    STARTUP_KEYS = ((DASH_TO_PANEL, "org.gnome.shell.extensions.dash-to-panel", "hide-overview-on-startup", "true"),
                    (JUST_PERFECTION, "org.gnome.shell.extensions.just-perfection", "startup-status", "0"))

    def _startup_actions(self, ctx: Context) -> list[Action]:
        s = self.resolved(ctx)
        on = s.start_on_desktop or s.overview_off
        acts: list[Action] = []
        for uuid, schema, key, value in self.STARTUP_KEYS:
            if not ctx.env.extension_on(uuid):
                continue
            acts.append(GSet(schema, key, value, keep_user_change=True) if on else GReset(schema, key))
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        notes = list(self.notes)
        st = glass_state(ctx.env)
        if st.kind == "old":
            notes.append(UPDATE_WAITS)
        elif st.blocked:
            notes.append(GLASS_BLOCKED[st.kind])
        elif st.kind != "running":
            notes.append("Restart your PC once so GNOME Shell starts the Fedora Glass extension. "
                         "The panel, menus, ArcMenu and Spawn switch to glass then. After that, changes show up instantly.")
        return notes

    @staticmethod
    def running(env: Env) -> bool:
        """Whether the Shell runs this version's glass extension. It only finds new ones at
        login, and keeps running the code it started with: after an upgrade the older
        version runs until the next login, and the Shell parts wait for the new one."""
        return glass_state(env).kind == "running"


# Shown while GNOME runs the glass extension of an older Fedora Glass (after an upgrade).
UPDATE_WAITS = "Restart your PC to finish the update. Until then the glass from the older version keeps running."

# Why the glass can't start, when a restart won't fix it: the app's note for each.
GLASS_BLOCKED = {
    "off": "Extensions are switched off in GNOME, so the glass can't start.",
    "out-of-date": "This version of Fedora Glass doesn't support your GNOME version yet. "
                   "Update Fedora Glass to get the glass back.",
    "error": "The glass effects hit an error and stopped. Your desktop works as usual.",
}
# The same, for a Shell part that needs the glass behind it (shown in the Apply results).
GLASS_BLOCKED_PART = {
    "off": "Extensions are switched off in GNOME, so this part can't show. Switch them on, then Apply again.",
    "out-of-date": "Left as it is: this version of Fedora Glass doesn't support your GNOME version yet. "
                   "Update Fedora Glass to fix it.",
    "error": "Left as it is: the glass effects hit an error, and this part needs them.",
}


@dataclass(frozen=True)
class GlassState:
    """What GNOME Shell says about the glass extension. kind:
    "running"      this version runs
    "old"          an older version is loaded (GNOME only loads new code at the next login)
    "off"          extensions are switched off in GNOME altogether
    "out-of-date"  GNOME won't start it: this GNOME isn't in its shell-version list
    "error"        it failed to start (`error` has GNOME's text)
    "not-started"  not running yet: new extensions start at the next login"""
    kind: str
    version: str = ""       # the loaded extension's version-name, when GNOME says
    error: str = ""

    @property
    def blocked(self) -> bool:
        """It won't start by itself, not even after a restart."""
        return self.kind in GLASS_BLOCKED


def _gvariant_str(out: str, key: str) -> str | None:
    # GVariant text quotes a string with ' unless it holds one, then with ".
    m = re.search(rf"""'{re.escape(key)}': <(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")>""", out)
    return (m.group(1) if m.group(1) is not None else m.group(2)) if m else None


def _version_key(v: str) -> tuple[int, ...] | None:
    parts = v.strip().split(".")
    return tuple(int(p) for p in parts) if parts and all(p.isdigit() for p in parts) else None


def older_than_app(version: str) -> bool:
    """True when `version` is an older Fedora Glass than this app. False when either
    can't be read: then nothing changes from before."""
    from .. import __version__
    have, want = _version_key(version), _version_key(__version__)
    return have is not None and want is not None and have < want


# GNOME's extension states (ExtensionState): 1 running, 3 error, 4 out of date.
_RUNNING, _ERROR, _OUT_OF_DATE = 1.0, 3.0, 4.0


def glass_state(env: Env) -> GlassState:
    if env.extensions_switched_off():
        return GlassState("off")
    r = env.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                 "--method", "org.gnome.Shell.Extensions.GetExtensionInfo", rg.UUID], timeout=5)
    if r.code != 0:
        return GlassState("not-started")
    m = re.search(r"'state': <([\d.]+)>", r.out)
    state = float(m.group(1)) if m else None
    version = _gvariant_str(r.out, "version-name") or ""
    if state in (_RUNNING, _ERROR, _OUT_OF_DATE) and older_than_app(version):
        # The older version's code, or its list of GNOME versions: the next login
        # loads this version, which may well start.
        return GlassState("old", version)
    if state == _RUNNING:
        return GlassState("running", version)
    # GNOME also marks an extension that is switched off as out of date or failed:
    # only the glass that is wanted (on GNOME's list) counts.
    if state in (_ERROR, _OUT_OF_DATE) and env.extension_enabled(rg.UUID):
        if state == _OUT_OF_DATE:
            return GlassState("out-of-date", version)
        return GlassState("error", version, _gvariant_str(r.out, "error") or "")
    return GlassState("not-started", version)


def glass_blocked(env: Env) -> str:
    """Why the glass can't start without the user's help ("off", "out-of-date", "error"), or ""."""
    if env.extensions_switched_off():
        return "off"
    if not env.extension_enabled(rg.UUID):
        return ""           # not switched on yet: nothing to ask GNOME
    st = glass_state(env)
    return st.kind if st.blocked else ""


def _waits_for_glass(env: Env, d: Detection) -> Detection:
    """For a Shell part that needs the glass behind it: with a glass that can't start
    (see glass_blocked), it is left as it is, said in plain words, instead of waiting
    for a restart that won't bring the glass."""
    if d.available and (why := glass_blocked(env)):
        return Detection(False, GLASS_BLOCKED_PART[why])
    return d


def glass_problem(env: Env, wanted: bool = True) -> tuple[str, str, str]:
    """For the app: what stands between the user and the glass, as (kind, a short note,
    details to copy), or ("", "", "") when nothing does (or the glass simply waits for
    the first restart, which the app already says). `wanted`: the glass part is on."""
    st = glass_state(env)
    if st.kind == "old":
        return "old", UPDATE_WAITS, ""
    if st.blocked and (wanted or st.kind != "off"):
        return st.kind, GLASS_BLOCKED[st.kind], st.error
    return "", "", ""


def extension_info(env: Env, uuid: str) -> tuple[float | None, str]:
    """The Shell's state for an extension (1 running, 3 failed) and its error text."""
    r = env.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                 "--method", "org.gnome.Shell.Extensions.GetExtensionInfo", uuid], timeout=5)
    if r.code != 0:
        return None, ""
    m = re.search(r"'state': <([\d.]+)>", r.out)
    # GVariant text quotes a string with ' unless it holds one, then with ".
    e = re.search(r"""'error': <(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")>""", r.out)
    return (float(m.group(1)) if m else None), ((e.group(1) or e.group(2) or "") if e else "")


# ArcMenu's own bug (see arcrescue.js): when an extension is switched off, GNOME
# restarts every extension that started after it, in start order, and an ArcMenu
# restarted before Dash to Panel finds no panel and fails until the next login.
# Restore original switches the glass extension off, and by then the glass is not
# there to bring ArcMenu back. So ArcMenu is set aside for that moment and started
# again last, after Dash to Panel.
def _shell_ext(env: Env, method: str, uuid: str) -> None:
    env.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
             "--method", f"org.gnome.Shell.Extensions.{method}", uuid], timeout=5)


def _wait_state(env: Env, uuid: str, done, wait_s: float, step_s: float = 0.1) -> bool:
    waited = 0.0
    while not done(extension_info(env, uuid)[0]):
        if waited >= wait_s:
            return False
        env.sleep(step_s)
        waited += step_s
    return True


def _known_state(env: Env, uuid: str, wait_s: float = 15.0, step_s: float = 0.25) -> float | None:
    """The Shell's state for an extension, asking again while the Shell is too busy to answer
    (reloading the Shell theme on a slow PC can hold it for seconds). None when the Shell
    doesn't know the extension, or never answers."""
    waited = 0.0
    while True:
        r = env.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                     "--method", "org.gnome.Shell.Extensions.GetExtensionInfo", uuid], timeout=5)
        if r.code == 0:
            m = re.search(r"'state': <([\d.]+)>", r.out)
            return float(m.group(1)) if m else None
        if waited >= wait_s:
            return None
        env.sleep(step_s)
        waited += step_s


def park_arcmenu(env: Env) -> bool:
    """Switch ArcMenu off before the glass extension goes. True if it was running."""
    # A missed answer here would leave ArcMenu in place for GNOME's restart, and red.
    if _known_state(env, ARCMENU) != 1.0 or _known_state(env, rg.UUID) != 1.0:
        return False
    _shell_ext(env, "DisableExtension", ARCMENU)
    # A busy desktop can take seconds to switch extensions; GNOME restarts the ones
    # after ArcMenu before it counts as off.
    _wait_state(env, ARCMENU, lambda st: st not in (1.0, 7.0), 15.0)
    return True


def unpark_arcmenu(env: Env) -> None:
    """Start ArcMenu again once the glass extension is off: it then comes after Dash to Panel."""
    # Not just "switching off" (7): GNOME restarts the others only after that, and
    # Dash to Panel must have its panels back. On a busy desktop that takes seconds.
    # No answer (None) is a Shell still busy with it, not "off".
    _wait_state(env, rg.UUID, lambda st: st is not None and st not in (1.0, 7.0), 20.0)
    if _known_state(env, DASH_TO_PANEL, 5.0) is not None:
        _wait_state(env, DASH_TO_PANEL, lambda st: st == 1.0, 10.0)
    _shell_ext(env, "EnableExtension", ARCMENU)
    _wait_state(env, ARCMENU, lambda st: st in (1.0, 3.0), 10.0)

@dataclass
class DashToPanel(Target):
    id: str = "dash-to-panel"
    name: str = "Dash to Panel"
    plain: str = "Sets Dash to Panel's colours, border and hover effect so your panel looks like glass."
    waits_for_glass: bool = True
    group: str = "Panel"
    summary: str = "Glass panel: translucent background, glass border, floating or docked, themed hover and dots."

    SCHEMA = "org.gnome.shell.extensions.dash-to-panel"

    def detect(self, env: Env) -> Detection:
        return _need_extension_on(env, DASH_TO_PANEL, "Dash to Panel", "gnome-shell-extension-dash-to-panel")

    def plan(self, ctx: Context) -> list[Action]:
        acts = _gset(self.SCHEMA, rs.dtp_values(ctx.tokens))
        # Its own hover animation and ours would both move the icons. Only switched off when
        # the user asks in the Motion card; Restore original (or turning that back) brings theirs back.
        s = ctx.settings
        # The gliding highlight (glide.js) stands in for Dash to Panel's own one, so its
        # hover colour is clear. Pressing an icon still shows Dash to Panel's pressed colour.
        if s.hover_glide:
            for i, a in enumerate(acts):
                if isinstance(a, GSet) and a.key == "highlight-appicon-hover-background-color":
                    acts[i] = GSet(self.SCHEMA, a.key, "'rgba(0,0,0,0)'")
        if s.motion_dtp_hover_off and s.motion_for("hover")["preset"] != "off":
            acts.append(GSet(self.SCHEMA, "animate-appicon-hover", "false", keep_user_change=True))
        else:
            acts.append(GReset(self.SCHEMA, "animate-appicon-hover"))
        return acts


@dataclass
class ArcMenu(Target):
    id: str = "arcmenu"
    name: str = "ArcMenu"
    plain: str = "Sets ArcMenu's colours and corners so the menu and its button look like glass."
    waits_for_glass: bool = True
    group: str = "Panel"
    summary: str = "Glass menu and menu button; colours, radius, search pill and hover washes."

    SCHEMA = "org.gnome.shell.extensions.arcmenu"

    def detect(self, env: Env) -> Detection:
        return _need_extension_on(env, ARCMENU, "ArcMenu", "gnome-shell-extension-arcmenu")

    def plan(self, ctx: Context) -> list[Action]:
        return _gset(self.SCHEMA, rs.arcmenu_values(ctx.tokens))


@dataclass
class Spawn(Target):
    """Spawn, the other start menu. Its theme keys are ArcMenu's (same names and types), and it
    has none of ArcMenu's restart bug, so nothing parks it (see park_arcmenu)."""
    id: str = "spawn"
    name: str = "Spawn"
    plain: str = "Sets Spawn's colours and corners so the menu and its button look like glass."
    waits_for_glass: bool = True
    group: str = "Panel"
    summary: str = "Glass menu and menu button; colours, radius, search pill and hover washes."

    SCHEMA = "org.gnome.shell.extensions.spawn"

    def detect(self, env: Env) -> Detection:
        return _need_extension_on(env, SPAWN, "Spawn", "gnome-shell-extension-spawn")

    def plan(self, ctx: Context) -> list[Action]:
        return _gset(self.SCHEMA, rs.arcmenu_values(ctx.tokens))


TARGETS: list[Target] = [GnomeShell(), GlassEffects(), DashToPanel(), ArcMenu(), Spawn()]
