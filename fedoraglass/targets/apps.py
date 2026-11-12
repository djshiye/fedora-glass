"""Third-party apps that are neither GTK nor Qt-themed by us.

Each target says honestly what it can do: apps with a real theming hook get
files written; the rest only show a note in the app.
"""

from __future__ import annotations

import configparser
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import _, N_
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


def flatpak_home(env: Env, app_id: str) -> Path:
    """Where a Flatpak app keeps its files. Inside its sandbox $HOME is the real home and
    XDG_CONFIG_HOME / XDG_DATA_HOME point at config/ and data/ here, so the same path works
    for the app as for us."""
    return env.home / ".var/app" / app_id


def which_installs(env: Env, native: bool, app_id: str, *folders: Path) -> tuple[bool, bool]:
    """(theme the native install, theme the Flatpak). The Flatpak counts when it is installed
    or its config folder is there; with nothing else to go on the native paths are used.
    Both are themed when both are there."""
    fp = env.flatpak_installed(app_id) or any(f.exists() for f in folders)
    return native or not fp, fp


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
    return None if merged is None else WriteFile(path, merged, edits=("json", tuple(updates)))


# ---- Discord (Vencord) ------------------------------------------------------------
DISCORD_FLATPAK = "com.discordapp.Discord"


@dataclass
class Discord(AppTarget):
    id: str = "discord"
    plain: str = N_("Adds a Fedora Glass theme to Vencord and turns it on, so Discord gets the glass colours.")
    name: str = "Discord"
    summary: str = N_("Glass theme for Discord, installed as a Vencord theme.")
    scheme_dependent: bool = False
    notes: list[str] = field(default_factory=lambda: [
        N_("Needs Vencord (vencord.dev). Restart Discord after applying."),
        N_("Discord's window is opaque unless Vencord's transparent-window option is on; "
        "without it you get glass-coloured surfaces but no see-through."),
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
        return Detection(False, _("{name} is not installed").format(name="Discord"))

    def plan(self, ctx: Context) -> list[Action]:
        acts: list[Action] = []
        css = ra.discord_css(*ctx.switching())
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
                acts.append(WriteFile(sp, merged, edits=("json", ("enabledThemes",))))
        return acts


# ---- VS Code and VSCodium ---------------------------------------------------------------
VSCODE_FLATPAK = "com.visualstudio.code"
VSCODIUM_FLATPAK = "com.vscodium.codium"


@dataclass
class VSCode(AppTarget):
    id: str = "vscode"
    plain: str = N_("Installs Fedora Glass Dark and Light colour themes in VS Code and selects the one that fits.")
    name: str = "VS Code"
    summary: str = N_("Fedora Glass Dark and Light colour themes, installed as a local extension.")
    notes: list[str] = field(default_factory=lambda: [
        N_("VS Code windows can't be translucent on Linux; the theme uses the glass colours on opaque surfaces."),
        N_("If settings.json contains comments, Fedora Glass leaves it alone: pick Fedora Glass Dark/Light "
        "yourself under Preferences > Color Theme."),
    ])
    # What differs between VS Code and VSCodium (names are under ~/.config, ~/ and the Flatpak's data/).
    cmd: str = "code"
    config_name: str = "Code"
    ext_home: str = ".vscode/extensions"
    flatpak: str = VSCODE_FLATPAK
    flatpak_data: str = "vscode"
    vsix_dir: str = "vscode"

    def native_dirs(self, env: Env) -> tuple[Path, ...]:
        return (env.config / self.config_name, env.home / self.ext_home.split("/")[0])

    def detect(self, env: Env) -> Detection:
        fp = flatpak_home(env, self.flatpak) / "config" / self.config_name
        if installed(env, cmds=(self.cmd,), flatpak=self.flatpak, dirs=(*self.native_dirs(env), fp)):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name=self.name))

    def installs(self, env: Env) -> list[tuple[Path, Path, Path, tuple[str, ...]]]:
        """Each install to theme: (settings.json, extensions folder, where the .vsix is kept,
        the command that runs it). The Flatpak keeps everything under its own folder, and the
        .vsix goes there too: the sandbox reads that folder whatever its other permissions are."""
        fh = flatpak_home(env, self.flatpak)
        native = bool(env.which(self.cmd)) or any(d.exists() for d in self.native_dirs(env))
        use_native, use_fp = which_installs(env, native, self.flatpak, fh / "config" / self.config_name)
        out = []
        if use_native:
            out.append((env.config / self.config_name / "User/settings.json", env.home / self.ext_home,
                        env.data / f"liquid-glass/{self.vsix_dir}/liquid-glass.vsix", (self.cmd,)))
        if use_fp:
            out.append((fh / "config" / self.config_name / "User/settings.json",
                        fh / "data" / self.flatpak_data / "extensions",
                        fh / "data/liquid-glass/liquid-glass.vsix", ("flatpak", "run", self.flatpak)))
        return out

    def plan(self, ctx: Context) -> list[Action]:
        env, t = ctx.env, ctx.tokens
        data = ra.vsix_bytes(ctx.dark, ctx.light)
        acts: list[Action] = []
        for settings, ext_dir, vsix, run in self.installs(env):
            acts.append(WriteFile(vsix, data))
            try:
                have = any(ext_dir.glob(f"{ra.VSCODE_ID}-*"))
                same = vsix.is_file() and vsix.read_bytes() == data
            except OSError:
                have = same = False
            if not (have and same):
                acts.append(Command((*run, "--install-extension", str(vsix), "--force"),
                                    "install the Fedora Glass colour themes",
                                    undo=(*run, "--uninstall-extension", ra.VSCODE_ID)))
            updates: dict = {"workbench.colorTheme": ra.VSCODE_LABELS[t.dark]}
            if ctx.settings.scheme == "auto":
                updates.update({"window.autoDetectColorScheme": True,
                                "workbench.preferredDarkColorTheme": ra.VSCODE_LABELS[True],
                                "workbench.preferredLightColorTheme": ra.VSCODE_LABELS[False]})
            edit = _json_edit(settings, updates)
            if edit is not None:
                acts.append(edit)
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        out = list(self.notes)
        for settings, *_rest in self.installs(ctx.env):
            if settings.exists() and ra.merge_json_text(ra.read_text(settings), {}) is None:
                out.insert(0, _("settings.json has comments, so it was not changed: select the theme manually."))
                break
        return out


@dataclass
class VSCodium(VSCode):
    id: str = "vscodium"
    plain: str = N_("Installs Fedora Glass Dark and Light colour themes in VSCodium and selects the one that fits.")
    name: str = "VSCodium"
    summary: str = N_("Fedora Glass Dark and Light colour themes, installed as a local extension.")
    cmd: str = "codium"
    config_name: str = "VSCodium"
    ext_home: str = ".vscode-oss/extensions"
    flatpak: str = VSCODIUM_FLATPAK
    flatpak_data: str = "codium"
    vsix_dir: str = "vscodium"


# ---- Obsidian ----------------------------------------------------------------------------
OBSIDIAN_FLATPAK = "md.obsidian.Obsidian"


@dataclass
class Obsidian(AppTarget):
    id: str = "obsidian"
    plain: str = N_("Adds the Fedora Glass theme to each of your vaults and selects it.")
    name: str = "Obsidian"
    summary: str = N_("Fedora Glass theme installed into every vault and selected.")
    scheme_dependent: bool = False
    notes: list[str] = field(default_factory=lambda: [
        N_("Restart Obsidian (or reload with Ctrl+R) to see the theme. Obsidian's window is opaque.")])

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("obsidian",), flatpak=OBSIDIAN_FLATPAK, dirs=tuple(self.config_dirs(env)),
                     appimage="obsidian"):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="Obsidian"))

    def config_dirs(self, env: Env) -> list[Path]:
        """Obsidian's own settings folder: the normal one and the Flatpak's."""
        return [env.config / "obsidian", flatpak_home(env, OBSIDIAN_FLATPAK) / "config/obsidian"]

    def vaults(self, env: Env) -> list[Path]:
        out: list[Path] = []
        for d in self.config_dirs(env):
            text = ra.read_text(d / "obsidian.json")
            try:
                vaults = json.loads(text or "")["vaults"]
            except (ValueError, KeyError, TypeError):
                continue
            if isinstance(vaults, dict):
                for v in vaults.values():
                    p = v.get("path") if isinstance(v, dict) else None
                    if isinstance(p, str) and Path(p).is_absolute() and Path(p).is_dir() and Path(p) not in out:
                        out.append(Path(p))
        return out

    def plan(self, ctx: Context) -> list[Action]:
        acts: list[Action] = []
        css = ra.obsidian_css(*ctx.switching())
        for v in self.vaults(ctx.env):
            base = v / ".obsidian"
            theme = base / "themes/Fedora Glass"
            # Vaults can be synced or shared folders: never follow links planted inside them.
            if any(p.is_symlink() for p in (base, base / "themes", theme, base / "appearance.json")):
                continue
            acts.append(WriteFile(theme / "manifest.json", ra.obsidian_manifest()))
            acts.append(WriteFile(theme / "theme.css", css))
            edit = _json_edit(base / "appearance.json", {"cssTheme": "Fedora Glass"})
            if edit is not None:
                acts.append(edit)
        return acts


# ---- qBittorrent ---------------------------------------------------------------------------
QBITTORRENT_FLATPAK = "org.qbittorrent.qBittorrent"


@dataclass
class QBittorrent(AppTarget):
    id: str = "qbittorrent"
    plain: str = N_("Adds a Fedora Glass theme for qBittorrent and selects it in its settings.")
    name: str = "qBittorrent"
    summary: str = N_("Folder-based custom UI theme (colours and a rounded style sheet).")
    # The style sheet can't switch by itself, so the colours follow the same scheme and
    # both are written again when GNOME switches dark and light.
    scheme_dependent: bool = True
    notes: list[str] = field(default_factory=lambda: [
        N_("Close qBittorrent before applying: it rewrites its settings file on exit and would undo this."),
        N_("Colours and style sheet follow the GNOME dark or light style; restart qBittorrent after a switch."),
    ])

    def config_dirs(self, env: Env) -> list[Path]:
        return [env.config / "qBittorrent", flatpak_home(env, QBITTORRENT_FLATPAK) / "config/qBittorrent"]

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("qbittorrent",), flatpak=QBITTORRENT_FLATPAK, dirs=tuple(self.config_dirs(env)),
                     appimage="qbittorrent"):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="qBittorrent"))

    def installs(self, env: Env) -> list[tuple[Path, Path]]:
        """Each install to theme: (its qBittorrent.conf, the folder for our theme files). The
        Flatpak reads only its own folders by default, so its theme lives there."""
        fh = flatpak_home(env, QBITTORRENT_FLATPAK)
        native = bool(env.which("qbittorrent")) or (env.config / "qBittorrent").exists() or has_appimage(env, "qbittorrent")
        use_native, use_fp = which_installs(env, native, QBITTORRENT_FLATPAK, fh / "config/qBittorrent")
        out = []
        if use_native:
            out.append((env.config / "qBittorrent/qBittorrent.conf", env.data / "liquid-glass/qbittorrent"))
        if use_fp:
            out.append((fh / "config/qBittorrent/qBittorrent.conf", fh / "data/liquid-glass/qbittorrent"))
        return out

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        acts: list[Action] = []
        for conf, d in self.installs(env):
            text = ra.read_text(conf) if conf.exists() else ""
            acts += [
                # Both blocks from the scheme in use: qBittorrent picks its block by its own
                # idea of dark mode, which need not match the style sheet's (a white side list).
                WriteFile(d / "config.json", ra.qbittorrent_config(ctx.tokens, ctx.tokens)),
                WriteFile(d / "stylesheet.qss", ra.qt_qss(ctx.tokens)),
            ]
            if text is not None:
                keys = {
                    "General\\UseCustomUITheme": "true",
                    "General\\CustomUIThemePath": str(d / "config.json"),
                }
                new = ra.ini_set(text, "Preferences", keys)
                acts.append(WriteFile(conf, new, edits=("ini", "Preferences", tuple(keys))))
        return acts


# ---- Prism Launcher -----------------------------------------------------------------------------
PRISM_FLATPAK = "org.prismlauncher.PrismLauncher"


@dataclass
class Prism(AppTarget):
    id: str = "prism"
    plain: str = N_("Adds a Fedora Glass theme for Prism Launcher and selects it.")
    name: str = "Prism Launcher"
    summary: str = N_("Custom Prism theme (palette and style sheet), selected as the application theme.")
    notes: list[str] = field(default_factory=lambda: [
        N_("Close Prism Launcher before applying so it doesn't overwrite its settings.")])

    def data_dir(self, env: Env) -> Path:
        fp = env.home / ".var/app" / PRISM_FLATPAK / "data/PrismLauncher"
        if fp.is_dir() or env.flatpak_installed(PRISM_FLATPAK):
            return fp
        return env.data / "PrismLauncher"

    def detect(self, env: Env) -> Detection:
        if installed(env, cmds=("prismlauncher",), flatpak=PRISM_FLATPAK, dirs=(env.data / "PrismLauncher",)):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="Prism Launcher"))

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
            acts.append(WriteFile(cfg, ra.ini_set(text, "General", {"ApplicationTheme": ra.PRISM_THEME_ID}),
                                  edits=("ini", "General", ("ApplicationTheme",))))
        return acts


# ---- Brave / Helium -----------------------------------------------------------------------------
@dataclass
class Browsers(AppTarget):
    id: str = "browsers"
    plain: str = N_("Writes a theme in your colours for Brave and Helium. You load it once yourself; the note says how.")
    name: str = "Brave and Helium"
    summary: str = N_("Chromium theme extension with the glass colours (loaded once by hand).")

    def detect(self, env: Env) -> Detection:
        if (installed(env, cmds=("brave-browser", "brave-origin", "brave", "helium"),
                      dirs=(env.config / "BraveSoftware", env.config / "net.imput.helium"),
                      appimage="helium")):
            return Detection(True)
        return Detection(False, _("Brave and Helium are not installed"))

    def theme_dir(self, env: Env) -> Path:
        return env.data / "liquid-glass/chromium-theme"

    def plan(self, ctx: Context) -> list[Action]:
        return [WriteFile(self.theme_dir(ctx.env) / "manifest.json", ra.chromium_manifest(ctx.tokens))]

    def live_notes(self, ctx: Context) -> list[str]:
        return [
            "One-time step per browser: open chrome://extensions, turn on Developer mode, choose "
            f"Load unpacked and pick {self.theme_dir(ctx.env)}.",
            _("Later changes need Reload on that extension's card. Chromium themes follow the scheme in use "
            "when you apply, and browser windows stay opaque."),
            _("Fedora Glass never edits browser profiles."),
        ]


# ---- Firefox ---------------------------------------------------------------------------------
FIREFOX_FLATPAK = "org.mozilla.firefox"


def firefox_roots(env: Env) -> list[Path]:
    """Folders that hold a profiles.ini: the classic one, the XDG one newer Firefox uses,
    and the same two inside the Flatpak's own home, and the Snap's (Ubuntu's Firefox)."""
    fp = env.home / ".var/app" / FIREFOX_FLATPAK
    return [env.home / ".mozilla/firefox", env.config / "mozilla/firefox",
            fp / ".mozilla/firefox", fp / "config/mozilla/firefox",
            env.home / "snap/firefox/common/.mozilla/firefox"]


def firefox_profiles(env: Env) -> list[Path]:
    """Every profile folder the profiles.ini files list, that exists. All of them, not only
    the default: each Firefox install (rpm, Flatpak, Developer Edition) has its own default,
    and profiles.ini only lists profiles the user made."""
    out: list[Path] = []
    seen: set[Path] = set()
    for root in firefox_roots(env):
        text = ra.read_text(root / "profiles.ini")
        if not text:
            continue
        cp = configparser.RawConfigParser(strict=False, interpolation=None)
        try:
            cp.read_string(text)
        except configparser.Error:
            continue
        for sec in cp.sections():
            if not sec.startswith("Profile") or not cp.has_option(sec, "Path"):
                continue
            rel = cp.get(sec, "IsRelative", fallback="1").strip() != "0"
            p = Path(cp.get(sec, "Path").strip())
            p = root / p if rel else p
            if not p.is_absolute() or not p.is_dir() or p.is_symlink():
                continue
            key = p.resolve()
            if key not in seen:
                seen.add(key)
                out.append(p)
    return out


def _read_exact(path: Path) -> str | None:
    """A file's text with its own line endings ("" when there is none); None when it isn't
    UTF-8 text or is a link. read_text would turn the user's CRLF lines into LF ones."""
    try:
        if path.is_symlink():
            return None
        return path.read_bytes().decode("utf-8") if path.exists() else ""
    except (OSError, UnicodeDecodeError):
        return None


@dataclass
class Firefox(AppTarget):
    """Opt-in: off until the user turns it on (settings.OPT_IN_TARGETS)."""
    id: str = "firefox-theme"
    name: str = "Firefox"
    summary: str = N_("Fedora Glass colours for Firefox's toolbars, tabs and menus.")
    plain: str = (N_("Adds a Fedora Glass style sheet to each Firefox profile and one line to its "
                  "userChrome.css, userContent.css and user.js. Restore original takes them away."))
    # Both palettes are in the style sheet; Firefox picks one by itself.
    scheme_dependent: bool = False
    notes: list[str] = field(default_factory=lambda: [
        N_("Restart Firefox to see it (Firefox only reads these files when it starts)."),
        N_("Keep Firefox's theme on System theme or Dark/Light (Add-ons > Themes): the colours follow "
        "the light or dark style Firefox uses. Windows stay solid."),
        N_("Your own userChrome.css and userContent.css are kept; Fedora Glass only adds one import line, "
        "and Restore original takes it away again."),
        N_("Firefox keeps the 'allow userChrome.css' switch in its own settings after Restore. "
        "Without the Fedora Glass files it changes nothing; reset it in about:config if you like."),
    ])

    def detect(self, env: Env) -> Detection:
        if not installed(env, cmds=("firefox",), flatpak=FIREFOX_FLATPAK, desktop=("firefox", "org.mozilla.firefox"),
                         dirs=tuple(firefox_roots(env))):
            return Detection(False, _("{name} is not installed").format(name="Firefox"))
        if not firefox_profiles(env):
            return Detection(False, _("No Firefox profile yet: start Firefox once, then come back"))
        return Detection(True)

    @staticmethod
    def _skipped(profile: Path) -> bool:
        # A linked chrome folder or file points into someone's dotfiles: never write through it.
        chrome = profile / "chrome"
        return any(p.is_symlink() for p in (chrome, chrome / "userChrome.css", chrome / "userContent.css",
                                            chrome / ra.FIREFOX_CHROME_FILE, chrome / ra.FIREFOX_CONTENT_FILE,
                                            profile / "user.js"))

    def plan(self, ctx: Context) -> list[Action]:
        acts: list[Action] = []
        block = ("block", ra.FIREFOX_BEGIN, ra.FIREFOX_END)
        chrome_css = ra.firefox_chrome_css(*ctx.switching())
        content_css = ra.firefox_content_css(*ctx.switching())
        for prof in firefox_profiles(ctx.env):
            if self._skipped(prof):
                continue
            chrome = prof / "chrome"
            edits: list[WriteFile] = []
            for user_file, ours in (("userChrome.css", ra.FIREFOX_CHROME_FILE),
                                    ("userContent.css", ra.FIREFOX_CONTENT_FILE)):
                path = chrome / user_file
                text = _read_exact(path)
                if text is None:
                    break           # not text we can read: leave this profile alone
                edits.append(WriteFile(path, ra.css_import_block(text, ours), edits=block))
            else:
                ujs = prof / "user.js"
                text = _read_exact(ujs)
                if text is None:
                    continue
                acts += [WriteFile(chrome / ra.FIREFOX_CHROME_FILE, chrome_css),
                         WriteFile(chrome / ra.FIREFOX_CONTENT_FILE, content_css), *edits]
                if not ra.userjs_has_pref(text):
                    # The user's own line already turns it on: theirs is enough, and stays.
                    acts.append(WriteFile(ujs, ra.userjs_block(text), edits=block))
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        out = list(self.notes)
        skipped = [p.name for p in firefox_profiles(ctx.env) if self._skipped(p)]
        if skipped:
            out.insert(0, _("Left alone because its chrome folder or user.js is a link: {names}.").format(names=", ".join(skipped)))
        return out


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
        return Detection(False, _("{name} is not installed").format(name=self.name))

    def plan(self, ctx: Context) -> list[Action]:
        return []


@dataclass
class Slack(NotesOnly):
    def live_notes(self, ctx: Context) -> list[str]:
        theme = ra.slack_theme(ctx.tokens)
        return [
            _("Slack has no theme file. Open Preferences > Themes, scroll to the bottom, choose "
            "'Create a custom theme' and paste this string:"),
            theme,
        ]


TARGETS: list[Target] = [
    Discord(), VSCode(), VSCodium(), Obsidian(), QBittorrent(), Prism(), Browsers(),
    Slack(id="slack", name="Slack", group="Apps", cmds=("slack",), dirs=(".config/Slack",),
          summary=N_("No theme file; a ready-made sidebar theme string is shown to paste."),
          plain=N_("Changes nothing: Slack has no theme file. Paste the theme string from the Apps page instead."),
          scheme_dependent=True),
    NotesOnly(id="steam", name="Steam", group="Apps", cmds=("steam",), dirs=(".local/share/Steam",),
              summary=N_("Not themed: Steam draws its own UI."), scheme_dependent=False,
              plain=N_("Changes nothing: Steam draws its own look."),
              notes=[N_("Steam has no supported theme hook; third-party skins break on updates, so Fedora Glass leaves it alone.")]),
    NotesOnly(id="zoom", name="Zoom", group="Apps", cmds=("zoom",), dirs=(".zoom",),
              summary=N_("Not themed; follows the system dark mode."), scheme_dependent=False,
              plain=N_("Changes nothing: Zoom follows your light or dark setting by itself."),
              notes=[N_("In Zoom: Settings > General > Theme > Use system setting.")]),
    NotesOnly(id="claude-desktop", name="Claude Desktop", group="Apps",
              cmds=("claude-desktop",), dirs=(".config/Claude",), desktop=("com.anthropic.Claude",),
              summary=N_("Not themed; follows the system dark mode."), scheme_dependent=False,
              plain=N_("Changes nothing: Claude follows your light or dark setting by itself."),
              notes=[N_("In Claude: Settings > Appearance > Match system.")]),
    NotesOnly(id="libreoffice", name="LibreOffice", group="Apps", cmds=("libreoffice", "soffice"),
              dirs=(".config/libreoffice",),
              summary=N_("Follows the GTK 3 theme automatically."), scheme_dependent=False,
              plain=N_("Changes nothing here: LibreOffice picks up the GTK 3 look by itself."),
              notes=[N_("LibreOffice's GTK 3 backend picks up the adw-gtk3 glass theme. If it looks flat, "
                     "set Tools > Options > LibreOffice > View > Icon/Application colours to Automatic.")]),
    Firefox(),
]
