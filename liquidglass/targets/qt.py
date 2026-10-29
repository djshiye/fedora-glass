"""Qt Widgets apps (qBittorrent, qt6ct, Prism Launcher, ...) through Kvantum."""

from __future__ import annotations

from pathlib import Path

from ..render import kvantum
from .base import Action, Context, FlatpakOverride, Detection, Target, WriteFile
from ..env import Env

STYLE_PLUGINS = (
    "/usr/lib64/qt6/plugins/styles/libkvantum.so",                  # Fedora
    "/usr/lib/x86_64-linux-gnu/qt6/plugins/styles/libkvantum.so",   # Debian, Ubuntu
    "/usr/lib/qt6/plugins/styles/libkvantum.so",                    # Arch
    "/usr/lib64/qt5/plugins/styles/libkvantum.so",
    "/usr/lib/x86_64-linux-gnu/qt5/plugins/styles/libkvantum.so",
)


class QtKvantum(Target):
    def __init__(self) -> None:
        super().__init__(
            id="qt", name="Qt apps (Kvantum)", group="Apps",
            summary="Glass buttons, entries, tabs, lists, menus and scrollbars in Qt Widgets apps, "
                    "drawn by a Kvantum theme built from your settings.",
            notes=[
                "Native Qt apps pick the style up after you log out and back in "
                "(QT_STYLE_OVERRIDE is set in ~/.config/environment.d).",
                "Open Qt apps keep their old look until restarted; light/dark changes apply to apps started afterwards.",
                "Flatpak Qt apps also need the Kvantum style extension matching the app's KDE runtime, "
                "e.g. flatpak install flathub org.kde.KStyle.Kvantum//6.9 "
                "(see the runtime branch with: flatpak info <app>).",
                "If you set QT_QPA_PLATFORMTHEME to qt6ct, pick 'kvantum' there too; "
                "QT_STYLE_OVERRIDE alone already wins for the widget style.",
            ],
        )

    def detect(self, env: Env) -> Detection:
        if any(Path(p).exists() for p in STYLE_PLUGINS) or env.which("kvantummanager"):
            return Detection(True, "Kvantum found")
        return Detection(False, "Install Kvantum: sudo dnf install kvantum")

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        kv = env.config / "Kvantum"
        main = kv / "kvantum.kvconfig"
        try:
            existing = main.read_text(encoding="utf-8") if main.is_file() and not main.is_symlink() else None
        except (OSError, UnicodeDecodeError):
            existing = None
        theme = kv / kvantum.THEME
        actions: list[Action] = [
            WriteFile(theme / f"{kvantum.THEME}.kvconfig", kvantum.build_config(ctx.tokens)),
            WriteFile(theme / f"{kvantum.THEME}.svg", kvantum.build_svg(ctx.tokens)),
            WriteFile(main, kvantum.build_main_config(existing)),
            WriteFile(env.config / "environment.d/90-liquid-glass-qt.conf", "QT_STYLE_OVERRIDE=kvantum\n"),
        ]
        if env.which("flatpak"):
            # Let Flatpak Qt apps load the Kvantum theme.
            actions.append(FlatpakOverride(filesystems=("xdg-config/Kvantum:ro",),
                                           env=(("QT_STYLE_OVERRIDE", "kvantum"),)))
        return actions


TARGETS: list[Target] = [QtKvantum()]
