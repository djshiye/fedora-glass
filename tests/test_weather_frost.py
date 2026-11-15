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
    assert "float iceSkin(" in ice and "vec4 iceField(" in ice and "vec3 iceLook(" in ice
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
    assert "if (flakes > OFF && mode < 1.5) {" in src
    assert "let frostNow = {frost: 0, flakes: 0, blur: 0};" in src
    # Without ice nothing is bent (the taps read where they always did) and nothing is drawn over.
    assert "vec2 pxi = px;" in src and "pxi += iceBend(iceF) * iceOn;" in src
    assert "if (iceF.x > OFF) {" in src
    # No ice grows in from a side of the glass that lies on the screen's edge, and its skin
    # is lit by the light where it rests (never the pointer's), so the ice lies still. It is
    # fixed to the glass's own corner (c + h), so the glass under a menu and the light layer
    # over it (whose pads differ) draw the very same ice.
    assert "iceF = iceField(cc, hh, c + h, normalize(vec2(hl_x, hl_y) + vec2(1e-4)), flakes);" in src
    assert "vec4 iceF = iceField(cc, hh, c + h, normalize(vec2(hl_x, hl_y) + vec2(1e-4)), flakes);" in src


def test_frozen_glass_is_stiff_on_the_desktop_and_in_the_preview():
    """Ice does not give like liquid glass: the press, the pull and the open bounce ease off
    as the glass freezes over, by the same rule in the extension and in the app."""
    glass = (EXT / "glass.js").read_text()
    motion = (EXT / "motion.js").read_text()
    assert "export function liquidNow(liquid)" in glass and "frozenLiquid(liquid, frostNow.flakes)" in glass
    assert "const lq = this._frosts() ? liquidNow(set) : set;" in glass, "only glass that frosts stiffens"
    assert "p._applyMotion();" in glass, "a change in the weather reaches the press at once"
    assert "const lq = liquidNow(" in motion and "liquidNow(1)" in motion
    # The app's copy of the rule (the preview): the same number, the same ends.
    math = (EXT / "frostmath.js").read_text()
    assert f"export const FROZEN_STIFF = {weather.FROZEN_STIFF};" in math
    assert weather.frozen_give(0) == 1 and weather.frozen_give(1) == pytest.approx(1 - weather.FROZEN_STIFF)
    assert weather.frozen_give(0.5) == pytest.approx(1 - weather.FROZEN_STIFF / 2)
    assert weather.frozen_give(9) == weather.frozen_give(1) and weather.frozen_give(-2) == 1
    qml = (ROOT / "fedoraglass/gui/qml/FedoraGlass/PreviewDesktop.qml").read_text()
    assert "Math.max(0.25, liquidSet * (glassOn ? ice.give ?? 1 : 1))" in qml


def test_menus_tell_the_ice_about_their_own_shadow():
    """St fills a menu's box with the theme's box-shadow, under the veil: 36 % black on dark
    glass. Not counted in, the ice of a dark menu came out a third too dark and dull."""
    s = Settings().normalized()
    for dark in (True, False):
        t = build(s, dark=dark)
        cfg = render_glass.config(s, t)
        for part in ("arcmenu", "quicksettings", "calendar"):
            assert cfg["parts"][part]["look"]["shade"] == round(t.shadow.a, 3) > 0, part
        assert cfg["menus"]["look"]["shade"] == round(t.shadow.a, 3)
        assert "shade" not in cfg["parts"]["panel"]["look"], "the panel's bar has no such shadow under it"
    tpl = (ROOT / "fedoraglass/data/shell/glass.css.tpl").read_text()
    for rule in (".popup-menu-content, .candidate-popup-content {", ".quick-settings {"):
        block = tpl[tpl.index(rule):tpl.index("; }", tpl.index(rule)) + 1]
        assert "box-shadow: 0 2px 6px 0 ${shadow};" in block, rule
    src = (EXT / "glass.js").read_text()
    assert "float passes = (1.0 - veil_a) * (1.0 - veil_shade);" in src
    assert "veil_shade: this._shade()," in src
    assert "return this._shadeShed ? 0 : Math.max(0, Math.min(0.9, this._look.shade ?? 0));" in src
    # Frozen, a menu sheds that shadow (the ice could not glow through it) and the glass is
    # told; thawed or gone, the menu has its own style back (tests/js/weather-frost-alive).
    fol = (EXT / "follower.js").read_text()
    assert "const ICE_STYLE = ' box-shadow: none;';" in fol
    assert "this.pane.setOnIce(frozen => this._iceStyle(frozen));" in fol
    destroy = fol[fol.index("    destroy() {"):]
    assert destroy.index("this._iceStyle(false);") < destroy.index("pane?.destroy();")


def test_frozen_glass_is_alive_only_while_in_use():
    """The vapour drifts and the light in the ice moves on a clock that runs only while the
    panel's or a menu's glass is in use, never for app windows or the lock screen, never with
    animations off or on the lightest quality, and stops once nothing is in use."""
    src = (EXT / "glass.js").read_text()
    assert "return frostNow.flakes > 0 && ICE_FPS[quality] > 0 && animationsOn();" in src
    live = src[src.index("    _iceLive() {"):src.index("    _iceInUse() {")]
    assert "(this._layer === LAYERS.glass || this._layer === LAYERS.reflections) && !(this._look.solid > 0.5)" in live
    use = src[src.index("    _iceInUse() {"):]
    use = use[:use.index("\n    }\n")]
    assert "!this._iceLive() || !this.mapped || !this.visible" in use
    tick = src[src.index("function iceTick() {"):src.index("export function wakeIce() {")]
    assert "iceTimer = 0;\n    return GLib.SOURCE_REMOVE;" in tick, "nothing in use: no more frames asked for"
    assert "if (!panes.size)\n                stopIce();" in src, "the last glass gone takes its clock along"
    # A step draws only the lens again (setFloats): nothing is copied or blurred again, and
    # only on a pane whose clock moved.
    assert "if (p.mapped && p._iceShown !== p._ice.t) {" in tick
    assert "p._glass.setFloats({ice_t: p._ice.t});" in tick
    # A menu's glass and the light layer over it share one clock, so the vapour and its light
    # never drift apart (with one each they did, a little more with every use).
    assert "clocks.set(p._ice, (clocks.get(p._ice) ?? false) || (runs && p._iceInUse()));" in tick
    fol = (EXT / "follower.js").read_text()
    assert "this.top.shareIce(this.pane);" in fol
    # Vapour rolls off a frozen menu, never off a bar such as the panel, an app window or the
    # lock screen (ice_live), and fades out inside the pane's own room.
    assert "if (flakes > OFF && ice_live > 0.5) {" in src
    assert "float big = smoothstep(80.0, 140.0, 2.0 * min(h.x, h.y));" in src
    assert "ice_live: this._iceLive() ? 1 : 0," in src
    # The app's preview: its clock runs only while the app is in front.
    pv = (ROOT / "fedoraglass/gui/qml/FedoraGlass/PreviewDesktop.qml").read_text()
    assert "paused: !(root.visible && root.glassOn && (root.ice.flakes || 0) > 0 && root.appInFront)" in pv


def test_frost_thins_out_around_text_instead_of_a_dark_shade():
    """Text and buttons on the frost at a menu's edge: 1.7.0 laid a 70 % black shade behind
    them, cut hard at a few of the blurred copy's 256 levels: blotchy, pixelated smudges. Now
    the frost thins out around them, down to the bare ice, by a soft measure of how much
    content is near."""
    src = (EXT / "glass.js").read_text()
    top = src[src.index("    if (mode > 1.5) {"):src.index("    // Weather frost, below freezing: the glass freezes over (frostmath.js).")]
    assert "sh = max(sh" not in top.split("vec3 iceLight")[1], "no shade for the ice any more"
    assert "float content = iceOver(contentAround(px, g));" in top
    assert "iceLookAt(vl + vec3(0.07, 0.09, 0.12) * passes, iceF, c + h, inside, 0.0, shortSide, litI," in top
    assert "inward, ice_t, 0.0);" in top, "the bare ice: no crust"
    # Drawn over the frost through the same veil as the glass under it, in its own colour.
    assert "float passes = (1.0 - veil_a) * (1.0 - veil_shade);" in top
    assert "thin = vec4(raw / max(1.0, max(raw.r, max(raw.g, raw.b))), 1.0) * melt;" in top
    assert "sh + thin.a * (1.0 - sh))" in top
    # The measure is the mean of five reads of the content's copy, so its levels show no steps.
    around = src[src.index("float contentAround(vec2 px, vec4 g) {"):src.index("void main() {")]
    assert "for (int i = 0; i < 4; i++) {" in around and "return s * 0.2;" in around
    math = (EXT / "frostmath.js").read_text()
    assert "float crust = crusted > 0.0 ? iceCrust(q, inside, shortSide) * crusted : 0.0;" in math
    assert "return iceLookAt(under, f, q, inside, lightGlass, shortSide, lit, inward, t, 1.0);" in math
    assert "return smoothstep(0.008, 0.055, bright);" in math
    # The ice's light fades out with the same soft measure; the line at the very edge stays.
    glow = math[math.index("vec3 iceGlow("):math.index("float iceOver(")]
    assert "float clear = 1.0 - clamp(content, 0.0, 1.0);" in glow
    assert "+ 0.20 * edge * (0.6 + 0.4 * clear)" in glow
    assert "onIt" not in glow and "nearIt" not in glow
    # The app's preview does the same in its one pass.
    frag = (ROOT / "fedoraglass/gui/qml/FedoraGlass/shaders/glass.frag").read_text()
    assert "onIt = iceOver(max(g.r, max(g.g, g.b)));" in frag
    assert "iceLookAt(seen, iceF, q, inq, lightGlass, shortIce, litI, inward, iceTime, 1.0 - onIt);" in frag
    assert "iced += iceGlow(iceF, q, inq, shortIce, litI, LIGHT, iceTime, onIt);" in frag


def test_glass_is_placed_again_when_frost_changes_the_room_it_needs():
    """Weather frost adds blur, and blur needs room around the glass. 1.7.0 changed the room
    and left the pane where it was: the panel's glass shrank to a thin strip as it frosted
    (and stuck out as it thawed) until something else placed it again."""
    src = (EXT / "glass.js").read_text()
    look = src[src.index("    _applyLook() {"):src.index("    setOnPad(fn) {")]
    assert "const padWas = this._pad;" in look
    assert "if (this._pad !== padWas && this._placed)\n            this.onPad?.();" in look
    assert look.index("this._applyShape();") < look.index("this.onPad?.();"), "after the new look is in"
    assert "this.pane.setOnPad(() => this.queue());" in (EXT / "follower.js").read_text()
    assert "this.pane.setOnPad(() => this.queue());" in (EXT / "windows.js").read_text()
    assert "this._card.setOnPad(() => this._queue());" in (EXT / "lock.js").read_text()
    # place() goes by the room too, so the same call places it anew.
    place = src[src.index("    place(x, y, w, h, radii, sx, sy, inner = null) {"):]
    assert "const key = [x, y, w, h, sx, sy, p, ...radii, ...part]" in place[:600]


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


def test_temperature_controls_are_dimmed_with_a_hint_until_weather_frost_is_on(qml):
    from tests.test_gui_polish import _find, _goto, _spin, _window
    from tests.test_gui_small_fixes import _backend
    win = _window(qml)
    _goto(win, "glass", 300)
    hint = _find(win, "weatherOffHint")
    scale = _find(win, "weatherScale")
    body = _find(win, "weatherStepsBody")
    try_row = _find(win, "weatherTry")
    cool = _find(win, "weatherCool")
    assert hint.property("visible") and "once frost with the weather is on" in hint.property("text")
    _spin(400)
    assert scale.property("opacity") < 1 and body.property("opacity") < 1
    assert cool.property("enabled"), "they can still be set up beforehand"
    assert try_row.property("enabled") and try_row.property("opacity") == 1, "Try in the preview keeps working"
    b = _backend(qml)
    b.setProperty("weatherFrost", True)
    _spin(500)
    assert not hint.property("visible")
    assert scale.property("opacity") == 1 and body.property("opacity") == 1
    b.setProperty("weatherFrost", False)
