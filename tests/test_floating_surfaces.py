"""Menus, dropdown lists, popovers, sheets and tooltips that an app draws over its own
content have nothing blurred behind them. A thin fill there leaves the window's text
readable through the pop-up (the "Mouse to protect" list in Wheelguard, Qt menus at
61 %, GTK menus at 90 %). One rule covers all of them: they are solid. The palette
publishes that fill as the `floating` and `tooltip` colours and every toolkit's style
uses it."""

from __future__ import annotations

import configparser
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fedoraglass import palette
from fedoraglass.render import apps, gtk3, gtk4, kvantum
from fedoraglass.settings import PRESETS, Settings, apply_preset

ROOT = Path(__file__).resolve().parent.parent

LOOKS = [(name, dark) for name in PRESETS for dark in (True, False)]


def look(name: str, dark: bool, **kw) -> palette.Tokens:
    return palette.build(apply_preset(Settings(**kw), name), dark=dark)


def alpha(css: str) -> float:
    """The alpha of a colour as the GTK renderers write it: rgb(r,g,b) or rgba(r,g,b,a)."""
    m = re.fullmatch(r"rgba?\(\d+,\d+,\d+(?:,([\d.]+))?\)", css.strip())
    assert m, css
    return float(m.group(1) or 1)


def rules(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        for sel in m.group(1).split(","):
            yield " ".join(sel.split()), m.group(2)


# ---- the palette ---------------------------------------------------------------------
@pytest.mark.parametrize("name,dark", LOOKS)
def test_floating_colours_are_solid_at_every_look(name, dark):
    for kw in ({}, {"opacity": 0.6}, {"tint_strength": 0.0},
               {"parts": {"quicksettings": {"frost": 0.0, "tint": "#ff0000", "tint_strength": 0.5}}}):
        t = look(name, dark, **kw)
        assert t.floating.a == 1.0, kw
        assert t.tooltip.a == 1.0, kw


@pytest.mark.parametrize("name,dark", LOOKS)
def test_floating_is_the_menu_colour_made_solid(name, dark):
    t = look(name, dark)
    assert t.floating.hex6 == t.popover.hex6
    assert t.tooltip.hex6 == t.osd.hex6


def test_the_shells_own_menus_stay_thin_glass():
    """The Shell blurs what is behind its menus, so `popover` keeps the look's own glass.
    The solid fill is a second colour, not a thicker `popover`."""
    for dark in (True, False):
        assert look("Liquid", dark).popover.a < 0.85


# ---- the public token file -----------------------------------------------------------
@pytest.mark.parametrize("name,dark", LOOKS)
def test_token_file_carries_the_floating_colours(name, dark):
    data = json.loads(look(name, dark).to_json())
    for key in ("floating", "tooltip"):
        value = data[key]
        assert re.fullmatch(r"#[0-9a-f]{6}ff", value), value


def test_the_token_guide_tells_apps_what_to_paint_pop_ups_with():
    doc = (ROOT / "docs/TOKENS.md").read_text(encoding="utf-8")
    assert "| `floating` |" in doc and "| `tooltip` |" in doc
    assert "## Things that float over your own content" in doc


# ---- GTK 4 and libadwaita ------------------------------------------------------------
# Every colour a pop-up may be filled with, and the rules that must use one of them.
GTK4_SOLID = ("--popover-bg-color", "--dialog-bg-color", "--lg-tooltip", "--lg-popover-solid")
GTK4_FLOATING = {
    "popover > contents": "--popover-bg-color",
    "popover > arrow": "--popover-bg-color",
    "dialog-host > dialog sheet": "--dialog-bg-color",
    "bottom-sheet > sheet": "--dialog-bg-color",
    "tooltip.background": "--lg-tooltip",
    "toast": "--lg-tooltip",
    ".app-notification": "--lg-tooltip",
    ".floating-bar": "--popover-bg-color",
}


@pytest.mark.parametrize("name,dark", LOOKS)
def test_gtk4_pop_up_colours_are_solid(name, dark):
    css = gtk4.render(look(name, dark))
    for var in GTK4_SOLID:
        values = re.findall(rf"{var}: ([^;]+);", css)
        assert values, var
        for v in values:
            assert alpha(v) == 1.0, (var, v)


def test_gtk4_pop_ups_are_filled_with_those_colours():
    css = gtk4.render(look("Liquid", True), look("Liquid", False))
    fills = {}
    for sel, body in rules(css):
        if m := re.search(r"background-color:\s*var\((--[\w-]+)\)", body):
            fills.setdefault(sel, m.group(1))
    for sel, var in GTK4_FLOATING.items():
        assert fills.get(sel) == var, sel
    # The terminal's menus lose their fill colour to the app's own style sheet, so the
    # same fill is also laid over them as a picture.
    assert re.search(r"\.window-contents popover > contents \{[^}]*var\(--lg-popover-solid\)", css)


def test_gtk4_overlay_controls_keep_their_own_clearer_fill():
    """.osd controls sit on pictures and video, not on text: they stay the clearer glass
    and no longer share the tooltip's colour."""
    t = look("Liquid", True)
    css = gtk4.render(t)
    osd = re.search(r"--lg-osd: ([^;]+);", css).group(1)
    assert 0.85 <= alpha(osd) < 1.0
    body = next(b for s, b in rules(css) if s.startswith(".osd:not(button)") and "background-color" in b)
    assert "var(--lg-osd)" in body


# ---- GTK 3 (also on top of a kept theme such as Orchis) ------------------------------
GTK3_FLOATING = {
    "popover": "popover_bg_color", "popover.background": "popover_bg_color",
    "menu": "popover_bg_color", ".menu": "popover_bg_color", ".context-menu": "popover_bg_color",
    "tooltip": "lg_tooltip", "tooltip.background": "lg_tooltip", ".app-notification": "lg_tooltip",
}


@pytest.mark.parametrize("name,dark", LOOKS)
@pytest.mark.parametrize("on_light_glass", (False, True))
def test_gtk3_pop_ups_are_solid(name, dark, on_light_glass):
    css = gtk3.render(look(name, dark), on_light_glass)
    colours = dict(re.findall(r"@define-color (\w+) ([^;]+);", css))
    for c in ("popover_bg_color", "dialog_bg_color", "lg_tooltip"):
        assert alpha(colours[c]) == 1.0, c
    fills = {}
    for sel, body in rules(css):
        if m := re.search(r"background-color:\s*@(\w+)", body):
            fills.setdefault(sel, m.group(1))
    for sel, colour in GTK3_FLOATING.items():
        assert fills.get(sel) == colour, sel


# ---- Qt (Kvantum) --------------------------------------------------------------------
def kvantum_fill(svg: str, element: str) -> list[float]:
    """The see-through of an element's body: the stops of the gradient that fills it."""
    root = ET.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    by_id = {e.get("id"): e for e in root.iter() if e.get("id")}
    fill = next(r.get("fill") for r in by_id[element].findall("s:rect", ns) if (r.get("fill") or "").startswith("url("))
    grad = by_id[fill[5:-1]]
    return [float(stop.get("stop-opacity")) for stop in grad.findall("s:stop", ns)]


@pytest.mark.parametrize("name,dark", LOOKS)
def test_qt_menus_combo_lists_and_tooltips_are_solid(name, dark):
    t = look(name, dark)
    svg = kvantum.build_svg(t)
    for element in ("menu-normal", "tooltip-normal"):
        stops = kvantum_fill(svg, element)
        assert stops and min(stops) == 1.0, (element, stops)
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str  # type: ignore[assignment]
    cp.read_string(kvantum.build_config(t))
    general = cp["%General"]
    # Kvantum multiplies this with the picture's own see-through: any value here thins the
    # menu a second time (0.78 x 0.78 = 61 % up to 1.7.9).
    assert general["reduce_menu_opacity"] == "0"
    # Combo box lists are drawn as menus, so they get the menu's fill.
    assert general["combo_menu"] == "true"
    assert general["popup_blurring"] == "false"


# ---- themed apps that take a style sheet ---------------------------------------------
@pytest.mark.parametrize("dark", (True, False))
def test_style_sheet_apps_paint_opaque_pop_ups(dark):
    t = look("Liquid", dark)
    qss = apps.qt_qss(t)
    for widget in ("QMenu", "QComboBox QAbstractItemView", "QToolTip"):
        assert re.search(rf"^{widget} \{{ background: #[0-9a-f]{{6}};", qss, flags=re.M), widget
    code = apps.vscode_theme(t)["colors"]
    for key in ("menu.background", "editorWidget.background", "editorSuggestWidget.background"):
        assert re.fullmatch(r"#[0-9a-f]{6}", code[key]), key
