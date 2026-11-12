"""Every setting can be changed and changed back.

For each setting: Apply with the defaults (the baseline), Apply with the setting changed,
Apply with the defaults again, and compare the desktop (every dconf key and every file
Fedora Glass writes) with the baseline. Anything that stays behind is a setting the user
can't undo. Run inside the test desktop:

    docker exec -u dino -e LGQA_OUT=/out NAME python3 /opt/lgqa/suite/checks/reversible.py [name ...]
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lgqa  # noqa: E402
from run_checks import RESTORE_IGNORE, dconf_keys, run_lg, same_value, schema_defaults  # noqa: E402

SETTINGS = lgqa.HOME / ".config/liquid-glass/settings.json"
# Files Fedora Glass writes, plus the folders apps read their themes from.
WATCH = [".config/gtk-3.0", ".config/gtk-4.0", ".config/Kvantum", ".config/liquid-glass",
         ".local/share/themes", ".local/share/icons", ".config/environment.d",
         ".local/share/applications", ".config/qt5ct", ".config/qt6ct", ".config/btop",
         ".config/micro", ".config/autostart"]
SKIP_FILES = ("settings.json", "safe-mode.json", "speed", "glass-state", ".bak")
# Kept off the comparison: the app's own record of the last Apply (time stamps) and
# Shell keys that move by themselves while the desktop runs.
NOISE = ("/org/gnome/shell/extensions/liquid-glass/applied-at",)

# Each setting changed to something clearly not its default.
CHANGES: dict[str, dict] = {
    "frost": {"frost": 0.95}, "scheme-light": {"scheme": "light"}, "scheme-dark": {"scheme": "dark"},
    "accent": {"accent": "red"}, "tint": {"tint": "#ff2200"}, "tint_strength": {"tint_strength": 0.6},
    "radius": {"radius": 0}, "radius-max": {"radius": 32}, "highlight": {"highlight": 0.1},
    "opacity": {"opacity": 0.3}, "blur": {"blur": 5}, "reduce_transparency": {"reduce_transparency": True},
    "glass_quality": {"glass_quality": "lightest"}, "panel_style": {"panel_style": "docked"},
    "panel_margin": {"panel_margin": 24}, "blur_app_windows": {"blur_app_windows": False},
    "terminal_opacity": {"terminal_opacity": 0.4}, "refraction": {"refraction": 0.0},
    "dispersion": {"dispersion": 1.0}, "vibrancy": {"vibrancy": 0.1}, "bleed": {"bleed": 0.0},
    "pointer_light": {"pointer_light": 1.0}, "liquid_motion": {"liquid_motion": False},
    "menu_grow": {"menu_grow": False}, "glass_panel": {"glass_panel": False},
    "glass_menus": {"glass_menus": False}, "glass_overview": {"glass_overview": False},
    "glass_see_windows": {"glass_see_windows": False}, "start_on_desktop": {"start_on_desktop": False},
    "overview_off": {"overview_off": True}, "parts-radius": {"parts": {"panel": {"radius": 0}, "windows": {"radius": 0}, "arcmenu": {"radius": 0}}},
    "parts-tint": {"parts": {"calendar": {"tint": "#00ff00", "frost": 1.0}}},
    "header_height": {"header_height": 60}, "header_opacity": {"header_opacity": 0.9},
    "terminal_colors": {"terminal_colors": True}, "terminal_follows_style": {"terminal_follows_style": True},
    "qt_gnome_titlebars": {"qt_gnome_titlebars": True},
    "app_glass": {"app_glass": {"org.gnome.Nautilus": "solid", "org.gnome.Ptyxis": "clearer"}},
    "motion": {"motion": {"open": {"preset": "off"}, "hover": {"preset": "jelly", "speed": 2.0}}},
    "motion_dtp_hover_off": {"motion_dtp_hover_off": True}, "hover_glide": {"hover_glide": False},
    "lock_glass": {"lock_glass": False}, "lock_look": {"lock_blur": 10, "lock_dim": 0.6, "lock_tint": 1.0, "lock_card": False,
                                                      "lock_clock": "thin", "lock_clock_position": "top", "lock_slide": "smooth",
                                                      "lock_slide_ms": 1200, "lock_bounce": 1.0},
    "lock_widgets": {"lock_widget_battery": False, "lock_widget_weather": True, "lock_weather_place": True,
                     "lock_greeting": True, "lock_message": "hi", "lock_widget_style": "plain", "lock_hide_notifications": True},
    "cursor": {"cursor_theme": "fedora-glass-bibata-ice", "cursor_size": 48},
    "target-off-gtk": {"targets": {"gtk4": False, "gtk3": False}},
    "target-off-shell": {"targets": {"shell": False, "dash-to-panel": False, "arcmenu": False}},
}


def write(values: dict) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"glass_quality": "full", **values}))


def snapshot() -> dict[str, str]:
    p = lgqa.subprocess.run(["dconf", "dump", "/"], env=lgqa.ENV, capture_output=True, text=True)
    out = {k: v for k, v in dconf_keys(p.stdout).items() if not RESTORE_IGNORE.search(k) and k not in NOISE}
    for d in WATCH:
        root = lgqa.HOME / d
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if any(s in f.name for s in SKIP_FILES):
                continue
            rel = "~/" + str(f.relative_to(lgqa.HOME))
            if f.is_symlink():
                out[rel] = "-> " + str(f.readlink())
            elif f.is_file():
                out[rel] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    return out


def apply(values: dict) -> str:
    write(values)
    rc, text = run_lg("apply")
    if rc != 0:
        return f"apply exit {rc}: {text[-400:]}"
    time.sleep(0.5)
    return ""


_DEFAULTS: dict[str, str] = {}


def diff(a: dict, b: dict) -> list[str]:
    """What differs. A key set to its default and the same key unset are the same setting."""
    if not _DEFAULTS:
        _DEFAULTS.update(schema_defaults())
    out = []
    for k in sorted(set(a) | set(b)):
        va, vb = a.get(k, _DEFAULTS.get(k)), b.get(k, _DEFAULTS.get(k))
        if not same_value(va, vb):
            out.append(f"{k}: {a.get(k)!r} -> {b.get(k)!r}")
    return out


def main(names: list[str]) -> int:
    names = names or list(CHANGES)
    err = apply({})
    if err:
        print("baseline:", err)
        return 2
    base = snapshot()
    bad = 0
    for name in names:
        changed = CHANGES[name]
        err = apply(changed)
        mid = snapshot()
        mid_note = "" if diff(base, mid) else "  (changed nothing on this desktop)"
        err = err or apply({})
        now = snapshot()
        d = diff(base, now)
        if err or d:
            bad += 1
            print(f"FAIL {name}: {err}")
            for line in d[:20]:
                print("     ", line)
            base = now      # keep going from where the desktop is now
        else:
            print(f"ok   {name}{mid_note}")
    print(f"{len(names) - bad} of {len(names)} settings come back exactly")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
