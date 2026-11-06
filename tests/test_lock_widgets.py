"""Lock screen widgets and the Lock screen tab: settings stay safe, the Shell gets a clean
config, nothing private shows by default, and the widgets never take input or read the
session behind the lock."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from liquidglass import palette
from liquidglass.render import glass as rg
from liquidglass.settings import LOCK_MESSAGE_MAX, Settings, clean_message

ROOT = Path(__file__).resolve().parents[1]
EXT = rg.SOURCE
JS = (EXT / "lockwidgets.js").read_text()
NODE = shutil.which("node")


def widgets(**kw):
    s = Settings(**kw)
    return rg.config(s, palette.build(s, dark=True))["lock"]["widgets"]


def test_nothing_about_the_owner_shows_by_default():
    w = widgets()
    assert w == {"battery": True, "weather": False, "weatherPlace": False, "greeting": False, "message": "",
                 "style": "chips", "hideNotifications": False}
    js = (EXT / "config.js").read_text()
    assert ("widgets: {battery: true, weather: false, weatherPlace: false, greeting: false, message: '',\n"
            "            style: 'chips', hideNotifications: false}") in js


def test_widgets_stay_with_the_glass_off_or_reduce_transparency():
    for kw in ({"lock_glass": False}, {"reduce_transparency": True}):
        assert widgets(lock_greeting=True, **kw)["greeting"] is True


@pytest.mark.parametrize("raw, want", [
    ("If found, call 555 0100", "If found, call 555 0100"),
    ("two\nlines\tand\x07bell", "two lines and bell"),
    ("  spaced   out  ", "spaced out"),
    ("<b>bold</b> &amp;", "<b>bold</b> &amp;"),      # kept as text: the Shell shows it plainly
    ("line sep", "line sep"),
    (None, ""), (42, ""),
])
def test_message_is_tidied(raw, want):
    assert clean_message(raw) == want
    assert Settings(lock_message=raw).normalized().lock_message == want


def test_message_is_short():
    m = Settings(lock_message="x" * 500).normalized().lock_message
    assert len(m) == LOCK_MESSAGE_MAX == 120
    js = (EXT / "config.js").read_text()
    assert "const MESSAGE_MAX = 120;" in js and "export const MESSAGE_MAX = 120;" in JS


def test_unknown_style_falls_back():
    assert Settings(lock_widget_style="sparkles").normalized().lock_widget_style == "chips"
    assert Settings(lock_widget_battery="yes", lock_hide_notifications=0).normalized().lock_widget_battery is True


def test_every_widget_key_is_cleaned_in_the_extension():
    js = (EXT / "config.js").read_text()
    body = js[js.index("function cleanWidgets("):js.index("export function parse(")]
    for key in ("battery", "weather", "weatherPlace", "greeting", "hideNotifications", "style", "message"):
        assert key in body, key
    assert "out.widgets = cleanWidgets(raw.widgets);" in js


@pytest.mark.parametrize("forbidden", [
    "window_group", "get_window_actors", "messageTray", "Main.uiGroup", "reactive: true", "can_focus",
    "pushModal", "grab(", "key-press-event", "captured-event", "button-press-event", "St.Button",
    "clutter_text.set_markup", "use_markup = true", "set_progress_func", "trackTitle", "MprisSource",
    "_promptBox", "_authPrompt",
])
def test_widgets_never_take_input_or_read_the_session(forbidden):
    assert forbidden not in JS


def test_the_message_is_plain_text_and_the_panel_is_only_read_for_the_weather():
    assert "msg.clutter_text.use_markup = false;" in JS
    assert JS.count("Main.panel") == 1
    assert "dateMenu?._weatherItem?._weatherClient" in JS


def test_widgets_fall_back_to_gnomes_lock_screen_on_errors():
    safe = JS[JS.index("    _safe(fn) {"):JS.index("    get _wanted() {")]
    assert "console.error" in safe and "this._detach();" in safe
    detach = JS[JS.index("    _detach() {"):JS.index("    /** The screen is unlocked")]
    # Timers, D-Bus, the weather listener and GNOME's notifications all go back.
    for gone in ("GLib.source_remove(this._timer)", "this._cancel?.cancel()", "this._battery?.disconnect(",
                 "this._weatherClient?.disconnect(", "_updateVisibility", "a.destroy()"):
        assert gone in detach, gone


def test_no_library_that_could_stop_the_extension_loading():
    # A missing typelib in a static import fails the whole extension, glass and all.
    imports = re.findall(r"from 'gi://(\w+)", JS)
    assert set(imports) <= {"Clutter", "Gio", "GLib", "Meta", "St"}


def test_extension_starts_and_stops_the_widgets_with_the_lock():
    ext = (EXT / "extension.js").read_text()
    sync = ext[ext.index("    _sync() {"):ext.index("    _effective(cfg) {")]
    assert sync.index("this._stopSession();") < sync.index("new LockWidgets(cfg)")
    assert "this._leavingWidgets?.unlocking();" in sync
    disable = ext[ext.index("    disable() {"):]
    assert "this._widgets?.destroy();" in disable and "this._leavingWidgets?.destroy();" in disable
    assert "this._widgets?.update(cfg);" in ext
    assert "lockwidgets.js" in rg.FILES


@pytest.mark.skipif(NODE is None, reason="needs node")
def test_widget_text_under_node():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/lockwidgets.test.mjs"],
                       capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_settings_json_round_trip_keeps_the_widgets(tmp_path):
    from liquidglass import settings as settings_mod
    s = Settings(lock_widget_weather=True, lock_message="Hi", lock_widget_style="plain")
    settings_mod.save(s, tmp_path / "s.json")
    got = settings_mod.load(tmp_path / "s.json")
    assert (got.lock_widget_weather, got.lock_message, got.lock_widget_style) == (True, "Hi", "plain")
    json.loads((tmp_path / "s.json").read_text())
