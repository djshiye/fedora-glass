"""GTK 3 stylesheet on top of the adw-gtk3 theme.

adw-gtk3 colours everything from libadwaita's named colours, and GTK 3 resolves
named colours late, so redefining them in ~/.config/gtk-3.0/gtk.css recolours
the whole theme. GTK 3 has no media queries or custom properties, so this file
is written for one scheme (the active one) and carries `@lg_*` colours of its own.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from ..color import Color
from ..palette import Tokens
from .gtk4 import _geometry, adwaita_colors, glass_colors

_TEMPLATE = Path(__file__).resolve().parent.parent / "data/gtk/gtk3.css.tpl"
HEADER = "/* Liquid Glass for GTK 3 (adw-gtk3). Generated, edits are overwritten. */\n"

THEMES = ("adw-gtk3", "adw-gtk3-dark")


def theme_name(t: Tokens) -> str:
    return "adw-gtk3-dark" if t.dark else "adw-gtk3"


def named_colors(t: Tokens) -> dict[str, Color]:
    colors = {k.replace("-", "_"): v for k, v in {**adwaita_colors(t), **glass_colors(t)}.items()}
    colors.update({
        "headerbar_bg_color": t.window, "headerbar_backdrop_color": t.window,
        # GTK 3 era names some apps still use
        "theme_bg_color": t.window, "theme_fg_color": t.fg,
        "theme_base_color": t.view, "theme_text_color": t.fg,
        "theme_selected_bg_color": t.accent, "theme_selected_fg_color": t.accent_fg,
    })
    return colors


def render(t: Tokens) -> str:
    colors = "\n".join(f"@define-color {k} {v.css};" for k, v in named_colors(t).items())
    rules = Template(_TEMPLATE.read_text(encoding="utf-8")).substitute(_geometry(t))
    return f"{HEADER}\n{colors}\n\n{rules}"
