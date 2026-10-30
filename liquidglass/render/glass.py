"""Config and files for the Liquid Glass GNOME Shell extension.

The extension (data/extension/) draws the glass itself: a live, blurred copy
of what is behind the panel, menus and windows, bent along a refracting rim.
It reads ~/.config/liquid-glass/shell-glass.json, which this module renders
from the tokens, and follows changes to that file live.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..palette import Tokens
from ..settings import Settings

UUID = "liquid-glass@djshiye.github.io"
SOURCE = Path(__file__).resolve().parent.parent / "data/extension" / UUID
FILES = ("metadata.json", "extension.js", "glass.js", "config.js", "surfaces.js", "prefs.js")

# Apps that paint opaque windows (Electron, games, launchers): glass behind
# them costs GPU time and shows nothing.
WINDOW_SKIP = ("Plank", "Conky", "steam", "Steam", "discord", "Code", "code", "obsidian", "Slack",
               "brave-browser", "brave-origin", "helium", "zoom", "Claude", "firefox", "libreoffice",
               "org.prismlauncher.PrismLauncher")


def extension_files() -> dict[str, str]:
    return {name: (SOURCE / name).read_text(encoding="utf-8") for name in FILES}


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
        "tint": [0, 0, 0, 0],          # the Shell theme paints the tint
        "highlight": t.glare,
        "lightAngle": -125,            # from the top left, as in the preview
        "falloff": 2.0,
        "shadow": 0,
    }
    return {
        "version": 1,
        "look": look,
        # A thin bar shows the lens best with a lighter blur.
        "panel": {"enabled": s.glass_panel and not off, "behind": behind,
                  "look": {"blur": round(blur * 0.6)}},
        "menus": {"enabled": s.glass_menus and not off, "behind": behind},
        # Windows paint their own rim; behind them the glass is plain frost.
        "windows": {"enabled": t.blur_app_windows, "radius": max(8, t.radius), "skip": list(WINDOW_SKIP),
                    "look": {"blur": max(24, blur), "refraction": 0, "bend": 0, "highlight": 0}},
        "overview": {"enabled": s.glass_overview and not off, "blur": max(30, blur),
                     "brightness": 0.62 if t.dark else 0.85},
    }


def render_config(s: Settings, t: Tokens) -> str:
    return json.dumps(config(s, t), indent=2) + "\n"
