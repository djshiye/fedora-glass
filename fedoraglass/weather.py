"""Weather frost, the app's side: how frosty the glass is for a temperature (the same
maths as the Shell extension's frostmath.js, for the preview), what the extension last
read from GNOME's weather (~/.cache/liquid-glass/weather-frost.json), and how the user
likes temperatures shown.

The app never asks for the weather itself: only the extension reads it, from GNOME's
own weather, so nothing about where you are goes anywhere new.
"""

from __future__ import annotations

import json
import locale
import math
import os
import stat
from pathlib import Path

STATE = "liquid-glass/weather-frost.json"
STATUSES = ("ok", "waiting", "no-weather", "no-place")
LEVELS = ("neutral", "cool", "cold", "freezing")

# As in frostmath.js.
COOL_TOP = 0.5
FLAKES_START = 0.4
FLAKES_SPAN = 10
FROST_BLUR = 18

# Where GNOME Weather's launcher is, installed from the distro or as a Flatpak.
WEATHER_APP = "org.gnome.Weather.desktop"


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def frost_for(temp: float | None, cool: int, cold: int, freezing: int, amount: float = 1.0) -> dict:
    """{level, frost, flakes} for `temp` °C, as frostmath.js frostFor (thresholds already clean)."""
    if temp is None or not isinstance(temp, (int, float)) or not math.isfinite(temp) or temp >= cool:
        return {"level": "neutral", "frost": 0.0, "flakes": 0.0}
    flakes = 0.0
    if temp >= cold:
        level = "cool"
        frost = 0.12 + (COOL_TOP - 0.12) * (cool - temp) / (cool - cold)
    elif temp > freezing:
        level = "cold"
        frost = COOL_TOP + (1 - COOL_TOP) * (cold - temp) / (cold - freezing)
    else:
        level = "freezing"
        frost = 1.0
        flakes = FLAKES_START + (1 - FLAKES_START) * _clamp((freezing - temp) / FLAKES_SPAN, 0, 1)
    a = _clamp(float(amount), 0.2, 1)
    return {"level": level, "frost": round(_clamp(frost, 0, 1) * a, 3), "flakes": round(_clamp(flakes, 0, 1) * a, 3)}


# The ice's shape, as frostmath.js crystalFor (Nakaya's diagram; more branches in humid air).
HABITS = {
    "plates": {"arm": 0.5, "twig": 0.15, "size": 0.6},
    "needles": {"arm": 0.12, "twig": 0.0, "size": 1.0},
    "ferns": {"arm": 1.0, "twig": 1.0, "size": 1.0},
    "columns": {"arm": 0.3, "twig": 0.0, "size": 0.45},
}
WET_DEFAULT = 0.6
SHAPES = tuple(HABITS)


def _ramp(a: float, b: float, v: float) -> float:
    t = _clamp((v - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def wetness(temp: float | None, dew: float | None) -> float:
    """How wet the air is, 0..1, from how far the dew point is under the temperature."""
    if not _finite(temp) or not _finite(dew):
        return WET_DEFAULT
    return round(_clamp(1 - max(0.0, temp - dew) / 8, 0.15, 1), 3)


def crystal_for(temp: float | None, dew: float | None = None) -> dict:
    """{shape, arm, twig, size}: the shape frost grows into at `temp` °C (air) and dew point `dew`."""
    t = min(float(temp), -1.0) if _finite(temp) else -6.0
    needles = _ramp(-3, -5, t) * (1 - _ramp(-9, -11, t))
    ferns = _ramp(-9, -11, t) * (1 - _ramp(-21, -23, t))
    columns = _ramp(-21, -23, t)
    w = {"plates": max(0.0, 1 - needles - ferns - columns), "needles": needles, "ferns": ferns, "columns": columns}
    shape = SHAPES[0]
    for h in SHAPES[1:]:
        if w[h] > w[shape]:
            shape = h

    def mix(k: str) -> float:
        return sum(w[h] * HABITS[h][k] for h in SHAPES)

    wet = wetness(temp, dew)
    return {
        "shape": shape,
        "arm": round(_clamp(mix("arm") * (0.55 + 0.45 * wet), 0, 1), 3),
        "twig": round(_clamp(mix("twig") * wet, 0, 1), 3),
        "size": round(_clamp(mix("size") * (0.75 + 0.25 * wet), 0, 1), 3),
    }


def frost_blur(frost: float) -> float:
    """The extra blur, px on the desktop: in three steps, as frostmath.js frostBlur."""
    return round(_clamp(frost, 0, 1) * 3) * (FROST_BLUR / 3)


def try_temp(level: str, cool: int, cold: int, freezing: int) -> float | None:
    """A temperature well inside a step, to show it in the preview."""
    if level == "cool":
        return (cool + cold) / 2
    if level == "cold":
        return (cold + freezing) / 2
    if level == "freezing":
        # Fern frost, the window frost everyone knows (around -15 °C), unless the step is colder.
        return min(freezing - 6, -15)
    return None


def read_state(cache: Path) -> dict:
    """What the extension last said, checked: {} when there is nothing (off, or never ran)."""
    path = Path(cache) / STATE
    try:
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode) or st.st_size > 4096:
            return {}
        with open(path, "rb") as f:
            raw = json.loads(f.read(4097))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict) or raw.get("status") not in STATUSES:
        return {}

    def num(k: str) -> float | None:
        v = raw.get(k)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and -90 < v < 70 else None

    return {
        "status": raw["status"],
        "level": raw.get("level") if raw.get("level") in LEVELS else "neutral",
        "temp": num("temp"),
        "feels": num("feels"),
        "dew": num("dew"),
        "shape": raw.get("shape") if raw.get("shape") in SHAPES else None,
        "feelsLike": raw.get("feelsLike") is not False,
        "frost": _clamp(float(raw["frost"]), 0, 1) if isinstance(raw.get("frost"), (int, float)) else 0.0,
        "flakes": _clamp(float(raw["flakes"]), 0, 1) if isinstance(raw.get("flakes"), (int, float)) else 0.0,
        "at": int(raw["at"]) if isinstance(raw.get("at"), int) and not isinstance(raw.get("at"), bool) else 0,
    }


def fahrenheit(unit_setting: str | None, region: str | None = None) -> bool:
    """Whether to show °F: GNOME Weather's own unit (org.gnome.GWeather4 temperature-unit),
    and for 'default' the region of the user's measurement locale, as libgweather does."""
    u = (unit_setting or "").strip().strip("'\"")
    if u == "fahrenheit":
        return True
    if u in ("centigrade", "kelvin"):
        return False
    if region is None:
        region = _region()
    return region in ("US", "LR", "MM", "BS", "BZ", "KY", "PW")


def _region() -> str:
    for var in ("LC_ALL", "LC_MEASUREMENT", "LANG"):
        v = os.environ.get(var, "")
        if v:
            break
    else:
        v = locale.getlocale()[0] or ""
    v = v.split(".")[0].split("@")[0]
    return v.split("_")[1].upper() if "_" in v else ""


def show(celsius: float, in_f: bool) -> str:
    """A temperature as the user reads them: '18 °C' or '64 °F'."""
    if in_f:
        return f"{round(celsius * 9 / 5 + 32)} °F"
    return f"{round(celsius)} °C"


def weather_app(data_dirs: list[Path]) -> Path | None:
    """GNOME Weather's launcher, if it is installed (from the distro or as a Flatpak)."""
    for d in data_dirs:
        p = Path(d) / "applications" / WEATHER_APP
        if p.is_file():
            return p
    return None


def data_dirs(user_data: Path) -> list[Path]:
    """Where launchers are: the user's (~/.local/share), Flatpak's (user and system) and the system's."""
    out = [Path(user_data), Path(user_data) / "flatpak/exports/share", Path("/var/lib/flatpak/exports/share")]
    out += [Path(p) for p in (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":") if p]
    return out
