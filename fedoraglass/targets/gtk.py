"""GTK 4 / libadwaita, GTK 3 and Flatpak targets."""

from __future__ import annotations

import re
from pathlib import Path

from ..i18n import _, N_
from .. import distro
from ..env import Env
from ..render import gtk3, gtk4, headerbar
from .base import Action, Context, FlatpakOverride, Detection, GReset, GSet, Target, WriteFile

def gtk3_partial() -> str:
    """What to say when adw-gtk3 is missing, with this Linux's install command."""
    how = distro.hint("adw-gtk3")
    return (_("Some GTK 3 details need adw-gtk3: {how}").format(how=how) if how else
            _("Some GTK 3 details need the adw-gtk3 theme (github.com/lassekongo83/adw-gtk3)"))


class Gtk4(Target):
    def __init__(self) -> None:
        super().__init__(
            id="gtk4", name=N_("GTK 4 and libadwaita apps"), group="Desktop",
            summary=N_("Glass windows, header bars, sidebars, menus and controls in every "
                    "GTK 4 app. Follows the system light/dark switch live."),
            plain=N_("Adds a Fedora Glass style file that GTK 4 apps, such as Files and Settings, "
                  "read when they open."),
            # The file switches by itself (prefers-color-scheme), or holds the one style the
            # user picked: the same for GNOME's dark and light.
            scheme_dependent=False,
        )

    def plan(self, ctx: Context) -> list[Action]:
        d = ctx.env.config / "gtk-4.0"
        dark, light = ctx.switching()
        css = gtk4.render(dark, light) + headerbar.gtk4_css(ctx.settings, dark, light)
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


_DARK_NAME = re.compile(r"[-_]dark(?![a-z])", re.I)
_BG_DEFINE = re.compile(
    r"@define-color\s+(?:window_bg_color|theme_bg_color|bg_color)\s+(#[0-9a-f]{6}|#[0-9a-f]{3})\b", re.I)


def _is_dark_hex(h: str) -> bool:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5


def kept_theme_is_dark(env: Env) -> bool | None:
    """Whether the user's own GTK 3 theme draws dark windows: from its name (Orchis-Dark,
    Foo_dark-compact) or the window background its gtk.css defines. None when unknown."""
    raw = env.gsettings_get("org.gnome.desktop.interface", "gtk-theme") or ""
    name = raw.strip().strip("'\"")
    if not name:
        return None
    if _DARK_NAME.search(name):
        return True
    if name in ("Adwaita", "Default"):
        return False                # GTK 3's built-in themes are light
    for d in adw_gtk3_dirs(env):
        css = d / name / "gtk-3.0/gtk.css"
        try:
            text = css.read_text(encoding="utf-8", errors="replace")[:200_000]
        except OSError:
            continue
        if m := _BG_DEFINE.search(text):
            return _is_dark_hex(m.group(1))
        return None
    return None


GEDIT = "org.gnome.gedit.preferences.editor"
_GEDIT_KEYS = {True: "style-scheme-for-dark-theme-variant", False: "style-scheme-for-light-theme-variant"}


def gedit_scheme(env: Env, dark: bool | None) -> list[Action]:
    """gedit picks its colour scheme by the desktop's light/dark setting, but it draws with
    the GTK 3 theme, which may stay dark on a light desktop (Orchis-Dark). It then used its
    light scheme (Tango) on the dark theme: a white line-number strip and current line with
    white numbers on it, and dark syntax colours on dark glass. So gedit's scheme for the
    other setting becomes the one it uses with the theme's own darkness. Restore (or a theme
    that follows the desktop) puts gedit's choice back; a choice the user makes later stays."""
    if dark is None:
        return [GReset(GEDIT, k) for k in _GEDIT_KEYS.values()]
    want = env.gsettings_get(GEDIT, _GEDIT_KEYS[dark])
    if not want:
        return []                   # gedit is not installed
    other = _GEDIT_KEYS[not dark]
    actions: list[Action] = [GReset(GEDIT, _GEDIT_KEYS[dark])]
    if env.gsettings_get(GEDIT, other) != want:
        actions.append(GSet(GEDIT, other, want, keep_user_change=True))
    return actions


class Gtk3(Target):
    """GTK 3 apps. With adw-gtk3 installed the whole theme is recoloured to glass (it draws
    every widget from libadwaita's named colours). On any other GTK 3 theme (Orchis, say)
    the user's theme stays and the same style sheet goes on top: header bars, window
    buttons, buttons, sidebars and menus get the glass look, and the rest stays the theme's."""

    def __init__(self) -> None:
        super().__init__(
            id="gtk3", name=N_("GTK 3 apps"), group="Desktop",
            summary=N_("Glass for older GTK 3 apps, on top of your GTK 3 theme. "
                    "GTK 3 cannot switch light/dark by itself, so Apply picks the active scheme."),
            plain=N_("Adds a Fedora Glass style file for older GTK 3 apps. Your GTK 3 theme stays, "
                  "unless adw-gtk3 is installed: then its light or dark version is picked."),
        )

    def detect(self, env: Env) -> Detection:
        found = find_adw_gtk3(env)
        if found is None:
            return Detection(True, _("On your current GTK 3 theme"))
        return Detection(True, _("adw-gtk3 found in {folder}").format(folder=found.parent))

    def live_notes(self, ctx: Context) -> list[str]:
        return [] if find_adw_gtk3(ctx.env) else [gtk3_partial()]

    def plan(self, ctx: Context) -> list[Action]:
        t = ctx.tokens
        if (kept := find_adw_gtk3(ctx.env) is None):
            # The user's own GTK 3 theme stays selected and keeps drawing tabs, entries and
            # the rest, so our sheet must match its darkness, not the desktop's light/dark.
            if (dark := kept_theme_is_dark(ctx.env)) is not None:
                t = ctx.dark if dark else ctx.light
        # A dark sheet over the light desktop's light window glass needs a denser fill.
        on_light_glass = t.dark and not ctx.tokens.dark
        css = WriteFile(ctx.env.config / "gtk-3.0/gtk.css",
                        gtk3.render(t, on_light_glass) + headerbar.gtk3_css(ctx.settings, t))
        if kept:
            return [css, *gedit_scheme(ctx.env, dark)]
        return [GSet("org.gnome.desktop.interface", "gtk-theme", f"'{gtk3.theme_name(t)}'"), css]


class Flatpak(Target):

    def __init__(self) -> None:
        super().__init__(
            id="flatpak", name=N_("Flatpak apps"), group="Desktop",
            summary=N_("Lets sandboxed GTK apps read the Fedora Glass GTK 3 and 4 style files."),
            plain=N_("Lets Flatpak apps read the Fedora Glass style files, so they get the same look. "
                  "They can read them, not change them."),
            scheme_dependent=False,     # the same grants in dark and light
            notes=[N_("GTK 3 Flatpak apps also need the adw-gtk3 theme runtime from Flathub: "
                   "flatpak install flathub org.gtk.Gtk3theme.adw-gtk3 org.gtk.Gtk3theme.adw-gtk3-dark")],
        )

    def detect(self, env: Env) -> Detection:
        if env.which("flatpak") is None:
            return Detection(False, _("{name} is not installed").format(name="Flatpak"))
        return Detection(True)

    # The GTK 3 files Flatpak apps read: the style sheet Apply writes (it only points at
    # GTK's built-in pictures, nothing in the folder) and GTK's own settings file. Not the
    # whole folder: it also holds the file manager's bookmarks. Apply writes gtk.css as a
    # real file, never a link, so there is no link target to share as well.
    GTK3_FILES = ("xdg-config/gtk-3.0/gtk.css:ro", "xdg-config/gtk-3.0/settings.ini:ro")
    # Up to 1.5.19 the whole folder was shared; an Apply takes that grant back.
    OLD_GRANTS = ("xdg-config/gtk-3.0:ro",)

    def plan(self, ctx: Context) -> list[Action]:
        # Read-only access to the Fedora Glass GTK style files for every Flatpak app.
        return [FlatpakOverride(filesystems=("xdg-config/gtk-4.0:ro", *self.GTK3_FILES), drop=self.OLD_GRANTS)]


TARGETS: list[Target] = [Gtk4(), Gtk3(), Flatpak()]
