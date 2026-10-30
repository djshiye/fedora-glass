"""GNOME Shell theme: CSS for St and the Dash to Panel / ArcMenu values.

St cannot blur, so every Shell surface is a translucent token colour and the
Liquid Glass extension (render/glass.py) supplies the glass behind it. St also draws a single box-shadow, which
is why large surfaces get their lit top edge from a lighter border-top and
small controls from an inset shadow.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

from ..color import BLACK, WHITE, Color, lerp
from ..palette import Tokens

_TEMPLATE = Path(__file__).resolve().parent.parent / "data/shell/glass.css.tpl"


_NONE = "rgba(0,0,0,0)"
LIGHT_HAIRLINE = BLACK.with_alpha(0.11)


def radii(t: Tokens, r: int | None = None) -> dict[str, int]:
    """One radius scale shared by the CSS and the Dash to Panel / ArcMenu keys,
    so the blur clip always matches the painted surface. `r` is the base radius
    (the menus' by default); each part of the desktop gets its own scale."""
    r = t.menu_radius if r is None else r
    return {
        "r": r,
        "r_small": max(4, round(r * 0.6)),
        "r_item": max(6, r - 4),
        "r_menu": r + 2,
        "r_sub": r + 6,
        "r_big": min(48, r * 2),
        "r_cal": min(48, round(r * 5 / 3)),
        "r_osd": r + 10,
        "r_dialog": r + 6,
        "r_folder": min(64, r * 3),
    }


def _thin(c: Color, t: Tokens, frost: float | None = None) -> Color:
    """Shell surfaces sit on a real blur, so they can be more see-through than the
    blur-less GTK surfaces the tokens were tuned for. Near-opaque tokens (reduce
    transparency, solid presets) are left alone."""
    if c.a >= 0.95 or t.blur_radius == 0:
        return c
    f = t.frost if frost is None else frost
    k = lerp(0.60, 1.0, f) if t.dark else lerp(0.74, 1.0, f)
    return c.with_alpha(max(0.0, c.a * k))


def veil(t: Tokens, kind: str, frost: float | None = None) -> float:
    """Alpha of a surface the extension draws glass behind. The extension already darkens,
    frosts and reflects the backdrop itself, so the theme only lays a light veil on top
    (kind is "menu" or "panel"). The glass layer is brightened/darkened to keep text readable
    over this thin veil, see render/glass.py."""
    f = t.frost if frost is None else frost
    if kind == "panel":
        return lerp(0.18, 0.45, f)
    return lerp(0.16, 0.45, f) if t.dark else lerp(0.30, 0.60, f)


# Which parts the extension draws glass behind as menus; the panel is the other one.
MENU_PARTS = ("arcmenu", "quicksettings", "calendar")


def surfaces(t: Tokens, part: str | None = None) -> dict[str, Color]:
    """Popover, dialog, osd and chrome as the Shell paints them. `part` picks one part's look
    (quick settings by default, with the panel's chrome)."""
    name = part or "quicksettings"
    look = t.parts[name]
    f = look["frost"]
    out = {k: look[k] for k in ("popover", "dialog", "osd")}
    chrome = look["chrome"] if part else t.chrome
    if name in MENU_PARTS and t.glass_menu_edges:
        v = veil(t, "menu", f)
        for k, extra in (("popover", 0.0), ("dialog", 0.04), ("osd", 0.0)):
            if out[k].a < 0.95:
                out[k] = out[k].with_alpha(min(out[k].a, v + extra))
    else:
        out = {k: _thin(c, t, f) for k, c in out.items()}
    if (part is None or part == "panel") and t.glass_panel_edges and chrome.a < 0.95:
        chrome = chrome.with_alpha(min(chrome.a, veil(t, "panel", t.parts["panel"]["frost"])))
    out["chrome"] = chrome
    return out


def values(t: Tokens) -> dict[str, str]:
    """Every placeholder of the CSS template, derived from tokens only."""
    surf = surfaces(t)
    arc, cal, ovw = surfaces(t, "arcmenu"), surfaces(t, "calendar"), surfaces(t, "overview")
    ink = WHITE if t.dark else BLACK
    if t.dark:
        # Translucent, so the glass shows through buttons instead of grey slabs.
        ctrl = (ink.with_alpha(0.14), ink.with_alpha(0.10))
        hov = (ink.with_alpha(0.20), ink.with_alpha(0.15))
        press = (ink.with_alpha(0.08), ink.with_alpha(0.12))
        # Fields stay mostly opaque, so text behind the glass never shows through them.
        field, field_hover = t.popover.with_alpha(0.62), t.popover.with_alpha(0.72)
        field_shadow = BLACK.with_alpha(0.35)
        switch_off, switch_hover = ink.with_alpha(0.20), ink.with_alpha(0.28)
        track = ink.with_alpha(0.16)
        scroll, scroll_hover = ink.with_alpha(0.30), ink.with_alpha(0.46)
        selected = ink.with_alpha(0.18)
    else:
        ctrl = (WHITE.with_alpha(0.80), WHITE.with_alpha(0.42))
        hov = (WHITE.with_alpha(0.92), WHITE.with_alpha(0.58))
        press = (WHITE.with_alpha(0.40), WHITE.with_alpha(0.62))
        field, field_hover = WHITE.with_alpha(0.62), WHITE.with_alpha(0.75)
        field_shadow = BLACK.with_alpha(0.10)
        switch_off, switch_hover = ink.with_alpha(0.18), ink.with_alpha(0.26)
        track = ink.with_alpha(0.14)
        scroll, scroll_hover = ink.with_alpha(0.30), ink.with_alpha(0.45)
        selected = ink.with_alpha(0.14)

    acc = t.accent
    acc_top, acc_bot = acc.mix(WHITE, 0.16), acc.mix(BLACK, 0.12)
    card_hover = t.card.mix(ink, 0.0).with_alpha(min(1.0, t.card.a + 0.05))
    card_active = t.card.with_alpha(min(1.0, t.card.a + 0.10))

    v: dict[str, str] = {
        "variant": "dark" if t.dark else "light",
        "chrome": surf["chrome"].css, "popover": surf["popover"].css,
        "dialog": surf["dialog"].css, "osd": surf["osd"].css,
        "card": t.card.css, "card_hover": card_hover.css, "card_active": card_active.css,
        "hover": t.hover.css, "active": t.active.css, "selected": selected.css,
        "rim": t.highlight.css, "edge": t.edge.css,
        # Dark glass gets its edge from the extension's optics, not a drawn line. Light
        # glass on a light wallpaper would have no edge at all, so it keeps a thin dark
        # hairline all round: a contact line, never a lit one.
        "glass_edge": (_NONE if t.dark else LIGHT_HAIRLINE.css) if t.glass_menu_edges else t.edge.css,
        "glass_rim": (_NONE if t.dark else LIGHT_HAIRLINE.css) if t.glass_menu_edges else t.highlight.css,
        "divider": t.divider.css, "shadow": t.shadow.css,
        "fg": t.fg.css, "fg_dim": t.fg_dim.css, "fg_faint": t.fg_faint.css,
        "accent": acc.css, "accent_fg": t.accent_fg.css, "accent_text": t.accent_text.css,
        "accent_edge": acc.mix(WHITE, 0.35).with_alpha(0.7).css,
        # Light glass is near white: a pale ring would vanish on it, so it takes the accent itself.
        "focus_ring": (acc.mix(WHITE, 0.3).with_alpha(0.75) if t.dark else acc.mix(BLACK, 0.12)).css,
        "selection": t.selection.css, "destructive": t.destructive.css, "success": t.success.css,
        "warning": t.warning.css, "warning_wash": t.warning.with_alpha(0.14).css,
        "ctrl_top": ctrl[0].css, "ctrl_bot": ctrl[1].css,
        "ctrl_hover_top": hov[0].css, "ctrl_hover_bot": hov[1].css,
        "ctrl_press_top": press[0].css, "ctrl_press_bot": press[1].css,
        "acc_top": acc_top.css, "acc_bot": acc_bot.css,
        "acc_hover_top": acc_top.mix(WHITE, 0.12).css, "acc_hover_bot": acc_bot.mix(WHITE, 0.12).css,
        "acc_press_top": acc_top.mix(BLACK, 0.12).css, "acc_press_bot": acc_bot.mix(BLACK, 0.12).css,
        "field": field.css, "field_hover": field_hover.css, "field_shadow": field_shadow.css,
        "switch_off": switch_off.css, "switch_off_hover": switch_hover.css,
        "track": track.css, "scroll": scroll.css, "scroll_hover": scroll_hover.css,
    }
    v.update({k: str(n) for k, n in radii(t).items()})
    # The calendar, overview and ArcMenu sections of the template use their own part's look.
    for prefix, part, surf_p in (("cal_", "calendar", cal), ("ov_", "overview", ovw), ("arc_", "arcmenu", arc)):
        v.update({prefix + k: str(n) for k, n in radii(t, t.parts[part]["radius"]).items()})
        v.update({prefix + k: c.css for k, c in surf_p.items()})
    return v


_BOOST = re.compile(r"/\* @boost.*?\*/(.*?)/\* @end \*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _boost(match: re.Match) -> str:
    """Prefix every selector with #uiGroup: extension stylesheets (Dash to Panel, Wheelguard)
    load after the theme, so equal-specificity rules in them would otherwise win."""
    def rule(m: re.Match) -> str:
        sels = [s.strip() for s in m.group(1).split(",") if s.strip() and not s.strip().startswith("/*")]
        return ",\n".join("#uiGroup " + s for s in sels) + " {" + m.group(2) + "}\n"
    body = re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)
    return _RULE.sub(rule, body)


def render_css(t: Tokens) -> str:
    """The whole ~/.local/share/themes/LiquidGlass/gnome-shell/gnome-shell.css."""
    text = Template(_TEMPLATE.read_text(encoding="utf-8")).substitute(values(t))
    return _BOOST.sub(_boost, text)



def dtp_values(t: Tokens) -> dict[str, str]:
    """gsettings text per Dash to Panel key. Layout keys (position, sizes) are never touched."""
    floating = t.panel_floating
    bg = surfaces(t)["chrome"]
    m = t.panel_margin if floating else 0
    return {
        "trans-use-custom-bg": "true",
        "trans-bg-color": f"'{bg.hex6}'",
        "trans-use-custom-opacity": "true",
        "trans-panel-opacity": f"{bg.a:.3f}",
        "trans-use-dynamic-opacity": "false",
        "trans-use-custom-gradient": "false",
        # Dark glass draws its own edge; light glass keeps the thin dark hairline.
        "trans-use-border": "false" if t.glass_panel_edges and t.dark else "true",
        "trans-border-width": "1",
        "trans-border-use-custom-color": "true",
        "trans-border-custom-color": f"'{(LIGHT_HAIRLINE if t.glass_panel_edges else t.edge).css}'",
        "global-border-radius": f"{_dtp_radius(t) if floating else 0}",
        "panel-top-bottom-margins": f"{m}",
        "panel-side-margins": f"{m}",
        "panel-top-bottom-padding": "0",
        "panel-side-padding": "0",
        "highlight-appicon-hover-background-color": f"'{t.hover.css}'",
        "highlight-appicon-pressed-background-color": f"'{t.active.css}'",
        "highlight-appicon-hover-border-radius": str(t.radius_small),
        # Running apps get a small dot, not a bar; the focused one a faint glass wash.
        "focus-highlight-color": f"'{(WHITE if t.dark else BLACK).hex6}'",
        "focus-highlight-opacity": "8",
        "dot-style-focused": "'DOTS'",
        "dot-style-unfocused": "'DOTS'",
        "dot-size": "3",
        "dot-color-override": "true",
        **{f"dot-color-{i}": f"'{t.fg.hex6}'" for i in (1, 2, 3, 4)},
        "dot-color-unfocused-different": "true",
        # No separator line before the show-desktop button at the panel's end.
        "desktop-line-use-custom-color": "true",
        "desktop-line-custom-color": "'rgba(0,0,0,0)'",
        **{f"dot-color-unfocused-{i}": f"'{t.fg.mix(BLACK if t.dark else WHITE, 0.45).hex6}'" for i in (1, 2, 3, 4)},
    }


def _dtp_radius(t: Tokens) -> int:
    """Dash to Panel stores the radius in steps of 4 px (0..5), not pixels."""
    return min(5, round(t.panel_radius / 4))


# ---- ArcMenu -----------------------------------------------------------------------------------
def arcmenu_values(t: Tokens) -> dict[str, str]:
    """gsettings text per ArcMenu key (colours are CSS strings; (bs)/(bi) are enable flags + value)."""
    r = radii(t, t.parts["arcmenu"]["radius"])
    ink = WHITE if t.dark else BLACK
    bg = surfaces(t, "arcmenu")["popover"]
    fg = t.fg
    hover = ink.with_alpha(0.10 if t.dark else 0.08)
    active = t.accent.with_alpha(0.85)
    return {
        "override-menu-theme": "true",
        "menu-background-color": f"'{bg.css}'",
        "menu-foreground-color": f"'{fg.css}'",
        "menu-border-color": f"'{(_NONE if t.dark else LIGHT_HAIRLINE.css) if t.glass_menu_edges else t.edge.css}'",
        "menu-border-width": "1",
        "menu-border-radius": str(r["r_menu"]),
        "menu-separator-color": f"'{t.divider.css}'",
        "menu-item-hover-bg-color": f"'{hover.css}'",
        "menu-item-hover-fg-color": f"'{fg.css}'",
        "menu-item-active-bg-color": f"'{active.css}'",
        "menu-item-active-fg-color": f"'{t.accent_fg.css}'",
        "search-entry-border-radius": "(true, 999)",
        "menu-button-fg-color": f"(true, '{fg.css}')",
        "menu-button-bg-color": f"(true, '{ink.with_alpha(0.0).css}')",
        "menu-button-hover-bg-color": f"(true, '{hover.css}')",
        "menu-button-hover-fg-color": f"(true, '{fg.css}')",
        "menu-button-active-bg-color": f"(true, '{ink.with_alpha(0.16).css}')",
        "menu-button-active-fg-color": f"(true, '{fg.css}')",
        "menu-button-border-radius": "(true, 999)",
        "menu-button-border-width": "(true, 0)",
        "menu-button-border-color": "(true, 'transparent')",
    }
