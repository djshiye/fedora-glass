"""The one corner-radius scale (liquidglass/radius.py) and the places that must use it."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from liquidglass import palette, radius
from liquidglass.render import apps, glass, gtk3, gtk4, kvantum
from liquidglass.render import shell as rs
from liquidglass.settings import Settings

DATA = Path(radius.__file__).resolve().parent / "data"
TEMPLATES = {
    "gtk4": DATA / "gtk/gtk4.css.tpl",
    "gtk3": DATA / "gtk/gtk3.css.tpl",
    "shell": DATA / "shell/glass.css.tpl",
}

# Where a capsule (999px) is allowed to stay literal, per template: switches, slider troughs
# and knobs, progress bars, scrollbars, search entries, label chips/pills and spinners. These
# are the selectors exactly as written in the template (whitespace collapsed). Everything else
# must use a scale step ($r_xs, $r_s, ...). Adding a selector here needs a reason in radius.py.
CAPSULES = {
    "gtk4": {
        "searchentry",                                   # search entries
        "switch", "switch > slider",                     # switches and their knobs
        ".floating-bar, .nautilus-floating-bar",         # Files' status pill (a label)
    },
    "gtk3": {
        "entry.search, searchentry",                     # search entries
        "switch", "switch slider",                       # switches and their knobs
        "radio",                                         # radio buttons are round
        "scale trough, progressbar trough, levelbar trough",
        "scale highlight, progressbar progress, levelbar block.filled",
        "scale slider",                                  # slider knob
        "scrollbar slider",
    },
    "shell": {
        ".quick-slider .slider-bin",                     # quick settings volume/brightness
        ".icon-button, .quick-toggle, .quick-toggle-has-menu",   # GNOME's round icon buttons, pill toggles
        ".search-entry",                                 # overview search
        ".wg-chip", ".wg-pill",                          # Wheelguard chips and pills (labels)
    },
}


def test_ladder_at_the_default_radius():
    assert Settings().radius == radius.DEFAULT_BASE == 18
    assert radius.scale(18) == {"xs": 8, "s": 12, "m": 16, "l": 24, "full": 999}


def test_zero_radius_is_square_everywhere_but_capsules():
    assert radius.scale(0) == {"xs": 0, "s": 0, "m": 0, "l": 0, "full": 999}


@pytest.mark.parametrize("r", range(0, 41))
def test_steps_are_ordered_whole_px_and_follow_the_base(r):
    sc = radius.scale(r)
    assert sc["xs"] <= sc["s"] <= sc["m"] <= sc["l"] < sc["full"]
    assert all(isinstance(v, int) for v in sc.values())
    for k, v in {"xs": 8, "s": 12, "m": 16, "l": 24}.items():
        assert sc[k] == round(v * r / 18)


def test_bigger_base_never_shrinks_a_step():
    for a, b in zip(range(0, 40), range(1, 41)):
        sa, sb = radius.scale(a), radius.scale(b)
        assert all(sa[k] <= sb[k] for k in ("xs", "s", "m", "l"))


def test_check_boxes_stay_square_ish():
    assert radius.check(18) == 5 and radius.check(0) == 0
    assert all(radius.check(r) <= radius.scale(r)["xs"] for r in range(0, 41))


def test_the_keypad_step_is_the_large_one():
    assert radius.KEYPAD == "l"
    assert "border-radius: $r_l; }" in TEMPLATES["gtk4"].read_text().split(".math-buttons $glass_btn,")[1].split("\n")[0]


# ---- guard: no stray literal radii in the CSS templates --------------------------------
def _rules(text: str):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"\$\{(\w+)\}", r"$\1", text)          # ${r_s} -> $r_s so its braces don't split rules
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        yield " ".join(m.group(1).split()), m.group(2)


def _radius_values(body: str):
    for m in re.finditer(r"border(?:-[a-z]+)*-radius\s*:\s*([^;]+)", body):
        yield from m.group(1).split()


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_use_scale_vars_and_capsules_only_where_allowed(name):
    seen = set()
    for selector, body in _rules(TEMPLATES[name].read_text(encoding="utf-8")):
        for v in _radius_values(body):
            if not re.fullmatch(r"\d+(\.\d+)?px", v) or float(v[:-2]) == 0:
                continue                                  # 0, $r_s, !important, ...
            assert v == "999px", f"{name}: literal radius {v} in `{selector}`: use a scale var"
            assert selector in CAPSULES[name], f"{name}: 999px on `{selector}` is not an allowed capsule"
            seen.add(selector)
    # The allow-list must not rot: every entry is still a capsule in the template.
    assert seen == CAPSULES[name]


# ---- rendered output ---------------------------------------------------------------------
def _toks(dark, **kw):
    return palette.build(Settings(**kw), dark=dark)


@pytest.mark.parametrize("dark", [True, False])
@pytest.mark.parametrize("r", [0, 18, 32])
def test_rendered_css_has_no_leftovers(dark, r):
    t, other = _toks(dark, radius=r), _toks(not dark, radius=r)
    outputs = [gtk4.render(t, other), gtk3.render(t), rs.render_css(t), apps.qt_qss(t),
               kvantum.build_config(t)]
    for css in outputs:
        assert "${" not in css and "$r_" not in css and "$pop_" not in css and "None" not in css


def test_default_gtk_output_uses_the_ladder():
    t = _toks(True)
    css = gtk4.render(t, _toks(False))
    assert "--window-radius: 24px" in css
    assert "border-radius: 16px" in css and "border-radius: 12px" in css and "border-radius: 8px" in css
    assert "border-radius: 12px 0 0 12px" in css           # linked group: outer corners s, inner 0
    assert "border-radius: 24px; }" in css                 # Calculator keypad
    assert "border-radius: 999px 0" not in css


def test_window_radius_is_one_value_everywhere():
    for base in (0, 10, 18, 26):
        t = _toks(True, radius=base)
        large = radius.scale(base)["l"]
        assert f"--window-radius: {large}px" in gtk4.render(t, _toks(False, radius=base))
        assert f"border-top-left-radius: {large}px" in gtk3.render(t)
        assert glass.config(Settings(radius=base), t)["windows"]["radius"] == large


def test_qt_and_kvantum_take_their_steps_from_the_windows_ladder():
    for base in (6, 18, 30):
        t = _toks(True, radius=base)
        sc = radius.scale(t.window_radius)
        qss = apps.qt_qss(t)
        assert f"QPushButton, QToolButton {{ background: " in qss
        assert re.search(rf"QPushButton, QToolButton \{{[^}}]*border-radius: {sc['s']}px", qss)
        assert re.search(rf"QMenu \{{[^}}]*border-radius: {sc['m']}px", qss)
        assert re.search(rf"QGroupBox \{{[^}}]*border-radius: {sc['m']}px", qss)
        assert re.search(rf"QTabBar::tab \{{[^}}]*border-radius: {sc['xs']}px", qss)
        k = kvantum.radii(t)
        assert k["R"] == max(4, min(10, sc["s"])) and k["RM"] == max(4, min(14, sc["m"]))
        assert k["RT"] == max(4, min(10, sc["xs"])) and k["RI"] == max(4, min(8, sc["xs"]))


def test_palette_small_radius_is_the_s_step():
    for base in (0, 12, 18, 30):
        assert _toks(True, radius=base).radius_small == radius.scale(base)["s"]


def test_a_part_override_scales_that_parts_ladder():
    t = palette.build(Settings(radius=18, parts={"arcmenu": {"radius": 9}}), dark=True)
    assert rs.radii(t, t.parts["arcmenu"]["radius"]) == {"r_xs": 4, "r_s": 6, "r_m": 8, "r_l": 12}
    assert rs.arcmenu_values(t)["menu-border-radius"] == "8"
    assert rs.radii(t) == {"r_xs": 8, "r_s": 12, "r_m": 16, "r_l": 24}
