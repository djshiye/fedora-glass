"""Config and files for the Fedora Glass GNOME Shell extension.

The extension (data/extension/) draws the glass itself: a live, blurred copy
of what is behind the panel, menus and windows, bent along a refracting rim.
It reads ~/.config/liquid-glass/shell-glass.json, which this module renders
from the tokens, and follows changes to that file live.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..color import Color, lerp
from ..palette import Tokens
from ..radius import scale
from ..settings import MOTION_EVENTS, Settings
from . import shell

UUID = "liquid-glass@djshiye.github.io"
SOURCE = Path(__file__).resolve().parent.parent / "data/extension" / UUID
FILES = ("metadata.json", "extension.js", "glass.js", "config.js", "surfaces.js", "common.js", "follower.js",
         "lock.js", "lock.css", "lockwidgets.js", "motion.js", "panels.js", "popups.js", "wallpaper.js", "windows.js", "desktop.js",
         "animations.js", "curves.js", "glide.js", "grabhover.js", "dtpquiet.js", "hold.js", "holdstate.js", "glsl.js", "arcrescue.js", "themetidy.js", "safety.js",
         "speed.js", "tuning.js", "popupstyle.js", "stackclip.js", "prefs.js", "power.js",
         "quicktoggle.js", "glass-symbolic.svg")

# Apps that paint opaque windows (Electron, games, launchers): glass behind
# them costs GPU time and shows nothing.
WINDOW_SKIP = ("Plank", "Conky", "steam", "Steam", "discord", "Code", "code", "obsidian", "Slack",
               "brave-browser", "brave-origin", "helium", "zoom", "Claude", "firefox", "libreoffice",
               "org.prismlauncher.PrismLauncher")
# The games and video players windows.js never gives glass (its NO_GLASS, the same pattern),
# so the app can show them as always without glass.
WINDOW_NO_GLASS = re.compile(
    r"^(steam_app_\d+|steam_proton|gamescope|mpv|vlc|celluloid|io\.github\.celluloid_player\.celluloid|totem|"
    r"org\.gnome\.totem|org\.gnome\.showtime|com\.github\.rafostar\.clapper|io\.mpv\.mpv|org\.videolan\.vlc|"
    r"retroarch|org\.libretro\.retroarch)$", re.IGNORECASE)


def always_without_glass(app_id: str) -> bool:
    """Whether the extension keeps glass off this app's windows whatever the user picks."""
    return app_id in WINDOW_SKIP or bool(WINDOW_NO_GLASS.match(app_id))


# config.js keeps at most this many skip ids (built-in and the user's together).
SKIP_MAX = 200


def window_skip(s: Settings) -> list[str]:
    """The apps whose windows get no glass: the built-in ones first, so the user's own can
    never push them out of the extension's limit, then the user's, each once."""
    return list(dict.fromkeys([*WINDOW_SKIP, *s.no_glass_apps]))[:SKIP_MAX]


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
    lift = LIFT.get(name, 0.0)
    if lift > 0 and shell.clarity(t.parts[name]["blur"]) > 0:
        lift = 1.0     # clear light glass shows the backdrop sharp: its milk thickens fully over dark parts
    out = {"lift": lift, "milk": [round(c.r, 4), round(c.g, 4), round(c.b, 4)]}
    if name in HAIRLINE:
        out["hairline"] = HAIRLINE[name]
    return out


# Frost per part: a thin bar shows the lens best with a light blur, menus hold
# text and want more.
# Grey smoke in dark glass (Glisse's dark glass is 40 grey at 62 %, ours adds the
# theme's light veil on top), so over a black wallpaper the glass reads as a pane.
DARK_HAZE = 0.45
CONTACT_SHADOW = {"panel": 0.2, "arcmenu": 0.28, "quicksettings": 0.28, "calendar": 0.28}
FROST_SCALE = {"panel": 0.35, "arcmenu": 1.2, "quicksettings": 1.2, "calendar": 1.2, "overview": 1.0}


def _shadow(t: Tokens, name: str) -> float:
    """Light glass on a light wallpaper has little to set it apart, so the panel's
    contact shadow is a little deeper there."""
    v = CONTACT_SHADOW.get(name, 0.0)
    return round(v * 1.6, 3) if name == "panel" and not t.dark else v


def _rim(t: Tokens, glare: float) -> float:
    """Strength of the thin bright line along the glass's edge: full on liquid glass,
    quieter as the glass frosts (glare already falls with frost)."""
    return round(min(1.0, 0.45 + 1.1 * glare), 3)


def _veil(t: Tokens, name: str) -> list[float] | None:
    """The theme's veil over a part's glass, straight rgba, so the extension can draw
    the edge line bright enough to read through it. None where the theme paints no veil."""
    surf = shell.surfaces(t, name)
    c = surf["chrome"] if name == "panel" else surf["popover"]
    return [round(c.r, 4), round(c.g, 4), round(c.b, 4), round(c.a, 3)]


# Dark text on light glass keeps at least this contrast (WCAG AA 4.5:1, with room).
LIGHT_TEXT_CONTRAST = 5.0


def light_floor(t: Tokens, veil: list[float]) -> float:
    """Light glass: the darkest its glass may get (linear Y) so dark text on it, under
    the theme's veil, keeps LIGHT_TEXT_CONTRAST. Over a vivid purple wallpaper the
    clear light panel showed its clock at 3.3:1. The veil and the glass blend in
    display values (gamma 2.2), so the sum is done there."""
    g = 1 / 2.2
    need = LIGHT_TEXT_CONTRAST * (t.fg.luminance() + 0.05) - 0.05     # Y behind the text
    vr, vg_, vb, a = veil
    v_veil = (0.2126 * vr ** 2.2 + 0.7152 * vg_ ** 2.2 + 0.0722 * vb ** 2.2) ** g
    if a >= 1:
        return 0.0
    v_glass = (need ** g - a * v_veil) / (1 - a)
    return round(min(0.9, max(0.0, v_glass) ** 2.2), 3)


def _part_config(t: Tokens, name: str, veiled: bool) -> dict:
    p = t.parts[name]
    look = {"blur": round(p["blur"] * FROST_SCALE.get(name, 1.0)), "refraction": p["lens_width"], "bend": p["lens_bend"],
            # A thin bar holds its icons close to both edges, so the same glow reads stronger there.
            "bleed": round(p["bleed"] * (0.7 if name == "panel" else 1.0), 3), "highlight": p["glare"],
            # A soft contact shadow, cast away from the light (it follows the pointer light).
            "shadow": _shadow(t, name), "rim": _rim(t, p["glare"]), **_milk(t, name)}
    if veiled and name != "overview":
        look["veil"] = _veil(t, name)
        # Clear glass has almost no veil: bright text gets a soft shade right behind it.
        look["textShade"] = round(0.3 * shell.clarity(p["blur"]), 3)
        # Clear dark glass keeps white text at 4.5:1 or better over any backdrop: over
        # bright things it darkens itself, in their own colour, up to this ceiling.
        if t.dark:
            look["ceiling"] = CLEAR_CEILING if shell.clarity(p["blur"]) > 0 else VEILED_CEILING
            # Smoked glass: a grey of its own, so over a black wallpaper it still
            # reads as a pane, with what is behind showing through it.
            look["haze"] = DARK_HAZE
        elif "milk" in look:
            # Light glass keeps dark text at 5:1 or better over any backdrop: over
            # dark or vivid things it lightens itself towards its milk, up to this floor.
            look["floor"] = light_floor(t, look["veil"])
    if veiled:
        # Dark glass is smoked instead of darkened (DARK_HAZE); the ceiling keeps
        # white text readable over bright backdrops.
        look["brightness"] = 1.0 if t.dark else _brightness(t, p["frost"])
        # Darkening dulls colour, so glass under a veil is a little more vivid.
        look["saturation"] = round(min(3.0, t.vibrancy * 1.3), 3)
    c = p["tint"]
    return {"look": look, "tint": [c.r, c.g, c.b, 0]}      # the Shell theme paints the fill


# Dark glass behind app windows: the brightest it may get (linear Y). Under a bright
# backdrop (a white or rainbow wallpaper) the glass darkens itself there, and only
# there, so header and window text keeps 4.5:1 or better. Dark backdrops pass unchanged.
# Measured on Orchis-Dark GTK 3 apps: 0.28 gives 4.8:1 or more on a white wallpaper.
WINDOW_CEILING = 0.28
# Clear dark glass on the panel and menus: almost no veil, so the glass itself must
# stay dark enough for white text (1.05 / (0.15 + 0.05) is 5.2:1 before the veil).
CLEAR_CEILING = 0.15
# The other dark presets keep a thin veil (about 30 %), which already darkens a little,
# so their glass may stay brighter: 0.22 still gives white text about 5:1 over a white
# wallpaper (it was 2.2:1). Dark backdrops are not touched.
VEILED_CEILING = 0.22


def _window_look(t: Tokens, name: str) -> dict:
    """App windows: the menus' lens, a little narrower and thinner, since a window is
    big and holds text near its edge. No colour bleed: content stays as the app draws it."""
    p = t.parts[name]
    look = {"blur": max(24, p["blur"]), "refraction": round(p["lens_width"] * 0.85, 1),
            "bend": round(p["lens_bend"] * 0.6, 1), "dispersion": round(t.dispersion * 0.6, 3),
            "depth": 0.1, "highlight": p["glare"], "bleed": 0, "shadow": 0, **_milk(t, name)}
    if t.dark and t.blur_radius > 0:
        look["ceiling"] = WINDOW_CEILING
    return look


def _lock_config(s: Settings, off: bool) -> dict:
    """The glass lock screen: one frosted sheet over the wallpaper, a glass card behind
    the password, and how the sheet slides up on unlock."""
    c = Color.hex(s.tint)
    return {"enabled": s.lock_glass and not off, "blur": s.lock_blur, "dim": round(1 - s.lock_dim, 3),
            "tint": [round(c.r, 4), round(c.g, 4), round(c.b, 4), round(s.lock_tint * 0.4, 3)],
            "card": s.lock_card, "clockStyle": s.lock_clock, "clockPosition": s.lock_clock_position,
            "slide": s.lock_slide, "slideMs": s.lock_slide_ms, "bounce": s.lock_bounce,
            # The widgets show with or without the glass, and with Reduce transparency too.
            "widgets": {"battery": s.lock_widget_battery, "weather": s.lock_widget_weather,
                        "weatherPlace": s.lock_weather_place, "greeting": s.lock_greeting,
                        "message": s.lock_message, "style": s.lock_widget_style,
                        "hideNotifications": s.lock_hide_notifications}}


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
                           **{k: menus_look[k] for k in ("lift", "milk", "veil", "textShade", "rim", "ceiling", "floor", "haze") if k in menus_look},
                           **({"brightness": menus_look["brightness"]} if "brightness" in menus_look else {})}},
        # Behind app windows: a lens along the edge and a rim that mirrors the real
        # surroundings, under the window's own background. Terminals have their own look.
        "windows": {"enabled": t.blur_app_windows, "behind": behind, "radius": scale(t.window_radius)["l"],   # the same as the GTK window corners
                    "skip": window_skip(s), "look": _window_look(t, "windows"),
                    "terminalLook": _window_look(t, "terminal")},
        "overview": {"enabled": s.glass_overview and not off, "blur": max(30, t.parts["overview"]["blur"]),
                     "brightness": 0.62 if t.dark else 0.85},
        "parts": parts,
        "lock": _lock_config(s, off),
        "grow": {"enabled": s.menu_grow},
        "speed": {"quality": s.glass_quality, "lighterOnBattery": s.lighter_on_battery},
        # The "Glass" tile in Quick Settings that pauses the glass until the next login.
        "quickToggle": {"enabled": s.quick_toggle},
        # Whether GNOME opens on the desktop or in Activities, and whether Activities opens at all.
        "desktop": {"startOnDesktop": bool(s.start_on_desktop) or s.overview_off, "overviewOff": s.overview_off},
        # How windows open, minimize and close, and how the panel responds (see curves.js).
        "animations": {ev: s.motion_for(ev) for ev in MOTION_EVENTS},
        # One hover highlight that glides along the Dash to Panel taskbar (glide.js).
        "glide": {"enabled": s.hover_glide, "color": t.hover.css, "radius": scale(t.panel_radius)["xs"]},
        # The theme's pop-up rules (OSD, Alt+Tab) again, loaded by the extension as its own
        # stylesheet so they win over other extensions' sheets (popupstyle.js).
        "popupCss": shell.render_extension_css(t),
    }


def render_config(s: Settings, t: Tokens) -> str:
    # The marker key first: the app's live preview rewrites this file while a slider
    # moves, and Apply's backup must still see it as ours (engine._has_header).
    return json.dumps({"generator": "Fedora Glass", **config(s, t)}, indent=2) + "\n"
