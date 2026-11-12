"""Kitty, Ghostty, Alacritty, Foot and WezTerm: our own file plus one marked line in the user's
settings; Restore original leaves the user's file byte-identical."""
from __future__ import annotations

import configparser
import re
import tomllib

import pytest

from fedoraglass import palette
from fedoraglass.engine import Engine
from fedoraglass.render import terminal as rt
from fedoraglass.settings import Settings
from fedoraglass.targets import terminal as tt
from fedoraglass.targets.base import Context, WriteFile

ALL = [tt.Kitty, tt.Ghostty, tt.Alacritty, tt.Foot]
MAIN = {"kitty": "kitty/kitty.conf", "ghostty": "ghostty/config", "alacritty": "alacritty/alacritty.toml",
        "foot": "foot/foot.ini"}
OWN = {"kitty": "kitty/fedora-glass.conf", "ghostty": "ghostty/fedora-glass.conf",
       "alacritty": "alacritty/fedora-glass.toml", "foot": "foot/fedora-glass.ini",
       "wezterm": "wezterm/colors/fedora-glass.toml"}
USERS = {"kitty": "font_size 12\nbackground_opacity 0.5\n", "ghostty": "font-size = 12\n",
         "alacritty": "[font]\nsize = 12\n\n[general]\nlive_config_reload = true\n", "foot": "[main]\nfont=mono\n"}


def ctx_for(env, dark=True, **kw):
    kw.setdefault("scheme", "dark" if dark else "light")
    s = Settings(**kw)
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d if dark else l, dark=d, light=l, env=env)


def snapshot(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()} | \
        {str(p.relative_to(folder)) + "/": b"" for p in folder.rglob("*") if p.is_dir()}


@pytest.fixture
def bare(fake_env, monkeypatch):
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: None)
    return fake_env


# ---- metadata and detection -------------------------------------------------------------------------
def test_targets_are_listed_with_names_and_plain_words():
    ids = {t.id: t for t in tt.TARGETS}
    for i, name in (("kitty", "Kitty"), ("ghostty", "Ghostty"), ("alacritty", "Alacritty"), ("foot", "Foot"),
                    ("wezterm", "WezTerm")):
        t = ids[i]
        assert t.name == name and t.group == "Terminal" and t.summary and t.notes
        assert t.plain.endswith(".") and t.plain != t.summary
        assert t.scheme_dependent            # re-applied when GNOME switches dark and light
    assert len(ids) == len(tt.TARGETS)


@pytest.mark.parametrize("cls", ALL + [tt.WezTerm])
def test_not_installed_then_found_by_folder_or_program(bare, monkeypatch, cls):
    t = cls()
    d = t.detect(bare)
    assert not d.available and d.detail == f"{t.name} is not installed"
    (bare.config / t.folder).mkdir(parents=True)
    assert t.detect(bare).available
    (bare.config / t.folder).rmdir()
    monkeypatch.setattr(type(bare), "which", lambda self, n: "/usr/bin/x" if n in t.cmds else None)
    assert t.detect(bare).available


def test_wezterm_found_by_its_home_lua_file(bare):
    assert not tt.WezTerm().detect(bare).available
    (bare.home / ".wezterm.lua").write_text("return {}")
    assert tt.WezTerm().detect(bare).available


# ---- rendered files ---------------------------------------------------------------------------------------
def test_kitty_and_ghostty_files_carry_16_colours_and_opacity(fake_env):
    c = ctx_for(fake_env, dark=True, terminal_opacity=0.8)
    p = rt.derive(c.tokens)
    kitty = tt.Kitty().plan(c)[0].content
    assert re.findall(r"^color(\d+) (#[0-9a-f]{6})$", kitty, re.M) == [(str(i), x.hex6) for i, x in enumerate(p.ansi)]
    for key in ("foreground", "background", "selection_foreground", "selection_background", "cursor",
                "cursor_text_color"):
        assert re.search(rf"^{key} #[0-9a-f]{{6}}$", kitty, re.M), key
    assert "background_opacity 0.8\n" in kitty
    ghostty = tt.Ghostty().plan(c)[0].content
    assert re.findall(r"^palette = (\d+)=(#[0-9a-f]{6})$", ghostty, re.M) == [(str(i), x.hex6) for i, x in enumerate(p.ansi)]
    assert f"background = {p.bg.hex6}\n" in ghostty and "background-opacity = 0.8\n" in ghostty
    for key in ("cursor-color", "cursor-text", "selection-background", "selection-foreground", "foreground"):
        assert re.search(rf"^{key} = #[0-9a-f]{{6}}$", ghostty, re.M), key


def test_alacritty_and_wezterm_files_are_valid_toml(fake_env):
    c = ctx_for(fake_env, terminal_opacity=0.7)
    p = rt.derive(c.tokens)
    a = tomllib.loads(tt.Alacritty().plan(c)[0].content)
    assert a["window"]["opacity"] == 0.7
    assert a["colors"]["primary"]["background"] == p.bg.hex6
    assert list(a["colors"]["normal"].values()) == [x.hex6 for x in p.ansi[:8]]
    assert list(a["colors"]["bright"].values()) == [x.hex6 for x in p.ansi[8:]]
    assert set(a["colors"]["selection"]) == {"text", "background"} and set(a["colors"]["cursor"]) == {"text", "cursor"}
    w = tomllib.loads(tt.WezTerm().plan(c)[0].content)
    assert w["metadata"]["name"] == "Fedora Glass"
    assert w["colors"]["ansi"] == [x.hex6 for x in p.ansi[:8]] and w["colors"]["brights"] == [x.hex6 for x in p.ansi[8:]]
    assert {"foreground", "background", "cursor_bg", "cursor_fg", "selection_bg", "selection_fg"} <= set(w["colors"])


def test_foot_file_parses_and_uses_bare_hex(fake_env):
    c = ctx_for(fake_env, terminal_opacity=0.9)
    cp = configparser.RawConfigParser()
    cp.read_string(tt.Foot().plan(c)[0].content)
    p = rt.derive(c.tokens)
    assert cp["colors"]["alpha"] == "0.9" and cp["colors"]["background"] == p.bg.hex6[1:]
    assert [cp["colors"][f"regular{i}"] for i in range(8)] == [x.hex6[1:] for x in p.ansi[:8]]
    assert [cp["colors"][f"bright{i}"] for i in range(8)] == [x.hex6[1:] for x in p.ansi[8:]]
    assert cp["cursor"]["color"] == f"{p.cursor_fg.hex6[1:]} {p.cursor.hex6[1:]}"


@pytest.mark.parametrize("cls", ALL + [tt.WezTerm])
def test_dark_and_light_differ_and_opacity_follows_the_setting(fake_env, cls):
    dark = cls().plan(ctx_for(fake_env, dark=True))[0].content
    light = cls().plan(ctx_for(fake_env, dark=False))[0].content
    assert dark != light
    if cls is not tt.WezTerm:
        a = cls().plan(ctx_for(fake_env, terminal_opacity=0.5))[0].content
        b = cls().plan(ctx_for(fake_env, terminal_opacity=0.95))[0].content
        assert a != b and "0.5" in a and "0.95" in b
        # Light glass stays at least 85% opaque unless the user chose a value (as in Ptyxis).
        assert "0.85" in cls().plan(ctx_for(fake_env, dark=False, terminal_opacity=None))[0].content or \
            tt.window_opacity(ctx_for(fake_env, dark=False)) >= 0.85


# ---- apply and restore -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("cls", ALL)
@pytest.mark.parametrize("variant", ["plain", "no-newline", "crlf", "empty", "missing"])
def test_apply_then_restore_leaves_the_users_file_byte_identical(fake_env, cls, variant):
    t = cls()
    main = fake_env.config / MAIN[t.id]
    user = USERS[t.id]
    if variant != "missing":
        main.parent.mkdir(parents=True)
        data = {"plain": user, "no-newline": user.rstrip("\n"), "crlf": user.replace("\n", "\r\n"), "empty": ""}[variant]
        main.write_bytes(data.encode())
    other = fake_env.config / MAIN[t.id].split("/")[0] / "my-other-file"
    if variant != "missing":
        other.write_bytes(b"keep")
    root = fake_env.config / t.folder
    before = snapshot(root) if root.exists() else {}
    eng = Engine(fake_env, [t])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    out = main.read_bytes().decode()
    assert out.count("Fedora Glass: begin") == 1 and out.count("Fedora Glass: end") == 1
    if variant == "crlf":
        assert "\n" not in out.replace("\r\n", "")      # our lines use the file's line endings too
    for line in (user if variant not in ("empty", "missing") else "").splitlines():
        assert line in out
    own = fake_env.config / OWN[t.id]
    assert own.is_file() and own.read_text().startswith("# Fedora Glass colours for")
    first = {p: p.read_bytes() for p in (main, own)}
    eng.apply(Settings())                                   # again: nothing changes, no second block
    assert {p: p.read_bytes() for p in (main, own)} == first
    assert main.read_text().count("Fedora Glass: begin") == 1
    assert eng.revert() == []
    assert (snapshot(root) if root.exists() else {}) == before
    assert not eng.is_applied()


@pytest.mark.parametrize("cls", ALL)
def test_restore_keeps_what_the_user_wrote_since(fake_env, cls):
    t = cls()
    main = fake_env.config / MAIN[t.id]
    main.parent.mkdir(parents=True)
    main.write_text(USERS[t.id])
    eng = Engine(fake_env, [t])
    eng.apply(Settings())
    main.write_text(main.read_text() + "# written later\n")
    assert eng.revert() == []
    assert main.read_text() == USERS[t.id] + "# written later\n"
    assert not (fake_env.config / OWN[t.id]).exists()


def test_include_lines_point_at_our_file(fake_env):
    for cls, want in ((tt.Kitty, "include fedora-glass.conf"), (tt.Ghostty, "config-file = ?fedora-glass.conf"),
                      (tt.Foot, f"include={fake_env.config}/foot/fedora-glass.ini")):
        acts = cls().plan(ctx_for(fake_env))
        main = acts[1].content
        assert want in main.splitlines() and acts[1].edits == ("block", "Fedora Glass: begin", "Fedora Glass: end")


def test_foot_include_goes_before_any_section(fake_env):
    main = fake_env.config / "foot/foot.ini"
    main.parent.mkdir(parents=True)
    main.write_text("[colors]\nbackground=000000\n")
    out = tt.Foot().plan(ctx_for(fake_env))[1].content
    assert out.index("include=") < out.index("[colors]")        # still the main section, and the user's [colors] win
    cp = configparser.RawConfigParser(strict=False)
    assert out.splitlines()[1].startswith("include=")


def test_ghostty_uses_the_config_file_the_user_has(fake_env):
    d = fake_env.config / "ghostty"
    d.mkdir(parents=True)
    (d / "config.ghostty").write_text("font-size = 10\n")
    assert tt.Ghostty().plan(ctx_for(fake_env))[1].path == d / "config.ghostty"
    (d / "config.ghostty").unlink()
    (d / "config").write_text("font-size = 10\n")
    assert tt.Ghostty().plan(ctx_for(fake_env))[1].path == d / "config"


# ---- Alacritty's TOML edit --------------------------------------------------------------------------------------------
def test_alacritty_import_goes_into_the_general_table(fake_env):
    main = fake_env.config / "alacritty/alacritty.toml"
    main.parent.mkdir(parents=True)
    main.write_text(USERS["alacritty"])
    out = tt.Alacritty().plan(ctx_for(fake_env))[1].content
    data = tomllib.loads(out)
    assert data["general"]["import"] == [str(fake_env.config / "alacritty/fedora-glass.toml")]
    assert data["general"]["live_config_reload"] is True and data["font"]["size"] == 12


def test_alacritty_without_general_table_appends_one(fake_env):
    main = fake_env.config / "alacritty/alacritty.toml"
    main.parent.mkdir(parents=True)
    main.write_text('[font]\nsize = 12')
    data = tomllib.loads(tt.Alacritty().plan(ctx_for(fake_env))[1].content)
    assert data["general"]["import"] and data["font"]["size"] == 12
    assert tomllib.loads(rt.alacritty_with_import("", '/p/"x".toml'))["general"]["import"] == ['/p/"x".toml']


def test_alacritty_with_its_own_import_is_not_edited_and_says_so(fake_env):
    main = fake_env.config / "alacritty/alacritty.toml"
    main.parent.mkdir(parents=True)
    main.write_text('[general]\nimport = ["~/themes/x.toml"]\n')
    c = ctx_for(fake_env)
    acts = tt.Alacritty().plan(c)
    assert [a.path.name for a in acts] == ["fedora-glass.toml"]
    assert "already have an import list" in tt.Alacritty().live_notes(c)[0]
    Engine(fake_env, [tt.Alacritty()]).apply(Settings())
    assert main.read_text() == '[general]\nimport = ["~/themes/x.toml"]\n'


def test_alacritty_old_yaml_is_left_alone(fake_env):
    d = fake_env.config / "alacritty"
    d.mkdir(parents=True)
    (d / "alacritty.yml").write_text("window: {}\n")
    assert tt.Alacritty().plan(ctx_for(fake_env)) == []
    assert "alacritty.yml" in tt.Alacritty().live_notes(ctx_for(fake_env))[0]


# ---- WezTerm -------------------------------------------------------------------------------------------------------------
def test_wezterm_only_adds_a_scheme_and_says_what_to_add(fake_env):
    d = fake_env.config / "wezterm"
    d.mkdir(parents=True)
    lua = d / "wezterm.lua"
    lua.write_bytes(b"local c = {}\r\nreturn c")
    t = tt.WezTerm()
    c = ctx_for(fake_env, terminal_opacity=0.8)
    acts = t.plan(c)
    assert [a.path for a in acts] == [d / "colors/fedora-glass.toml"] and all(not a.edits for a in acts)
    notes = t.live_notes(c)
    assert "config.color_scheme = 'Fedora Glass'" in notes and "config.window_background_opacity = 0.8" in notes
    before = snapshot(d)
    eng = Engine(fake_env, [t])
    eng.apply(Settings())
    assert lua.read_bytes() == b"local c = {}\r\nreturn c"
    assert (d / "colors/fedora-glass.toml").is_file()
    assert eng.revert() == []
    assert snapshot(d) == before


# ---- links ----------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cls", ALL + [tt.WezTerm])
def test_linked_settings_folder_is_never_replaced(fake_env, tmp_path, cls):
    t = cls()
    dot = tmp_path / "dotfiles"
    dot.mkdir()
    (dot / "keep").write_text("mine")
    fake_env.config.mkdir(parents=True)
    (fake_env.config / t.folder).symlink_to(dot)
    c = ctx_for(fake_env)
    assert t.plan(c) == []
    assert "is a link" in t.live_notes(c)[0]
    Engine(fake_env, [t]).apply(Settings())
    assert (fake_env.config / t.folder).is_symlink() and [p.name for p in dot.iterdir()] == ["keep"]


@pytest.mark.parametrize("cls", ALL)
def test_linked_settings_file_gets_our_file_but_is_not_edited(fake_env, tmp_path, cls):
    t = cls()
    real = tmp_path / "dotfiles-main"
    real.write_bytes(USERS[t.id].encode())
    main = fake_env.config / MAIN[t.id]
    main.parent.mkdir(parents=True)
    main.symlink_to(real)
    c = ctx_for(fake_env)
    assert [a.path for a in t.plan(c)] == [fake_env.config / OWN[t.id]]
    note = t.live_notes(c)[0]
    assert "is a link" in note and t.block_body(fake_env.config / OWN[t.id])[0] in note
    eng = Engine(fake_env, [t])
    eng.apply(Settings())
    assert main.is_symlink() and real.read_bytes() == USERS[t.id].encode()
    assert eng.revert() == []
    assert main.is_symlink() and not (fake_env.config / OWN[t.id]).exists()


@pytest.mark.parametrize("cls", ALL)
def test_a_linked_colour_file_is_not_followed(fake_env, tmp_path, cls):
    t = cls()
    target = tmp_path / "elsewhere"
    target.write_text("mine")
    own = fake_env.config / OWN[t.id]
    own.parent.mkdir(parents=True)
    own.symlink_to(target)
    assert t.plan(ctx_for(fake_env)) == []
    assert target.read_text() == "mine"


def test_unreadable_settings_file_is_left_alone(fake_env):
    main = fake_env.config / "kitty/kitty.conf"
    main.parent.mkdir(parents=True)
    main.write_bytes(b"\xff\xfe nope")
    acts = tt.Kitty().plan(ctx_for(fake_env))
    assert [a.path.name for a in acts] == ["fedora-glass.conf"]
    assert all(isinstance(a, WriteFile) for a in acts)
