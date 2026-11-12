"""Engine fixes from the 1.5.28 review: a style the user picked (Dark or Light) reaches the
apps that switch by themselves, linked app folders stay links, GNOME's high-contrast Shell
sheet under High Contrast, one Apply call from the app, and writes skipped when nothing changed."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from fedoraglass import engine as engine_mod
from fedoraglass.engine import Backup, Engine
from fedoraglass.render import apps as ra, gtk4, headerbar, shell as rs, terminal as rt
from fedoraglass.settings import Settings
from fedoraglass.targets import apps as ta, gtk as tg, shell as ts, terminal as tt
from fedoraglass.targets.base import Target, WriteFile

from test_firefox import make_profile

GNOME_STYLES = ("'default'", "'prefer-dark'")


def _gnome(env, style):
    env.gs[("org.gnome.desktop.interface", None)]["color-scheme"] = style


def _media(css: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in
            re.finditer(r"@media \(prefers-color-scheme: (\w+)\) \{(.*?)\n\}\n", css, re.S)}


def _ptyxis(env):
    env.gs[("org.gnome.Ptyxis", None)] = {"profile-uuids": "['0123456789abcdef0123456789abcdef']",
                                          "default-profile-uuid": "'0123456789abcdef0123456789abcdef'"}


def _outputs(env, settings) -> dict[str, str]:
    """What each part that switches by itself writes, by file name."""
    _ptyxis(env)
    (env.config / "Vencord").mkdir(parents=True, exist_ok=True)
    make_profile(env.home / ".mozilla/firefox")
    vault = env.home / "Notes"
    (vault / ".obsidian").mkdir(parents=True, exist_ok=True)
    (env.config / "obsidian").mkdir(parents=True, exist_ok=True)
    (env.config / "obsidian/obsidian.json").write_text('{"vaults": {"a": {"path": "%s"}}}' % vault)
    ctx = Engine(env, []).context(settings)
    out = {}
    for t in (tg.Gtk4(), tt.Ptyxis(), ta.Discord(), ta.Firefox(), ta.Obsidian()):
        for a in t.plan(ctx):
            if isinstance(a, WriteFile) and not a.edits and a.path.suffix in (".css", ".palette"):
                out[f"{t.id}:{a.path.name}"] = a.content
    return out


# ---- B1: Dark or Light picked by the user ------------------------------------------------------
@pytest.mark.parametrize("scheme", ("dark", "light"))
def test_a_picked_style_is_the_only_one_gtk4_apps_get(fake_env, scheme):
    css = {}
    for style in GNOME_STYLES:
        _gnome(fake_env, style)
        css[style] = tg.Gtk4().plan(Engine(fake_env, []).context(Settings(scheme=scheme)))[0].content
    assert css["'default'"] == css["'prefer-dark'"], "the same whatever GNOME says"
    blocks = _media(css["'default'"])
    assert set(blocks) == {"dark", "light"} and blocks["dark"] == blocks["light"]
    t = Engine(fake_env, []).context(Settings(scheme=scheme)).tokens
    assert t.dark == (scheme == "dark")
    assert css["'default'"] == gtk4.render(t, t) + headerbar.gtk4_css(Settings(scheme=scheme), t, t)


@pytest.mark.parametrize("scheme", ("dark", "light"))
def test_a_picked_style_reaches_every_part_that_switches_by_itself(fake_env, scheme):
    _gnome(fake_env, "'default'" if scheme == "dark" else "'prefer-dark'")     # GNOME says the other
    s = Settings(scheme=scheme, targets={"firefox-theme": True})
    out = _outputs(fake_env, s)
    t = Engine(fake_env, []).context(s).tokens
    assert out["discord:" + ra.DISCORD_THEME_FILE] == ra.discord_css(t, t)
    assert out["firefox-theme:" + ra.FIREFOX_CHROME_FILE] == ra.firefox_chrome_css(t, t)
    assert out["firefox-theme:" + ra.FIREFOX_CONTENT_FILE] == ra.firefox_content_css(t, t)
    assert out["obsidian:theme.css"] == ra.obsidian_css(t, t)
    palette = out["ptyxis:Fedora Glass.palette"]
    light, dark = palette.split("[Dark]")
    assert light.split("[Light]")[1].strip() == dark.strip(), "Ptyxis's light and dark are the same"


def test_follow_the_system_is_byte_identical(fake_env):
    """"Follow the system" writes exactly what it wrote before: both palettes."""
    s = Settings(targets={"firefox-theme": True})
    out = _outputs(fake_env, s)
    ctx = Engine(fake_env, []).context(s)
    d, l = ctx.dark, ctx.light
    assert d.dark and not l.dark
    assert out["gtk4:gtk.css"] == gtk4.render(d, l) + headerbar.gtk4_css(s, d, l)
    assert out["discord:" + ra.DISCORD_THEME_FILE] == ra.discord_css(d, l)
    assert out["firefox-theme:" + ra.FIREFOX_CHROME_FILE] == ra.firefox_chrome_css(d, l)
    assert out["firefox-theme:" + ra.FIREFOX_CONTENT_FILE] == ra.firefox_content_css(d, l)
    assert out["obsidian:theme.css"] == ra.obsidian_css(d, l)
    o = tt.window_opacity(ctx)
    titlebar = {n: headerbar.ptyxis_titlebar(s, t, o) for n, t in (("dark", d), ("light", l))}
    assert out["ptyxis:Fedora Glass.palette"] == rt.ptyxis_palette(d, l, titlebar)
    blocks = _media(out["gtk4:gtk.css"])
    assert blocks["dark"] != blocks["light"]
    # And the same in GNOME's light as in its dark: GTK 4 needs nothing at a switch.
    _gnome(fake_env, "'default'")
    assert _outputs(fake_env, s)["gtk4:gtk.css"] == out["gtk4:gtk.css"]


# ---- S3: parts that don't change at a dark/light switch ------------------------------------------
def test_gtk4_and_flatpak_are_left_out_of_a_dark_light_switch():
    assert tg.Gtk4().scheme_dependent is False
    assert tg.Flatpak().scheme_dependent is False
    assert tg.Gtk3().scheme_dependent is True       # GTK 3 can't switch by itself


def test_an_unchanged_flatpak_override_is_not_written_again(fake_env):
    eng = Engine(fake_env, [tg.Flatpak()])
    eng.apply(Settings())
    f = fake_env.data / "flatpak/overrides/global"
    before = f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns
    eng.apply(Settings())
    assert (f.read_bytes(), f.stat().st_ino, f.stat().st_mtime_ns) == before
    assert eng.revert() == [] and not f.read_text().strip()


# ---- B2: linked app folders ------------------------------------------------------------------------
class WriteTo(Target):
    def __init__(self, *paths: Path):
        super().__init__(id="probe", name="Probe")
        self.paths = paths

    def plan(self, ctx):
        return [WriteFile(p, "/* ours */") for p in self.paths]


def _dotfiles(env, sub: str, to: Path) -> Path:
    to.mkdir(parents=True, exist_ok=True)
    (to / "own.conf").write_text("mine")
    d = env.config / sub
    d.parent.mkdir(parents=True, exist_ok=True)
    d.symlink_to(to)
    return d


@pytest.mark.parametrize("sub", ("btop", "Code/User", "micro"))
def test_an_app_folder_linked_by_a_dotfiles_tool_stays_a_link(fake_env, sub):
    dots = fake_env.home / "dotfiles" / sub.replace("/", "-")
    d = _dotfiles(fake_env, sub, dots)
    probe = WriteTo(d / "themes/fedora-glass.theme", d / "own.conf")
    got = Engine(fake_env, [probe]).apply(Settings())
    assert [r.status for r in got] == ["applied"]
    assert d.is_symlink() and os.readlink(d) == str(dots), "still the user's link"
    assert (dots / "themes/fedora-glass.theme").read_text() == "/* ours */"
    assert (dots / "own.conf").read_text() == "/* ours */"
    assert Backup(fake_env).data["dirlinks"] == {}
    # Restore original puts back what the dotfiles folder held, through the same link.
    assert Engine(fake_env, [probe]).revert() == []
    assert d.is_symlink() and (dots / "own.conf").read_text() == "mine"
    assert not (dots / "themes").exists()


def test_an_app_folder_linked_outside_home_is_left_alone(fake_env, tmp_path):
    outside = tmp_path / "shared/btop"
    d = _dotfiles(fake_env, "btop", outside)
    probe = WriteTo(d / "themes/fedora-glass.theme", d / "own.conf")
    got = Engine(fake_env, [probe]).apply(Settings())
    assert [(r.status, r.message) for r in got] == [(
        "skipped", "Left alone: ~/.config/btop is a link to a folder outside your home folder, "
                   "or to one that isn't yours.")]
    assert d.is_symlink() and (outside / "own.conf").read_text() == "mine"
    assert not (outside / "themes").exists()
    assert Backup(fake_env).targets_with_changes() == set()


def test_a_deeper_link_out_of_home_is_left_alone(fake_env, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    dots = fake_env.home / "dotfiles/btop"
    d = _dotfiles(fake_env, "btop", dots)
    (dots / "themes").symlink_to(outside)
    got = Engine(fake_env, [WriteTo(d / "themes/fedora-glass.theme")]).apply(Settings())
    assert got[0].status == "skipped" and not any(outside.iterdir())


@pytest.mark.parametrize("kind", ("dangling", "file", "loop"))
def test_a_linked_app_folder_that_leads_nowhere_is_left_alone(fake_env, kind):
    d = fake_env.config / "btop"
    d.parent.mkdir(parents=True, exist_ok=True)
    if kind == "dangling":
        d.symlink_to(fake_env.home / "gone")
    elif kind == "file":
        (fake_env.home / "a-file").write_text("x")
        d.symlink_to(fake_env.home / "a-file")
    else:
        d.symlink_to(d)
    got = Engine(fake_env, [WriteTo(d / "btop.conf")]).apply(Settings())
    assert got[0].status == "skipped" and d.is_symlink()


def test_a_linked_app_folder_of_someone_else_is_left_alone(fake_env, monkeypatch):
    dots = fake_env.home / "dotfiles/btop"
    d = _dotfiles(fake_env, "btop", dots)
    monkeypatch.setattr(engine_mod.os, "getuid", lambda: os.getuid() + 1)
    got = Engine(fake_env, [WriteTo(d / "btop.conf")]).apply(Settings())
    assert got[0].status == "skipped" and not (dots / "btop.conf").exists()


def test_a_theme_folder_is_still_swapped(fake_env, tmp_path):
    """gtk-4.0 linked into a theme (even outside home) still becomes a real folder."""
    theme = tmp_path / "themes/Orchis/gtk-4.0"
    theme.mkdir(parents=True)
    (theme / "gtk.css").write_text("/* orchis */")
    d = fake_env.config / "gtk-4.0"
    d.parent.mkdir(parents=True, exist_ok=True)
    d.symlink_to(theme)
    eng = Engine(fake_env, [tg.Gtk4()])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    assert not d.is_symlink() and (theme / "gtk.css").read_text() == "/* orchis */"
    assert eng.revert() == [] and d.is_symlink()


def test_backup_swaps_only_theme_folders(fake_env):
    b = Backup(fake_env)
    for p in (fake_env.config / "gtk-3.0", fake_env.config / "gtk-4.0", fake_env.config / "Kvantum",
              fake_env.config / "Kvantum/FedoraGlass", fake_env.data / "themes",
              fake_env.data / "themes/FedoraGlass"):
        assert b.swaps(p), p
    for p in (fake_env.config / "btop", fake_env.config / "Code", fake_env.config / "micro",
              fake_env.config / "gtk-4.0-old", fake_env.data / "org.gnome.Ptyxis"):
        assert not b.swaps(p), p


# ---- B3: High Contrast ------------------------------------------------------------------------------
def _theme_resource(tmp_path, names):
    p = tmp_path / "gnome-shell-theme.gresource"
    p.write_bytes(b"GVariant\0\0\0\0" + b"\0".join(n.encode() for n in names) + b"\0css data")
    return p


def _hc(env, on: bool):
    env.gs[("org.gnome.desktop.a11y.interface", None)] = {"high-contrast": "true" if on else "false"}


def _shell_css(env):
    return next(a for a in ts.GnomeShell().plan(Engine(env, []).context(Settings()))
                if isinstance(a, WriteFile)).content


GNOME_50 = ("gnome-shell-dark.css", "gnome-shell-light.css", "gnome-shell-high-contrast.css", "pad-osd.css")


def test_high_contrast_builds_on_gnomes_high_contrast_sheet(fake_env, tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "SHELL_THEME_RESOURCE", _theme_resource(tmp_path, GNOME_50))
    _hc(fake_env, True)
    css = _shell_css(fake_env)
    assert '@import url("resource:///org/gnome/shell/theme/gnome-shell-high-contrast.css");' in css
    assert "gnome-shell-dark.css" not in css
    _hc(fake_env, False)
    assert '@import url("resource:///org/gnome/shell/theme/gnome-shell-dark.css");' in _shell_css(fake_env)


@pytest.mark.parametrize("names", (("gnome-shell-dark.css", "gnome-shell-light.css"),   # an older GNOME
                                   ("gnome-shell-high-contrast.css",),                   # not the Shell's theme
                                   None))                                               # no file at all
def test_high_contrast_without_gnomes_sheet_keeps_todays_import(fake_env, tmp_path, monkeypatch, names):
    res = _theme_resource(tmp_path, names) if names else tmp_path / "missing.gresource"
    monkeypatch.setattr(ts, "SHELL_THEME_RESOURCE", res)
    _hc(fake_env, True)
    css = _shell_css(fake_env)
    assert "gnome-shell-high-contrast.css" not in css
    assert '@import url("resource:///org/gnome/shell/theme/gnome-shell-dark.css");' in css


def test_the_theme_file_is_read_again_once_it_changes(tmp_path):
    res = _theme_resource(tmp_path, ("gnome-shell-dark.css",))
    assert not ts.shell_has_sheet(ts.HIGH_CONTRAST_SHEET, res)
    res.write_bytes(res.read_bytes() + b"gnome-shell-high-contrast.css")
    os.utime(res, ns=(1, 1))
    assert ts.shell_has_sheet(ts.HIGH_CONTRAST_SHEET, res)


def test_render_css_high_contrast_changes_only_the_import():
    from fedoraglass import palette
    t = palette.build(Settings(), dark=True)
    plain, hc = rs.render_css(t), rs.render_css(t, high_contrast=True)
    assert hc == plain.replace("gnome-shell-dark.css", "gnome-shell-high-contrast.css")


def test_a_pending_file_nested_too_deep_is_damaged_not_a_crash(fake_env):
    p = engine_mod.pending_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"[" * 100_000 + b"]" * 100_000)
    assert engine_mod.read_pending() == set()
    assert [r.status for r in Engine(fake_env, [tg.Flatpak()]).apply(Settings())] == ["applied"]
