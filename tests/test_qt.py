"""Kvantum theme and the Qt target."""

from __future__ import annotations

from pathlib import Path
import configparser
import re
import xml.etree.ElementTree as ET

import pytest

from liquidglass import palette
from liquidglass.render import kvantum
from liquidglass.settings import Settings
from liquidglass.targets import qt
from liquidglass.targets.base import Context, FlatpakOverride, WriteFile

SIDES = kvantum.SIDES
CASES = [(f, d) for f in (0.0, 0.5, 1.0) for d in (True, False)]


def tokens(frost: float = 0.45, dark: bool = True, **kw):
    return palette.build(Settings(frost=frost, **kw), dark=dark)


def parse_config(text: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str  # type: ignore[assignment]
    cp.read_string(text)
    return cp


def svg_ids(svg: str) -> set[str]:
    root = ET.fromstring(svg)
    return {e.get("id") for e in root.iter() if e.get("id")}


@pytest.mark.parametrize("frost,dark", CASES)
def test_config_sections_and_keys(frost, dark):
    t = tokens(frost, dark)
    cp = parse_config(kvantum.build_config(t))
    for sec in ("%General", "GeneralColors", "Hacks", "PanelButtonCommand", "LineEdit", "Tab",
                "ItemView", "MenuItem", "Menu", "ScrollbarSlider", "Progressbar", "ToolTip"):
        assert sec in cp, sec
    g = cp["%General"]
    assert g["composite"] == "true" and g["translucent_windows"] == "true"
    assert g["blurring"] == "false"
    assert 0 <= int(g["reduce_window_opacity"]) <= 90
    c = cp["GeneralColors"]
    assert c["text.color"] == t.fg.hex6
    assert c["highlight.color"] == t.accent.hex6
    assert c["window.color"].startswith("#") and len(c["window.color"]) == 7


@pytest.mark.parametrize("frost,dark", CASES)
def test_svg_is_well_formed_and_has_every_referenced_element(frost, dark):
    t = tokens(frost, dark)
    config = kvantum.build_config(t)
    ids = svg_ids(kvantum.build_svg(t))
    refs = kvantum.referenced_elements(config)
    for name in refs["frame"]:
        for side in SIDES:
            assert f"{name}-normal-{side}" in ids, f"{name}-normal-{side}"
        assert f"{name}-normal" in ids
    for name in refs["interior"]:
        assert f"{name}-normal" in ids, name
    for name in refs["indicator"]:
        if name == "arrow-down":
            assert "arrow-down-normal" in ids
        elif name == "arrow":
            assert {f"arrow-{d}-normal" for d in ("up", "down", "left", "right")} <= ids
        elif name == "menuitem":
            assert {"menuitem-left-normal", "menuitem-right-normal"} <= ids
        elif name == "tree":
            assert {"tree-plus-normal", "tree-minus-normal"} <= ids
        else:
            assert f"{name}-normal" in ids, name


def test_state_pieces_exist_for_interactive_elements():
    ids = svg_ids(kvantum.build_svg(tokens()))
    for name, states in (("button", ("focused", "pressed", "toggled")),
                         ("tbutton", ("focused", "pressed", "toggled")),
                         ("lineedit", ("focused",)), ("tab", ("focused", "toggled")),
                         ("itemview", ("focused", "toggled", "pressed")),
                         ("menuitem", ("focused", "toggled")),
                         ("scrollbarslider", ("focused", "pressed")),
                         ("slider", ("toggled",))):
        for s in states:
            assert f"{name}-{s}" in ids
            assert all(f"{name}-{s}-{side}" in ids for side in SIDES), (name, s)
    for kind in ("checkbox", "radio", "item-checkbox", "menu-checkbox", "menu-radio"):
        for v in ("", "checked-"):
            assert f"{kind}-{v}normal" in ids
    assert {"slidercursor-normal", "slidercursor-pressed"} <= ids


def test_ids_are_unique():
    root = ET.fromstring(kvantum.build_svg(tokens()))
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids))


def test_svg_has_no_junk():
    for f, d in CASES:
        svg = kvantum.build_svg(tokens(f, d))
        assert "None" not in svg and "nan" not in svg
        for v in re.findall(r'(?:fill|stroke|stop-color)="(#[^"]*)"', svg):
            assert re.fullmatch(r"#[0-9a-f]{6}", v), v
        for v in re.findall(r'opacity="([^"]*)"', svg):
            assert 0 <= float(v) <= 1, v


def test_colours_follow_tokens():
    blue = kvantum.build_svg(tokens(accent="#3584e4"))
    pink = kvantum.build_svg(tokens(accent="#d56199"))
    assert "#3584e4" in blue and "#3584e4" not in pink
    assert "#d56199" in pink
    dark, light = tokens(dark=True), tokens(dark=False)
    assert kvantum.build_svg(dark) != kvantum.build_svg(light)
    assert kvantum.build_config(dark) != kvantum.build_config(light)
    assert parse_config(kvantum.build_config(dark))["GeneralColors"]["text.color"] == dark.fg.hex6


def test_radius_scales_frames():
    small = parse_config(kvantum.build_config(tokens(radius=8)))
    big = parse_config(kvantum.build_config(tokens(radius=28)))
    assert int(small["PanelButtonCommand"]["frame.top"]) < int(big["PanelButtonCommand"]["frame.top"])


def test_light_windows_keep_body_over_dark_wallpapers():
    for f in (0.0, 0.3):
        cp = parse_config(kvantum.build_config(tokens(f, dark=False)))
        assert int(cp["%General"]["reduce_window_opacity"]) <= 25


def test_main_config_merge():
    assert kvantum.build_main_config(None) == "[General]\ntheme=LiquidGlass\n"
    merged = kvantum.build_main_config("[General]\ntheme=KvFlat\nx=1\n\n[Applications]\nKvFlat=qbittorrent\n")
    cp = parse_config(merged)
    assert cp["General"]["theme"] == "LiquidGlass" and cp["General"]["x"] == "1"
    assert cp["Applications"]["KvFlat"] == "qbittorrent"
    assert merged.count("theme=") == 1
    assert "theme=LiquidGlass" in kvantum.build_main_config("[Applications]\na=b\n")
    assert "theme=LiquidGlass" in kvantum.build_main_config("[General]\nfoo=bar\n[Other]\nz=1\n").split("[Other]")[0]


def ctx(fake_env, frost=0.45, dark=True):
    s = Settings(frost=frost)
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d if dark else l, dark=d, light=l, env=fake_env)


def test_plan_writes_theme_main_config_and_env(fake_env):
    actions = qt.TARGETS[0].plan(ctx(fake_env))
    paths = {a.path.name: a for a in actions if isinstance(a, WriteFile)}
    cfg = fake_env.config
    assert {a.path for a in actions if isinstance(a, WriteFile)} == {
        cfg / "Kvantum/LiquidGlass/LiquidGlass.kvconfig", cfg / "Kvantum/LiquidGlass/LiquidGlass.svg",
        cfg / "Kvantum/kvantum.kvconfig", cfg / "environment.d/90-liquid-glass-qt.conf"}
    assert paths["90-liquid-glass-qt.conf"].content == "QT_STYLE_OVERRIDE=kvantum\n"
    assert "theme=LiquidGlass" in paths["kvantum.kvconfig"].content


def test_plan_preserves_existing_kvantum_config(fake_env):
    main = fake_env.config / "Kvantum/kvantum.kvconfig"
    main.parent.mkdir(parents=True)
    main.write_text("[General]\ntheme=KvArc\n\n[Applications]\nKvFlat=vlc\n")
    actions = qt.TARGETS[0].plan(ctx(fake_env))
    new = next(a for a in actions if isinstance(a, WriteFile) and a.path == main).content
    assert "theme=LiquidGlass" in new and "KvFlat=vlc" in new and "KvArc" not in new


def test_plan_flatpak_override(fake_env):
    (ov,) = [a for a in qt.TARGETS[0].plan(ctx(fake_env)) if isinstance(a, FlatpakOverride)]
    assert ov.filesystems == ("xdg-config/Kvantum:ro",)
    assert ov.env == (("QT_STYLE_OVERRIDE", "kvantum"),)


def test_plan_follows_scheme(fake_env):
    d = next(a for a in qt.TARGETS[0].plan(ctx(fake_env, dark=True))
             if isinstance(a, WriteFile) and a.path.suffix == ".kvconfig" and "LiquidGlass/" in str(a.path))
    l = next(a for a in qt.TARGETS[0].plan(ctx(fake_env, dark=False))
             if isinstance(a, WriteFile) and a.path.suffix == ".kvconfig" and "LiquidGlass/" in str(a.path))
    assert d.content != l.content


def test_detect(fake_env, monkeypatch):
    t = qt.TARGETS[0]
    assert t.detect(fake_env).available  # fake which() finds kvantummanager
    monkeypatch.setattr(qt, "STYLE_PLUGINS", ())
    monkeypatch.setattr(type(fake_env), "which", lambda self, name: None)
    d = t.detect(fake_env)
    assert not d.available and "dnf install kvantum" in d.detail


def test_qt_title_bars_like_gnome_are_opt_in_and_fall_back_to_wayland(fake_env):
    def env_file(**kw):
        c = ctx(fake_env)
        for k, v in kw.items():
            setattr(c.settings, k, v)
        (a,) = [a for a in qt.TARGETS[0].plan(c)
                if isinstance(a, WriteFile) and a.path.name == "90-liquid-glass-qt.conf"]
        return a.content
    assert Settings().qt_gnome_titlebars is False
    assert "QT_QPA_PLATFORM" not in env_file()
    # XWayland first, Wayland if it is missing: never an app that cannot start.
    assert env_file(qt_gnome_titlebars=True) == "QT_STYLE_OVERRIDE=kvantum\nQT_QPA_PLATFORM=xcb;wayland\n"
    # Flatpak Qt apps are left alone: most can only use X11 when there is no Wayland.
    (ov,) = [a for a in qt.TARGETS[0].plan(ctx(fake_env)) if isinstance(a, FlatpakOverride)]
    assert all(k != "QT_QPA_PLATFORM" for k, _ in ov.env)


def test_the_customizer_itself_stays_on_wayland():
    src = (Path(__file__).resolve().parents[1] / "liquidglass/gui/app.py").read_text()
    assert 'os.environ.get("QT_QPA_PLATFORM") == "xcb;wayland"' in src
    assert 'os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"' in src


def test_qt_title_bar_switch_names_the_x11_trade_off():
    qml = (Path(__file__).resolve().parents[1] / "liquidglass/gui/qml/LiquidGlass/HeaderBarCard.qml").read_text()
    tip = qml[qml.index('objectName: "qtGnomeTitlebars"'):]
    assert "other X11 apps can see what you type" in tip and "fractional scaling" in tip
