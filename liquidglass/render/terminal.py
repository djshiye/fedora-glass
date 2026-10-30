"""Terminal colours derived from tokens, shared by every terminal-like target.

One 16-colour palette is derived per scheme so Ptyxis, GNOME Terminal, btop,
micro and the editor terminals all agree. Hues are fixed (a terminal needs red
to look red) but nudged towards the accent, and lightness is solved against the
background so text stays legible whatever the frost slider does.
"""

from __future__ import annotations

import colorsys
from dataclasses import dataclass

from ..color import Color
from ..palette import Tokens

ANSI_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")

# Hue in degrees for ANSI 1..6 (red, green, yellow, blue, magenta, cyan).
_HUES = (4, 140, 42, 214, 284, 184)


@dataclass(frozen=True)
class TermPalette:
    bg: Color            # opaque; the window's opacity is applied separately
    fg: Color
    cursor: Color
    cursor_fg: Color
    selection_bg: Color
    selection_fg: Color
    ansi: tuple[Color, ...]   # 16 entries: 0-7 normal, 8-15 bright
    dim: Color           # comments, autosuggestions, inactive text
    accent: Color

    def named(self) -> dict[str, Color]:
        out = {}
        for i, n in enumerate(ANSI_NAMES):
            out[n] = self.ansi[i]
            out["bright_" + n] = self.ansi[i + 8]
        return out


def _hsl(c: Color) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(c.r, c.g, c.b)
    return h, s, l


def _from_hsl(h: float, s: float, l: float) -> Color:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, min(1, max(0, l)), min(1, max(0, s)))
    return Color(r, g, b)


def ensure_contrast(c: Color, bg: Color, ratio: float) -> Color:
    """Move lightness away from the background until the ratio is met."""
    if c.contrast(bg) >= ratio:
        return c
    h, s, l = _hsl(c)
    step = 0.02 if bg.luminance() < 0.4 else -0.02
    for _ in range(50):
        l += step
        c = _from_hsl(h, s, l)
        if c.contrast(bg) >= ratio or not 0.0 < l < 1.0:
            break
    return c


def _hue_of(c: Color) -> float:
    return colorsys.rgb_to_hls(c.r, c.g, c.b)[0]


def derive(t: Tokens) -> TermPalette:
    dark = t.dark
    bg = t.parts["terminal"]["view"].with_alpha(1.0)
    fg = t.fg.with_alpha(1.0)
    accent = t.accent.with_alpha(1.0)
    acc_h = _hue_of(accent)

    def hue_shift(h: float) -> float:
        # Pull each hue 10% of the way round towards the accent hue.
        d = ((acc_h - h / 360 + 0.5) % 1.0) - 0.5
        return h / 360 + d * 0.10

    if dark:
        normal, bright = (0.64, 0.58), (0.76, 0.78)       # (lightness, saturation)
    else:
        normal, bright = (0.36, 0.72), (0.28, 0.80)

    ansi: list[Color] = [Color(0, 0, 0)] * 16
    for i, h in enumerate(_HUES, start=1):
        hh = hue_shift(h)
        ansi[i] = ensure_contrast(_from_hsl(hh, normal[1], normal[0]), bg, 4.6)
        ansi[i + 8] = ensure_contrast(_from_hsl(hh, bright[1], bright[0]), bg, 5.6)

    if dark:
        ansi[0] = ensure_contrast(bg.mix(fg, 0.20), bg, 2.4)
        ansi[7] = fg.mix(bg, 0.18)
        ansi[8] = ensure_contrast(fg.mix(bg, 0.52), bg, 4.2)
        ansi[15] = fg
    else:
        ansi[0] = fg.mix(bg, 0.10)
        ansi[7] = ensure_contrast(bg.mix(fg, 0.30), bg, 3.0)
        ansi[8] = ensure_contrast(fg.mix(bg, 0.50), bg, 4.2)
        ansi[15] = fg.mix(bg, 0.0)
    sel = bg.mix(accent, 0.36 if dark else 0.28)
    return TermPalette(
        bg=bg, fg=fg, cursor=t.accent_text.with_alpha(1.0), cursor_fg=bg,
        selection_bg=sel, selection_fg=fg, ansi=tuple(ansi),
        dim=ansi[8], accent=ensure_contrast(t.accent_text.with_alpha(1.0), bg, 4.5),
    )


# ---- Ptyxis ---------------------------------------------------------------
PTYXIS_PALETTE_NAME = "Liquid Glass"


def _ptyxis_section(name: str, p: TermPalette, titlebar: Color | None = None) -> str:
    lines = [f"[{name}]", f"Background={p.bg.hex6}", f"Foreground={p.fg.hex6}",
             f"Cursor={p.cursor.hex6}"]
    if titlebar is not None:
        # Ptyxis paints its top bar from these, above our gtk.css, and keeps their alpha.
        lines += [f"TitlebarBackground={titlebar.hex8}", f"TitlebarForeground={p.fg.hex6}"]
    lines += [f"Color{i}={c.hex6}" for i, c in enumerate(p.ansi)]
    return "\n".join(lines) + "\n"


def ptyxis_palette(dark: Tokens, light: Tokens, titlebar: dict[str, Color] | None = None) -> str:
    """A .palette file for ~/.local/share/org.gnome.Ptyxis/palettes/ with both schemes.
    `titlebar` maps "dark"/"light" to the top bar colour (with alpha)."""
    tb = titlebar or {}
    head = f"[Palette]\nName={PTYXIS_PALETTE_NAME}\n"
    return (head + "\n" + _ptyxis_section("Light", derive(light), tb.get("light"))
            + "\n" + _ptyxis_section("Dark", derive(dark), tb.get("dark")))


# ---- GNOME Terminal ---------------------------------------------------------
def gvariant_str_list(colors: list[str]) -> str:
    return "[" + ", ".join(f"'{c}'" for c in colors) + "]"


# ---- btop ---------------------------------------------------------------------
def _grad(a: Color, b: Color, c: Color) -> tuple[str, str, str]:
    return a.hex6, b.hex6, c.hex6


def btop_theme(t: Tokens) -> str:
    p = derive(t)
    n = p.named()
    dim = p.dim
    meter_bg = p.bg.mix(p.fg, 0.16)
    rows: list[tuple[str, str]] = [
        ("main_bg", p.bg.hex6),     # unused while theme_background is false
        ("main_fg", p.fg.hex6),
        ("title", p.fg.hex6),
        ("hi_fg", p.accent.hex6),
        ("selected_bg", p.selection_bg.hex6),
        ("selected_fg", p.selection_fg.hex6),
        ("inactive_fg", dim.mix(p.bg, 0.25).hex6),
        ("graph_text", dim.hex6),
        ("meter_bg", meter_bg.hex6),
        ("proc_misc", n["cyan"].hex6),
        ("cpu_box", p.accent.mix(p.bg, 0.25).hex6),
        ("mem_box", n["green"].mix(p.bg, 0.25).hex6),
        ("net_box", n["magenta"].mix(p.bg, 0.25).hex6),
        ("proc_box", n["blue"].mix(p.bg, 0.25).hex6),
        ("div_line", p.fg.mix(p.bg, 0.78).hex6),
    ]
    grads = {
        "temp": (n["cyan"], n["yellow"], n["red"]),
        "cpu": (n["green"], n["yellow"], n["red"]),
        "free": (n["red"], n["yellow"], n["green"]),
        "cached": (n["blue"], n["cyan"], n["bright_cyan"]),
        "available": (n["green"], n["bright_green"], n["bright_cyan"]),
        "used": (n["cyan"], n["blue"], n["magenta"]),
        "download": (n["blue"], n["cyan"], n["bright_cyan"]),
        "upload": (n["magenta"], n["bright_magenta"], n["red"]),
        "process": (n["green"], n["yellow"], n["red"]),
    }
    for k, (a, b, c) in grads.items():
        rows += [(f"{k}_start", a.hex6), (f"{k}_mid", b.hex6), (f"{k}_end", c.hex6)]
    body = "\n".join(f'theme[{k}]="{v}"' for k, v in rows)
    return f"# Liquid Glass for btop\n{body}\n"


# ---- micro --------------------------------------------------------------------
def micro_colorscheme(t: Tokens) -> str:
    p = derive(t)
    n = p.named()
    cl = p.bg.mix(p.fg, 0.07)       # current line
    bar = p.bg.mix(p.fg, 0.12)

    def fb(fg: Color, bg: Color | None = None, attr: str = "") -> str:
        s = fg.hex6 + (f",{bg.hex6}" if bg else "")
        return f'"{attr + " " if attr else ""}{s}"'

    links = [
        ("default", fb(p.fg)),            # no background: the terminal's glass shows through
        ("comment", fb(p.dim, attr="italic")),
        ("identifier", fb(n["blue"])),
        ("identifier.class", fb(n["bright_cyan"])),
        ("identifier.var", fb(p.fg)),
        ("constant", fb(n["yellow"])),
        ("constant.number", fb(n["yellow"])),
        ("constant.string", fb(n["green"])),
        ("constant.string.char", fb(n["green"])),
        ("constant.specialChar", fb(n["bright_green"])),
        ("symbol", fb(n["cyan"])),
        ("symbol.operator", fb(n["cyan"])),
        ("symbol.brackets", fb(p.fg.mix(p.bg, 0.2))),
        ("type", fb(n["bright_cyan"])),
        ("type.keyword", fb(n["magenta"])),
        ("statement", fb(n["magenta"], attr="bold")),
        ("preproc", fb(n["red"])),
        ("special", fb(n["bright_blue"])),
        ("underlined", fb(p.accent, attr="underline")),
        ("error", fb(n["bright_red"], attr="bold")),
        ("todo", fb(n["bright_yellow"], attr="bold")),
        ("diff-added", fb(n["green"])),
        ("diff-modified", fb(n["yellow"])),
        ("diff-deleted", fb(n["red"])),
        ("gutter-error", fb(n["bright_red"])),
        ("gutter-warning", fb(n["yellow"])),
        ("line-number", fb(p.dim)),
        ("current-line-number", fb(p.accent, attr="bold")),
        ("indent-char", fb(p.dim.mix(p.bg, 0.5))),
        ("cursor-line", fb(cl)),          # micro takes just the line colour here
        ("color-column", fb(bar)),
        ("statusline", fb(p.fg, bar)),
        ("tabbar", fb(p.fg, bar)),
        ("tabbar.active", fb(p.accent, bar, "bold")),
        ("scrollbar", fb(p.accent.mix(p.bg, 0.4))),
        ("divider", fb(p.dim.mix(p.bg, 0.5))),
        ("match-brace", fb(p.bg, p.accent)),
        ("tab-error", fb(p.fg, n["red"].mix(p.bg, 0.6))),
        ("trailingws", fb(p.fg, n["red"].mix(p.bg, 0.6))),
        ("message", fb(p.fg, bar)),
        ("selection", fb(p.selection_fg, p.selection_bg)),
    ]
    body = "\n".join(f"color-link {k} {v}" for k, v in links)
    return f"# Liquid Glass for micro\n{body}\n"
