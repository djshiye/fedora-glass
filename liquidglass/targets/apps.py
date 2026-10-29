"""Third-party apps that are neither GTK nor Qt-themed by us.

Each target says honestly what it can do: apps with a real theming hook get
files written; the rest only show a note in the app.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..env import Env
from ..render import apps as ra
from .base import Action, Command, Context, Detection, Target, WriteFile

APPIMAGE_DIRS = ("AppImages", "Applications", ".local/bin", "Downloads")


def has_appimage(env: Env, word: str) -> bool:
    for d in APPIMAGE_DIRS:
        base = env.home / d
        try:
            if base.is_dir() and any(word in p.name.lower() and p.suffix.lower() == ".appimage"
                                     for p in base.iterdir()):
                return True
        except OSError:
            pass
    return False


def has_desktop_file(env: Env, desktop_id: str) -> bool:
    return any((d / f"{desktop_id}.desktop").is_file() for d in (
        env.data / "applications", Path("/usr/share/applications"), Path("/usr/local/share/applications"),
        env.data / "flatpak/exports/share/applications", Path("/var/lib/flatpak/exports/share/applications")))


def installed(env: Env, *, cmds: tuple[str, ...] = (), flatpak: str | None = None,
              dirs: tuple[Path, ...] = (), appimage: str | None = None,
              desktop: tuple[str, ...] = ()) -> bool:
    return (any(env.which(c) for c in cmds)
            or (flatpak is not None and env.flatpak_installed(flatpak))
            or any(d.exists() for d in dirs)
            or (appimage is not None and has_appimage(env, appimage))
            or any(has_desktop_file(env, d) for d in desktop))


@dataclass
class AppTarget(Target):
    """A target whose notes can depend on the current tokens (see live_notes)."""
    group: str = "Apps"

    def live_notes(self, ctx: Context) -> list[str]:
        return list(self.notes)


def _json_edit(path: Path, updates: dict) -> Action | None:
    """WriteFile of `path` with keys merged in; None if it holds something that isn't plain JSON."""
    text = ra.read_text(path) if path.exists() else None
    if path.exists() and text is None:
        return None
    merged = ra.merge_json_text(text, updates)
    return None if merged is None else WriteFile(path, merged)


# ---- Discord (Vencord) ------------------------------------------------------------
DISCORD_FLATPAK = "com.discordapp.Discord"


@dataclass
class Discord(AppTarget):
    id: str = "discord"
    name: str = "Discord"
    summary: str = "Glass theme for Discord, installed as a Vencord theme."
    scheme_dependent: bool = False
    notes: list[str] = field(default_factory=lambda: [
        "Needs Vencord (vencord.dev). Restart Discord after applying.",
        "Discord's window is opaque unless Vencord's transparent-window option is on; "
        "without it you get glass-coloured surfaces but no see-through.",
    ])

    def vencord_dirs(self, env: Env) -> list[Path]:
        cands = [env.home / ".var/app" / DISCORD_FLATPAK / "config/Vencord", env.config / "Vencord"]
        found = [d for d in cands if d.is_dir()]
        if found:
            return found
        return cands[:1] if env.flatpak_installed(DISCORD_FLATPAK) else []

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("discord",), flatpak=DISCORD_FLATPAK, dirs=(env.config / "discord",)):
            return Detection(True)
        return Detection(False, "Discord is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        acts: list[Action] = []
        css = ra.discord_css(ctx.dark, ctx.light)
        for d in self.vencord_dirs(ctx.env):
            acts.append(WriteFile(d / "themes" / ra.DISCORD_THEME_FILE, css))
            sp = d / "settings/settings.json"
            if not sp.is_file():
                continue
            text = ra.read_text(sp)
            try:
                data = json.loads(text) if text else None
            except ValueError:
                data = None
            if not isinstance(data, dict):
                continue
            cur = data.get("enabledThemes")
            enabled = [e for e in cur if isinstance(e, str)] if isinstance(cur, list) else []
            if ra.DISCORD_THEME_FILE not in enabled:
                enabled.append(ra.DISCORD_THEME_FILE)
            merged = ra.merge_json_text(text, {"enabledThemes": enabled})
            if merged is not None:
                acts.append(WriteFile(sp, merged))
        return acts


# ---- VS Code ------------------------------------------------------------------------
@dataclass
class VSCode(AppTarget):
    id: str = "vscode"
    name: str = "VS Code"
    summary: str = "Liquid Glass Dark and Light colour themes, installed as a local extension."
    notes: list[str] = field(default_factory=lambda: [
        "VS Code windows can't be translucent on Linux; the theme uses the glass colours on opaque surfaces.",
        "If settings.json contains comments, Liquid Glass leaves it alone: pick Liquid Glass Dark/Light "
        "yourself under Preferences > Color Theme.",
    ])

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("code",), dirs=(env.config / "Code", env.home / ".vscode")):
            return Detection(True)
        return Detection(False, "VS Code is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        env, t = ctx.env, ctx.tokens
        vsix = env.data / "liquid-glass/vscode/liquid-glass.vsix"
        data = ra.vsix_bytes(ctx.dark, ctx.light)
        acts: list[Action] = [WriteFile(vsix, data)]
        ext_dir = env.home / ".vscode/extensions"
        try:
            have = any(ext_dir.glob(f"{ra.VSCODE_ID}-*"))
            same = vsix.is_file() and vsix.read_bytes() == data
        except OSError:
            have = same = False
        if not (have and same):
            acts.append(Command(("code", "--install-extension", str(vsix), "--force"),
                                "install the Liquid Glass colour themes",
                                undo=("code", "--uninstall-extension", ra.VSCODE_ID)))
        updates: dict = {"workbench.colorTheme": ra.VSCODE_LABELS[t.dark]}
        if ctx.settings.scheme == "auto":
            updates.update({"window.autoDetectColorScheme": True,
                            "workbench.preferredDarkColorTheme": ra.VSCODE_LABELS[True],
                            "workbench.preferredLightColorTheme": ra.VSCODE_LABELS[False]})
        edit = _json_edit(env.config / "Code/User/settings.json", updates)
        if edit is not None:
            acts.append(edit)
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        path = ctx.env.config / "Code/User/settings.json"
        out = list(self.notes)
        if path.exists() and ra.merge_json_text(ra.read_text(path), {}) is None:
            out.insert(0, "settings.json has comments, so it was not changed: select the theme manually.")
        return out


# ---- Obsidian ----------------------------------------------------------------------------
@dataclass
class Obsidian(AppTarget):
    id: str = "obsidian"
    name: str = "Obsidian"
    summary: str = "Liquid Glass theme installed into every vault and selected."
    scheme_dependent: bool = False
    notes: list[str] = field(default_factory=lambda: [
        "Restart Obsidian (or reload with Ctrl+R) to see the theme. Obsidian's window is opaque."])

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("obsidian",), dirs=(env.config / "obsidian",), appimage="obsidian"):
            return Detection(True)
        return Detection(False, "Obsidian is not installed")

    def vaults(self, env: Env) -> list[Path]:
        text = ra.read_text(env.config / "obsidian/obsidian.json")
        try:
            vaults = json.loads(text or "")["vaults"]
        except (ValueError, KeyError, TypeError):
            return []
        out: list[Path] = []
        if isinstance(vaults, dict):
            for v in vaults.values():
                p = v.get("path") if isinstance(v, dict) else None
                if isinstance(p, str) and Path(p).is_absolute() and Path(p).is_dir() and Path(p) not in out:
                    out.append(Path(p))
        return out

    def plan(self, ctx: Context) -> list[Action]:
        acts: list[Action] = []
        css = ra.obsidian_css(ctx.dark, ctx.light)
        for v in self.vaults(ctx.env):
            base = v / ".obsidian"
            theme = base / "themes/Liquid Glass"
            # Vaults can be synced or shared folders: never follow links planted inside them.
            if any(p.is_symlink() for p in (base, base / "themes", theme, base / "appearance.json")):
                continue
            acts.append(WriteFile(theme / "manifest.json", ra.obsidian_manifest()))
            acts.append(WriteFile(theme / "theme.css", css))
            edit = _json_edit(base / "appearance.json", {"cssTheme": "Liquid Glass"})
            if edit is not None:
                acts.append(edit)
        return acts


# ---- qBittorrent ---------------------------------------------------------------------------
@dataclass
class QBittorrent(AppTarget):
    id: str = "qbittorrent"
    name: str = "qBittorrent"
    summary: str = "Folder-based custom UI theme (colours and a rounded style sheet)."
    notes: list[str] = field(default_factory=lambda: [
        "Close qBittorrent before applying: it rewrites its settings file on exit and would undo this.",
        "The style sheet follows the scheme in use when you apply; colours switch with the app's own dark mode.",
    ])

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("qbittorrent",), dirs=(env.config / "qBittorrent",), appimage="qbittorrent"):
            return Detection(True)
        return Detection(False, "qBittorrent is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        d = env.data / "liquid-glass/qbittorrent"
        conf = env.config / "qBittorrent/qBittorrent.conf"
        text = ra.read_text(conf) if conf.exists() else ""
        acts: list[Action] = [
            WriteFile(d / "config.json", ra.qbittorrent_config(ctx.dark, ctx.light)),
            WriteFile(d / "stylesheet.qss", ra.qt_qss(ctx.tokens)),
        ]
        if text is not None:
            new = ra.ini_set(text, "Preferences", {
                "General\\UseCustomUITheme": "true",
                "General\\CustomUIThemePath": str(d / "config.json"),
            })
            acts.append(WriteFile(conf, new))
        return acts


# ---- Prism Launcher -----------------------------------------------------------------------------
PRISM_FLATPAK = "org.prismlauncher.PrismLauncher"


@dataclass
class Prism(AppTarget):
    id: str = "prism"
    name: str = "Prism Launcher"
    summary: str = "Custom Prism theme (palette and style sheet), selected as the application theme."
    notes: list[str] = field(default_factory=lambda: [
        "Close Prism Launcher before applying so it doesn't overwrite its settings."])

    def data_dir(self, env: Env) -> Path:
        fp = env.home / ".var/app" / PRISM_FLATPAK / "data/PrismLauncher"
        if fp.is_dir() or env.flatpak_installed(PRISM_FLATPAK):
            return fp
        return env.data / "PrismLauncher"

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("prismlauncher",), flatpak=PRISM_FLATPAK, dirs=(env.data / "PrismLauncher",)):
            return Detection(True)
        return Detection(False, "Prism Launcher is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        d = self.data_dir(ctx.env)
        theme = d / "themes" / ra.PRISM_THEME_ID
        acts: list[Action] = [
            WriteFile(theme / "theme.json", ra.prism_theme_json(ctx.tokens)),
            WriteFile(theme / "themeStyle.css", ra.qt_qss(ctx.tokens)),
        ]
        cfg = d / "prismlauncher.cfg"
        text = ra.read_text(cfg) if cfg.exists() else None
        if text is not None:
            acts.append(WriteFile(cfg, ra.ini_set(text, "General", {"ApplicationTheme": ra.PRISM_THEME_ID})))
        return acts


# ---- Brave / Helium -----------------------------------------------------------------------------
@dataclass
class Browsers(AppTarget):
    id: str = "browsers"
    name: str = "Brave and Helium"
    summary: str = "Chromium theme extension with the glass colours (loaded once by hand)."

    def detect(self, env: Env) -> Detection:
        if (installed(env, cmds=("brave-browser", "brave-origin", "brave", "helium"),
                      dirs=(env.config / "BraveSoftware", env.config / "net.imput.helium"),
                      appimage="helium")):
            return Detection(True)
        return Detection(False, "Brave and Helium are not installed")

    def theme_dir(self, env: Env) -> Path:
        return env.data / "liquid-glass/chromium-theme"

    def plan(self, ctx: Context) -> list[Action]:
        return [WriteFile(self.theme_dir(ctx.env) / "manifest.json", ra.chromium_manifest(ctx.tokens))]

    def live_notes(self, ctx: Context) -> list[str]:
        return [
            "One-time step per browser: open chrome://extensions, turn on Developer mode, choose "
            f"Load unpacked and pick {self.theme_dir(ctx.env)}.",
            "Later changes need Reload on that extension's card. Chromium themes follow the scheme in use "
            "when you apply, and browser windows stay opaque.",
            "Liquid Glass never edits browser profiles.",
        ]


# ---- apps with no theming hook ----------------------------------------------------------------------
@dataclass
class NotesOnly(AppTarget):
    """Appears in the app with an honest note; plan() writes nothing."""
    cmds: tuple[str, ...] = ()
    dirs: tuple[str, ...] = ()       # paths under $HOME
    flatpak: str | None = None
    desktop: tuple[str, ...] = ()

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=self.cmds, flatpak=self.flatpak, desktop=self.desktop,
                     dirs=tuple(env.home / d for d in self.dirs)):
            return Detection(True)
        return Detection(False, f"{self.name} is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        return []


@dataclass
class Slack(NotesOnly):
    def live_notes(self, ctx: Context) -> list[str]:
        theme = ra.slack_theme(ctx.tokens)
        return [
            "Slack has no theme file. Open Preferences > Themes, scroll to the bottom, choose "
            "'Create a custom theme' and paste this string:",
            theme,
        ]


TARGETS: list[Target] = [
    Discord(), VSCode(), Obsidian(), QBittorrent(), Prism(), Browsers(),
    Slack(id="slack", name="Slack", group="Apps", cmds=("slack",), dirs=(".config/Slack",),
          summary="No theme file; a ready-made sidebar theme string is shown to paste.",
          scheme_dependent=True),
    NotesOnly(id="steam", name="Steam", group="Apps", cmds=("steam",), dirs=(".local/share/Steam",),
              summary="Not themed: Steam draws its own UI.", scheme_dependent=False,
              notes=["Steam has no supported theme hook; third-party skins break on updates, so Liquid Glass leaves it alone."]),
    NotesOnly(id="zoom", name="Zoom", group="Apps", cmds=("zoom",), dirs=(".zoom",),
              summary="Not themed; follows the system dark mode.", scheme_dependent=False,
              notes=["In Zoom: Settings > General > Theme > Use system setting."]),
    NotesOnly(id="claude-desktop", name="Claude Desktop", group="Apps",
              cmds=("claude-desktop",), dirs=(".config/Claude",), desktop=("com.anthropic.Claude",),
              summary="Not themed; follows the system dark mode.", scheme_dependent=False,
              notes=["In Claude: Settings > Appearance > Match system."]),
    NotesOnly(id="libreoffice", name="LibreOffice", group="Apps", cmds=("libreoffice", "soffice"),
              dirs=(".config/libreoffice",),
              summary="Follows the GTK 3 theme automatically.", scheme_dependent=False,
              notes=["LibreOffice's GTK 3 backend picks up the adw-gtk3 glass theme. If it looks flat, "
                     "set Tools > Options > LibreOffice > View > Icon/Application colours to Automatic."]),
    NotesOnly(id="firefox", name="Firefox", group="Apps", cmds=("firefox",), dirs=(".config/mozilla", ".mozilla"),
              summary="Not themed; follows the GTK theme for its window frame.", scheme_dependent=False,
              notes=["Use Firefox's built-in System theme (Add-ons > Themes) so the toolbar matches. "
                     "Liquid Glass does not edit Firefox profiles."]),
]
