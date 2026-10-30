"""GTK 4 / libadwaita stylesheet.

libadwaita 1.9 colours everything from `--*-bg-color` custom properties (and
the matching `@define-color` names for older apps), so overriding those
recolours every app. The glass rules below only use `--lg-*` properties, which
means the rule block is written once and the two schemes differ only in a
small `:root` block wrapped in `@media (prefers-color-scheme: ...)`.
"""

from __future__ import annotations

from pathlib import Path
from string import Template

from ..color import Color
from ..palette import Tokens

_TEMPLATE = Path(__file__).resolve().parent.parent / "data/gtk/gtk4.css.tpl"

HEADER = "/* Liquid Glass for GTK 4 and libadwaita. Generated, edits are overwritten. */\n"


def popover_color(t: Tokens) -> Color:
    """Menus sit over text and controls, so they never get thinner than this."""
    return t.popover.with_alpha(max(t.popover.a, 0.90))


def dialog_color(t: Tokens) -> Color:
    return t.dialog.with_alpha(max(t.dialog.a, 0.95))


def bar_color(t: Tokens) -> Color:
    """Search and action bars sit on the window, so they only add a little to its alpha."""
    return t.window_chrome.with_alpha(max(0.0, t.window_chrome.a - t.window.a * 0.6))


def adwaita_colors(t: Tokens) -> dict[str, Color]:
    """Every colour libadwaita 1.9 (and adw-gtk3) derives its look from, by token name."""
    clear = Color(0, 0, 0, 0)
    ink, white = Color(0.07, 0.07, 0.09), Color(1, 1, 1)
    on_status = ink if t.dark else white
    sidebar = t.window_chrome
    secondary = t.window_chrome.with_alpha(t.window_chrome.a * 0.7)
    return {
        "window-bg-color": t.window, "window-fg-color": t.fg,
        "view-bg-color": t.view, "view-fg-color": t.fg,
        # Header bars are part of the window glass, so they add no surface of their own.
        "headerbar-bg-color": clear, "headerbar-fg-color": t.fg,
        "headerbar-backdrop-color": clear, "headerbar-border-color": t.fg,
        "headerbar-shade-color": t.divider, "headerbar-darker-shade-color": t.divider,
        "sidebar-bg-color": sidebar, "sidebar-fg-color": t.fg,
        "sidebar-backdrop-color": sidebar,
        "sidebar-shade-color": t.divider, "sidebar-border-color": t.divider,
        "secondary-sidebar-bg-color": secondary, "secondary-sidebar-fg-color": t.fg,
        "secondary-sidebar-backdrop-color": secondary,
        "secondary-sidebar-shade-color": t.divider, "secondary-sidebar-border-color": t.divider,
        "card-bg-color": t.card, "card-fg-color": t.fg, "card-shade-color": t.divider,
        "dialog-bg-color": dialog_color(t), "dialog-fg-color": t.fg,
        "popover-bg-color": popover_color(t), "popover-fg-color": t.fg,
        "popover-shade-color": t.divider,
        "thumbnail-bg-color": t.view, "thumbnail-fg-color": t.fg,
        "shade-color": t.divider, "scrollbar-outline-color": t.edge,
        "accent-bg-color": t.accent, "accent-fg-color": t.accent_fg, "accent-color": t.accent_text,
        "destructive-bg-color": t.destructive, "destructive-fg-color": white if not t.dark else ink,
        "destructive-color": t.destructive,
        "success-bg-color": t.success, "success-fg-color": on_status, "success-color": t.success,
        "warning-bg-color": t.warning, "warning-fg-color": on_status, "warning-color": t.warning,
        "error-bg-color": t.destructive, "error-fg-color": white if not t.dark else ink,
        "error-color": t.destructive,
    }


def glass_colors(t: Tokens) -> dict[str, Color]:
    """Colours only the glass rules use (as --lg-* properties)."""
    return {
        "lg-rim": t.highlight, "lg-edge": t.edge, "lg-divider": t.divider,
        "lg-shadow": t.shadow, "lg-hover": t.hover, "lg-active": t.active,
        "lg-fg-dim": t.fg_dim, "lg-fg-faint": t.fg_faint,
        "lg-accent": t.accent, "lg-accent-text": t.accent_text,
        "lg-selection": t.selection,
        "lg-chrome": t.window_chrome, "lg-bar": bar_color(t),
        "lg-glass": t.fg.with_alpha(0.10 if t.dark else 0.07),
        "lg-glass-hi": t.fg.with_alpha(0.16 if t.dark else 0.11),
        "lg-sheen-top": Color(1, 1, 1, 0.16 if t.dark else 0.55),
        "lg-sheen-bottom": Color(1, 1, 1, 0.0),
        "lg-tooltip": t.osd.with_alpha(max(t.osd.a, 0.88)),
        "lg-tooltip-fg": Color.hex("#f4f5f9") if t.dark else t.fg,
        "lg-deep-shadow": Color(0, 0, 0, 0.34 if t.dark else 0.22),
    }


def scheme_vars(t: Tokens) -> str:
    """The colour variables of one scheme (inside :root)."""
    extra = {
        "overview-bg-color": t.window.with_alpha(max(t.window.a, 0.8)), "overview-fg-color": t.fg,
        "active-toggle-bg-color": t.fg.with_alpha(0.22 if t.dark else 0.9),
        "active-toggle-fg-color": t.fg,
    }
    rows = {**adwaita_colors(t), **extra, **glass_colors(t)}
    return "\n".join(f"  --{k}: {v.css};" for k, v in rows.items())


def named_colors(t: Tokens) -> str:
    """@define-color aliases for apps written against the named colours."""
    return "\n".join(f"  @define-color {k.replace('-', '_')} {v.css};"
                     for k, v in adwaita_colors(t).items())


def _geometry(t: Tokens) -> dict[str, str]:
    r = t.window_radius
    return {
        "radius": f"{r}px",
        "radius_small": f"{max(4, round(r * 0.6))}px",
        "radius_card": f"{max(6, round(r * 0.75))}px",
        "radius_popover": f"{t.menu_radius}px",
        "radius_menu_item": f"{max(6, round(r * 0.5))}px",
        "radius_window": f"{max(8, r)}px",
        "glass_btn": "button:not(.flat):not(.suggested-action):not(.destructive-action)"
                     ":not(.opaque):not(.osd):not(.close):not(.minimize):not(.maximize):not(.chip):not(.swatch)",
    }


def rules(t: Tokens) -> str:
    return Template(_TEMPLATE.read_text(encoding="utf-8")).substitute(_geometry(t))


def render(dark: Tokens, light: Tokens | None = None) -> str:
    """Full gtk.css. With both schemes the file switches live with GNOME's
    light/dark setting through prefers-color-scheme; with one it is fixed."""
    parts = [HEADER]
    if light is not None:
        for name, t in (("light", light), ("dark", dark)):
            parts.append(f"@media (prefers-color-scheme: {name}) {{\n:root {{\n{scheme_vars(t)}\n}}\n"
                         f"{named_colors(t)}\n}}\n")
    else:
        parts.append(f":root {{\n{scheme_vars(dark)}\n}}\n"
                     f"{named_colors(dark).replace('  ', '')}\n")
    parts.append(rules(dark))
    return "\n".join(parts)
