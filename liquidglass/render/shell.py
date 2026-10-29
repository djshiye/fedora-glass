"""GNOME Shell theme: CSS for St, the Blur my Shell pipelines and the Dash to Panel / ArcMenu values.

St cannot blur, so every Shell surface is a translucent token colour and Blur
my Shell supplies the glass behind it. St also draws a single box-shadow, which
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


def radii(t: Tokens) -> dict[str, int]:
    """One radius scale shared by the CSS and Blur my Shell's corner keys,
    so the blur clip always matches the painted surface."""
    r = t.radius
    return {
        "r": r,
        "r_small": t.radius_small,
        "r_item": max(6, r - 4),
        "r_menu": r + 2,
        "r_sub": r + 6,
        "r_big": min(48, r * 2),
        "r_cal": min(48, round(r * 5 / 3)),
        "r_osd": r + 10,
        "r_dialog": r + 6,
        "r_folder": min(64, r * 3),
    }


def _thin(c: Color, t: Tokens) -> Color:
    """Shell surfaces sit on a real blur, so they can be more see-through than the
    blur-less GTK surfaces the tokens were tuned for. Near-opaque tokens (reduce
    transparency, solid presets) are left alone."""
    if c.a >= 0.95 or t.blur_radius == 0:
        return c
    k = lerp(0.60, 1.0, t.frost) if t.dark else lerp(0.74, 1.0, t.frost)
    return c.with_alpha(max(0.0, c.a * k))


def surfaces(t: Tokens) -> dict[str, Color]:
    return {"popover": _thin(t.popover, t), "dialog": _thin(t.dialog, t),
            "osd": _thin(t.osd, t), "chrome": t.chrome}


def values(t: Tokens) -> dict[str, str]:
    """Every placeholder of the CSS template, derived from tokens only."""
    surf = surfaces(t)
    ink = WHITE if t.dark else BLACK
    if t.dark:
        ctrl = (ink.with_alpha(0.17), ink.with_alpha(0.06))
        hov = (ink.with_alpha(0.24), ink.with_alpha(0.11))
        press = (ink.with_alpha(0.08), ink.with_alpha(0.20))
        field, field_hover = BLACK.with_alpha(0.22), BLACK.with_alpha(0.30)
        field_shadow = BLACK.with_alpha(0.35)
        switch_off, switch_hover = ink.with_alpha(0.20), ink.with_alpha(0.28)
        track = ink.with_alpha(0.16)
        scroll, scroll_hover = ink.with_alpha(0.30), ink.with_alpha(0.46)
        selected = ink.with_alpha(0.18)
    else:
        ctrl = (WHITE.with_alpha(0.80), WHITE.with_alpha(0.42))
        hov = (WHITE.with_alpha(0.92), WHITE.with_alpha(0.58))
        press = (WHITE.with_alpha(0.40), WHITE.with_alpha(0.62))
        field, field_hover = WHITE.with_alpha(0.55), WHITE.with_alpha(0.70)
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
        "rim": t.highlight.css, "edge": t.edge.css, "divider": t.divider.css, "shadow": t.shadow.css,
        "fg": t.fg.css, "fg_dim": t.fg_dim.css, "fg_faint": t.fg_faint.css,
        "accent": acc.css, "accent_fg": t.accent_fg.css, "accent_text": t.accent_text.css,
        "accent_edge": acc.mix(WHITE, 0.35).with_alpha(0.7).css,
        "focus_ring": acc.mix(WHITE, 0.3).with_alpha(0.75).css,
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


# ---- Blur my Shell ------------------------------------------------------------------------
PIPELINE_IDS = ("pipeline_liquidglass_panel", "pipeline_liquidglass_popup",
                "pipeline_liquidglass_overview", "pipeline_liquidglass_apps")

# Which component uses which of our pipelines.
COMPONENT_PIPELINE = {
    "panel": "pipeline_liquidglass_panel",
    "overview": "pipeline_liquidglass_overview",
    "appfolder": "pipeline_liquidglass_overview",
    "popup": "pipeline_liquidglass_popup",
    "applications": "pipeline_liquidglass_apps",
    "window-list": "pipeline_liquidglass_panel",
    "coverflow-alt-tab": "pipeline_liquidglass_popup",
    "lockscreen": "pipeline_liquidglass_overview",
    "screenshot": "pipeline_liquidglass_popup",
}


def _tint(t: Tokens, strength: float) -> tuple[float, tuple[float, float, float, float]]:
    """Blur my Shell's tint is a strength plus an rgba colour; lean towards the surface colour."""
    base = t.popover
    return strength, (round(base.r, 3), round(base.g, 3), round(base.b, 3), 1.0)


def refraction_params(t: Tokens, kind: str) -> dict[str, float | bool | tuple]:
    """Parameters of one `refraction` effect. frost 0 bends the backdrop hard with a
    bright rim and little blur; frost 1 barely bends it, blurs heavily and adds milk."""
    f = t.frost
    weight = {"panel": 0.5, "popup": 1.0, "overview": 0.8, "apps": 0.35}[kind]
    blur = max(1, min(48, round(t.blur_radius * {"panel": 0.55, "popup": 0.8, "overview": 1.0, "apps": 0.9}[kind])))
    tint_strength, tint_color = _tint(t, lerp(0.05, 0.30, f) if t.dark else lerp(0.10, 0.38, f))
    p: dict[str, float | bool | tuple] = {
        "strength": round(lerp(0.55, 0.10, f) * weight, 3),
        "blur_radius": float(blur),
        "edge_size": 22.0,
        "falloff": round(lerp(2.2, 4.5, f), 2),
        "rim_width": round(lerp(4.8, 2.0, f), 2),
        "rgb_fringing": round(lerp(0.12, 0.02, f) * (0.5 if kind == "apps" else 1.0), 3),
        "gloss": round(lerp(0.60, 0.12, f) * (0.6 if kind == "apps" else 1.0), 3),
        "specular_strength": round(lerp(0.35, 0.0, f), 3),
        "tint": round(tint_strength, 3),
        "tint_color": tint_color,
        "backdrop_zoom": 1.0,
        "shadow": round(lerp(0.12, 0.05, f), 3),
        "texture_repeat": 0,
    }
    if kind == "apps":
        p["strength"] = round(lerp(0.10, 0.0, f), 3)
    return p


def kawase_params(t: Tokens, kind: str) -> dict[str, float]:
    scale = {"panel": 0.7, "popup": 1.0, "overview": 1.2, "apps": 1.0}[kind]
    return {"unscaled_radius": float(max(1, round(t.blur_radius * scale))),
            "brightness": float(t.blur_brightness)}


# A pipeline is a nested GVariant (a{sa{sv}}). Parsing and printing its text form here
# keeps the engine free of PyGObject and keeps foreign pipelines byte-for-byte as they were.
_Node = tuple  # ("dict", [(key, val)]) | ("arr", [..]) | ("tup", [..]) | ("var", node) | ("raw", text)


class _Parser:
    def __init__(self, text: str):
        self.s, self.i = text, 0

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def node(self) -> _Node:
        self.ws()
        c = self.s[self.i]
        if c == "{":
            self.i += 1
            items = []
            while True:
                self.ws()
                if self.s[self.i] == "}":
                    self.i += 1
                    return ("dict", items)
                k = self.node()
                self.ws()
                if self.s[self.i] != ":":
                    raise ValueError("expected ':'")
                self.i += 1
                items.append((k, self.node()))
                self.ws()
                if self.s[self.i] == ",":
                    self.i += 1
        if c in "[(":
            end = "]" if c == "[" else ")"
            self.i += 1
            items = []
            while True:
                self.ws()
                if self.s[self.i] == end:
                    self.i += 1
                    return ("arr" if c == "[" else "tup", items)
                items.append(self.node())
                self.ws()
                if self.s[self.i] == ",":
                    self.i += 1
        if c == "<":
            self.i += 1
            inner = self.node()
            self.ws()
            if self.s[self.i] != ">":
                raise ValueError("expected '>'")
            self.i += 1
            return ("var", inner)
        if c in "'\"":
            j = self.i + 1
            while self.s[j] != c:
                j += 2 if self.s[j] == "\\" else 1
            raw, self.i = self.s[self.i:j + 1], j + 1
            return ("raw", raw)
        j = self.i
        while j < len(self.s) and not self.s[j].isspace() and self.s[j] not in ",:>)]}":
            j += 1
        word, self.i = self.s[self.i:j], j
        if word.startswith("@") or re.fullmatch(r"[a-z]+[0-9]*", word) and word not in ("true", "false", "nan", "inf"):
            # a type annotation or numeric prefix (@as [], uint32 5): the value follows
            return ("raw", word + " " + _dump(self.node()))
        if not word:
            raise ValueError(f"unexpected {c!r}")
        return ("raw", word)


def _dump(n: _Node) -> str:
    kind, v = n
    if kind == "raw":
        return v
    if kind == "var":
        return f"<{_dump(v)}>"
    if kind == "dict":
        return "{" + ", ".join(f"{_dump(k)}: {_dump(x)}" for k, x in v) + "}"
    body = ", ".join(_dump(x) for x in v)
    return f"[{body}]" if kind == "arr" else f"({body}{',' if len(v) == 1 else ''})"


def _q(s: str) -> _Node:
    return ("raw", "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'")


def _scalar(x: object) -> _Node:
    if isinstance(x, bool):
        return ("var", ("raw", "true" if x else "false"))
    if isinstance(x, int):
        return ("var", ("raw", str(x)))
    if isinstance(x, float):
        r = repr(round(x, 4))
        return ("var", ("raw", r if ("." in r or "e" in r) else r + ".0"))
    if isinstance(x, tuple):
        return ("var", ("tup", [_scalar(c)[1] for c in x]))
    raise TypeError(type(x))


def _pipeline(pid: str, name: str, effect: str, params: dict) -> _Node:
    """One pipeline in the shape Blur my Shell stores."""
    fx = ("dict", [(_q("type"), ("var", _q(effect))),
                   (_q("id"), ("var", _q(f"effect_{pid}"))),
                   (_q("params"), ("var", ("dict", [(_q(k), _scalar(v)) for k, v in params.items()])))])
    return ("dict", [(_q("name"), ("var", _q(name))),
                     (_q("effects"), ("var", ("arr", [("var", fx)])))])


def merge_pipelines(current: str | None, ours: dict[str, _Node]) -> str:
    """The `pipelines` value (gsettings text) with our pipelines added or replaced in place.

    Pipelines we don't own are carried over as they were, so applying twice gives the same text."""
    items: list[tuple[str, _Node]] = []
    text = (current or "").strip()
    if text.startswith("@"):
        text = text.split(None, 1)[1] if " " in text else ""
    if text:
        # Never drop the user's own pipelines: if we can't read them, refuse to write.
        try:
            kind, entries = _Parser(text).node()
        except (ValueError, IndexError) as e:
            raise ValueError("couldn't read the current Blur my Shell pipelines, left them untouched") from e
        if kind != "dict":
            raise ValueError("unexpected Blur my Shell pipelines value, left it untouched")
        items = [(k[1][1:-1], v) for k, v in entries if k[0] == "raw"]
    seen = set()
    merged = []
    for pid, node in items:
        merged.append((pid, ours.get(pid, node)))
        seen.add(pid)
    merged += [(pid, node) for pid, node in ours.items() if pid not in seen]
    if not merged:
        return "@a{sa{sv}} {}"
    return _dump(("dict", [(_q(pid), node) for pid, node in merged]))


def our_pipelines(t: Tokens, have_refraction: bool) -> dict:
    out = {}
    for pid, kind, name in (("pipeline_liquidglass_panel", "panel", "Liquid Glass Panel"),
                            ("pipeline_liquidglass_popup", "popup", "Liquid Glass Popup"),
                            ("pipeline_liquidglass_overview", "overview", "Liquid Glass Overview"),
                            ("pipeline_liquidglass_apps", "apps", "Liquid Glass Apps")):
        if have_refraction:
            out[pid] = _pipeline(pid, name, "refraction", refraction_params(t, kind))
        else:
            out[pid] = _pipeline(pid, name, "dual_kawase_blur", kawase_params(t, kind))
    return out


def popup_corner_keys(t: Tokens) -> dict[str, int]:
    r = radii(t)
    return {
        "corner-radius": r["r"], "dialog-corner-radius": r["r_dialog"], "menu-corner-radius": r["r_menu"],
        "notification-corner-radius": r["r"], "osd-corner-radius": r["r_osd"],
        "osd-window-corner-radius": 48, "quick-settings-corner-radius": r["r_big"],
        "submenu-corner-radius": r["r_sub"], "calendar-corner-radius": r["r_cal"],
        "candidate-corner-radius": r["r_small"], "resize-popup-corner-radius": r["r_small"],
    }


# ---- Dash to Panel ---------------------------------------------------------------------------
def dtp_values(t: Tokens) -> dict[str, str]:
    """gsettings text per Dash to Panel key. Layout keys (position, sizes) are never touched."""
    floating = t.panel_floating
    bg = t.chrome
    m = t.panel_margin if floating else 0
    return {
        "trans-use-custom-bg": "true",
        "trans-bg-color": f"'{bg.hex6}'",
        "trans-use-custom-opacity": "true",
        "trans-panel-opacity": f"{bg.a:.3f}",
        "trans-use-dynamic-opacity": "false",
        "trans-use-custom-gradient": "false",
        "trans-use-border": "true",
        "trans-border-width": "1",
        "trans-border-use-custom-color": "true",
        "trans-border-custom-color": f"'{t.edge.css}'",
        "global-border-radius": f"{_dtp_radius(t) if floating else 0}",
        "panel-top-bottom-margins": f"{m}",
        "panel-side-margins": f"{m}",
        "panel-top-bottom-padding": "0",
        "panel-side-padding": "0",
        "highlight-appicon-hover-background-color": f"'{t.hover.css}'",
        "highlight-appicon-pressed-background-color": f"'{t.active.css}'",
        "highlight-appicon-hover-border-radius": str(t.radius_small),
        "focus-highlight-color": f"'{(WHITE if t.dark else BLACK).hex6}'",
        "dot-color-override": "true",
        **{f"dot-color-{i}": f"'{t.fg.hex6}'" for i in (1, 2, 3, 4)},
    }


def _dtp_radius(t: Tokens) -> int:
    """Dash to Panel stores the radius in steps of 4 px (0..5), not pixels."""
    return min(5, round(t.radius / 4))


# ---- ArcMenu -----------------------------------------------------------------------------------
def arcmenu_values(t: Tokens) -> dict[str, str]:
    """gsettings text per ArcMenu key (colours are CSS strings; (bs)/(bi) are enable flags + value)."""
    r = radii(t)
    ink = WHITE if t.dark else BLACK
    bg = surfaces(t)["popover"]
    fg = t.fg
    hover = ink.with_alpha(0.10 if t.dark else 0.08)
    active = t.accent.with_alpha(0.85)
    return {
        "override-menu-theme": "true",
        "menu-background-color": f"'{bg.css}'",
        "menu-foreground-color": f"'{fg.css}'",
        "menu-border-color": f"'{t.edge.css}'",
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
