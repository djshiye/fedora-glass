"""GTK 4 / libadwaita, GTK 3 and Flatpak targets."""

from __future__ import annotations

from pathlib import Path

from ..env import Env
from ..render import gtk3, gtk4, headerbar
from .base import Action, Context, FlatpakOverride, Detection, GSet, Target, WriteFile

GTK3_PARTIAL = "Some GTK 3 details need adw-gtk3: sudo dnf install adw-gtk3-theme"


class Gtk4(Target):
    def __init__(self) -> None:
        super().__init__(
            id="gtk4", name="GTK 4 and libadwaita apps", group="Desktop",
            summary="Glass windows, header bars, sidebars, menus and controls in every "
                    "GTK 4 app. Follows the system light/dark switch live.",
        )

    def plan(self, ctx: Context) -> list[Action]:
        d = ctx.env.config / "gtk-4.0"
        css = gtk4.render(ctx.dark, ctx.light) + headerbar.gtk4_css(ctx.settings, ctx.dark, ctx.light)
        # Plain GTK 4 apps may read gtk-dark.css instead of gtk.css in dark mode, and
        # an old gtk-dark.css (often a link into another theme) must not linger.
        return [WriteFile(d / "gtk.css", css), WriteFile(d / "gtk-dark.css", css)]


def adw_gtk3_dirs(env: Env) -> list[Path]:
    return [env.data / "themes", env.home / ".themes",
            Path("/usr/local/share/themes"), Path("/usr/share/themes")]


def find_adw_gtk3(env: Env) -> Path | None:
    for d in adw_gtk3_dirs(env):
        if (d / "adw-gtk3/gtk-3.0").is_dir():
            return d / "adw-gtk3"
    return None


class Gtk3(Target):
    """GTK 3 apps. With adw-gtk3 installed the whole theme is recoloured to glass (it draws
    every widget from libadwaita's named colours). On any other GTK 3 theme (Orchis, say)
    the user's theme stays and the same style sheet goes on top: header bars, window
    buttons, buttons, sidebars and menus get the glass look, and the rest stays the theme's."""

    def __init__(self) -> None:
        super().__init__(
            id="gtk3", name="GTK 3 apps", group="Desktop",
            summary="Glass for older GTK 3 apps, on top of your GTK 3 theme. "
                    "GTK 3 cannot switch light/dark by itself, so Apply picks the active scheme.",
        )

    def detect(self, env: Env) -> Detection:
        found = find_adw_gtk3(env)
        if found is None:
            return Detection(True, "On your current GTK 3 theme")
        return Detection(True, f"adw-gtk3 found in {found.parent}")

    def live_notes(self, ctx: Context) -> list[str]:
        return [] if find_adw_gtk3(ctx.env) else [GTK3_PARTIAL]

    def plan(self, ctx: Context) -> list[Action]:
        t = ctx.tokens
        css = WriteFile(ctx.env.config / "gtk-3.0/gtk.css", gtk3.render(t) + headerbar.gtk3_css(ctx.settings, t))
        if find_adw_gtk3(ctx.env) is None:
            return [css]            # the user's own GTK 3 theme stays selected
        return [GSet("org.gnome.desktop.interface", "gtk-theme", f"'{gtk3.theme_name(t)}'"), css]


class Flatpak(Target):

    def __init__(self) -> None:
        super().__init__(
            id="flatpak", name="Flatpak apps", group="Desktop",
            summary="Lets sandboxed GTK apps read the Liquid Glass GTK 3 and 4 style files.",
            notes=["GTK 3 Flatpak apps also need the adw-gtk3 theme runtime from Flathub: "
                   "flatpak install flathub org.gtk.Gtk3theme.adw-gtk3 org.gtk.Gtk3theme.adw-gtk3-dark"],
        )

    def detect(self, env: Env) -> Detection:
        if env.which("flatpak") is None:
            return Detection(False, "Flatpak is not installed")
        return Detection(True)

    def plan(self, ctx: Context) -> list[Action]:
        # Read-only access to the Liquid Glass GTK style files for every Flatpak app.
        return [FlatpakOverride(filesystems=("xdg-config/gtk-4.0:ro", "xdg-config/gtk-3.0:ro"))]


TARGETS: list[Target] = [Gtk4(), Gtk3(), Flatpak()]
