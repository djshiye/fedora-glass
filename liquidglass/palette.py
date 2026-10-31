"""Turn Settings into concrete design tokens.

Every renderer (GTK, Shell, terminal, Qt, apps) takes a Tokens object, so all
targets move together when the slider moves. The model:

* frost 0 (liquid): thin, clear glass. Low surface opacity, light blur, a
  bright specular rim along the top edge, vivid backdrop.
* frost 1 (frosted): thick, milky glass. Higher opacity with a white haze,
  heavy blur, a quiet rim.

Content surfaces (lists, text views) always stay more solid than chrome
(header bars, sidebars, panels) so text stays readable at any setting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .color import BLACK, WHITE, Color, lerp
from .radius import scale
from .settings import GNOME_ACCENTS, PARTS, Settings


@dataclass(frozen=True)
class Tokens:
    dark: bool
    frost: float
    # Surfaces (all carry alpha)
    window: Color        # window background
    chrome: Color        # header bars, sidebars, panel, dash
    view: Color          # lists, text areas, terminal-like content
    card: Color          # cards and boxed lists, drawn on window/view
    window_chrome: Color # sidebars and bars inside app windows (chrome, with the windows part's look)
    popover: Color       # menus and popovers (no live blur behind them in GTK)
    dialog: Color
    osd: Color           # Shell OSD / on-screen overlays
    hover: Color         # hover wash
    active: Color        # pressed wash
    # Lines and light
    highlight: Color     # specular rim along the top edge
    edge: Color          # 1px glass border
    divider: Color
    shadow: Color
    # Text
    fg: Color
    fg_dim: Color
    fg_faint: Color
    # Accent
    accent: Color        # accent background (buttons, switches, selection)
    accent_fg: Color     # text on accent
    accent_text: Color   # accent used as text/icon colour on glass
    selection: Color     # text and row selection wash
    destructive: Color
    success: Color
    warning: Color
    # Geometry and effects
    # `radius` is the base of the corner ladder (radius.scale); the *_radius fields below are
    # the base of each part's own ladder. radius_small is the ladder's "s" step (buttons, fields).
    radius: int
    radius_small: int
    blur_radius: int     # blur behind glass, px
    # Per-part look (settings.parts); each equals the global value unless that part overrides it.
    # `chrome` is the panel's surface, `popover`/`dialog`/`osd` the quick settings' (the generic
    # menu look) and `window`/`view`/`window_chrome` the app windows'. `parts` has all of them.
    panel_radius: int
    menu_radius: int
    window_radius: int
    panel_blur: int
    menu_blur: int
    window_blur: int
    parts: dict          # part name -> its colours and numbers, see _part_look()
    blur_brightness: float
    terminal_opacity: float
    panel_floating: bool
    panel_margin: int
    blur_app_windows: bool
    # The Shell's glass lens (see the extension's glass.js)
    lens_width: float      # px of rim that bends the backdrop
    lens_bend: float       # px, thickness of the glass slab the light bends through
    dispersion: float      # 0..1
    vibrancy: float        # saturation multiplier, 1 = unchanged
    glare: float           # directional highlight along the rim, 0..1
    bleed: float           # how much the colours of content light up the glass around it, 0..1
    # The glass extension draws these surfaces' edges itself, so the theme leaves them unbordered.
    glass_panel_edges: bool
    glass_menu_edges: bool

    def to_json(self) -> str:
        """Public token file for apps that read it (see docs/TOKENS.md)."""
        out: dict[str, object] = {"version": 1}
        for k, v in self.__dict__.items():
            out[k] = _jsonable(v)
        return json.dumps(out, indent=2) + "\n"


def _jsonable(v: object) -> object:
    if isinstance(v, Color):
        return v.hex8
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    return v


def _surfaces(s: Settings, dark: bool, tint: Color, strength: float, f: float) -> dict[str, Color]:
    """Surface colours for one tint, tint strength and frost. Every part of the
    desktop goes through here, so they only differ by the numbers they are given."""
    if dark:
        base = Color.hex("#17181d").mix(tint, strength * 0.55)
        surface = base.mix(WHITE, lerp(0.02, 0.11, f))     # milky lift towards white when frosted
        a_chrome, a_window = lerp(0.24, 0.66, f), lerp(0.50, 0.78, f)
        a_view, a_pop = lerp(0.86, 0.92, f), lerp(0.78, 0.90, f)   # text areas stay solid enough to read
    else:
        base = Color.hex("#f5f6fa").mix(tint, strength * 0.45)
        surface = base.mix(WHITE, lerp(0.0, 0.25, f))
        a_chrome, a_window = lerp(0.40, 0.76, f), lerp(0.52, 0.82, f)
        a_view, a_pop = lerp(0.86, 0.93, f), lerp(0.80, 0.93, f)

    if s.opacity is not None:
        o = s.opacity
        a_chrome, a_window = o, min(1.0, o + 0.08)
        a_view, a_pop = min(1.0, o + 0.22), max(a_pop, min(1.0, o + 0.25))
    if s.reduce_transparency:
        a_chrome = a_window = a_view = a_pop = 0.97

    return {
        "window": surface.with_alpha(a_window),
        "chrome": surface.with_alpha(a_chrome),
        # How solid a content view (the Files grid, a text area) looks in the end, glass
        # included: the frosted glass shows a little through, text stays readable.
        "view": surface.mix(BLACK if dark else WHITE, 0.25).with_alpha(a_view),
        "popover": surface.with_alpha(a_pop),
        "dialog": surface.with_alpha(min(1.0, a_pop + 0.04)),
        "osd": surface.mix(BLACK, 0.2 if dark else 0.0).with_alpha(max(0.55, a_chrome)),
    }


def _lens(s: Settings, f: float, refraction: float, bleed: float, reflections: float) -> dict[str, float]:
    """The glass lens numbers for one frost, bend, colour bleed and edge reflection strength."""
    off = s.reduce_transparency
    return {
        # Liquid glass bends a wide rim hard; frosted glass is thick and calm.
        "lens_width": 0.0 if off else round(lerp(26, 16, f) * (0.4 + 0.6 * refraction), 1),
        "lens_bend": 0.0 if off else round(lerp(60, 24, f) * refraction, 1),
        "bleed": 0.0 if off else round(bleed * lerp(1.0, 0.6, f), 3),
        "glare": round(reflections * lerp(0.7, 0.3, f), 3),
    }


def _part_look(s: Settings, dark: bool, part: str) -> dict:
    """Everything one part of the desktop needs: its surfaces (tint, strength and frost
    applied), corner radius, blur and lens. A key the part doesn't override follows the global one."""
    o = s.parts.get(part, {})
    f = o.get("frost", s.frost)
    tint = Color.hex(o.get("tint", s.tint))
    out: dict = _surfaces(s, dark, tint, o.get("tint_strength", s.tint_strength), f)
    if s.reduce_transparency:
        blur = 0
    elif s.blur is not None and "frost" not in o:
        blur = s.blur             # the Blur fine-tune covers every part that doesn't set its own frost
    else:
        blur = round(lerp(8, 56, f))
    out.update(tint=tint.with_alpha(0.0), frost=f, radius=o.get("radius", s.radius), blur=int(blur))
    out.update(_lens(s, f, o.get("refraction", s.refraction), o.get("bleed", s.bleed),
                     o.get("reflections", s.highlight)))
    return out


def resolve_accent(settings: Settings, system_accent: str | None) -> Color:
    a = settings.accent
    if a == "system":
        a = system_accent or "blue"
    if a in GNOME_ACCENTS:
        a = GNOME_ACCENTS[a]
    try:
        return Color.hex(a)
    except ValueError:
        return Color.hex(GNOME_ACCENTS["blue"])


def build(settings: Settings, *, dark: bool, system_accent: str | None = None) -> Tokens:
    s = settings.normalized()
    f = s.frost
    tint = Color.hex(s.tint)
    accent = resolve_accent(s, system_accent)

    if dark:
        fg = Color.hex("#f4f5f9")
        rim = WHITE.with_alpha(s.highlight * lerp(0.42, 0.16, f))
        edge = WHITE.with_alpha(lerp(0.17, 0.09, f))
        card = WHITE.with_alpha(lerp(0.07, 0.06, f))
        hover, active = WHITE.with_alpha(0.08), WHITE.with_alpha(0.14)
        divider = WHITE.with_alpha(0.09)
        shadow = BLACK.with_alpha(0.36)
        brightness = lerp(0.96, 0.70, f)
        accent_text = accent.mix(WHITE, 0.28)
    else:
        fg = Color.hex("#1a1b20")
        rim = WHITE.with_alpha(s.highlight * lerp(0.95, 0.55, f))
        edge = BLACK.with_alpha(lerp(0.10, 0.07, f))
        card = WHITE.with_alpha(lerp(0.50, 0.55, f))
        hover, active = BLACK.with_alpha(0.05), BLACK.with_alpha(0.10)
        divider = BLACK.with_alpha(0.08)
        shadow = BLACK.with_alpha(0.16)
        brightness = 1.0
        accent_text = accent.mix(BLACK, 0.18)

    parts = {p: _part_look(s, dark, p) for p in PARTS}
    panel, menus, wins = parts["panel"], parts["quicksettings"], parts["windows"]
    lens = _lens(s, f, s.refraction, s.bleed, s.highlight)

    blur = s.blur if s.blur is not None else round(lerp(8, 56, f))
    if s.reduce_transparency:
        blur = 0

    accent_fg = WHITE if accent.contrast(WHITE) >= accent.contrast(BLACK) * 0.6 else BLACK
    # 88% solid at the default frost: a little glass shows, text stays readable on any wallpaper.
    term = s.terminal_opacity if s.terminal_opacity is not None else lerp(0.84, 0.94, parts["terminal"]["frost"])
    if s.reduce_transparency:
        term = 1.0

    return Tokens(
        dark=dark,
        frost=f,
        window=wins["window"],
        chrome=panel["chrome"],
        view=wins["view"],
        card=card,
        window_chrome=wins["chrome"],
        popover=menus["popover"],
        dialog=menus["dialog"],
        osd=menus["osd"],
        hover=hover,
        active=active,
        highlight=rim,
        edge=edge,
        divider=divider,
        shadow=shadow,
        fg=fg,
        fg_dim=fg.with_alpha(0.70),
        fg_faint=fg.with_alpha(0.46),
        accent=accent,
        accent_fg=accent_fg,
        accent_text=accent_text,
        selection=accent.with_alpha(0.32 if dark else 0.24),
        destructive=Color.hex("#ff6b6b" if dark else "#d32f3f"),
        success=Color.hex("#4ad48a" if dark else "#1f9d55"),
        warning=Color.hex("#f5c04f" if dark else "#b87a00"),
        radius=s.radius,
        radius_small=scale(s.radius)["s"],       # the buttons/fields step of the one radius scale
        blur_radius=int(blur),
        panel_radius=panel["radius"],
        menu_radius=menus["radius"],
        window_radius=wins["radius"],
        panel_blur=panel["blur"],
        menu_blur=menus["blur"],
        window_blur=wins["blur"],
        parts=parts,
        blur_brightness=round(brightness, 3),
        terminal_opacity=round(term, 3),
        panel_floating=s.panel_style == "floating",
        panel_margin=s.panel_margin,
        blur_app_windows=s.blur_app_windows and not s.reduce_transparency,
        lens_width=lens["lens_width"],
        lens_bend=lens["lens_bend"],
        dispersion=0.0 if s.reduce_transparency else round(s.dispersion * lerp(1.0, 0.35, f), 3),
        vibrancy=round(1.0 + s.vibrancy * lerp(1.0, 0.6, f), 3),
        glare=lens["glare"],
        bleed=lens["bleed"],
        glass_panel_edges=s.glass_panel and s.target_enabled("glass") and not s.reduce_transparency,
        glass_menu_edges=s.glass_menus and s.target_enabled("glass") and not s.reduce_transparency,
    )
