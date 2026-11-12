"""Terminal emulators and terminal UIs: Ptyxis, GNOME Terminal, Kitty, Ghostty, Alacritty, Foot,
WezTerm, btop, micro."""

from __future__ import annotations

import configparser
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..i18n import _, N_
from ..env import Env
from ..render import apps as ra
from ..render import headerbar
from ..render import terminal as rt
from .. import unmerge
from .apps import _read_exact
from .base import Action, Context, Detection, GReset, GSet, Target, WriteFile

_UUID = re.compile(r"'([^']+)'")


def _list_values(text: str | None) -> list[str]:
    return _UUID.findall(text or "")


def _safe_uuid(u: str) -> bool:
    return bool(re.fullmatch(r"[0-9A-Za-z-]{8,64}", u))


def window_opacity(ctx: Context) -> float:
    """Light glass over a dark wallpaper turns grey and kills text contrast, so unless the
    user chose an opacity, light terminals stay at least 85% opaque."""
    o = ctx.tokens.terminal_opacity
    if not ctx.tokens.dark and ctx.settings.terminal_opacity is None:
        o = max(o, 0.85)
    return round(o, 3)


PTYXIS_FLATPAKS = ("app.devsuite.Ptyxis", "org.gnome.Ptyxis")


def ptyxis_flatpak(env: Env) -> str | None:
    """The id of the Flatpak Ptyxis, if one is installed."""
    return next((i for i in PTYXIS_FLATPAKS if env.flatpak_installed(i)), None)


def ptyxis_native(env: Env) -> bool:
    return bool(env.which("ptyxis") or Path("/usr/bin/ptyxis").exists())


def _keyfile(text: str) -> configparser.RawConfigParser | None:
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    try:
        cp.read_string(text)
    except configparser.Error:
        return None
    return cp


@dataclass
class Ptyxis(Target):
    id: str = "ptyxis"
    name: str = "Ptyxis"
    plain: str = (N_("Makes Ptyxis windows see-through on every profile, and uses the Fedora Glass colours "
                  "if you turned them on."))
    group: str = "Terminal"
    summary: str = N_("Window opacity on every profile, and the Fedora Glass colour palette if you turn it on.")
    notes: list[str] = field(default_factory=lambda: [
        N_("Profiles keep their own colours unless you choose Fedora Glass terminal colours."),
        N_("Profiles are changed in place; reverting restores each profile's old palette and opacity."),
        N_("Ptyxis creates its first profile on first launch: open it once, then Apply again.")])

    def detect(self, env: Env) -> Detection:
        if ptyxis_native(env) or ptyxis_flatpak(env):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="Ptyxis"))

    def palette_path(self, env: Env) -> Path:
        return env.data / "org.gnome.Ptyxis/palettes/Fedora Glass.palette"

    # Ptyxis from Flatpak has no door to the desktop's settings store (its permissions
    # carry no dconf access), so it keeps its settings in a file of its own, and its
    # palettes in its own data folder. Writing the desktop's settings would change nothing there.
    def flatpak_keyfile(self, env: Env, app_id: str) -> Path:
        return env.home / ".var/app" / app_id / "config/glib-2.0/settings/keyfile"

    def flatpak_palette(self, env: Env, app_id: str) -> Path:
        return env.home / ".var/app" / app_id / "data/org.gnome.Ptyxis/palettes/Fedora Glass.palette"

    def profiles(self, env: Env) -> list[str]:
        uuids = _list_values(env.gsettings_get("org.gnome.Ptyxis", "profile-uuids"))
        default = _list_values(env.gsettings_get("org.gnome.Ptyxis", "default-profile-uuid"))
        out: list[str] = []
        for u in uuids + default:
            if _safe_uuid(u) and u not in out:
                out.append(u)
        return out

    def palette_in_use(self, env: Env) -> str | None:
        """The palette of the profile new Terminal windows open with, or None when Ptyxis
        has no profile yet."""
        default = _list_values(env.gsettings_get("org.gnome.Ptyxis", "default-profile-uuid"))
        uuids = [u for u in default + self.profiles(env) if _safe_uuid(u)]
        if not uuids:
            return None
        names = _list_values(env.gsettings_get("org.gnome.Ptyxis.Profile", "palette",
                                               f"/org/gnome/Ptyxis/Profiles/{uuids[0]}/"))
        return names[0] if names else None

    def _titlebars(self, ctx: Context, opacity: float) -> dict:
        return {name: headerbar.ptyxis_titlebar(ctx.settings, t, opacity)
                for name, t in (("dark", ctx.dark), ("light", ctx.light))}

    def plan(self, ctx: Context) -> list[Action]:
        opacity = window_opacity(ctx)
        titlebar = self._titlebars(ctx, opacity)
        palette = rt.ptyxis_palette(ctx.dark, ctx.light, titlebar)
        fp = ptyxis_flatpak(ctx.env)
        acts: list[Action] = []
        if ptyxis_native(ctx.env) or fp is None:
            acts.append(WriteFile(self.palette_path(ctx.env), palette))
            acts += self._host_settings(ctx, opacity)
        if fp is not None:
            acts += self._flatpak_actions(ctx, fp, opacity, palette)
        return acts

    def _host_settings(self, ctx: Context, opacity: float) -> list[Action]:
        acts: list[Action] = []
        for u in self.profiles(ctx.env):
            path = f"/org/gnome/Ptyxis/Profiles/{u}/"
            if ctx.settings.terminal_colors:
                acts.append(GSet("org.gnome.Ptyxis.Profile", "palette", f"'{rt.PTYXIS_PALETTE_NAME}'", path))
            else:
                # Turned off: the profile gets its own palette back (a no-op if we never set it).
                acts.append(GReset("org.gnome.Ptyxis.Profile", "palette", path))
            acts.append(GSet("org.gnome.Ptyxis.Profile", "opacity", f"{opacity}", path))
        # Ptyxis's own style switch, only when the user asks; a value they pick later is kept.
        if ctx.settings.terminal_follows_style:
            acts.append(GSet("org.gnome.Ptyxis", "interface-style", "'system'", keep_user_change=True))
        else:
            acts.append(GReset("org.gnome.Ptyxis", "interface-style"))
        return acts

    def _flatpak_actions(self, ctx: Context, app_id: str, opacity: float, palette: str) -> list[Action]:
        env = ctx.env
        acts: list[Action] = [WriteFile(self.flatpak_palette(env, app_id), palette)]
        kf = self.flatpak_keyfile(env, app_id)
        text = _read_exact(kf)
        cp = _keyfile(text) if text else None
        if text is None or (text and cp is None):
            return acts          # a link or not text: left alone (live_notes says so)
        uuids: list[str] = []
        if cp is not None and cp.has_section("org/gnome/Ptyxis"):
            for key in ("profile-uuids", "default-profile-uuid"):
                for u in _list_values(cp.get("org/gnome/Ptyxis", key, fallback="")):
                    if _safe_uuid(u) and u not in uuids:
                        uuids.append(u)
        if not uuids:
            return acts
        edits: list = []
        new = text
        for u in uuids:
            section = f"org/gnome/Ptyxis/Profiles/{u}"
            if ctx.settings.terminal_colors:
                new = ra.ini_set(new, section, {"palette": f"'{rt.PTYXIS_PALETTE_NAME}'", "opacity": f"{opacity}"})
            else:
                new = ra.ini_set(new, section, {"opacity": f"{opacity}"})
                if unmerge.ini_get(new, section, "palette") == f"'{rt.PTYXIS_PALETTE_NAME}'":
                    new = unmerge.ini_del(new, section, "palette")      # ours from before: the profile's own again
            edits.append((section, ("palette", "opacity")))
        acts.append(WriteFile(kf, new, edits=("inis", tuple(edits))))
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        out = list(self.notes)
        fp = ptyxis_flatpak(ctx.env)
        if fp is not None:
            out.append(_("Ptyxis from Flatpak keeps its settings in its own file, which Fedora Glass changes. "
                         "Restart Ptyxis to see it."))
            kf = self.flatpak_keyfile(ctx.env, fp)
            text = _read_exact(kf)
            if text is None or (text and _keyfile(text) is None):
                out.insert(0, _("The Flatpak Ptyxis settings file is a link or can't be read, so its profiles were not changed."))
        return out


@dataclass
class GnomeTerminal(Target):
    id: str = "gnome-terminal"
    name: str = "GNOME Terminal"
    plain: str = N_("Sets the colours and the see-through background on every GNOME Terminal profile.")
    group: str = "Terminal"
    summary: str = N_("Glass palette, colours and transparency on every profile.")
    notes: list[str] = field(default_factory=lambda: [N_("GNOME Terminal has one colour set per profile, so it follows the scheme in use when you Apply.")])

    def detect(self, env: Env) -> Detection:
        if env.which("gnome-terminal"):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="GNOME Terminal"))

    def plan(self, ctx: Context) -> list[Action]:
        env, t = ctx.env, ctx.tokens
        uuids = [u for u in _list_values(env.gsettings_get("org.gnome.Terminal.ProfilesList", "list"))
                 if _safe_uuid(u)]
        p = rt.derive(t)
        pal = rt.gvariant_str_list([c.hex6 for c in p.ansi])
        pct = round((1 - window_opacity(ctx)) * 100)
        acts: list[Action] = []
        for u in uuids:
            path = f"/org/gnome/terminal/legacy/profiles:/:{u}/"
            for key, val in (
                ("use-theme-colors", "false"), ("palette", pal),
                ("background-color", f"'{p.bg.hex6}'"), ("foreground-color", f"'{p.fg.hex6}'"),
                ("bold-color-same-as-fg", "true"),
                ("cursor-colors-set", "true"), ("cursor-background-color", f"'{p.cursor.hex6}'"),
                ("cursor-foreground-color", f"'{p.cursor_fg.hex6}'"),
                ("highlight-colors-set", "true"),
                ("highlight-background-color", f"'{p.selection_bg.hex6}'"),
                ("highlight-foreground-color", f"'{p.selection_fg.hex6}'"),
                ("use-theme-transparency", "false"), ("use-transparent-background", "true"),
                ("background-transparency-percent", str(pct)),
            ):
                acts.append(GSet("org.gnome.Terminal.Legacy.Profile", key, val, path))
        return acts


@dataclass
class Btop(Target):
    id: str = "btop"
    name: str = "btop"
    plain: str = N_("Adds a Fedora Glass colour theme for btop and selects it, without btop's own background.")
    group: str = "Terminal"
    summary: str = N_("Glass colour theme; btop's own background is dropped so the terminal glass shows.")
    notes: list[str] = field(default_factory=lambda: [N_("Restart btop to load the theme. Only color_theme and theme_background are set in btop.conf (made if btop hasn't written one yet).")])

    def detect(self, env: Env) -> Detection:
        if env.which("btop") or (env.config / "btop").is_dir():
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="btop"))

    def plan(self, ctx: Context) -> list[Action]:
        d = ctx.env.config / "btop"
        acts: list[Action] = [WriteFile(d / "themes/fedora-glass.theme", rt.btop_theme(ctx.tokens))]
        conf = d / "btop.conf"
        # btop writes btop.conf on its first exit. Before that there is none, so start one
        # with only these two settings: btop fills in the rest with its defaults.
        text = ra.read_text(conf) if conf.exists() or conf.is_symlink() else "#? Config file for btop\n"
        if text is not None:
            new = ra.conf_set(text, {"color_theme": '"fedora-glass"', "theme_background": "False"})
            acts.append(WriteFile(conf, new, edits=("conf", ("color_theme", "theme_background"))))
        return acts


@dataclass
class Micro(Target):
    id: str = "micro"
    name: str = "micro"
    plain: str = N_("Adds a Fedora Glass colour scheme for micro and selects it.")
    group: str = "Terminal"
    summary: str = N_("Glass colour scheme with a transparent background.")
    notes: list[str] = field(default_factory=lambda: [N_("Needs a true-colour terminal (Ptyxis is one).")])

    def detect(self, env: Env) -> Detection:
        if env.which("micro") or (env.config / "micro").is_dir():
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name="micro"))

    def plan(self, ctx: Context) -> list[Action]:
        d = ctx.env.config / "micro"
        acts: list[Action] = [WriteFile(d / "colorschemes/fedora-glass.micro", rt.micro_colorscheme(ctx.tokens))]
        sp = d / "settings.json"
        existing = ra.read_text(sp) if sp.exists() else None
        if not sp.exists() or existing is not None:
            merged = ra.merge_json_text(existing, {"colorscheme": "fedora-glass"})
            if merged is not None:
                acts.append(WriteFile(sp, merged, edits=("json", ("colorscheme",))))
        return acts


class _Skip(Exception):
    """Something at this terminal's settings is a link we must not write through."""


@dataclass
class IncludeTerminal(Target):
    """A terminal with a settings file the user keeps: our colours go in a file of our own, and
    the user's file gets one marked block that points at it (WezTerm's is Lua: no block).
    Restore takes the block away again, so the user's file is as it was."""
    group: str = "Terminal"
    cmds: tuple[str, ...] = ()
    folder: str = ""                       # under ~/.config
    main_files: tuple[str, ...] = ()       # the user's settings file, in order of preference
    own_file: str = "fedora-glass.conf"    # ours, in the same folder
    where: str = "top"
    extra_dirs: tuple[str, ...] = ()       # paths under $HOME that also mean "installed"

    def detect(self, env: Env) -> Detection:
        if (any(env.which(c) for c in self.cmds) or (env.config / self.folder).exists()
                or any((env.home / d).exists() for d in self.extra_dirs)):
            return Detection(True)
        return Detection(False, _("{name} is not installed").format(name=self.name))

    # -- what the subclasses say --
    def render(self, p: rt.TermPalette, opacity: float) -> str:
        raise NotImplementedError

    def block_body(self, own: Path) -> list[str]:
        raise NotImplementedError

    def edit(self, text: str, own: Path) -> str | None:
        """The user's settings with our block in; None when they can't take it."""
        return rt.with_block(text, self.block_body(own), self.where)

    def manual_line(self, own: Path) -> str:
        return "\n".join(self.block_body(own))

    # -- paths --
    def own_path(self, env: Env) -> Path:
        return env.config / self.folder / self.own_file

    def main_path(self, env: Env) -> Path:
        base = env.config / self.folder
        for m in self.main_files:
            if (base / m).exists() or (base / m).is_symlink():
                return base / m
        return base / self.main_files[0]

    def _check_links(self, env: Env) -> None:
        # A settings folder linked into a dotfiles repo is the user's: the engine would have
        # to swap the link for a real folder to write there, which we never do.
        own = self.own_path(env)
        d = env.config
        linked = any((d := d / part).is_symlink() for part in own.parent.relative_to(env.config).parts)
        if linked or own.is_symlink():
            raise _Skip(_("{name}'s settings folder is a link, so Fedora Glass left it alone.").format(name=self.name))

    def status(self, env: Env) -> tuple[str | None, str | None]:
        """(why nothing is written at all, why our block is not added to the user's file)."""
        try:
            self._check_links(env)
        except _Skip as e:
            return str(e), None
        if not self.main_files:
            return None, None
        text = _read_exact(self.main_path(env))
        if text is None:
            return None, "link"
        if self.edit(text, self.own_path(env)) is None:
            return None, "own"
        return None, None

    def plan(self, ctx: Context) -> list[Action]:
        env = ctx.env
        stop, _blocked = self.status(env)
        if stop:
            return []
        own = self.own_path(env)
        acts: list[Action] = [WriteFile(own, self.render(rt.derive(ctx.tokens), window_opacity(ctx)))]
        if self.main_files:
            main = self.main_path(env)
            text = _read_exact(main)
            new = self.edit(text, own) if text is not None else None
            if new is not None:
                acts.append(WriteFile(main, new, edits=("block", rt.BLOCK_BEGIN, rt.BLOCK_END)))
        return acts

    def live_notes(self, ctx: Context) -> list[str]:
        out = list(self.notes)
        stop, blocked = self.status(ctx.env)
        own = self.own_path(ctx.env)
        if stop:
            out.insert(0, stop)
        elif blocked == "link":
            out.insert(0, _("Your {name} settings file is a link or can't be read, so Fedora Glass did not change it. "
                            "Add this to it yourself:\n{line}").format(name=self.name, line=self.manual_line(own)))
        elif blocked == "own":
            out.insert(0, _("Your {name} settings already have an import list, so Fedora Glass did not change it. "
                            "Add this file to it yourself: {path}").format(name=self.name, path=own))
        return out


@dataclass
class Kitty(IncludeTerminal):
    id: str = "kitty"
    name: str = "Kitty"
    summary: str = N_("Glass colours and see-through background, in a file Kitty includes.")
    plain: str = N_("Adds a Fedora Glass colour file for Kitty and one include line to kitty.conf. Restore original takes the line away.")
    cmds: tuple[str, ...] = ("kitty",)
    folder: str = "kitty"
    main_files: tuple[str, ...] = ("kitty.conf",)
    notes: list[str] = field(default_factory=lambda: [
        N_("Open a new Kitty window, or press Ctrl+Shift+F5, to load it. Colours and opacity you set in kitty.conf yourself win."),
        N_("Follows the GNOME dark or light style in use when you Apply.")])

    def render(self, p, opacity):
        return rt.kitty_conf(p, opacity)

    def block_body(self, own):
        return [f"include {own.name}"]


@dataclass
class Ghostty(IncludeTerminal):
    id: str = "ghostty"
    name: str = "Ghostty"
    summary: str = N_("Glass colours and see-through background, in a file Ghostty includes.")
    plain: str = N_("Adds a Fedora Glass colour file for Ghostty and one config-file line to its config. Restore original takes the line away.")
    cmds: tuple[str, ...] = ("ghostty",)
    folder: str = "ghostty"
    main_files: tuple[str, ...] = ("config.ghostty", "config")
    where: str = "end"
    notes: list[str] = field(default_factory=lambda: [
        N_("Reload Ghostty's settings or restart it. Ghostty reads the Fedora Glass file after your own, so its colours and opacity win."),
        N_("Follows the GNOME dark or light style in use when you Apply.")])

    def main_path(self, env):
        base = env.config / self.folder
        for m in self.main_files:
            if (base / m).exists() or (base / m).is_symlink():
                return base / m
        return base / "config"          # read by every Ghostty version

    def render(self, p, opacity):
        return rt.ghostty_conf(p, opacity)

    def block_body(self, own):
        return [f"config-file = ?{own.name}"]


@dataclass
class Alacritty(IncludeTerminal):
    id: str = "alacritty"
    name: str = "Alacritty"
    summary: str = N_("Glass colours and see-through background, in a file Alacritty imports.")
    plain: str = N_("Adds a Fedora Glass colour file for Alacritty and one import line to alacritty.toml. Restore original takes the line away.")
    cmds: tuple[str, ...] = ("alacritty",)
    folder: str = "alacritty"
    main_files: tuple[str, ...] = ("alacritty.toml",)
    own_file: str = "fedora-glass.toml"
    where: str = "end"
    notes: list[str] = field(default_factory=lambda: [
        N_("Needs Alacritty 0.14 or newer. It reloads by itself. Colours and opacity you set in alacritty.toml yourself win."),
        N_("Follows the GNOME dark or light style in use when you Apply.")])

    def status(self, env):
        stop, blocked = super().status(env)
        # The old alacritty.yml format can't import a TOML file.
        if not stop and (env.config / "alacritty/alacritty.yml").exists() and not self.main_path(env).exists():
            return _("{name} is using its old alacritty.yml file, so Fedora Glass left it alone.").format(name=self.name), None
        return stop, blocked

    def render(self, p, opacity):
        return rt.alacritty_toml(p, opacity)

    def block_body(self, own):
        return [f"import = [{rt.toml_string(str(own))}]"]

    def edit(self, text, own):
        return rt.alacritty_with_import(text, str(own))


@dataclass
class Foot(IncludeTerminal):
    id: str = "foot"
    name: str = "Foot"
    summary: str = N_("Glass colours and see-through background, in a file Foot includes.")
    plain: str = N_("Adds a Fedora Glass colour file for Foot and one include line to foot.ini. Restore original takes the line away.")
    cmds: tuple[str, ...] = ("foot", "footclient")
    folder: str = "foot"
    main_files: tuple[str, ...] = ("foot.ini",)
    own_file: str = "fedora-glass.ini"
    notes: list[str] = field(default_factory=lambda: [
        N_("Open a new Foot window to see it. Colours and opacity you set in foot.ini yourself win."),
        N_("Follows the GNOME dark or light style in use when you Apply.")])

    def render(self, p, opacity):
        return rt.foot_ini(p, opacity)

    def block_body(self, own):
        return [f"include={own}"]


@dataclass
class WezTerm(IncludeTerminal):
    """WezTerm's settings are a Lua program: never edited. Only a colour scheme file is made."""
    id: str = "wezterm"
    name: str = "WezTerm"
    summary: str = N_("A Fedora Glass colour scheme for WezTerm; you choose it once yourself.")
    plain: str = N_("Adds a Fedora Glass colour scheme file for WezTerm. Your wezterm.lua is never changed; the note says what to add.")
    cmds: tuple[str, ...] = ("wezterm",)
    folder: str = "wezterm"
    main_files: tuple[str, ...] = ()
    extra_dirs: tuple[str, ...] = (".wezterm.lua",)
    notes: list[str] = field(default_factory=lambda: [
        N_("WezTerm settings are a Lua program, so Fedora Glass never edits them. Add the two lines below to your wezterm.lua once; the colours then follow each Apply."),
    ])

    def own_path(self, env):
        return env.config / "wezterm/colors/fedora-glass.toml"

    def render(self, p, opacity):
        return rt.wezterm_scheme(p)

    def live_notes(self, ctx):
        out = super().live_notes(ctx)
        out.append(f"config.color_scheme = '{rt.WEZTERM_SCHEME_NAME}'")
        out.append(f"config.window_background_opacity = {rt._fmt_opacity(window_opacity(ctx))}")
        return out


TARGETS: list[Target] = [Ptyxis(), GnomeTerminal(), Kitty(), Ghostty(), Alacritty(), Foot(), WezTerm(), Btop(), Micro()]
