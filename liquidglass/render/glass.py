"""Config and files for the Liquid Glass GNOME Shell extension.

The extension (data/extension/) draws the glass itself: a live, blurred copy
of what is behind the panel, menus and windows, bent along a refracting rim.
It reads ~/.config/liquid-glass/shell-glass.json, which this module renders
from the tokens, and follows changes to that file live.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..color import Color, lerp
from ..palette import Tokens
from ..radius import scale
from ..settings import MOTION_EVENTS, Settings

UUID = "liquid-glass@djshiye.github.io"
SOURCE = Path(__file__).resolve().parent.parent / "data/extension" / UUID
FILES = ("metadata.json", "extension.js", "glass.js", "config.js", "surfaces.js", "common.js", "follower.js",
         "lock.js", "lock.css", "motion.js", "panels.js", "popups.js", "wallpaper.js", "windows.js", "desktop.js",
         "animations.js", "curves.js", "glide.js", "dtpquiet.js", "prefs.js")

# Apps that paint opaque windows (Electron, games, launchers): glass behind
# them costs GPU time and shows nothing.
WINDOW_SKIP = ("Plank", "Conky", "steam", "Steam", "discord", "Code", "code", "obsidian", "Slack",
               "brave-browser", "brave-origin", "helium", "zoom", "Claude", "firefox", "libreoffice",
               "org.prismlauncher.PrismLauncher")


def extension_files() -> dict[str, str]:
    return {name: (SOURCE / name).read_text(encoding="utf-8") for name in FILES}


def _brightness(t: Tokens, f: float) -> float:
    """The extension darkens (or, in light mode, lifts) the glass behind a thin theme veil,
    so text keeps its contrast without the theme painting an 85% opaque fill."""
    return round(lerp(0.88, 0.92, f) if t.dark else lerp(1.06, 1.0, f), 3)


# Light glass only: how much its milk thickens over a dark backdrop (see glass.js).
# Menus hold the most text; the panel is a thin bar whose icons need less; app
# windows paint most of their own background already.
LIFT = {"panel": 0.6, "arcmenu": 0.72, "quicksettings": 0.72, "calendar": 0.72, "windows": 0.45, "terminal": 0.0}
# Light glass only: the panel's thin dark edge line, drawn in the glass under its
# 30 % veil (about the 11 % black hairline the menus draw in CSS). Menus have theirs.
HAIRLINE = {"panel": 0.14}


def _milk(t: Tokens, name: str) -> dict:
    """Light mode: the glass's own body colour (the part's surface, user tint included)
    and how much it thickens over dark backdrops. Dark glass never does."""
    if t.dark or t.blur_radius == 0:
        return {}
    c = t.parts[name]["popover"]
    out = {"lift": LIFT.get(name, 0.0), "milk": [round(c.r, 4), round(c.g, 4), round(c.b, 4)]}
    if name in HAIRLINE:
        out["hairline"] = HAIRLINE[name]
    return out


# Frost per part: a thin bar shows the lens best with a light blur, menus hold
# text and want more.
CONTACT_SHADOW = {"panel": 0.2, "arcmenu": 0.28, "quicksettings": 0.28, "calendar": 0.28}
FROST_SCALE = {"panel": 0.35, "arcmenu": 1.2, "quicksettings": 1.2, "calendar": 1.2, "overview": 1.0}


def _shadow(t: Tokens, name: str) -> float:
    """Light glass on a light wallpaper has little to set it apart, so the panel's
    contact shadow is a little deeper there."""
    v = CONTACT_SHADOW.get(name, 0.0)
    return round(v * 1.6, 3) if name == "panel" and not t.dark else v


def _part_config(t: Tokens, name: str, veiled: bool) -> dict:
    p = t.parts[name]
    look = {"blur": round(p["blur"] * FROST_SCALE.get(name, 1.0)), "refraction": p["lens_width"], "bend": p["lens_bend"],
            # A thin bar holds its icons close to both edges, so the same glow reads stronger there.
            "bleed": round(p["bleed"] * (0.7 if name == "panel" else 1.0), 3), "highlight": p["glare"],
            # A soft contact shadow, cast away from the light (it follows the pointer light).
            "shadow": _shadow(t, name), **_milk(t, name)}
    if veiled:
        look["brightness"] = _brightness(t, p["frost"])
        # Darkening dulls colour, so glass under a veil is a little more vivid.
        look["saturation"] = round(min(3.0, t.vibrancy * 1.3), 3)
    c = p["tint"]
    return {"look": look, "tint": [c.r, c.g, c.b, 0]}      # the Shell theme paints the fill


def _window_look(t: Tokens, name: str) -> dict:
    """App windows: the menus' lens, a little narrower and thinner, since a window is
    big and holds text near its edge. No colour bleed: content stays as the app draws it."""
    p = t.parts[name]
    return {"blur": max(24, p["blur"]), "refraction": round(p["lens_width"] * 0.85, 1),
            "bend": round(p["lens_bend"] * 0.6, 1), "dispersion": round(t.dispersion * 0.6, 3),
            "depth": 0.1, "highlight": p["glare"], "bleed": 0, "shadow": 0, **_milk(t, name)}


def _lock_config(s: Settings, off: bool) -> dict:
    """The glass lock screen: one frosted sheet over the wallpaper, a glass card behind
    the password, and how the sheet slides up on unlock."""
    c = Color.hex(s.tint)
    return {"enabled": s.lock_glass and not off, "blur": s.lock_blur, "dim": round(1 - s.lock_dim, 3),
            "tint": [round(c.r, 4), round(c.g, 4), round(c.b, 4), round(s.lock_tint * 0.4, 3)],
            "card": s.lock_card, "clockStyle": s.lock_clock, "clockPosition": s.lock_clock_position,
            "slide": s.lock_slide, "slideMs": s.lock_slide_ms, "bounce": s.lock_bounce}


def config(s: Settings, t: Tokens) -> dict:
    s = s.normalized()
    off = s.reduce_transparency
    blur = t.blur_radius
    behind = "windows" if s.glass_see_windows else "wallpaper"
    look = {
        "blur": blur,
        "refraction": t.lens_width,
        "bend": t.lens_bend,
        "depth": 0.35,
        "dispersion": t.dispersion,
        "saturation": t.vibrancy,
        "brightness": 1.0,
        "bleed": t.bleed,              # how much content colours light up the glass
        "pointerLight": 0.0 if off else s.pointer_light,   # the light turns towards the pointer
        "motion": 1 if s.liquid_motion and not off else 0, # press and open springs
        "tint": [0, 0, 0, 0],          # the Shell theme paints the tint
        "highlight": t.glare,
        "lightAngle": -125,            # from the top left, as in the preview
        "falloff": 2.0,
        "shadow": 0,
    }
    # Per part of the Shell: the same keys, with that part's own tint, frost, bend and so on.
    veiled = {"panel": t.glass_panel_edges, "arcmenu": t.glass_menu_edges,
              "quicksettings": t.glass_menu_edges, "calendar": t.glass_menu_edges, "overview": False}
    parts = {name: _part_config(t, name, ok) for name, ok in veiled.items()}
    menus_look = _part_config(t, "quicksettings", t.glass_menu_edges)["look"]
    panel_look = _part_config(t, "panel", t.glass_panel_edges)["look"]
    return {
        "version": 1,
        "look": look,
        "panel": {"enabled": s.glass_panel and not off, "behind": behind, "look": panel_look},
        "menus": {"enabled": s.glass_menus and not off, "behind": behind,
                  "look": {"blur": menus_look["blur"], "bleed": menus_look["bleed"],
                           **{k: menus_look[k] for k in ("lift", "milk") if k in menus_look},
                           **({"brightness": menus_look["brightness"]} if "brightness" in menus_look else {})}},
        # Behind app windows: a lens along the edge and a rim that mirrors the real
        # surroundings, under the window's own background. Terminals have their own look.
        "windows": {"enabled": t.blur_app_windows, "behind": behind, "radius": scale(t.window_radius)["l"],   # the same as the GTK window corners
                    "skip": list(WINDOW_SKIP), "look": _window_look(t, "windows"),
                    "terminalLook": _window_look(t, "terminal")},
        "overview": {"enabled": s.glass_overview and not off, "blur": max(30, t.parts["overview"]["blur"]),
                     "brightness": 0.62 if t.dark else 0.85},
        "parts": parts,
        "lock": _lock_config(s, off),
        # Whether GNOME opens on the desktop or in Activities, and whether Activities opens at all.
        "desktop": {"startOnDesktop": s.start_on_desktop or s.overview_off, "overviewOff": s.overview_off},
        # How windows open, minimize and close, and how the panel responds (see curves.js).
        "animations": {ev: s.motion_for(ev) for ev in MOTION_EVENTS},
        # One hover highlight that glides along the Dash to Panel taskbar (glide.js).
        "glide": {"enabled": s.hover_glide, "color": t.hover.css, "radius": scale(t.panel_radius)["xs"]},
    }


def render_config(s: Settings, t: Tokens) -> str:
    return json.dumps(config(s, t), indent=2) + "\n"
