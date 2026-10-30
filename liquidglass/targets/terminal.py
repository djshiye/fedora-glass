"""Terminal emulators and terminal UIs: Ptyxis, GNOME Terminal, btop, micro."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..env import Env
from ..render import apps as ra
from ..render import headerbar
from ..render import terminal as rt
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


@dataclass
class Ptyxis(Target):
    id: str = "ptyxis"
    name: str = "Ptyxis"
    group: str = "Terminal"
    summary: str = "Window opacity on every profile, and the Liquid Glass colour palette if you turn it on."
    notes: list[str] = field(default_factory=lambda: [
        "Profiles keep their own colours unless you choose Liquid Glass terminal colours.",
        "Profiles are changed in place; reverting restores each profile's old palette and opacity.",
        "Ptyxis creates its first profile on first launch: open it once, then Apply again."])

    def detect(self, env: Env) -> Detection:
        if env.which("ptyxis") or Path("/usr/bin/ptyxis").exists() or env.flatpak_installed("app.devsuite.Ptyxis"):
            return Detection(True)
        return Detection(False, "Ptyxis is not installed")

    def palette_path(self, env: Env) -> Path:
        return env.data / "org.gnome.Ptyxis/palettes/Liquid Glass.palette"

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

    def plan(self, ctx: Context) -> list[Action]:
        opacity = window_opacity(ctx)
        titlebar = {name: headerbar.ptyxis_titlebar(ctx.settings, t, opacity)
                    for name, t in (("dark", ctx.dark), ("light", ctx.light))}
        acts: list[Action] = [WriteFile(self.palette_path(ctx.env),
                                        rt.ptyxis_palette(ctx.dark, ctx.light, titlebar))]
        for u in self.profiles(ctx.env):
            path = f"/org/gnome/Ptyxis/Profiles/{u}/"
            if ctx.settings.terminal_colors:
                acts.append(GSet("org.gnome.Ptyxis.Profile", "palette", f"'{rt.PTYXIS_PALETTE_NAME}'", path))
            acts.append(GSet("org.gnome.Ptyxis.Profile", "opacity", f"{opacity}", path))
        # Ptyxis's own style switch, only when the user asks; a value they pick later is kept.
        if ctx.settings.terminal_follows_style:
            acts.append(GSet("org.gnome.Ptyxis", "interface-style", "'system'", keep_user_change=True))
        else:
            acts.append(GReset("org.gnome.Ptyxis", "interface-style"))
        return acts


@dataclass
class GnomeTerminal(Target):
    id: str = "gnome-terminal"
    name: str = "GNOME Terminal"
    group: str = "Terminal"
    summary: str = "Glass palette, colours and transparency on every profile."
    notes: list[str] = field(default_factory=lambda: ["GNOME Terminal has one colour set per profile, so it follows the scheme in use when you Apply."])

    def detect(self, env: Env) -> Detection:
        if env.which("gnome-terminal"):
            return Detection(True)
        return Detection(False, "GNOME Terminal is not installed")

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
    group: str = "Terminal"
    summary: str = "Glass colour theme; btop's own background is dropped so the terminal glass shows."
    notes: list[str] = field(default_factory=lambda: ["Restart btop to load the theme. Only color_theme and theme_background are edited in btop.conf."])

    def detect(self, env: Env) -> Detection:
        if env.which("btop") or (env.config / "btop").is_dir():
            return Detection(True)
        return Detection(False, "btop is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        d = ctx.env.config / "btop"
        acts: list[Action] = [WriteFile(d / "themes/liquid-glass.theme", rt.btop_theme(ctx.tokens))]
        conf = d / "btop.conf"
        text = ra.read_text(conf)
        if text is not None:
            new = ra.conf_set(text, {"color_theme": '"liquid-glass"', "theme_background": "False"})
            acts.append(WriteFile(conf, new))
        return acts


@dataclass
class Micro(Target):
    id: str = "micro"
    name: str = "micro"
    group: str = "Terminal"
    summary: str = "Glass colour scheme with a transparent background."
    notes: list[str] = field(default_factory=lambda: ["Needs a true-colour terminal (Ptyxis is one)."])

    def detect(self, env: Env) -> Detection:
        if env.which("micro") or (env.config / "micro").is_dir():
            return Detection(True)
        return Detection(False, "micro is not installed")

    def plan(self, ctx: Context) -> list[Action]:
        d = ctx.env.config / "micro"
        acts: list[Action] = [WriteFile(d / "colorschemes/liquid-glass.micro", rt.micro_colorscheme(ctx.tokens))]
        sp = d / "settings.json"
        existing = ra.read_text(sp) if sp.exists() else None
        if not sp.exists() or existing is not None:
            merged = ra.merge_json_text(existing, {"colorscheme": "liquid-glass"})
            if merged is not None:
                acts.append(WriteFile(sp, merged))
        return acts


TARGETS: list[Target] = [Ptyxis(), GnomeTerminal(), Btop(), Micro()]
