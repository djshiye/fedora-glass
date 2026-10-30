from __future__ import annotations

import configparser
import json
import re

import pytest

from liquidglass import palette
from liquidglass.render import apps as ra
from liquidglass.render import terminal as rt
from liquidglass.settings import Settings
from liquidglass.targets import terminal as tt
from liquidglass.targets.base import Context, GSet, WriteFile

CASES = [(d, f) for d in (True, False) for f in (0.0, 0.5, 1.0)]


def toks(dark, frost, **kw):
    return palette.build(Settings(frost=frost, **kw), dark=dark)


def ctx_for(env, dark=True, frost=0.4, **kw):
    s = Settings(frost=frost, scheme="dark" if dark else "light", **kw)
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d if dark else l, dark=d, light=l, env=env)


@pytest.mark.parametrize("dark,frost", CASES)
def test_palette_is_legible(dark, frost):
    t = toks(dark, frost)
    p = rt.derive(t)
    assert len(p.ansi) == 16
    assert p.fg.contrast(p.bg) >= 7
    for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15):
        assert p.ansi[i].contrast(p.bg) >= 4.5, i
    assert p.ansi[8].contrast(p.bg) >= 4.0
    assert len({c.hex6 for c in p.ansi}) == 16


def test_palette_follows_accent():
    a = rt.derive(toks(True, 0.4, accent="#e62d42"))
    b = rt.derive(toks(True, 0.4, accent="#3584e4"))
    assert a.cursor != b.cursor and a.ansi[4] != b.ansi[4]


def test_ptyxis_palette_is_valid_keyfile():
    txt = rt.ptyxis_palette(toks(True, 0.3), toks(False, 0.3))
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    cp.read_string(txt)
    assert cp["Palette"]["Name"] == "Liquid Glass"
    for sec in ("Light", "Dark"):
        keys = set(cp[sec])
        assert {"Background", "Foreground", "Cursor"} <= keys
        assert {f"Color{i}" for i in range(16)} <= keys
        assert all(re.fullmatch(r"#[0-9a-f]{6}", v) for v in cp[sec].values())
    assert "None" not in txt


@pytest.mark.parametrize("dark,frost", CASES)
def test_btop_theme(dark, frost):
    txt = rt.btop_theme(toks(dark, frost))
    rows = dict(re.findall(r'theme\[(\w+)\]="(#[0-9a-f]{6})"', txt))
    for k in ("main_fg", "title", "hi_fg", "selected_bg", "cpu_start", "cpu_mid", "cpu_end",
              "download_end", "upload_start", "process_mid", "meter_bg", "div_line"):
        assert k in rows, k
    assert txt.count("theme[") == len(rows)


@pytest.mark.parametrize("dark,frost", CASES)
def test_micro_colorscheme(dark, frost):
    txt = rt.micro_colorscheme(toks(dark, frost))
    assert "None" not in txt
    for line in txt.splitlines()[1:]:
        assert re.fullmatch(r'color-link [\w.-]+ "(?:(?:bold|italic|underline) )?#[0-9a-f]{6}(,#[0-9a-f]{6})?"', line), line
    assert 'color-link default "#' in txt and ",#" not in next(l for l in txt.splitlines() if " default " in l)


def test_conf_set_only_touches_wanted_lines():
    conf = '#comment\r\nupdate_ms = 2000\ncolor_theme = "Default"\ntheme_background = True\nshown_boxes = "cpu mem"\n'
    new = ra.conf_set(conf, {"color_theme": '"liquid-glass"', "theme_background": "False"})
    assert new.splitlines(keepends=True)[0] == "#comment\r\n"
    assert 'color_theme = "liquid-glass"\n' in new and "theme_background = False\n" in new
    assert new.replace('"liquid-glass"', '"Default"').replace("False", "True") == conf
    assert ra.conf_set("a = 1\n", {"b": "2"}) == "a = 1\nb = 2\n"


# ---- targets ------------------------------------------------------------------------
def test_ptyxis_plan(fake_env):
    fake_env.gs[("org.gnome.Ptyxis", None)] = {
        "profile-uuids": "['76cf880fca2d7db1aa047b0c6a3ae60f', 'bad uuid/../x']",
        "default-profile-uuid": "'76cf880fca2d7db1aa047b0c6a3ae60f'",
    }
    plan = tt.Ptyxis().plan(ctx_for(fake_env, dark=True))
    wf = [a for a in plan if isinstance(a, WriteFile)]
    assert len(wf) == 1 and wf[0].path.name == "Liquid Glass.palette"
    assert wf[0].path.parent.parts[-2:] == ("org.gnome.Ptyxis", "palettes")
    gs = [a for a in plan if isinstance(a, GSet)]
    assert {a.path for a in gs} == {"/org/gnome/Ptyxis/Profiles/76cf880fca2d7db1aa047b0c6a3ae60f/"}
    assert {a.key: a.value for a in gs}["palette"] == "'Liquid Glass'"


def test_ptyxis_opacity_follows_user_value_and_light_floor(fake_env):
    fake_env.gs[("org.gnome.Ptyxis", None)] = {"profile-uuids": "['abcdef0123456789']", "default-profile-uuid": "''"}
    def opacity(**kw):
        plan = tt.Ptyxis().plan(ctx_for(fake_env, **kw))
        return float(next(a.value for a in plan if isinstance(a, GSet) and a.key == "opacity"))
    assert opacity(dark=True, terminal_opacity=0.5) == 0.5
    assert opacity(dark=False, terminal_opacity=0.5) == 0.5
    assert opacity(dark=False, frost=0.0) >= 0.85
    assert opacity(dark=True, frost=0.0) == pytest.approx(0.84)     # a little glass shows, text stays readable


def test_gnome_terminal_plan(fake_env):
    fake_env.gs[("org.gnome.Terminal.ProfilesList", None)] = {"list": "['b1dcc9dd-5262-4d8d-a863-c897e6d979b9']"}
    plan = tt.GnomeTerminal().plan(ctx_for(fake_env))
    vals = {a.key: a.value for a in plan}
    assert vals["use-theme-colors"] == "false" and vals["use-transparent-background"] == "true"
    assert vals["palette"].count("'#") == 16
    assert 0 <= int(vals["background-transparency-percent"]) <= 100
    assert all(a.path == "/org/gnome/terminal/legacy/profiles:/:b1dcc9dd-5262-4d8d-a863-c897e6d979b9/" for a in plan)


def test_btop_target_keeps_rest_of_conf(fake_env):
    d = fake_env.config / "btop"
    d.mkdir(parents=True)
    conf = 'color_theme = "Default"\ntheme_background = True\nvim_keys = False\n'
    (d / "btop.conf").write_text(conf)
    plan = tt.Btop().plan(ctx_for(fake_env))
    new = next(a.content for a in plan if a.path.name == "btop.conf")
    assert new == 'color_theme = "liquid-glass"\ntheme_background = False\nvim_keys = False\n'
    assert any(a.path.name == "liquid-glass.theme" for a in plan)


def test_btop_without_conf_skips_conf(fake_env):
    plan = tt.Btop().plan(ctx_for(fake_env))
    assert [a.path.name for a in plan] == ["liquid-glass.theme"]


def test_micro_merges_settings(fake_env):
    d = fake_env.config / "micro"
    d.mkdir(parents=True)
    (d / "settings.json").write_text('{"tabsize": 2, "colorscheme": "default"}')
    plan = tt.Micro().plan(ctx_for(fake_env))
    new = json.loads(next(a.content for a in plan if a.path.name == "settings.json"))
    assert new == {"tabsize": 2, "colorscheme": "liquid-glass"}


def test_micro_leaves_broken_settings_alone(fake_env):
    d = fake_env.config / "micro"
    d.mkdir(parents=True)
    (d / "settings.json").write_text("{ not json")
    plan = tt.Micro().plan(ctx_for(fake_env))
    assert [a.path.name for a in plan] == ["liquid-glass.micro"]


def test_detect_missing(fake_env, monkeypatch):
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: None)
    assert not tt.Btop().detect(fake_env).available
    assert not tt.Micro().detect(fake_env).available
    assert not tt.GnomeTerminal().detect(fake_env).available
    (fake_env.config / "btop").mkdir(parents=True)
    assert tt.Btop().detect(fake_env).available
