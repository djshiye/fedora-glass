"""An unfocused window must be exactly as big as the focused one.

GTK sizes a client-side-decorated window by its shadow, and sets the window's
margins from it. In 1.5.15 the unfocused shadow reached less far than the focused
one, so the click that focused a window (on its close button, say) made the window
grow and shift under the pointer, and GTK dropped the click: the close button needed
2-4 clicks on an inactive window.
"""
from __future__ import annotations

import re

import pytest

from fedoraglass import palette
from fedoraglass.render import gtk3, gtk4
from fedoraglass.settings import Settings

SIZE_PROPS = ("margin", "padding", "border-width", "border", "min-width", "min-height",
              "outline-width", "outline-offset")
STATES = (":backdrop", ":hover", ":active")


def rules(css: str):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@media[^{]*\{", "", css)       # flatten the scheme blocks
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        decls = {}
        for d in body.split(";"):
            if ":" in d:
                k, v = d.split(":", 1)
                decls[k.strip()] = v.strip()
        for one in sel.split(","):
            yield " ".join(one.split()), decls


def split_layers(v: str):
    out, depth, cur = [], 0, ""
    for ch in v:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


def reach(shadow: str) -> tuple[float, float, float, float]:
    """How far a box-shadow reaches past the box: left, top, right, bottom."""
    far = [0.0, 0.0, 0.0, 0.0]
    if shadow in ("none", ""):
        return tuple(far)
    for layer in split_layers(shadow):
        if layer.startswith("inset"):
            continue
        nums = [float(n) for n in re.findall(r"(-?[\d.]+)px|(?<![\w.-])(0)(?![\w.])", layer) for n in n if n][:4]
        nums += [0.0] * (4 - len(nums))
        x, y, blur, spread = nums
        r = blur + spread
        far = [max(far[0], r - x), max(far[1], r - y), max(far[2], r + x), max(far[3], r + y)]
    return tuple(far)


def toks(dark):
    return palette.build(Settings(frost=0.5), dark=dark)


SHEETS = {
    "gtk4": lambda: gtk4.render(toks(True), toks(False)),
    "gtk3-dark": lambda: gtk3.render(toks(True)),
    "gtk3-light": lambda: gtk3.render(toks(False)),
}


@pytest.mark.parametrize("sheet", SHEETS)
def test_unfocused_window_shadow_reaches_as_far_as_the_focused_one(sheet):
    css = SHEETS[sheet]()
    found = {}
    for sel, decls in rules(css):
        if "box-shadow" in decls and sel.startswith("window.csd") and "maximized" not in sel and \
                "tiled" not in sel and "fullscreen" not in sel:
            found[sel] = decls["box-shadow"]
    pairs = [(s, s.replace(":backdrop", "")) for s in found if ":backdrop" in s]
    assert pairs, f"no unfocused window shadow found in {sheet}"
    for back, front in pairs:
        base = found.get(front)
        assert base, f"{back} has no focused rule {front}"
        assert reach(found[back]) == reach(base), (back, reach(found[back]), reach(base))


@pytest.mark.parametrize("sheet", SHEETS)
def test_focus_hover_and_press_never_change_a_windows_or_buttons_size(sheet):
    """Unfocused, hovered and pressed looks change colours only, never sizes: a window
    or button that moves between press and release loses the click."""
    all_rules = list(rules(SHEETS[sheet]()))
    base = {}
    for sel, decls in all_rules:
        if not any(st in sel for st in STATES):
            base.setdefault(sel, {}).update(decls)
    bad = []
    for sel, decls in all_rules:
        if not any(st in sel for st in STATES):
            continue
        if not ("window" in sel or "windowcontrols" in sel or "headerbar" in sel or "titlebutton" in sel
                or "decoration" in sel or "tabbar" in sel or ".top-bar" in sel):
            continue
        for k in decls:
            if k in SIZE_PROPS or k.startswith(("margin-", "padding-", "border-")) and "width" in k:
                plain = sel
                for st in STATES:
                    plain = plain.replace(st, "")
                if base.get(plain, {}).get(k) != decls[k]:      # the same in every state is fine
                    bad.append((sel, k, decls[k]))
    assert not bad, bad


def test_reach_maths():
    assert reach("0 0 0 1px red, 0 18px 48px 4px blue") == (52, 34, 52, 70)
    assert reach("inset 0 1px 0 red") == (0, 0, 0, 0)
