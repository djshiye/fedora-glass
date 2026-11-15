"""Eleven small fixes in the settings app: the frost slider and presets, error toasts,
the weather "Try" step, the speed folder appearing late, Undo that can be undone, one set
of weather names, the wider sidebar, and a few wording and colour fixes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401

from fedoraglass import settings as settings_mod  # noqa: E402
from tests.test_gui_backend import app, home, make_backend  # noqa: E402,F401 - fixtures
from tests.test_gui_ux_keys import _backend, _find, _goto, _spin, win  # noqa: E402,F401 - win is a fixture

QML = Path(__file__).resolve().parents[1] / "fedoraglass/gui/qml"


# ---- 1. the frost slider and the presets -----------------------------------------------
def test_clear_then_slider_up_lets_the_blur_follow(make_backend):
    b = make_backend()
    b.applyPreset("Clear")
    assert b.settings().blur == 2
    seen = []
    b.settingsChanged.connect(lambda: seen.append(1))
    b.setFrost(1.0)
    assert b.settings().blur is None and b.property("frost") == 1.0
    assert len(seen) == 1, "one change, one signal"
    low = b.tokens["blur_radius"] if "blur_radius" in b.tokens else None
    b.setFrost(0.0)
    if low is not None:
        assert b.tokens["blur_radius"] < low, "the blur follows the slider now"


def test_frosted_and_solid_pins_are_let_go_too(make_backend):
    b = make_backend()
    b.applyPreset("Frosted")
    b.setFrost(0.3)
    assert b.settings().blur is None
    b.applyPreset("Solid")
    assert b.settings().opacity == 0.92
    b.setFrost(0.5)
    assert b.settings().opacity is None


def test_a_blur_set_by_hand_survives_the_slider(make_backend):
    b = make_backend()
    b.applyPreset("Clear")
    b.setProperty("blur", 40)           # Advanced: not what Clear pinned
    b.setFrost(0.9)
    assert b.settings().blur == 40
    b.applyPreset("Solid")
    b.setProperty("opacity", 0.7)
    b.setFrost(0.5)
    assert b.settings().opacity == 0.7


def test_slider_between_presets_keeps_hand_set_values(make_backend):
    """Only the preset the slider was sitting on counts: 26 is Frosted's blur, not Balanced's."""
    b = make_backend()
    b.setProperty("blur", 26)
    b.setFrost(0.9)                     # from Balanced's 0.45: no preset pinned that blur
    assert b.settings().blur == 26


def test_reset_pill_of_how_much_glass_covers_the_whole_family(make_backend):
    b = make_backend()
    b.applyPreset("Frosted")
    assert set(b.property("changedFromDefault")) >= {"frost", "blur", "highlight", "tint_strength"}
    family = ["frost", "blur", "opacity", "highlight", "tint_strength"]
    b.resetSettings(family)
    s, d = b.settings(), settings_mod.Settings()
    assert all(getattr(s, k) == getattr(d, k) for k in family)
    assert not set(b.property("changedFromDefault")) & set(family)
    b.applyPreset("Solid")
    b.resetSettings(family)
    assert not set(b.property("changedFromDefault")) & set(family)
    page = (QML / "FedoraGlass/GlassPage.qml").read_text()
    assert 'resetKeys: ["frost", "blur", "opacity", "highlight", "tint_strength"]' in page
    for name in ("GlassPage", "HomePage"):
        assert "Backend.frost = v" not in (QML / f"FedoraGlass/{name}.qml").read_text()


# ---- 2. error toasts -----------------------------------------------------------------------
def test_error_toast_wraps_stays_and_closes(qml, win):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    b = _backend(qml)
    toast = _find(win, "toast")
    reason = ("Dein ursprünglicher Look ist zurück, aber das Entfernen von Fedora Glass ist fehlgeschlagen: "
              "Fehler: Es wurde keine Übereinstimmung für fedora-glass gefunden (Transaktionsprüfung fehlgeschlagen)")
    b.failed.emit(reason)
    _spin(500)
    assert toast.property("shown") and toast.property("sticky")
    assert toast.property("height") > 44, "a long reason wraps instead of being cut to one line"
    assert toast.property("width") <= 640
    _spin(4800)
    assert toast.property("shown"), "an error does not vanish by itself"
    close = _find(win, "toastClose")
    assert close.property("visible")
    close.clicked.emit()
    _spin(400)
    assert not toast.property("shown")
    # Esc closes it as well.
    b.failed.emit("Could not save settings: disk full")
    _spin(300)
    assert toast.property("shown")
    QTest.keyClick(win, Qt.Key_Escape)
    _spin(300)
    assert not toast.property("shown")


def test_info_toast_still_goes_by_itself(qml, win):
    from PySide6.QtCore import QMetaObject, Qt, Q_ARG
    toast = _find(win, "toast")
    QMetaObject.invokeMethod(toast, "show", Qt.DirectConnection, Q_ARG("QVariant", "Hello"),
                                Q_ARG("QVariant", "info"), Q_ARG("QVariant", "#ffffff"))
    _spin(200)
    assert toast.property("shown") and not toast.property("sticky")
    _spin(4600)
    assert not toast.property("shown")


def test_toast_source_has_alert_role_and_a_close_button():
    src = (QML / "FedoraGlass/Toast.qml").read_text()
    assert "Accessible.AlertMessage" in src and 'Accessible.name: qsTr("Close")' in src
    assert "toast.showError(message)" in (QML / "Main.qml").read_text()


# ---- 3. weather "Try" ---------------------------------------------------------------------
def test_try_step_is_cleared_by_undo_and_reset_all(make_backend):
    b = make_backend()
    b.setProperty("weatherTry", "freezing")
    b.discardChanges()
    assert b.property("weatherTry") == ""
    b.setProperty("weatherTry", "cold")
    b.setProperty("radius", 3)
    b.resetDefaults()
    assert b.property("weatherTry") == ""


def test_try_step_is_cleared_on_leaving_the_glass_page(qml, win):
    b = _backend(qml)
    _goto(win, "glass", 100)
    b.setProperty("weatherTry", "cool")
    assert b.property("weatherTry") == "cool"
    win.setProperty("page", "colour")
    _spin(100)
    assert b.property("weatherTry") == ""
    win.setProperty("page", "home")


# ---- 4. the speed folder appearing after the app started -----------------------------------
def test_speed_folder_that_appears_later_is_picked_up(make_backend, home, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    b = make_backend()
    folder = home / ".cache/liquid-glass"
    assert not folder.exists()
    b._check_speed_watch()
    assert not folder.exists(), "the app never creates it"
    assert b.property("weatherNow") == {}
    folder.mkdir(parents=True)
    (folder / "weather-frost.json").write_text(json.dumps(
        {"status": "ok", "level": "cold", "temp": -3, "feels": -6, "frost": 0.6, "flakes": 0.1, "at": 1}))
    (folder / "speed.json").write_text(json.dumps({"fps": 60}))
    got = []
    b.weatherFrostChanged.connect(lambda: got.append(1))
    b._poll_safe_mode()                  # the timer that is already running
    assert b.property("weatherNow")["temp"] == -3 and got
    assert str(folder) in b._speed_watch.directories()
    assert b._speed_status == {"fps": 60}
    b._poll_safe_mode()                  # nothing new: no more reads
    assert len(got) == 1


def test_apply_watches_the_folder_it_made(make_backend, home, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))
    b = make_backend()
    folder = home / ".cache/liquid-glass"
    assert b.property("weatherNow") == {}
    folder.mkdir(parents=True)
    (folder / "weather-frost.json").write_text(json.dumps({"status": "ok", "temp": 1.0, "feels": 1.0}))
    b.setProperty("frost", 0.9)
    b.apply()
    b.waitIdle()
    assert b.property("weatherNow").get("temp") == 1.0


# ---- 5. Undo and Put back ------------------------------------------------------------------
def test_undo_can_be_put_back(make_backend):
    b = make_backend()
    b.setProperty("radius", 5)
    b.setProperty("tint", "#112233")
    undone = []
    b.undone.connect(lambda: undone.append(1))
    b.discardChanges()
    assert undone and b.property("canRestore") and b.property("radius") != 5
    b.restoreDiscarded()
    assert b.property("radius") == 5 and b.property("tint") == "#112233"
    assert b.property("dirty") and not b.property("canRestore")


def test_put_back_is_forgotten_by_any_change(make_backend):
    b = make_backend()
    b.setProperty("radius", 5)
    b.discardChanges()
    assert b.property("canRestore")
    b.setProperty("highlight", 0.1)
    assert not b.property("canRestore")
    b.restoreDiscarded()                 # nothing kept: nothing happens
    assert b.property("radius") != 5


def test_put_back_is_forgotten_by_apply(make_backend):
    b = make_backend()
    b.setProperty("radius", 5)
    b.discardChanges()
    b.apply()
    b.waitIdle()
    assert not b.property("canRestore")
    b.restoreDiscarded()
    assert b.property("radius") != 5


def test_undo_toast_offers_put_back(qml, win):
    b = _backend(qml)
    toast = _find(win, "toast")
    before = b.property("radius")
    b.setProperty("radius", 5 if before != 5 else 6)
    b.discardChanges()
    _spin(400)
    assert toast.property("shown") and toast.property("text") == "Changes undone"
    action = _find(win, "toastAction")
    assert action.property("visible") and action.property("text") == "Put back"
    action.clicked.emit()
    _spin(300)
    assert b.property("radius") == (5 if before != 5 else 6)
    assert not toast.property("shown")
    b.discardChanges()


def test_put_back_offer_goes_when_something_changes(qml, win):
    b = _backend(qml)
    toast = _find(win, "toast")
    b.setProperty("radius", 9 if b.property("radius") != 9 else 10)
    b.discardChanges()
    _spin(300)
    assert toast.property("shown")
    b.setProperty("highlight", 0.11)
    _spin(300)
    assert not toast.property("shown")
    b.discardChanges()


# ---- 6. one set of weather names -----------------------------------------------------------
def test_weather_uses_cool_cold_freezing_everywhere():
    src = (QML / "FedoraGlass/WeatherFrostCard.qml").read_text()
    for gone in ('"Icy', 'icy below', 'qsTr("Frosted")', 'qsTr("Misty")', "Icy below"):
        assert gone not in src, gone
    for word in ('qsTr("Freezing below")', 'qsTr("Freezing")', 'qsTr("Cold")', 'qsTr("Cool")'):
        assert word in src, word


# ---- 7. sidebar ------------------------------------------------------------------------------
def test_sidebar_is_wider_and_says_the_full_name_when_cut():
    assert "width: 248" in (QML / "Main.qml").read_text()
    side = (QML / "FedoraGlass/Sidebar.qml").read_text()
    assert "navLabel.truncated" in side


# ---- 8, 9: Home captions ----------------------------------------------------------------------
def test_look_caption_is_whole_or_gone():
    src = (QML / "FedoraGlass/HomePage.qml").read_text()
    assert "Pick one to start. Everything else follows it." in src
    block = src.split('qsTr("Pick one to start.')[0].rsplit("Text {", 1)[1]
    assert "elide" not in block and "implicitWidth <=" in block


def test_day_night_caption_names_what_the_user_sees():
    src = (QML / "FedoraGlass/DayNightCard.qml").read_text()
    assert "Works only when the style is set to Auto (under Colour)" in src
    assert "Works only when Style is Auto" not in src


# ---- 10. Fahrenheit is read once --------------------------------------------------------------
def test_fahrenheit_is_read_once(make_backend):
    b = make_backend()
    calls = []
    real = b._env.gsettings_get

    def spy(schema, key, path=None):
        if schema == "org.gnome.GWeather4":
            calls.append(key)
        return real(schema, key, path)

    b._env.gsettings_get = spy
    for t in range(-20, 30):
        b.showTemp(float(t))
    assert len(calls) == 1
    assert b.property("weatherFahrenheit") in (True, False) and len(calls) == 1


# ---- 11. disabled red buttons -------------------------------------------------------------------
def test_disabled_destructive_buttons_are_grey_not_red():
    src = (QML / "FedoraGlass/LgButton.qml").read_text()
    assert "_redOff" in src and "Theme.textFaint" in src


# ---- reset and the wallpaper match ----------------------------------------------------------------
def test_resets_that_change_the_style_match_the_wallpaper(make_backend):
    b = make_backend()
    b.setProperty("scheme", "light")
    calls = []
    b._match_wallpaper = lambda: calls.append(1)
    b.resetSettings(["scheme"])
    assert b.property("scheme") == "auto" and calls
    calls.clear()
    b.setProperty("scheme", "dark")
    calls.clear()
    b.resetDefaults()
    assert b.property("scheme") == "auto" and calls
    calls.clear()
    b.resetDefaults()                    # nothing to change: nothing to match
    assert not calls
