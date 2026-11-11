"""Unapplied changes in plain words, for "See changes": "Frost: 45 % → 60 %".

Each row names the page the setting is on and the control's objectName there (the same
names searchindex.js uses), so a click on the row goes to it. A setting this table doesn't
know (one added later) still shows, under its own name on the Advanced page, so no change
is ever left out of the list. No Qt in here.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Callable

from .. import settings as settings_mod
from ..settings import GNOME_ACCENTS, MOTION_EVENTS, Settings

PAGE_ORDER = ("home", "colour", "glass", "windows", "motion", "pointer", "lock", "apps", "advanced", "about")


def pct(v: Any) -> str:
    return f"{round(float(v) * 100)} %"


def px(v: Any) -> str:
    return f"{int(v)} px"


def onoff(v: Any) -> str:
    return "On" if v else "Off"


def _auto(fmt: Callable[[Any], str], word: str = "Automatic") -> Callable[[Any], str]:
    return lambda v: word if v is None else fmt(v)


def _choice(labels: dict[str, str]) -> Callable[[Any], str]:
    return lambda v: labels.get(v, str(v).capitalize())


def colour_hex(v: Any) -> str:
    return str(v).upper()


def accent(v: Any, system: str = "") -> str:
    if v == "system":
        return f"System ({system.capitalize()})" if system in GNOME_ACCENTS else "System"
    if v in GNOME_ACCENTS:
        return str(v).capitalize()
    return f"Custom ({str(v).upper()})"


def _quoted(v: Any) -> str:
    text = str(v or "")
    if not text:
        return "None"
    return "“" + (text if len(text) <= 32 else text[:31] + "…") + "”"


def _cursor(v: Any) -> str:
    if v == "keep":
        return "Your own"
    from ..cursors import STYLES
    return next((c.name for c in STYLES if c.id == v), str(v))


_GNOME = "GNOME's own"
# Settings name -> (label, page, objectName of its control, how a value reads).
FIELDS: dict[str, tuple[str, str, str, Callable[[Any], str]]] = {
    "frost": ("Frost", "glass", "glassFrost", pct),
    "scheme": ("Style", "colour", "schemeChoice", _choice({"auto": "Auto", "dark": "Dark", "light": "Light"})),
    "accent": ("Accent", "colour", "accentRow", accent),
    "tint": ("Tint", "colour", "tintButton", colour_hex),
    "tint_strength": ("Tint strength", "colour", "tintStrength", pct),
    "radius": ("Corner roundness", "colour", "cornerRoundness", px),
    "highlight": ("Edge reflections", "home", "presetRow", pct),
    "opacity": ("Transparency", "advanced", "fineOpacity", _auto(pct)),
    "blur": ("Blur", "advanced", "fineBlur", _auto(px)),
    "reduce_transparency": ("Reduce transparency", "advanced", "reduceTransparency", onoff),
    "glass_quality": ("Glass quality", "glass", "speedCard",
                      _choice({"auto": "Auto", "full": "Full", "lighter": "Lighter", "lightest": "Lightest"})),
    "panel_style": ("Panel", "windows", "panelStyle", _choice({"floating": "Floating", "docked": "Docked"})),
    "panel_margin": ("Panel margin", "windows", "panelMargin", px),
    "blur_app_windows": ("Window glass", "glass", "glassAppWindows", onoff),
    "terminal_opacity": ("Terminal opacity", "advanced", "fineTerminalOpacity", _auto(pct)),
    "refraction": ("Bend", "glass", "bend", pct),
    "dispersion": ("Rainbow edge", "glass", "rainbowEdge", pct),
    "vibrancy": ("Colour through glass", "glass", "colourThroughGlass", pct),
    "bleed": ("Colour bleed", "glass", "colourBleed", pct),
    "pointer_light": ("Light follows pointer", "glass", "lightFollowsPointer", pct),
    "liquid_motion": ("Liquid motion", "motion", "liquidMotion", onoff),
    "menu_grow": ("Menus grow from their button", "motion", "menuGrow", onoff),
    "glass_panel": ("Glass on the panel", "glass", "glassPanel", onoff),
    "glass_menus": ("Glass on menus", "glass", "glassMenus", onoff),
    "glass_overview": ("Glass in the overview", "glass", "glassOverview", onoff),
    "glass_see_windows": ("See windows through the glass", "glass", "glassSeeWindows", onoff),
    "start_on_desktop": ("Start on the desktop", "pointer", "startOnDesktop", onoff),
    "overview_off": ("Turn off the overview", "pointer", "overviewOff", onoff),
    "header_height": ("Header bar height", "windows", "headerHeight", px),
    "header_opacity": ("Header bar opacity", "windows", "headerOpacity", _auto(pct, "Same as the window")),
    "terminal_colors": ("Terminal colours", "windows", "terminalColors", onoff),
    "terminal_follows_style": ("Terminal follows light and dark", "windows", "terminalFollowsStyle", onoff),
    "qt_gnome_titlebars": ("Qt apps get the same title bar", "windows", "qtGnomeTitlebars", onoff),
    "motion_dtp_hover_off": ("Dash to Panel's own hover animation off", "motion", "motionDtpNote", onoff),
    "hover_glide": ("Gliding highlight", "motion", "motionGlide", onoff),
    "lock_glass": ("Glass lock screen", "lock", "lockGlass", onoff),
    "lock_blur": ("Lock screen frost", "lock", "lockBlur", px),
    "lock_dim": ("Lock screen darken", "lock", "lockDim", pct),
    "lock_tint": ("Lock screen tint", "lock", "lockTint", pct),
    "lock_card": ("Glass card behind the password", "lock", "lockCard", onoff),
    "lock_clock": ("Lock screen clock", "lock", "lockClock", _choice({"gnome": _GNOME, "bold": "Bold", "thin": "Thin"})),
    "lock_clock_position": ("Clock position", "lock", "lockClockPosition",
                            _choice({"gnome": _GNOME, "top": "Top", "middle": "Middle"})),
    "lock_slide": ("Unlock animation", "lock", "lockSlide", _choice({"gnome": _GNOME, "smooth": "Smooth", "spring": "Spring"})),
    "lock_slide_ms": ("Unlock slide time", "lock", "lockSlideMs", lambda v: f"{int(v)} ms"),
    "lock_bounce": ("Unlock bounce", "lock", "lockBounce", pct),
    "lock_widget_battery": ("Battery on the lock screen", "lock", "lockWidgetBattery", onoff),
    "lock_widget_weather": ("Weather on the lock screen", "lock", "lockWidgetWeather", onoff),
    "lock_weather_place": ("Name the place for weather", "lock", "lockWeatherPlace", onoff),
    "lock_greeting": ("Greeting on the lock screen", "lock", "lockGreeting", onoff),
    "lock_message": ("Message on the lock screen", "lock", "lockMessageChip", _quoted),
    "lock_widget_style": ("Lock screen widget look", "lock", "lockWidgetStyle", _choice({"chips": "Glass", "plain": "Text only"})),
    "lock_hide_notifications": ("Hide notifications on the lock screen", "lock", "lockHideNotifications", onoff),
    "cursor_theme": ("Mouse pointer", "pointer", "cursorCard", _cursor),
    "cursor_size": ("Pointer size", "pointer", "cursorSize", lambda v: "Your own" if not v else px(v)),
    "tint_from_wallpaper": ("Tint matches the wallpaper", "colour", "wallpaperTint", onoff),
    "accent_from_wallpaper": ("Accent matches the wallpaper", "colour", "wallpaperAccent", onoff),
}
# Not shown: saved the moment it is switched, or bookkeeping that follows another setting.
HIDDEN = {"undo_on_remove", "tint_own", "accent_own", "wallpaper_match"}

PART_LABELS = {"panel": "Panel", "arcmenu": "Start menu", "quicksettings": "Quick settings", "calendar": "Calendar",
               "overview": "Overview", "windows": "Windows", "terminal": "Terminal"}
PART_KEY_LABELS = {"tint": ("tint", colour_hex), "tint_strength": ("tint strength", pct), "radius": ("corners", px),
                   "frost": ("frost", pct), "refraction": ("bend", pct), "bleed": ("colour bleed", pct),
                   "reflections": ("edge reflections", pct)}
EVENT_LABELS = {"open": "Open", "minimize": "Minimize and restore", "close": "Close", "launch": "App starting",
                "hover": "Panel hover"}
MOTION_LABELS = {"gnome": "GNOME default", "spring": "Spring", "bounce": "Bounce", "jelly": "Jelly", "genie": "Genie",
                 "scalefade": "Scale and fade", "off": "Off"}
STYLE_LABELS = {"off": "Off", "calm": "Calm", "gnome": "GNOME", "lively": "Lively", "playful": "Playful",
                "custom": "Your own mix"}


def _row(page: str, name: str, label: str, before: str, after: str, key: str) -> dict:
    return {"page": page, "name": name, "label": label, "before": before, "after": after, "key": key}


def _human(field: str) -> str:
    return field.replace("_", " ").capitalize()


def _motion_rows(now: Settings, was: Settings) -> list[dict]:
    a = {ev: now.motion_for(ev) for ev in MOTION_EVENTS}
    b = {ev: was.motion_for(ev) for ev in MOTION_EVENTS}
    if a == b:
        return []
    rows = []
    sa, sb = settings_mod.motion_style_of(a), settings_mod.motion_style_of(b)
    styled = sa != "custom" and sb != "custom" and sa != sb
    if styled:
        rows.append(_row("motion", "motionStyle", "Motion style", STYLE_LABELS[sb], STYLE_LABELS[sa], "motion.style"))
    speeds_a = {round(a[ev]["speed"], 3) for ev in MOTION_EVENTS}
    speeds_b = {round(b[ev]["speed"], 3) for ev in MOTION_EVENTS}
    one_speed = len(speeds_a) == 1 and len(speeds_b) == 1
    if one_speed and speeds_a != speeds_b:
        rows.append(_row("motion", "motionSpeed", "Animation speed", f"{speeds_b.pop():g}×", f"{speeds_a.pop():g}×",
                         "motion.speed"))
    for ev in MOTION_EVENTS:
        x, y = a[ev], b[ev]
        label = EVENT_LABELS[ev]
        if not styled and x["preset"] != y["preset"]:
            rows.append(_row("motion", "eachAnimation", f"{label} animation", MOTION_LABELS.get(y["preset"], y["preset"]),
                             MOTION_LABELS.get(x["preset"], x["preset"]), f"motion.{ev}.preset"))
        if not styled and x["intensity"] != y["intensity"]:
            rows.append(_row("motion", "eachAnimation", f"{label} strength", pct(y["intensity"]), pct(x["intensity"]),
                             f"motion.{ev}.intensity"))
        if not one_speed and x["speed"] != y["speed"]:
            rows.append(_row("motion", "eachAnimation", f"{label} speed", f"{y['speed']:g}×", f"{x['speed']:g}×",
                             f"motion.{ev}.speed"))
    return rows


def _part_rows(now: Settings, was: Settings) -> list[dict]:
    rows = []
    for part in settings_mod.PARTS:
        a, b = now.parts.get(part, {}), was.parts.get(part, {})
        for key in settings_mod.PART_KEYS:
            if a.get(key) == b.get(key):
                continue
            word, fmt = PART_KEY_LABELS.get(key, (key, str))
            same = "Same as everywhere"
            rows.append(_row("advanced", "partRow", f"{PART_LABELS.get(part, part)}: {word}",
                             same if key not in b else fmt(b[key]), same if key not in a else fmt(a[key]),
                             f"parts.{part}.{key}"))
    return rows


def _target_rows(now: Settings, was: Settings, names: dict[str, str]) -> list[dict]:
    rows = []
    for tid in sorted(set(now.targets) | set(was.targets), key=lambda t: names.get(t, t).casefold()):
        on, before = now.target_enabled(tid), was.target_enabled(tid)
        if on != before:
            rows.append(_row("apps", "appsList", names.get(tid, tid), "Themed" if before else "Left alone",
                             "Themed" if on else "Left alone", f"targets.{tid}"))
    return rows


def change_rows(now: Settings, was: Settings, *, has_dash_to_panel: bool = True,
                target_names: dict[str, str] | None = None, system_accent: str = "") -> list[dict]:
    """Every difference between the editor (`now`) and the look applied last (`was`), as
    rows {"page", "name", "label", "before", "after", "key"}, in page order."""
    now, was = now.normalized(), was.normalized()
    rows: list[dict] = []
    for f in fields(Settings):
        k = f.name
        if k in HIDDEN or k in ("motion", "parts", "targets"):
            continue
        a, b = getattr(now, k), getattr(was, k)
        if k == "start_on_desktop":
            a, b = now.start_on_desktop_for(has_dash_to_panel), was.start_on_desktop_for(has_dash_to_panel)
        if a == b:
            continue
        label, page, name, fmt = FIELDS.get(k, (_human(k), "advanced", "", str))
        if k in ("accent", "accent_own"):
            fmt = lambda v: accent(v, system_accent)    # noqa: E731
        try:
            before, after = fmt(b), fmt(a)
        except (TypeError, ValueError):
            before, after = str(b), str(a)
        if before == after and fmt is pct and isinstance(a, float) and isinstance(b, float):
            # 45.2 % and 45.4 % both read 45 %: still say it moved.
            digits = next((n for n in (1, 2, 3) if round(a * 100, n) != round(b * 100, n)), 4)
            before, after = f"{b * 100:.{digits}f} %", f"{a * 100:.{digits}f} %"
        elif before == after:
            before, after = str(b), str(a)
        rows.append(_row(page, name, label, before, after, k))
    rows += _motion_rows(now, was)
    rows += _part_rows(now, was)
    rows += _target_rows(now, was, target_names or {})
    order = {p: i for i, p in enumerate(PAGE_ORDER)}
    return sorted(rows, key=lambda r: order.get(r["page"], len(order)))   # stable: field order inside a page
