"""Qt Widgets apps (qBittorrent, qt6ct, Prism Launcher, ...) through Kvantum."""

from __future__ import annotations

from pathlib import Path

from ..i18n import _, N_
from .. import distro
from ..render import apps as ra, kvantum
from .base import Action, Context, FlatpakOverride, Detection, Target, WriteFile
from ..env import Env

STYLE_PLUGINS = (
    "/usr/lib64/qt6/plugins/styles/libkvantum.so",                  # Fedora
    "/usr/lib/x86_64-linux-gnu/qt6/plugins/styles/libkvantum.so",   # Debian, Ubuntu
    "/usr/lib/qt6/plugins/styles/libkvantum.so",                    # Arch
    "/usr/lib64/qt5/plugins/styles/libkvantum.so",
    "/usr/lib/x86_64-linux-gnu/qt5/plugins/styles/libkvantum.so",
)


def environment(settings) -> str:
    """The session environment for native Qt apps. With Qt title bars like GNOME's on,
    Qt tries XWayland first (GNOME then draws the title bar with the header bar
    style) and falls back to Wayland if XWayland is missing, so no app fails to start."""
    lines = ["QT_STYLE_OVERRIDE=kvantum"]
    if settings.qt_gnome_titlebars:
        lines.append("QT_QPA_PLATFORM=xcb;wayland")
    return "\n".join(lines) + "\n"


class QtKvantum(Target):
    def __init__(self) -> None:
        super().__init__(
            id="qt", name=N_("Qt apps (Kvantum)"), group="Apps",
            summary=N_("Glass buttons, entries, tabs, lists, menus and scrollbars in Qt Widgets apps, "
                    "drawn by a Kvantum theme built from your settings."),
            plain=N_("Adds a Kvantum theme in your colours and tells Qt apps to use it. "
                  "Apps started after your next restart pick it up."),
            notes=[
                N_("Native Qt apps pick the style up after you restart your PC "
                "(QT_STYLE_OVERRIDE is set in ~/.config/environment.d)."),
                N_("Open Qt apps keep their old look until restarted; light/dark changes apply to apps started afterwards."),
                N_("Flatpak Qt apps also need the Kvantum style extension matching the app's KDE runtime, "
                "e.g. flatpak install flathub org.kde.KStyle.Kvantum//6.9 "
                "(see the runtime branch with: flatpak info <app>)."),
                N_("If you set QT_QPA_PLATFORMTHEME to qt6ct, pick 'kvantum' there too; "
                "QT_STYLE_OVERRIDE alone already wins for the widget style."),
            ],
        )

    def detect(self, env: Env) -> Detection:
        if any(Path(p).exists() for p in STYLE_PLUGINS) or env.which("kvantummanager"):
            return Detection(True, _("Kvantum found"))
        how = distro.hint("kvantum")
        return Detection(False, _("Install Kvantum: {how}").format(how=how) if how else _("Install Kvantum (the kvantum package)"))

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        kv = env.config / "Kvantum"
        main = kv / "kvantum.kvconfig"
        existing = ra.read_text(main) if main.exists() else None
        # A link, or a file that isn't text: the user's own, left alone (live_notes says so).
        left_alone = main.is_symlink() or (main.exists() and existing is None)
        theme = kv / kvantum.THEME
        actions: list[Action] = [
            WriteFile(theme / f"{kvantum.THEME}.kvconfig", kvantum.build_config(ctx.tokens)),
            WriteFile(theme / f"{kvantum.THEME}.svg", kvantum.build_svg(ctx.tokens)),
        ]
        if not left_alone:
            actions.append(WriteFile(main, kvantum.build_main_config(existing), edits=("ini", "General", ("theme",))))
        actions.append(WriteFile(env.config / "environment.d/90-liquid-glass-qt.conf", environment(ctx.settings)))
        if env.which("flatpak"):
            # Let Flatpak Qt apps load the Kvantum theme.
            actions.append(FlatpakOverride(filesystems=("xdg-config/Kvantum:ro",),
                                           env=(("QT_STYLE_OVERRIDE", "kvantum"),)))
        return actions

    def live_notes(self, ctx: Context) -> list[str]:
        out = list(self.notes)
        main = ctx.env.config / "Kvantum/kvantum.kvconfig"
        if main.is_symlink() or (main.exists() and ra.read_text(main) is None):
            out.insert(0, _("Left alone because kvantum.kvconfig is a link or not text: select the FedoraGlass theme in Kvantum Manager."))
        return out


TARGETS: list[Target] = [QtKvantum()]
