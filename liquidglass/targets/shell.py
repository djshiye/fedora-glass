"""GNOME Shell and its extensions: User Themes CSS, Blur my Shell, Dash to Panel, ArcMenu."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..env import Env
from ..render import shell as rs
from .base import Action, Context, Detection, GSet, ListEdit, Target, WriteFile

USER_THEME = "user-theme@gnome-shell-extensions.gcampax.github.com"
BLUR = "blur-my-shell@aunetx"
DASH_TO_PANEL = "dash-to-panel@jderose9.github.com"
ARCMENU = "arcmenu@arcmenu.com"
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
        "Surfaces are translucent; the blur behind them comes from Blur my Shell."])

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
class BlurMyShell(Target):
    id: str = "blur"
    name: str = "Blur my Shell"
    group: str = "Desktop"
    summary: str = "Liquid Glass refraction pipelines behind the panel, menus, overview and app windows."
    notes: list[str] = field(default_factory=lambda: [
        "Your own Blur my Shell pipelines are kept; Liquid Glass adds four of its own.",
        "Falls back to plain blur when the installed Blur my Shell has no refraction effect."])

    SCHEMA = "org.gnome.shell.extensions.blur-my-shell"

    def detect(self, env: Env) -> Detection:
        return _need_extension(env, BLUR, "Blur my Shell", "gnome-shell-extension-blur-my-shell")

    def plan(self, ctx: Context) -> list[Action]:
        env, t = ctx.env, ctx.tokens
        ext = env.extension_path(BLUR)
        refraction = ext is not None and (ext / "effects/refraction").is_dir()
        pipelines = rs.merge_pipelines(env.gsettings_get(self.SCHEMA, "pipelines"),
                                       rs.our_pipelines(t, refraction))
        acts: list[Action] = [GSet(self.SCHEMA, "pipelines", pipelines)]

        for comp, pid in rs.COMPONENT_PIPELINE.items():
            acts.append(GSet(f"{self.SCHEMA}.{comp}", "pipeline", f"'{pid}'"))
        s = lambda comp: f"{self.SCHEMA}.{comp}"  # noqa: E731

        # Our theme paints the tint, so Blur my Shell must not overpaint these with its own.
        acts += [GSet(s("panel"), "blur", "true"), GSet(s("panel"), "override-background", "false"),
                 GSet(s("popup"), "blur", "true"), GSet(s("popup"), "override-background", "false"),
                 GSet(s("popup"), "preserve-shell-theme", "true"),
                 GSet(s("overview"), "blur", "true"), GSet(s("overview"), "style-components", "0"),
                 GSet(s("appfolder"), "blur", "true"), GSet(s("appfolder"), "style-dialogs", "0")]
        acts += [GSet(s("popup"), k, str(v)) for k, v in rs.popup_corner_keys(t).items()]

        apps = s("applications")
        acts += [GSet(apps, "blur", "true" if t.blur_app_windows else "false"),
                 GSet(apps, "enable-all", "true" if t.blur_app_windows else "false"),
                 # The window actor stays opaque: our CSS already makes GTK surfaces translucent,
                 # and a translucent actor would fade text and content too.
                 GSet(apps, "opacity", "255"),
                 GSet(apps, "dynamic-opacity", "false"),
                 GSet(apps, "unblur-when-fullscreen", "true"),
                 GSet(apps, "blacklist", _blacklist(env.gsettings_get(apps, "blacklist"))),
                 GSet(apps, "corner-radius", str(t.radius))]
        return acts


# Apps that paint opaque windows (Electron, games, launchers): blurring behind them costs GPU
# time and shows nothing.
BLUR_SKIP = ("Plank", "Conky", "steam", "Steam", "discord", "Code", "code", "obsidian", "Slack",
             "brave-browser", "brave-origin", "helium", "zoom", "Claude", "firefox", "libreoffice",
             "org.prismlauncher.PrismLauncher")


def _blacklist(current: str | None) -> str:
    """Our skip list merged into the user's own (GVariant 'as' text in and out)."""
    import ast
    names: list[str] = []
    if current:
        text = current.removeprefix("@as ").strip()
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                names = [n for n in parsed if isinstance(n, str)]
        except (ValueError, SyntaxError):
            names = []
    for n in BLUR_SKIP:
        if n not in names:
            names.append(n)
    return "[" + ", ".join("'" + n.replace("\\", "\\\\").replace("'", "\\'") + "'" for n in names) + "]"


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


TARGETS: list[Target] = [GnomeShell(), BlurMyShell(), DashToPanel(), ArcMenu()]
