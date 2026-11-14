"""Unapplied changes in plain words, for "See changes": "Frost: 45% → 60%".

Each row names the page the setting is on and the control's objectName there (the same
names searchindex.js uses), so a click on the row goes to it. A setting this table doesn't
know (one added later) still shows, under its own name on the Advanced page, so no change
is ever left out of the list. No Qt in here.
"""

from __future__ import annotations

from dataclasses import fields
from typing import Any, Callable

from .. import settings as settings_mod
from ..i18n import _, N_, gettext as tr, pgettext
from ..settings import GNOME_ACCENTS, MOTION_EVENTS, Settings

PAGE_ORDER = ("home", "colour", "glass", "windows", "motion", "pointer", "lock", "apps", "advanced", "about")


def pct(v: Any) -> str:
    return f"{round(float(v) * 100)}%"


def px(v: Any) -> str:
    return f"{int(v)} px"


def onoff(v: Any) -> str:
    return _("On") if v else _("Off")


def _auto(fmt: Callable[[Any], str], word: str = N_("Automatic")) -> Callable[[Any], str]:
    return lambda v: tr(word) if v is None else fmt(v)


def _choice(labels: dict[str, str]) -> Callable[[Any], str]:
    return lambda v: tr(labels[v]) if v in labels else str(v).capitalize()


def colour_hex(v: Any) -> str:
    return str(v).upper()


_ACCENT_NAMES = {"blue": N_("Blue"), "teal": N_("Teal"), "green": N_("Green"), "yellow": N_("Yellow"),
                 "orange": N_("Orange"), "red": N_("Red"), "pink": N_("Pink"), "purple": N_("Purple"),
                 "slate": N_("Slate")}


def _accent_name(v: Any) -> str:
    return tr(_ACCENT_NAMES[v]) if v in _ACCENT_NAMES else str(v).capitalize()


def accent(v: Any, system: str = "") -> str:
    if v == "system":
        return _("System ({name})").format(name=_accent_name(system)) if system in GNOME_ACCENTS else _("System")
    if v in GNOME_ACCENTS:
        return _accent_name(v)
    return _("Custom ({hex})").format(hex=str(v).upper())


def _quoted(v: Any) -> str:
    text = str(v or "")
    if not text:
        return _("None")
    return "“" + (text if len(text) <= 32 else text[:31] + "…") + "”"


def _cursor(v: Any) -> str:
    if v == "keep":
        return _("Your own")
    from ..cursors import STYLES
    return next((tr(c.name) for c in STYLES if c.id == v), str(v))


_GNOME = N_("GNOME's own")
# Settings name -> (label, page, objectName of its control, how a value reads).
FIELDS: dict[str, tuple[str, str, str, Callable[[Any], str]]] = {
    "frost": (N_("Frost"), "glass", "glassFrost", pct),
    "scheme": (N_("Style"), "colour", "schemeChoice", _choice({"auto": N_("Auto"), "dark": N_("Dark"), "light": N_("Light")})),
    "accent": (N_("Accent"), "colour", "accentRow", accent),
    "tint": (N_("Tint"), "colour", "tintButton", colour_hex),
    "tint_strength": (N_("Tint strength"), "colour", "tintStrength", pct),
    "radius": (N_("Corner roundness"), "colour", "cornerRoundness", px),
    "highlight": (N_("Edge reflections"), "glass", "edgeReflections", pct),
    "opacity": (N_("Transparency"), "advanced", "fineOpacity", _auto(pct)),
    "blur": (N_("Blur"), "advanced", "fineBlur", _auto(px)),
    "reduce_transparency": (N_("Reduce transparency"), "advanced", "reduceTransparency", onoff),
    "glass_quality": (N_("Glass quality"), "glass", "speedCard",
                      _choice({"auto": N_("Auto"), "full": N_("Full"), "lighter": N_("Lighter"), "lightest": N_("Lightest")})),
    "panel_style": (N_("Panel"), "windows", "panelStyle", _choice({"floating": N_("Floating"), "docked": N_("Docked")})),
    "panel_margin": (N_("Panel margin"), "windows", "panelMargin", px),
    "blur_app_windows": (N_("Window glass"), "glass", "glassAppWindows", onoff),
    "terminal_opacity": (N_("Terminal opacity"), "advanced", "fineTerminalOpacity", _auto(pct)),
    "refraction": (N_("Bend"), "glass", "bend", pct),
    "dispersion": (N_("Rainbow edge"), "glass", "rainbowEdge", pct),
    "vibrancy": (N_("Colour through glass"), "glass", "colourThroughGlass", pct),
    "bleed": (N_("Colour bleed"), "glass", "colourBleed", pct),
    "pointer_light": (N_("Light follows pointer"), "glass", "lightFollowsPointer", pct),
    "liquid_motion": (N_("Liquid motion"), "motion", "liquidMotion", onoff),
    "liquid_strength": (N_("How liquid"), "motion", "liquidStrength", pct),
    "menu_grow": (N_("Menus grow from their button"), "motion", "menuGrow", onoff),
    "glass_panel": (N_("Glass on the panel"), "glass", "glassPanel", onoff),
    "glass_menus": (N_("Glass on menus"), "glass", "glassMenus", onoff),
    "glass_overview": (N_("Glass in the overview"), "glass", "glassOverview", onoff),
    "glass_see_windows": (N_("See windows through the glass"), "glass", "glassSeeWindows", onoff),
    "start_on_desktop": (N_("Start on the desktop"), "pointer", "startOnDesktop", onoff),
    "overview_off": (N_("Turn off the overview"), "pointer", "overviewOff", onoff),
    "header_height": (N_("Header bar height"), "windows", "headerHeight", px),
    "header_opacity": (N_("Header bar opacity"), "windows", "headerOpacity", _auto(pct, N_("Same as the window"))),
    "terminal_colors": (N_("Terminal colours"), "windows", "terminalColors", onoff),
    "terminal_follows_style": (N_("Terminal follows light and dark"), "windows", "terminalFollowsStyle", onoff),
    "qt_gnome_titlebars": (N_("Qt apps get the same title bar"), "windows", "qtGnomeTitlebars", onoff),
    "motion_dtp_hover_off": (N_("Dash to Panel's own hover animation off"), "motion", "motionDtpNote", onoff),
    "hover_glide": (N_("Gliding highlight"), "motion", "motionGlide", onoff),
    "lock_glass": (N_("Glass lock screen"), "lock", "lockGlass", onoff),
    "lock_blur": (N_("Lock screen frost"), "lock", "lockBlur", px),
    "lock_dim": (N_("Lock screen darken"), "lock", "lockDim", pct),
    "lock_tint": (N_("Lock screen tint"), "lock", "lockTint", pct),
    "lock_card": (N_("Glass card behind the password"), "lock", "lockCard", onoff),
    "lock_clock": (N_("Lock screen clock"), "lock", "lockClock", _choice({"gnome": _GNOME, "bold": N_("Bold"), "thin": N_("Thin")})),
    "lock_clock_position": (N_("Clock position"), "lock", "lockClockPosition",
                            _choice({"gnome": _GNOME, "top": N_("Top"), "middle": N_("Middle")})),
    "lock_slide": (N_("Unlock animation"), "lock", "lockSlide", _choice({"gnome": _GNOME, "smooth": N_("Smooth"), "spring": N_("Spring")})),
    "lock_slide_ms": (N_("Unlock slide time"), "lock", "lockSlideMs", lambda v: f"{int(v)} ms"),
    "lock_bounce": (N_("Unlock bounce"), "lock", "lockBounce", pct),
    "lock_widget_battery": (N_("Battery on the lock screen"), "lock", "lockWidgetBattery", onoff),
    "lock_widget_weather": (N_("Weather on the lock screen"), "lock", "lockWidgetWeather", onoff),
    "lock_weather_place": (N_("Name the place for weather"), "lock", "lockWeatherPlace", onoff),
    "lock_greeting": (N_("Greeting on the lock screen"), "lock", "lockGreeting", onoff),
    "lock_message": (N_("Message on the lock screen"), "lock", "lockMessageChip", _quoted),
    "lock_widget_style": (N_("Lock screen widget look"), "lock", "lockWidgetStyle", _choice({"chips": N_("Glass"), "plain": N_("Text only")})),
    "lock_hide_notifications": (N_("Hide notifications on the lock screen"), "lock", "lockHideNotifications", onoff),
    "login_match_lock": (N_("Login screen matches my lock screen"), "lock", "loginMatchLock", onoff),
    "login_blur": (N_("Login screen frost"), "lock", "loginBlur", px),
    "login_dim": (N_("Login screen darken"), "lock", "loginDim", pct),
    "login_tint": (N_("Login screen tint"), "lock", "loginTint", pct),
    "login_card": (N_("Glass card on the login screen"), "lock", "loginCardSwitch", onoff),
    "login_clock": (N_("Login screen clock"), "lock", "loginClock",
                    _choice({"gnome": N_("GNOME's small clock"), "bold": N_("Bold"), "thin": N_("Thin")})),
    "login_picture": (N_("Login screen picture"), "lock", "loginPicture",
                      _choice({"wallpaper": N_("My wallpaper"), "system": N_("System picture"), "glow": N_("Glow")})),
    "login_battery": (N_("Battery on the login screen"), "lock", "loginBattery", onoff),
    "login_message": (N_("Message on the login screen"), "lock", "loginMessage", _quoted),
    "cursor_theme": (N_("Mouse pointer"), "pointer", "cursorCard", _cursor),
    "cursor_size": (N_("Pointer size"), "pointer", "cursorSize", lambda v: _("Your own") if not v else px(v)),
    "tint_from_wallpaper": (N_("Tint matches the wallpaper"), "colour", "wallpaperTint", onoff),
    "accent_from_wallpaper": (N_("Accent matches the wallpaper"), "colour", "wallpaperAccent", onoff),
    # Shell features
    "lighter_on_battery": (N_("Lighter glass on battery"), "glass", "lighterOnBattery", onoff),
    "quick_toggle": (N_("Glass switch in Quick Settings"), "glass", "quickToggle", onoff),
    "no_glass_apps": (N_("Apps without glass"), "windows", "noGlassCard",
                      lambda v: _("None") if not v else (_("1 app") if len(v) == 1 else _("{n} apps").format(n=len(v)))),
    "app_glass": (N_("Glass strength for apps"), "windows", "noGlassCard", lambda v: _app_glass(v)),
    # Weather frost
    "weather_frost": (N_("Weather frost"), "glass", "weatherFrostSwitch", onoff),
    "weather_feels_like": (N_("Weather frost goes by"), "glass", "weatherFeelsLike",
                           lambda v: _("Feels like") if v else _("Air temperature")),
    "weather_cool": (N_("Cool below"), "glass", "weatherCool", lambda v: f"{int(v)} °C"),
    "weather_cold": (N_("Cold below"), "glass", "weatherCold", lambda v: f"{int(v)} °C"),
    "weather_freezing": (N_("Icy below"), "glass", "weatherFreezing", lambda v: f"{int(v)} °C"),
    "weather_amount": (N_("How much frost"), "glass", "weatherAmount", pct),
}
# Not shown: saved the moment it is switched, or bookkeeping that follows another setting.
HIDDEN = {"undo_on_remove", "look_for_light", "look_for_dark", "tint_own", "accent_own", "wallpaper_match"}

PART_LABELS = {"panel": N_("Panel"), "arcmenu": N_("Start menu"), "quicksettings": N_("Quick settings"), "calendar": N_("Calendar"),
               "overview": N_("Overview"), "windows": N_("Windows"), "terminal": N_("Terminal")}
PART_KEY_LABELS = {"tint": (N_("tint"), colour_hex), "tint_strength": (N_("tint strength"), pct), "radius": (N_("corners"), px),
                   "frost": (N_("frost"), pct), "refraction": (N_("bend"), pct), "bleed": (N_("colour bleed"), pct),
                   "reflections": (N_("edge reflections"), pct)}
# "Open" the verb is the extension's button; this one is the noun, so it has a context.
EVENT_LABELS = {"minimize": N_("Minimize and restore"), "close": N_("Close"), "launch": N_("App starting"),
                "hover": N_("Panel hover")}
MOTION_LABELS = {"gnome": N_("GNOME default"), "spring": N_("Spring"), "bounce": N_("Bounce"), "jelly": N_("Jelly"), "genie": N_("Genie"),
                 "scalefade": N_("Scale and fade"), "off": N_("Off")}
STYLE_LABELS = {"off": N_("Off"), "calm": N_("Calm"), "gnome": N_("GNOME"), "lively": N_("Lively"), "playful": N_("Playful"),
                "custom": N_("Your own mix")}


APP_GLASS_LABELS = {"solid": N_("More solid"), "clearer": N_("Clearer")}


def _app_glass(v: Any) -> str:
    """Per-app glass strength in words: "More solid: gimp, Code; Clearer: kitty"."""
    if not v:
        return _("None")
    out = []
    for look, word in APP_GLASS_LABELS.items():
        ids = [i for i, x in v.items() if x == look]
        if ids:
            out.append(_("{look}: {apps}").format(look=tr(word), apps=", ".join(ids[:3]) + (" …" if len(ids) > 3 else "")))
    return "; ".join(out)


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
        rows.append(_row("motion", "motionStyle", _("Motion style"), tr(STYLE_LABELS[sb]), tr(STYLE_LABELS[sa]), "motion.style"))
    speeds_a = {round(a[ev]["speed"], 3) for ev in MOTION_EVENTS}
    speeds_b = {round(b[ev]["speed"], 3) for ev in MOTION_EVENTS}
    one_speed = len(speeds_a) == 1 and len(speeds_b) == 1
    if one_speed and speeds_a != speeds_b:
        rows.append(_row("motion", "motionSpeed", _("Animation speed"), f"{speeds_b.pop():g}×", f"{speeds_a.pop():g}×",
                         "motion.speed"))
    for ev in MOTION_EVENTS:
        x, y = a[ev], b[ev]
        label = pgettext("motion event", "Open") if ev == "open" else tr(EVENT_LABELS[ev])
        if not styled and x["preset"] != y["preset"]:
            rows.append(_row("motion", "eachAnimation", _("{event} animation").format(event=label), _motion_name(y["preset"]),
                             _motion_name(x["preset"]), f"motion.{ev}.preset"))
        if not styled and x["intensity"] != y["intensity"]:
            rows.append(_row("motion", "eachAnimation", _("{event} strength").format(event=label), pct(y["intensity"]), pct(x["intensity"]),
                             f"motion.{ev}.intensity"))
        if not one_speed and x["speed"] != y["speed"]:
            rows.append(_row("motion", "eachAnimation", _("{event} speed").format(event=label), f"{y['speed']:g}×", f"{x['speed']:g}×",
                             f"motion.{ev}.speed"))
    return rows


def _motion_name(preset: str) -> str:
    return tr(MOTION_LABELS[preset]) if preset in MOTION_LABELS else preset


def _part_rows(now: Settings, was: Settings) -> list[dict]:
    rows = []
    for part in settings_mod.PARTS:
        a, b = now.parts.get(part, {}), was.parts.get(part, {})
        for key in settings_mod.PART_KEYS:
            if a.get(key) == b.get(key):
                continue
            word, fmt = PART_KEY_LABELS.get(key, (key, str))
            same = _("Same as everywhere")
            rows.append(_row("advanced", "partRow", _("{part}: {setting}").format(part=tr(PART_LABELS[part]) if part in PART_LABELS else part, setting=tr(word)),
                             same if key not in b else fmt(b[key]), same if key not in a else fmt(a[key]),
                             f"parts.{part}.{key}"))
    return rows


def _target_rows(now: Settings, was: Settings, names: dict[str, str]) -> list[dict]:
    rows = []
    for tid in sorted(set(now.targets) | set(was.targets), key=lambda t: names.get(t, t).casefold()):
        on, before = now.target_enabled(tid), was.target_enabled(tid)
        if on != before:
            rows.append(_row("apps", "appsList", names.get(tid, tid), _("Themed") if before else _("Left alone"),
                             _("Themed") if on else _("Left alone"), f"targets.{tid}"))
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
            # 45.2% and 45.4% both read 45%: still say it moved.
            digits = next((n for n in (1, 2, 3) if round(a * 100, n) != round(b * 100, n)), 4)
            before, after = f"{b * 100:.{digits}f}%", f"{a * 100:.{digits}f}%"
        elif before == after:
            before, after = str(b), str(a)
        rows.append(_row(page, name, tr(label), before, after, k))
    rows += _motion_rows(now, was)
    rows += _part_rows(now, was)
    rows += _target_rows(now, was, target_names or {})
    order = {p: i for i, p in enumerate(PAGE_ORDER)}
    return sorted(rows, key=lambda r: order.get(r["page"], len(order)))   # stable: field order inside a page
