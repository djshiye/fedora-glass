"""GNOME Shell and its extensions: User Themes CSS, our glass extension, Dash to Panel, ArcMenu."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..env import Env
from ..render import glass as rg
from ..render import shell as rs
from .base import Action, Context, Detection, GReset, GSet, ListEdit, Target, WriteFile

USER_THEME = "user-theme@gnome-shell-extensions.gcampax.github.com"
BLUR = "blur-my-shell@aunetx"
DASH_TO_PANEL = "dash-to-panel@jderose9.github.com"
ARCMENU = "arcmenu@arcmenu.com"
JUST_PERFECTION = "just-perfection-desktop@just-perfection"
THEME_NAME = "LiquidGlass"



def _need_extension(env: Env, uuid: str, label: str, package: str) -> Detection:
    if env.extension_path(uuid) is None:
        return Detection(False, f"{label} is not installed ({package})")
    return Detection(True)


def _gset(schema: str, values: dict[str, str]) -> list[Action]:
    return [GSet(schema, k, v) for k, v in values.items()]


@dataclass
class GnomeShell(Target):
    id: str = "shell"
    name: str = "GNOME Shell"
    group: str = "Desktop"
    summary: str = "Glass menus, quick settings, calendar, notifications, dialogs, OSD and overview, as a Shell theme."
    notes: list[str] = field(default_factory=lambda: [
        "Needs the User Themes extension (enabled automatically when installed).",
        "Surfaces are translucent; the glass behind them comes from Liquid Glass effects."])

    def detect(self, env: Env) -> Detection:
        return _need_extension(env, USER_THEME, "User Themes", "gnome-shell-extension-user-theme")

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
    name: str = "Liquid Glass effects"
    group: str = "Desktop"
    summary: str = ("Real glass behind the panel, menus, quick settings, ArcMenu, app windows and the overview: "
                    "live blur, a refracting rim, rim light and a rainbow edge.")
    notes: list[str] = field(default_factory=lambda: [
        "Uses Liquid Glass's own GNOME Shell extension; Blur my Shell isn't needed."])

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

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        d = self.ext_dir(env)
        acts: list[Action] = [WriteFile(d / name, text) for name, text in rg.extension_files().items()]
        acts.append(WriteFile(self.config_path(env), rg.render_config(ctx.settings, ctx.tokens)))
        acts.append(ListEdit("org.gnome.shell", "enabled-extensions", add=(rg.UUID,)))
        acts.append(ListEdit("org.gnome.shell", "disabled-extensions", remove=(rg.UUID,)))
        if env.extension_path(BLUR) is not None:
            acts += [GSet(f"{self.BLUR_SCHEMA}.{part}", "blur", "false") for part in self.BLUR_OVERLAP]
        acts += self._startup_actions(ctx)
        return acts

    # Dash to Panel and Just Perfection each have their own "start on the desktop" option, and
    # each would open the overview again if theirs said otherwise, so theirs follows ours.
    STARTUP_KEYS = ((DASH_TO_PANEL, "org.gnome.shell.extensions.dash-to-panel", "hide-overview-on-startup", "true"),
                    (JUST_PERFECTION, "org.gnome.shell.extensions.just-perfection", "startup-status", "0"))

    def _startup_actions(self, ctx: Context) -> list[Action]:
        s = ctx.settings
        on = s.start_on_desktop or s.overview_off
        acts: list[Action] = []
        for uuid, schema, key, value in self.STARTUP_KEYS:
            if ctx.env.extension_path(uuid) is None:
                continue
            acts.append(GSet(schema, key, value, keep_user_change=True) if on else GReset(schema, key))
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        notes = list(self.notes)
        if not self.running(ctx.env):
            notes.append("Log out and back in once so GNOME Shell starts the Liquid Glass extension. "
                         "After that, changes show up instantly.")
        return notes

    @staticmethod
    def running(env: Env) -> bool:
        """Whether the Shell has loaded our extension (it only finds new ones at login)."""
        r = env.run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                     "--method", "org.gnome.Shell.Extensions.GetExtensionInfo", rg.UUID], timeout=5)
        m = re.search(r"'state': <([\d.]+)>", r.out) if r.code == 0 else None
        return m is not None and float(m.group(1)) == 1.0   # 1 = enabled and running


@dataclass
class DashToPanel(Target):
    id: str = "dash-to-panel"
    name: str = "Dash to Panel"
    group: str = "Panel"
    summary: str = "Glass panel: translucent background, glass border, floating or docked, themed hover and dots."

    SCHEMA = "org.gnome.shell.extensions.dash-to-panel"

    def detect(self, env: Env) -> Detection:
        return _need_extension(env, DASH_TO_PANEL, "Dash to Panel", "gnome-shell-extension-dash-to-panel")

    def plan(self, ctx: Context) -> list[Action]:
        return _gset(self.SCHEMA, rs.dtp_values(ctx.tokens))


@dataclass
class ArcMenu(Target):
    id: str = "arcmenu"
    name: str = "ArcMenu"
    group: str = "Panel"
    summary: str = "Glass menu and menu button; colours, radius, search pill and hover washes."

    SCHEMA = "org.gnome.shell.extensions.arcmenu"

    def detect(self, env: Env) -> Detection:
        return _need_extension(env, ARCMENU, "ArcMenu", "gnome-shell-extension-arcmenu")

    def plan(self, ctx: Context) -> list[Action]:
        return _gset(self.SCHEMA, rs.arcmenu_values(ctx.tokens))


TARGETS: list[Target] = [GnomeShell(), GlassEffects(), DashToPanel(), ArcMenu()]
