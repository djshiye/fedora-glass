"""Weather frost: the glass frosts over when it is cold outside. The settings (off by
default, Dino's outdoor table as the steps), what Apply hands the Shell extension, the
app's copy of the extension's maths (the preview), what the app reads back from the
extension, and the Glass page's card."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from fedoraglass import weather
from fedoraglass.palette import build
from fedoraglass.render import glass as render_glass
from fedoraglass.settings import WEATHER_RANGES, Settings, clean_weather_steps

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


# ---------------------------------------------------------------- settings

def test_off_by_default_with_the_outdoor_table():
    s = Settings().normalized()
    assert s.weather_frost is False, "the glass never changes with the weather unless asked"
    assert (s.weather_cool, s.weather_cold, s.weather_freezing) == (18, 10, 0)
    assert s.weather_feels_like is True and s.weather_amount == 1.0


def test_only_a_real_true_turns_it_on():
    for v in ("yes", 1, "true", None):
        assert Settings(weather_frost=v).normalized().weather_frost is False


@pytest.mark.parametrize("raw, want", [
    ((18, 10, 0), (18, 10, 0)),
    ((99, -99, -99), (26, -10, -30)),
    ((12, 15, 40), (12, 11, 10)),          # each at least 1 under the one above
    (("x", None, float("nan")), (18, 10, 0)),
    ((16.6, 7.4, -2.5), (17, 7, -2)),
])
def test_steps_are_whole_degrees_in_order_and_range(raw, want):
    assert clean_weather_steps(*raw) == want
    c, d, f = want
    assert WEATHER_RANGES["cool"][0] <= c <= WEATHER_RANGES["cool"][1]
    assert f < d < c


def test_apply_hands_the_extension_its_settings():
    s = Settings(weather_frost=True, weather_cool=16, weather_cold=8, weather_freezing=-3,
                 weather_amount=0.6, weather_feels_like=False)
    cfg = render_glass.config(s, build(s, dark=True))
    assert cfg["weather"] == {"enabled": True, "feelsLike": False, "cool": 16, "cold": 8, "freezing": -3, "amount": 0.6}
    # Reduce transparency: there is no glass to frost.
    cfg = render_glass.config(replace(s, reduce_transparency=True), build(s, dark=True))
    assert cfg["weather"]["enabled"] is False


# ---------------------------------------------------------------- the maths, as the extension has it

def test_frost_grows_with_the_cold_and_never_shrinks():
    last = (-1.0, -1.0)
    for t10 in range(300, -300, -5):
        f = weather.frost_for(t10 / 10, 18, 10, 0)
        assert (f["frost"], f["flakes"]) >= last or f["frost"] >= last[0]
        assert f["frost"] >= last[0] and f["flakes"] >= last[1]
        last = (f["frost"], f["flakes"])
    assert weather.frost_for(20, 18, 10, 0) == {"level": "neutral", "frost": 0.0, "flakes": 0.0}
    assert weather.frost_for(None, 18, 10, 0)["level"] == "neutral"
    assert weather.frost_for(5, 18, 10, 0)["flakes"] == 0
    assert weather.frost_for(-1, 18, 10, 0)["level"] == "freezing"


@pytest.mark.skipif(not shutil.which("node"), reason="needs node for the extension's maths")
def test_the_preview_frosts_exactly_like_the_desktop():
    temps = [t / 2 for t in range(-60, 70)]
    script = (f"import('{(EXT / 'frostmath.js').as_uri()}').then(M => console.log(JSON.stringify("
              f"{json.dumps(temps)}.map(t => [M.frostFor(t, {{cool: 16, cold: 7, freezing: -2, amount: 0.8}}),"
              f" M.frostBlur(M.frostFor(t, {{}}).frost), M.frostFor(t, {{}}, t - 1.5), M.frostFor(t, {{}}, t - 12)]))))")
    out = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True)
    js = json.loads(out.stdout)
    for t, (f, blur, wet, dry) in zip(temps, js):
        py = weather.frost_for(t, 16, 7, -2, 0.8)
        assert py["level"] == f["level"] and py["frost"] == pytest.approx(f["frost"]) and py["flakes"] == pytest.approx(f["flakes"]), t
        assert weather.frost_blur(weather.frost_for(t, 18, 10, 0)["frost"]) == pytest.approx(blur), t
        # With a dew point too, humid and dry: to the last digit.
        for dew, want in ((t - 1.5, wet), (t - 12, dry)):
            assert weather.frost_for(t, 18, 10, 0, dew=dew) == want, (t, dew)


def test_the_preview_draws_the_same_frost_as_the_desktop():
    """One frost shader, word for word: frostmath.js ICE_GLSL in glass.js and in the app's glass.frag."""
    if not shutil.which("node"):
        pytest.skip("needs node")
    script = f"import('{(EXT / 'frostmath.js').as_uri()}').then(M => process.stdout.write(M.ICE_GLSL))"
    ice = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True).stdout
    assert "float iceSheet(" in ice and "vec3 iceLook(" in ice
    frag = (ROOT / "fedoraglass/gui/qml/FedoraGlass/shaders/glass.frag").read_text()
    assert ice in frag, "glass.frag's frost differs from frostmath.js ICE_GLSL: copy it over"
    assert "${ICE_GLSL}" in (EXT / "glass.js").read_text()


def test_try_temperatures_land_in_their_step():
    for level in ("cool", "cold", "freezing"):
        t = weather.try_temp(level, 18, 10, 0)
        assert weather.frost_for(t, 18, 10, 0)["level"] == level
    assert weather.try_temp("", 18, 10, 0) is None
    assert weather.frost_for(weather.try_temp("freezing", 18, 10, -20), 18, 10, -20)["level"] == "freezing"


def test_humid_air_frosts_a_little_more_than_dry_air():
    plain = weather.frost_for(5, 18, 10, 0)
    assert weather.frost_for(5, 18, 10, 0, dew=None) == plain == weather.frost_for(5, 18, 10, 0, dew=float("nan"))
    assert weather.frost_for(5, 18, 10, 0, dew=4.5)["frost"] > plain["frost"] > weather.frost_for(5, 18, 10, 0, dew=-15)["frost"]
    ice, dry = weather.frost_for(-4, 18, 10, 0)["flakes"], weather.frost_for(-4, 18, 10, 0, dew=-20)["flakes"]
    assert 0.6 * ice < dry < ice
    assert weather.wetness(-15, None) == weather.WET_DEFAULT == weather.wetness(-15, float("nan"))
    assert weather.frost_for(25, 18, 10, 0, dew=25)["frost"] == 0


# ---------------------------------------------------------------- what the extension said

def _state(tmp_path, text):
    p = tmp_path / weather.STATE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return tmp_path


def test_state_is_read_carefully(tmp_path):
    assert weather.read_state(tmp_path) == {}
    good = {"version": 1, "status": "ok", "level": "cold", "temp": 7.2, "feels": 4.1, "dew": 2.5, "feelsLike": True,
            "frost": 0.8, "flakes": 0, "at": 1794581000}
    got = weather.read_state(_state(tmp_path, json.dumps(good)))
    assert got["status"] == "ok" and got["level"] == "cold" and got["feels"] == 4.1 and got["frost"] == 0.8
    assert got["dew"] == 2.5
    assert weather.read_state(_state(tmp_path, json.dumps({**good, "dew": "wet"})))["dew"] is None
    for bad in ("not json", "[]", json.dumps({**good, "status": "hacked"}), "x" * 5000):
        assert weather.read_state(_state(tmp_path, bad)) == {}
    odd = weather.read_state(_state(tmp_path, json.dumps({**good, "temp": "hot", "feels": 1e9, "level": "lava",
                                                           "frost": 7, "at": True})))
    assert odd["temp"] is None and odd["feels"] is None and odd["level"] == "neutral" and odd["frost"] == 1 and odd["at"] == 0


def test_a_link_is_never_followed(tmp_path):
    secret = tmp_path / "secret.json"
    secret.write_text(json.dumps({"status": "ok"}))
    p = tmp_path / weather.STATE
    p.parent.mkdir(parents=True)
    os.symlink(secret, p)
    assert weather.read_state(tmp_path) == {}


@pytest.mark.parametrize("unit, region, f", [
    ("'fahrenheit'", "DE", True), ("'centigrade'", "US", False), ("'kelvin'", "US", False),
    ("'default'", "US", True), ("'default'", "GB", False), (None, "US", True), (None, "HR", False),
])
def test_degrees_as_gnome_weather_shows_them(unit, region, f):
    assert weather.fahrenheit(unit, region) is f


def test_temperatures_read_naturally():
    assert weather.show(18, False) == "18 °C"
    assert weather.show(18, True) == "64 °F"
    assert weather.show(-10, True) == "14 °F"


# ---------------------------------------------------------------- the extension's side

def test_extension_reads_only_gnome_weather_and_never_the_place():
    src = (EXT / "frost.js").read_text()
    assert "_weatherClient" in src
    assert "get_location_name" not in src and "get_coords" not in src and "geoclue" not in src.lower()
    assert "gi://GWeather" not in src, "no extra library: a missing one would stop the whole extension"
    assert "Soup" not in src and "http" not in src, "no other service is contacted"


def test_frost_is_skipped_entirely_when_off():
    """Weather frost off (or warm out): both uniforms 0, so the shader skips its frost branches."""
    src = (EXT / "glass.js").read_text()
    assert "if (frost > OFF && mode < 1.5)" in src
    assert "if (flakes > OFF && mode < 1.5 && inside < iceReach" in src
    assert "let frostNow = {frost: 0, flakes: 0, blur: 0};" in src
    # Without ice nothing is bent (the taps read where they always did) and nothing is drawn over.
    assert "vec2 pxi = px;" in src and "pxi += iceBend(iceF) * iceOn;" in src
    assert "if (iceF.x > OFF) {" in src
    # No ice grows in from a side of the glass that lies on the screen's edge.
    assert "iceF = iceField(cc, hh, px + at0, iceReach, flakes);" in src


# ---------------------------------------------------------------- the app

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _backend(fake_env, tmp_path):
    pytest.importorskip("PySide6.QtQuick")
    from tests.test_gui_features_looks import _backend as make
    return make(fake_env, tmp_path)


def test_thresholds_make_room_for_each_other(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("weatherCool", 9)
    assert (b.property("weatherCool"), b.property("weatherCold"), b.property("weatherFreezing")) == (9, 8, 0)
    b.setProperty("weatherFreezing", 9)
    assert (b.property("weatherCool"), b.property("weatherCold"), b.property("weatherFreezing")) == (11, 10, 9)
    b.setProperty("weatherCold", -50)
    assert (b.property("weatherCold"), b.property("weatherFreezing")) == (-10, -11)
    b.resetSettings(["weather_cool", "weather_cold", "weather_freezing"])
    assert (b.property("weatherCool"), b.property("weatherCold"), b.property("weatherFreezing")) == (18, 10, 0)


def test_the_preview_tries_each_step_and_shows_the_weather_now(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    assert b.property("weatherPreview")["level"] == "neutral"
    for level in ("cool", "cold", "freezing"):
        b.setProperty("weatherTry", level)
        assert b.property("weatherPreview")["level"] == level
    b.setProperty("weatherTry", "")
    # As it is now: what the extension read, only while weather frost is on.
    _state(fake_env.cache, json.dumps({"status": "ok", "level": "cold", "temp": 12, "feels": 3}))
    b._read_weather_frost()
    assert b.property("weatherPreview")["level"] == "neutral"
    b.setProperty("weatherFrost", True)
    assert b.property("weatherPreview")["level"] == "cold"           # feels like 3 °C
    b.setProperty("weatherFeelsLike", False)
    assert b.property("weatherPreview")["level"] == "cool"           # 12 °C in the air
    assert b.property("weatherPreview")["blur"] > 0
    # The reading's dew point counts, as on the desktop.
    _state(fake_env.cache, json.dumps({"status": "ok", "level": "freezing", "temp": -7, "feels": -12, "dew": -8}))
    b._read_weather_frost()
    p = b.property("weatherPreview")
    assert p["level"] == "freezing" and p["flakes"] == weather.frost_for(-7, 18, 10, 0, dew=-8)["flakes"]
    assert "shape" not in p


def test_glass_page_has_the_card_and_search_finds_it(qml):
    from tests.test_gui_polish import _find, _goto, _window
    win = _window(qml)
    _goto(win, "glass", 300)
    for name in ("weatherFrost", "weatherFrostSwitch", "weatherTry", "weatherScale"):
        assert _find(win, name) is not None, name
    index = (ROOT / "fedoraglass/gui/qml/FedoraGlass/searchindex.js").read_text()
    assert 'name: "weatherFrostSwitch"' in index
