"""Kvantum theme for Qt Widgets apps, generated from design tokens.

Kvantum draws every widget from named elements in one SVG. Framed elements
are 9-slice: ``<name>-<state>`` is the interior and ``<name>-<state>-<side>``
the eight frame pieces, each drawn at its natural size F so corners stay
round. The generator below builds those pieces analytically (no clipping),
so every id's bounding box is exactly its piece, which is what Kvantum scales.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..color import BLACK, WHITE, Color
from ..palette import Tokens

THEME = "LiquidGlass"
PROGRESS = 16
SIDES = ("topleft", "top", "topright", "left", "right", "bottomleft", "bottom", "bottomright")
CLEAR = Color(0, 0, 0, 0)


def over(top: Color, bottom: Color) -> Color:
    """Alpha-composite `top` over `bottom`."""
    a = top.a + bottom.a * (1 - top.a)
    if a <= 0:
        return CLEAR
    k = lambda x, y: (x * top.a + y * bottom.a * (1 - top.a)) / a  # noqa: E731
    return Color(k(top.r, bottom.r), k(top.g, bottom.g), k(top.b, bottom.b), a)


def _clamp(v: float, lo: int, hi: int) -> int:
    return int(min(hi, max(lo, round(v))))


# ---- SVG plumbing ------------------------------------------------------------
def _paint(c: Color) -> str:
    return f'fill="{c.hex6}" fill-opacity="{c.a:.3f}"'


def _num(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


class Sheet:
    """Lays pieces out on a grid and collects ids, so each is placed once."""

    WIDTH = 1200

    def __init__(self) -> None:
        self.defs: list[str] = []
        self.body: list[str] = []
        self.ids: list[str] = []
        self._x = self._y = 0.0
        self._row = 0.0
        self._n = 0

    def place(self, w: float, h: float) -> tuple[float, float]:
        if self._x + w > self.WIDTH:
            self._x, self._y, self._row = 0.0, self._y + self._row + 4, 0.0
        pos = (self._x, self._y)
        self._x += w + 4
        self._row = max(self._row, h)
        return pos

    def height(self) -> float:
        return self._y + self._row + 4

    def uid(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def gradient(self, top: Color, bot: Color, horizontal: bool = False) -> str:
        gid = self.uid("g")
        x2, y2 = ("1", "0") if horizontal else ("0", "1")
        self.defs.append(
            f'<linearGradient id="{gid}" x1="0" y1="0" x2="{x2}" y2="{y2}">'
            f'<stop offset="0" stop-color="{top.hex6}" stop-opacity="{top.a:.3f}"/>'
            f'<stop offset="1" stop-color="{bot.hex6}" stop-opacity="{bot.a:.3f}"/></linearGradient>')
        return gid

    def piece(self, pid: str, w: float, h: float, shapes: str, flip: str = "") -> None:
        """A group whose bounds are exactly w*h (an invisible rect guarantees it)."""
        ox, oy = self.place(w, h)
        sx, sy = (-1, 1) if flip == "x" else (1, -1) if flip == "y" else (-1, -1) if flip == "xy" else (1, 1)
        tx = ox + (w if sx < 0 else 0)
        ty = oy + (h if sy < 0 else 0)
        tf = f"translate({_num(tx)},{_num(ty)})" + (f" scale({sx},{sy})" if flip else "")
        self.ids.append(pid)
        self.body.append(
            f'<g id="{pid}" transform="{tf}"><rect width="{_num(w)}" height="{_num(h)}" '
            f'fill="#000000" fill-opacity="0"/>{shapes}</g>')

    def render(self) -> str:
        h = _num(self.height())
        return ('<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.WIDTH}" height="{h}" '
                f'viewBox="0 0 {self.WIDTH} {h}">\n<defs>\n' + "\n".join(self.defs)
                + "\n</defs>\n" + "\n".join(self.body) + "\n</svg>\n")


# ---- 9-slice boxes -----------------------------------------------------------
@dataclass(frozen=True)
class Look:
    top: Color
    bot: Color | None = None      # None = flat
    edge: Color | None = None
    rim: Color | None = None      # specular line just inside the top edge
    ew: float = 1.0               # edge width


def _rect(x: float, y: float, w: float, h: float, paint: str) -> str:
    return f'<rect x="{_num(x)}" y="{_num(y)}" width="{_num(w)}" height="{_num(h)}" {paint}/>'


def _corner(sh: Sheet, F: float, look: Look, rounded: bool, top_row: bool) -> str:
    """Top-left corner in a F*F cell; mirrored for the other three."""
    e = look.ew if look.edge else 0.0
    fill = look.top if top_row or look.bot is None else look.bot
    out = []
    if rounded:
        out.append(f'<path d="M{_num(F)},{_num(F)} L{_num(F)},0 A{_num(F)},{_num(F)} 0 0 0 0,{_num(F)} Z" '
                   f'{_paint(fill)}/>')
        if look.edge and e:
            r = F - e
            out.append(f'<path d="M{_num(F)},0 A{_num(F)},{_num(F)} 0 0 0 0,{_num(F)} L{_num(e)},{_num(F)} '
                       f'A{_num(r)},{_num(r)} 0 0 1 {_num(F)},{_num(e)} Z" {_paint(look.edge)}/>')
        if look.rim and top_row:
            r0, r1 = F - e, F - e - 1
            gid = sh.uid("r")
            c = look.rim
            sh.defs.append(
                f'<linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="0">'
                f'<stop offset="0" stop-color="{c.hex6}" stop-opacity="0"/>'
                f'<stop offset="1" stop-color="{c.hex6}" stop-opacity="{c.a:.3f}"/></linearGradient>')
            out.append(f'<path d="M{_num(F)},{_num(e)} A{_num(r0)},{_num(r0)} 0 0 0 {_num(e)},{_num(F)} '
                       f'L{_num(e + 1)},{_num(F)} A{_num(r1)},{_num(r1)} 0 0 1 {_num(F)},{_num(e + 1)} Z" '
                       f'fill="url(#{gid})"/>')
    else:
        out.append(_rect(0, 0, F, F, _paint(fill)))
        if look.edge and e:
            out.append(_rect(0, 0, F, e, _paint(look.edge)))
            out.append(_rect(0, e, e, F - e, _paint(look.edge)))
        if look.rim and top_row:
            out.append(_rect(e, e, F - e, 1, _paint(look.rim)))
    return "".join(out)


def box(sh: Sheet, name: str, state: str, look: Look, F: float, *,
        rounded: bool = True, frame: bool = True) -> None:
    """Emit `name-state` (interior) and, if `frame`, its eight frame pieces."""
    pid = f"{name}-{state}"
    bot = look.bot or look.top
    grad = sh.gradient(look.top, bot) if look.bot else None
    mid = f'fill="url(#{grad})"' if grad else _paint(look.top)
    sh.piece(pid, 16, 16, f'<rect width="16" height="16" {mid}/>')
    if not frame:
        return
    e = look.ew if look.edge else 0.0
    W = 8.0
    for side in SIDES:
        top_row, bottom_row = side.startswith("top"), side.startswith("bottom")
        left_col, right_col = side.endswith("left"), side.endswith("right")
        if side in ("topleft", "topright", "bottomleft", "bottomright"):
            flip = ("x" if right_col else "") + ("y" if bottom_row else "")
            sh.piece(f"{pid}-{side}", F, F, _corner(sh, F, look, rounded, top_row), flip)
        elif side in ("top", "bottom"):
            c = look.top if top_row else bot
            shapes = _rect(0, 0, W, F, _paint(c))
            if look.edge and e:
                shapes += _rect(0, 0, W, e, _paint(look.edge))
            if look.rim and top_row:
                shapes += _rect(0, e, W, 1, _paint(look.rim))
            sh.piece(f"{pid}-{side}", W, F, shapes, "y" if bottom_row else "")
        else:
            shapes = _rect(0, 0, F, 16, f'fill="url(#{grad})"' if grad else _paint(look.top))
            if look.edge and e:
                shapes += _rect(0, 0, e, 16, _paint(look.edge))
            sh.piece(f"{pid}-{side}", F, 16, shapes, "x" if right_col else "")


# ---- indicators ----------------------------------------------------------------
def _icon(sh: Sheet, pid: str, w: float, h: float, shapes: str) -> None:
    sh.piece(pid, w, h, shapes)


def _stroke(c: Color, w: float) -> str:
    return (f'fill="none" stroke="{c.hex6}" stroke-opacity="{c.a:.3f}" stroke-width="{_num(w)}" '
            f'stroke-linecap="round" stroke-linejoin="round"')


CHEVRONS = {
    "up": "M1.5,6 L4.5,3 L7.5,6", "down": "M1.5,3 L4.5,6 L7.5,3",
    "left": "M6,1.5 L3,4.5 L6,7.5", "right": "M3,1.5 L6,4.5 L3,7.5",
}
STATES = ("normal", "focused", "pressed", "toggled", "disabled")


class Palette:
    """Every colour the sheet uses, derived from the tokens in one place."""

    def __init__(self, t: Tokens):
        self.t = t
        wash = t.fg if t.dark else WHITE
        self.surface = t.window.with_alpha(1)
        self.ctl_top = wash.with_alpha(min(1, t.card.a * 1.9))
        self.ctl_bot = wash.with_alpha(t.card.a)
        self.ctl_hover = over(t.hover, self.ctl_top), over(t.hover, self.ctl_bot)
        self.ctl_press = over(t.active, self.ctl_top), over(t.active, self.ctl_bot)
        self.acc_top = t.accent.mix(WHITE, 0.14)
        self.acc_bot = t.accent
        self.acc_edge = t.accent.mix(BLACK, 0.3).with_alpha(0.7)
        self.field = t.view.with_alpha(max(t.view.a, 0.55))
        self.arrow = {"normal": t.fg_dim, "focused": t.fg, "pressed": t.fg,
                      "toggled": t.accent_fg, "disabled": t.fg_faint}

    @property
    def glass_rim(self) -> Color:
        return self.t.highlight


def _button_looks(p: Palette, flat: bool) -> dict[str, Look]:
    t = p.t
    edge, rim = t.edge, t.highlight
    if flat:
        normal = Look(CLEAR)
        focused = Look(t.hover, None, edge, rim)
        pressed = Look(t.active, None, edge, rim)
        dis = normal
    else:
        normal = Look(p.ctl_top, p.ctl_bot, edge, rim)
        focused = Look(*p.ctl_hover, edge, rim)
        pressed = Look(*p.ctl_press, edge, rim)
        dis = Look(p.ctl_top.with_alpha(p.ctl_top.a * 0.45), p.ctl_bot.with_alpha(p.ctl_bot.a * 0.45),
                   edge.with_alpha(edge.a * 0.6))
    toggled = Look(t.selection, None, p.acc_edge, rim) if flat else Look(p.acc_top, p.acc_bot, p.acc_edge, rim)
    return {"normal": normal, "focused": focused, "pressed": pressed, "toggled": toggled, "disabled": dis}


def _indicator_box(sh: Sheet, p: Palette, kind: str, prefix: str) -> None:
    """Checkbox / radio, 16px, in every state Kvantum asks for."""
    t = p.t
    for variant in ("", "checked-", "tristate-"):
        for state in ("normal", "focused", "pressed", "disabled"):
            on = bool(variant)
            hov = state in ("focused", "pressed")
            top = p.acc_top if on else (p.ctl_hover[0] if hov else p.ctl_top)
            bot = p.acc_bot if on else (p.ctl_hover[1] if hov else p.ctl_bot)
            if not on:
                top, bot = top.with_alpha(max(top.a, 0.3)), bot.with_alpha(max(bot.a, 0.22))
            edge = p.acc_edge if on else t.fg.with_alpha(0.38 if t.dark else 0.34)
            glow = t.accent_text.with_alpha(0.9) if state == "pressed" and not on else None
            dim = 0.45 if state == "disabled" else 1.0
            gid = sh.gradient(top, bot)
            if kind == "checkbox":
                shape = (f'<rect x="0.5" y="0.5" width="15" height="15" rx="4.5" fill="url(#{gid})" '
                         f'fill-opacity="{dim}" stroke="{edge.hex6}" stroke-opacity="{edge.a * dim:.3f}"/>')
                if variant == "checked-":
                    shape += f'<path d="M4.2,8.3 L6.9,11 L11.8,5.2" {_stroke(t.accent_fg, 2)}/>'
                elif variant == "tristate-":
                    shape += f'<path d="M4.5,8 L11.5,8" {_stroke(t.accent_fg, 2)}/>'
                if on is False and glow:
                    shape += (f'<rect x="0.5" y="0.5" width="15" height="15" rx="4.5" fill="none" '
                              f'stroke="{glow.hex6}" stroke-opacity="{glow.a:.3f}"/>')
            else:
                shape = (f'<circle cx="8" cy="8" r="7.5" fill="url(#{gid})" fill-opacity="{dim}" '
                         f'stroke="{edge.hex6}" stroke-opacity="{edge.a * dim:.3f}"/>')
                if variant == "checked-":
                    shape += f'<circle cx="8" cy="8" r="3" {_paint(t.accent_fg)}/>'
                elif variant == "tristate-":
                    shape += f'<path d="M5,8 L11,8" {_stroke(t.accent_fg, 2)}/>'
            if kind == "checkbox" and variant == "checked-":
                shape += (f'<path d="M3.5,2 H12.5" stroke="{t.highlight.hex6}" '
                          f'stroke-opacity="{t.highlight.a * 0.6:.3f}" stroke-linecap="round" fill="none"/>')
            _icon(sh, f"{prefix}-{variant}{state}", 16, 16, shape)


def build_svg(t: Tokens) -> str:
    sh = Sheet()
    p = Palette(t)
    R = _clamp(t.radius * 0.45, 4, 10)       # buttons, entries, tabs
    RM = _clamp(t.radius * 0.5, 4, 10)       # menus
    RI = 4                                   # list selections, menu items
    RG = 4                                   # generic frames, group boxes
    PR = PROGRESS // 2                       # progress bars are pills
    edge, rim = t.edge, t.highlight

    # buttons (push/combo), flat tool buttons
    for state, look in _button_looks(p, flat=False).items():
        box(sh, "button", state, look, R)
    for state, look in _button_looks(p, flat=True).items():
        box(sh, "tbutton", state, look, R)

    # line edits and spin boxes: darker, recessed glass
    field_top = p.field.mix(BLACK if t.dark else WHITE, 0.0)
    for state in ("normal", "focused", "disabled"):
        if state == "focused":
            look = Look(field_top, field_top, t.accent_text.with_alpha(0.95), None, 2.0)
        elif state == "disabled":
            look = Look(field_top.with_alpha(field_top.a * 0.5), None, edge.with_alpha(edge.a * 0.6))
        else:
            look = Look(field_top, field_top, t.fg.with_alpha(0.22 if t.dark else 0.20))
        box(sh, "lineedit", state, look, R)

    # generic frame around scroll areas and group boxes
    for state in ("normal", "focused"):
        box(sh, "common", state, Look(CLEAR, None, edge if state == "normal" else t.accent_text.with_alpha(0.6)), RG)
    box(sh, "group", "normal", Look(t.card.with_alpha(t.card.a * (0.9 if t.dark else 0.6)), None, edge.with_alpha(min(1, edge.a * 1.3))), RG)
    box(sh, "tabframe", "normal", Look(CLEAR, None, edge), RG)

    # list rows
    sel_press = t.selection.with_alpha(min(1.0, t.selection.a + 0.12))
    box(sh, "itemview", "normal", Look(CLEAR), RI)
    box(sh, "itemview", "focused", Look(t.hover), RI)
    box(sh, "itemview", "pressed", Look(sel_press), RI)
    box(sh, "itemview", "toggled", Look(t.selection), RI)

    # menus and tooltips
    pop_top = t.popover
    box(sh, "menu", "normal", Look(pop_top, pop_top, edge.with_alpha(min(1, edge.a * 1.4)), rim), RM)
    box(sh, "menuitem", "normal", Look(CLEAR), RI)
    for state in ("focused", "pressed", "toggled"):
        wash = t.hover if state == "focused" else t.selection
        box(sh, "menuitem", state, Look(wash, None, None, None), RI)
    box(sh, "menubaritem", "normal", Look(CLEAR), RI + 1)
    box(sh, "menubaritem", "focused", Look(t.hover, None, edge, rim), RI + 1)
    box(sh, "menubaritem", "pressed", Look(t.selection, None, p.acc_edge), RI + 1)
    box(sh, "menubaritem", "toggled", Look(t.selection, None, p.acc_edge), RI + 1)
    box(sh, "tooltip", "normal", Look(t.popover, t.popover, edge.with_alpha(min(1, edge.a * 1.5)), rim), R)

    # tabs: a raised glass pill for the current one
    tabs = {"normal": Look(CLEAR), "focused": Look(t.hover, None, None, None),
            "toggled": Look(p.ctl_top, p.ctl_bot, edge.with_alpha(min(1, edge.a * 1.4)), rim)}
    tabs["pressed"] = tabs["toggled"]
    for state, look in tabs.items():
        box(sh, "tab", state, look, R)

    # progress bar and slider tracks
    groove = t.fg.with_alpha(0.14 if t.dark else 0.12)
    for state in ("normal", "disabled"):
        box(sh, "progress", state, Look(groove, None, edge), PR)
    box(sh, "progress-pattern", "normal", Look(p.acc_top, p.acc_bot, p.acc_edge, rim.with_alpha(rim.a * 0.8)), PR)
    box(sh, "progress-pattern", "disabled", Look(t.fg.with_alpha(0.22)), PR)
    box(sh, "slider", "normal", Look(groove), 2)
    box(sh, "slider", "toggled", Look(p.acc_top, p.acc_bot), 2)

    # scrollbars: thin pills over an invisible groove
    SB = 4
    box(sh, "scrollbargroove", "normal", Look(CLEAR), SB)
    for state, a in (("normal", 0.34), ("focused", 0.52), ("pressed", 0.68)):
        c = t.fg.with_alpha(a if t.dark else a * 0.9)
        box(sh, "scrollbarslider", state, Look(c), SB)

    # header cells of tables and trees
    hdr = Look(t.card, None, t.divider)
    box(sh, "header", "normal", hdr, 2, rounded=False)
    box(sh, "header", "focused", Look(over(t.hover, t.card), None, t.divider), 2, rounded=False)
    box(sh, "header", "pressed", Look(over(t.active, t.card), None, t.divider), 2, rounded=False)
    box(sh, "header", "toggled", Look(t.selection, None, t.divider), 2, rounded=False)
    _icon(sh, "header-separator", 2, 16, _rect(0, 3, 1, 10, _paint(t.divider)))

    # slider handle: a glass bead
    for state in ("normal", "focused", "pressed", "disabled"):
        fill = WHITE.with_alpha({"normal": 0.96, "focused": 1.0, "pressed": 0.86, "disabled": 0.45}[state])
        ring = BLACK.with_alpha(0.22 if t.dark else 0.20)
        shadow = BLACK.with_alpha(0.28 if t.dark else 0.14)
        gid = sh.gradient(fill, fill.mix(Color.hex("#c9d0dc"), 0.45))
        _icon(sh, f"slidercursor-{state}", 20, 20,
              f'<circle cx="10" cy="11.2" r="8.6" {_paint(shadow)}/>'
              f'<circle cx="10" cy="10" r="8.6" fill="url(#{gid})" stroke="{ring.hex6}" stroke-opacity="{ring.a:.3f}"/>'
              f'<path d="M5.2,6.6 A5.6,5.6 0 0 1 14.8,6.6" fill="none" stroke="#ffffff" stroke-opacity="0.85" '
              f'stroke-width="1" stroke-linecap="round"/>')
    # check boxes and radios
    _indicator_box(sh, p, "checkbox", "checkbox")
    _indicator_box(sh, p, "checkbox", "item-checkbox")
    _indicator_box(sh, p, "checkbox", "menu-checkbox")
    _indicator_box(sh, p, "radio", "radio")
    _indicator_box(sh, p, "radio", "menu-radio")

    # arrows and tree expanders
    for d, path in CHEVRONS.items():
        for state in STATES:
            c = p.arrow[state]
            _icon(sh, f"arrow-{d}-{state}", 9, 9, f'<path d="{path}" {_stroke(c, 1.5)}/>')
    for d in ("left", "right"):
        for state in STATES:
            _icon(sh, f"menuitem-{d}-{state}", 9, 9,
                  f'<path d="{CHEVRONS[d]}" {_stroke(t.fg_dim if state != "disabled" else t.fg_faint, 1.5)}/>')
    for kind, path in (("plus", "M2.5,4.5 H6.5 M4.5,2.5 V6.5"), ("minus", "M2.5,4.5 H6.5")):
        for state in ("normal", "focused", "pressed", "disabled"):
            c = p.arrow["normal" if state == "normal" else state]
            _icon(sh, f"tree-{kind}-{state}", 9, 9, f'<path d="{path}" {_stroke(c, 1.5)}/>')
    # splitter grip: three beads
    for state in ("normal", "focused", "pressed"):
        c = t.fg.with_alpha({"normal": 0.35, "focused": 0.55, "pressed": 0.7}[state])
        dots = "".join(f'<circle cx="{4 + 8 * i}" cy="2" r="1.2" {_paint(c)}/>' for i in range(3))
        _icon(sh, f"splitter-grip-{state}", 20, 4, dots)
    return sh.render()


# ---- kvconfig -------------------------------------------------------------------
def _hex(c: Color) -> str:
    return c.hex6


def _opaque(c: Color, over_c: Color) -> Color:
    return over(c, over_c.with_alpha(1)).with_alpha(1)


def build_config(t: Tokens) -> str:
    surface = t.window.with_alpha(1)
    base = t.view.with_alpha(1)
    fg = _hex(t.fg)
    dim = _hex(_opaque(t.fg_faint, surface))
    R = _clamp(t.radius * 0.45, 4, 10)
    RM = _clamp(t.radius * 0.5, 4, 10)
    RI = 4
    RG = 4
    # Qt draws no backdrop blur here, so keep enough body behind the text:
    # dark text on a see-through light window over a dark wallpaper is unreadable.
    window_alpha = max(t.window.a, 0.45 if t.dark else 0.78)
    window_reduce = _clamp((1 - window_alpha) * 100, 0, 75)
    menu_reduce = _clamp((1 - t.popover.a) * 100, 0, 60)

    def fr(n: int) -> str:
        return f"frame.top={n}\nframe.bottom={n}\nframe.left={n}\nframe.right={n}"

    return f"""[%General]
author=Liquid Glass
comment=Liquid Glass for Qt widgets (generated, do not edit)
x11drag=all
alt_mnemonic=true
left_tabs=false
attach_active_tab=false
mirror_doc_tabs=true
group_toolbar_buttons=false
toolbar_item_spacing=2
toolbar_interior_spacing=2
spread_progressbar=true
progressbar_thickness={PROGRESS}
composite=true
translucent_windows=true
blurring=false
popup_blurring=false
reduce_window_opacity={window_reduce}
reduce_menu_opacity={menu_reduce}
menu_shadow_depth=0
tooltip_shadow_depth=0
spread_menuitems=true
splitter_width=7
scroll_width=8
scroll_min_extent=40
scroll_arrows=false
transient_scrollbar=false
transient_groove=false
scrollbar_in_view=false
slider_width=4
slider_handle_width=20
slider_handle_length=20
tickless_slider_handle_size=20
check_size=16
toolbar_icon_size=20
small_icon_size=16
button_icon_size=16
combo_as_lineedit=false
combo_menu=true
square_combo_button=false
hide_combo_checkboxes=true
inline_spin_indicators=true
vertical_spin_indicators=true
spin_button_width=22
animate_states=true
tree_branch_line=false
layout_spacing=4
layout_margin=8
submenu_overlap=0
menubar_mouse_tracking=true
merge_menubar_with_toolbar=false
dialog_button_layout=0
click_behavior=0
fill_rubberband=false
dark_titlebar={"true" if t.dark else "false"}
respect_DE=true
contrast=1.00
intensity=1.00
saturation=1.00

[GeneralColors]
window.color={_hex(surface)}
inactive.window.color={_hex(surface)}
base.color={_hex(base)}
inactive.base.color={_hex(base)}
alt.base.color={_hex(base.mix(t.fg, 0.04))}
inactive.alt.base.color={_hex(base.mix(t.fg, 0.04))}
button.color={_hex(_opaque(t.card.with_alpha(0.5), surface))}
light.color={_hex(surface.mix(WHITE, 0.25))}
mid.light.color={_hex(surface.mix(WHITE, 0.12))}
dark.color={_hex(surface.mix(BLACK, 0.35))}
mid.color={_hex(surface.mix(BLACK, 0.18))}
highlight.color={_hex(t.accent)}
inactive.highlight.color={_hex(t.accent.mix(surface, 0.35))}
text.color={fg}
inactive.text.color={fg}
window.text.color={fg}
inactive.window.text.color={fg}
button.text.color={fg}
disabled.text.color={dim}
tooltip.text.color={fg}
highlight.text.color={_hex(t.accent_fg)}
link.color={_hex(t.accent_text)}
link.visited.color={_hex(t.accent_text.mix(t.fg, 0.4))}
progress.indicator.text.color={_hex(t.accent_fg)}

[Hacks]
transparent_ktitle_label=true
transparent_dolphin_view=false
transparent_pcmanfm_sidepane=true
respect_darkness=true
no_selection_tint=false
blur_translucent=false
middle_click_scroll=false
iconless_pushbutton=false
normal_default_pushbutton=false

[PanelButtonCommand]
frame=true
frame.element=button
{fr(R)}
interior=true
interior.element=button
indicator.size=9
indicator.element=arrow
text.normal.color={fg}
text.focus.color={fg}
text.press.color={fg}
text.toggle.color={_hex(t.accent_fg)}
text.shadow=0
text.margin=0
text.margin.top=0
text.margin.bottom=0
text.margin.left=6
text.margin.right=6
text.iconspacing=5

[PanelButtonTool]
inherits=PanelButtonCommand
frame.element=tbutton
interior.element=tbutton
text.margin.left=2
text.margin.right=2
text.toggle.color={fg}

[ToolbarButton]
inherits=PanelButtonTool

[Dock]
inherits=PanelButtonCommand
frame=false
interior=false

[DockTitle]
inherits=PanelButtonCommand
frame=false
interior=false
text.bold=true

[IndicatorSpinBox]
inherits=PanelButtonCommand
indicator.element=arrow
indicator.size=7
frame=false
interior=false
text.margin=0

[RadioButton]
inherits=PanelButtonCommand
frame=false
interior.element=radio
text.margin.left=2
text.margin.right=2
text.toggle.color={fg}

[CheckBox]
inherits=PanelButtonCommand
frame=false
interior.element=checkbox
text.margin.left=2
text.margin.right=2
text.toggle.color={fg}

[GenericFrame]
inherits=PanelButtonCommand
frame=true
interior=false
frame.element=common
interior.element=common
{fr(RG)}

[LineEdit]
inherits=PanelButtonCommand
frame.element=lineedit
interior.element=lineedit
text.margin.left=4
text.margin.right=4
text.toggle.color={fg}

[DropDownButton]
inherits=PanelButtonCommand
indicator.element=arrow-down

[IndicatorArrow]
indicator.element=arrow
indicator.size=9

[ToolboxTab]
inherits=PanelButtonCommand
text.toggle.color={fg}

[Tab]
inherits=PanelButtonCommand
interior.element=tab
frame.element=tab
indicator.element=tab
{fr(R)}
text.margin.left=6
text.margin.right=6
text.margin.top=0
text.margin.bottom=0
text.normal.color={_hex(_opaque(t.fg.with_alpha(0.85), surface))}
text.focus.color={fg}
text.press.color={fg}
text.toggle.color={fg}
min_width=+4
min_height=+2

[TabFrame]
inherits=GenericFrame
frame.element=tabframe
interior=false
{fr(RG)}

[TreeExpander]
inherits=PanelButtonCommand
frame=false
interior=false
indicator.size=9
indicator.element=tree

[HeaderSection]
inherits=PanelButtonCommand
frame.element=header
interior.element=header
{fr(2)}
text.margin.top=5
text.margin.bottom=5
text.margin.left=6
text.margin.right=6
text.bold=false
text.toggle.color={fg}
indicator.element=arrow

[SizeGrip]
inherits=PanelButtonCommand
frame=false
interior=false
indicator.size=0

[Toolbar]
inherits=PanelButtonCommand
frame=false
interior=false
indicator.size=0
text.margin=0

[Slider]
inherits=PanelButtonCommand
frame.element=slider
interior.element=slider
{fr(2)}
text.margin=0

[SliderCursor]
inherits=PanelButtonCommand
frame=false
interior.element=slidercursor

[Progressbar]
inherits=PanelButtonCommand
frame.element=progress
interior.element=progress
{fr(PROGRESS // 2)}
text.margin=0
text.normal.color={fg}
text.focus.color={fg}
text.press.color={fg}
text.toggle.color={fg}

[ProgressbarContents]
inherits=PanelButtonCommand
frame=true
frame.element=progress-pattern
interior.element=progress-pattern
{fr(PROGRESS // 2)}
text.margin=0

[ItemView]
inherits=PanelButtonCommand
text.margin=0
text.margin.top=2
text.margin.bottom=2
text.margin.left=3
text.margin.right=3
frame.element=itemview
interior.element=itemview
{fr(RI)}
indicator.element=tree
text.normal.color={fg}
text.focus.color={fg}
text.press.color={fg}
text.toggle.color={fg}
min_height=0

[Splitter]
inherits=PanelButtonCommand
frame=false
interior=false
indicator.element=splitter-grip
indicator.size=16

[Scrollbar]
inherits=PanelButtonCommand
indicator.size=9

[ScrollbarSlider]
inherits=PanelButtonCommand
frame.element=scrollbarslider
interior.element=scrollbarslider
{fr(4)}
text.margin=0

[ScrollbarGroove]
inherits=PanelButtonCommand
interior.element=scrollbargroove
frame.element=scrollbargroove
frame.top=0
frame.bottom=0
frame.left=4
frame.right=4

[MenuItem]
inherits=PanelButtonCommand
frame=true
frame.element=menuitem
interior.element=menuitem
indicator.element=menuitem
{fr(RI)}
text.focus.color={fg}
text.press.color={fg}
text.toggle.color={fg}
text.margin.top=2
text.margin.bottom=2
text.margin.left=6
text.margin.right=6

[MenuBar]
inherits=PanelButtonCommand
frame=false
interior=false
text.margin=0

[MenuBarItem]
inherits=PanelButtonCommand
interior.element=menubaritem
frame.element=menubaritem
{fr(RI + 1)}
text.margin.left=4
text.margin.right=4
text.margin.top=0
text.margin.bottom=0
text.focus.color={fg}
text.press.color={fg}
text.toggle.color={fg}

[TitleBar]
inherits=PanelButtonCommand
frame=false
interior=false
indicator.size=12
text.bold=true

[ComboBox]
inherits=PanelButtonCommand
indicator.element=arrow

[Menu]
inherits=PanelButtonCommand
frame=true
interior=true
frame.element=menu
interior.element=menu
{fr(RM)}
text.margin=0
text.normal.color={fg}

[GroupBox]
inherits=GenericFrame
frame=true
interior=true
frame.element=group
interior.element=group
text.shadow=0
text.margin=0
{fr(RG)}

[TabBarFrame]
inherits=GenericFrame
frame=false
interior=false
text.shadow=0

[ToolTip]
inherits=GenericFrame
frame.element=tooltip
interior.element=tooltip
interior=true
{fr(R)}
text.shadow=0
text.margin=0
text.normal.color={fg}

[StatusBar]
inherits=GenericFrame
frame=false
interior=false

[Window]
interior=false
"""


def build_main_config(existing: str | None) -> str:
    """kvantum.kvconfig with `theme=LiquidGlass`, keeping everything else."""
    if not existing or not existing.strip():
        return f"[General]\ntheme={THEME}\n"
    lines = existing.splitlines()
    out: list[str] = []
    section = ""
    seen_general = done = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            if section == "General" and not done:
                out.append(f"theme={THEME}")
                done = True
            section = s[1:-1]
            seen_general = seen_general or section == "General"
        elif section == "General" and re.match(r"theme\s*=", s):
            if not done:
                out.append(f"theme={THEME}")
                done = True
            continue
        out.append(line)
    if seen_general and not done:
        out.append(f"theme={THEME}")
    elif not seen_general:
        out = ["[General]", f"theme={THEME}", ""] + out
    return "\n".join(out) + "\n"


def referenced_elements(config: str) -> dict[str, set[str]]:
    """Element names the config points at, split by how Kvantum looks them up."""
    frames: set[str] = set()
    interiors: set[str] = set()
    indicators: set[str] = set()
    for key, val in re.findall(r"^(frame|interior|indicator)\.element=(\S+)$", config, re.M):
        {"frame": frames, "interior": interiors, "indicator": indicators}[key].add(val)
    return {"frame": frames, "interior": interiors, "indicator": indicators}


__all__ = ["THEME", "build_svg", "build_config", "build_main_config", "referenced_elements"]
