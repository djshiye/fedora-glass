"""Shell features in the app: lighter glass on battery (Speed card), apps without glass
(Panel and windows page, with the app picker), the Glass switch in Quick Settings
(Glass page). Backend first, then the QML controls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtGui")
from test_gui_backend import app, home, make_backend  # noqa: E402,F401
from test_gui_reliability import _find, _js, _spin, _window  # noqa: E402


# ---- lighter glass on battery: backend ----------------------------------------------------
def test_battery_switch_is_a_setting_with_a_default(make_backend):
    b = make_backend()
    assert b.property("lighterOnBattery") is True
    assert b.property("defaults")["lighter_on_battery"] is True
    b.setProperty("lighterOnBattery", False)
    assert b.settings().lighter_on_battery is False and b.property("dirty")
    assert "lighter_on_battery" in b.property("changedFromDefault")


def test_speed_status_says_battery_or_power_saver(make_backend, home, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / "cache"))
    b = make_backend()
    p = home / "cache/liquid-glass/speed.json"
    p.parent.mkdir(parents=True)
    for power, want in (("battery", "battery"), ("saver", "saver"), ("warp", ""), (None, "")):
        p.write_text(json.dumps({"level": "lighter", "reason": "battery", "power": power}))
        b._on_speed_file()
        assert (b.property("speedLevel"), b.property("speedReason"), b.property("speedPower")) == \
            ("lighter", "battery", want)
    p.write_text(json.dumps({"level": "lighter", "reason": "slow", "power": "battery"}))
    b._on_speed_file()
    assert b.property("speedPower") == "", "only when the battery is the reason"


# ---- the controls ---------------------------------------------------------------------------
def _probe(qml):
    from test_gui_reliability import _probe as probe
    return probe(qml)


def _page(win, page):
    win.setProperty("page", page)
    _spin(150)


def test_speed_card_battery_switch_and_reason(qml):
    b = _probe(qml)
    win = _window(qml)
    saved = (b._speed_status, b._glass_live)
    try:
        win.show()
        _spin(150)
        _page(win, "glass")
        row = _find(win, "lighterOnBattery")
        assert row is not None and row.property("visible")
        assert row.property("checked") is True
        assert "Power Saver" in row.property("caption")
        row.toggled.emit(False)
        assert b.property("lighterOnBattery") is False
        b.resetSettings(["lighter_on_battery"])
        assert row.property("checked") is True
        b._glass_live = True
        b._speed_status = {"level": "lighter", "reason": "battery", "power": "battery"}
        b.speedChanged.emit()
        b.targetsChanged.emit()
        _spin()
        status = _find(win, "speedStatus")
        assert status.property("text") == "Right now: lighter glass, because you're on battery."
        b._speed_status = {"level": "lighter", "reason": "battery", "power": "saver"}
        b.speedChanged.emit()
        _spin()
        assert status.property("text") == "Right now: lighter glass, because Power Saver is on."
    finally:
        b._speed_status, b._glass_live = saved
        b.speedChanged.emit()
        b.targetsChanged.emit()
        b.resetSettings(["lighter_on_battery"])
        win.close()


def test_search_finds_the_new_controls(qml):
    win = _window(qml)
    side = _find(win, "sidebar")
    field = _find(win, "searchField")

    def found(text):
        field.setProperty("text", text)
        _spin(30)
        return [e["name"] for e in _js(side.property("allResults"))]
    try:
        win.show()
        _spin(150)
        assert "lighterOnBattery" in found("battery")
        assert "lighterOnBattery" in found("power saver")
    finally:
        field.setProperty("text", "")
        win.close()
