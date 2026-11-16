"""Fixes after the 1.7.4 review, the settings app (G1-G10)."""

from __future__ import annotations

import json
import time

import pytest

from test_gui_backend import FakeTarget, app, home, make_backend  # noqa: F401  (fixtures)

from fedoraglass import engine as engine_mod
from fedoraglass import weather
from fedoraglass.engine import Engine
from fedoraglass.gui import backend as backend_mod


# ---- G1: an Apply the engine refuses is not an applied look ------------------------------------
def test_refused_apply_is_not_an_applied_look(make_backend, home, monkeypatch):
    b = make_backend()
    b.setProperty("radius", 7)
    b.apply()
    b.waitIdle()
    previous = b._previous
    b.setProperty("radius", 21)
    monkeypatch.setattr(engine_mod, "disk_version", lambda: "99.0")
    logins, failed, finished = [], [], []
    b._login_refresh = lambda s: logins.append(s.radius)
    b.failed.connect(failed.append)
    b.applyFinished.connect(finished.append)
    b.apply()
    b.waitIdle()
    on_disk = json.loads((home / "config/liquid-glass/settings.json").read_text())
    assert on_disk["radius"] == 7, "settings.json keeps the look that is really applied"
    assert b.property("dirty"), "the look is still waiting to be applied"
    assert b._saved.radius == 7
    assert b._previous is previous
    assert logins == [] and finished == []
    assert len(failed) == 1 and "updated while it was open" in failed[0]
    assert not b.property("partlyApplied")


# ---- G2: quitting while a wallpaper colour is read -------------------------------------------------
def test_shutdown_waits_for_wallpaper_task_and_runs_once(make_backend, monkeypatch):
    b = make_backend()
    monkeypatch.setattr(backend_mod.wallcolour, "colours_of",
                        lambda path: (time.sleep(0.4), {"key": "k", "tint": "#123456", "accent": "blue"})[1])
    b._match_path = lambda s=None, dark=None: "/tmp/some-wallpaper.jpg"
    b.setProperty("tintFromWallpaper", True)
    tasks = list(b._wall_tasks.values())
    assert tasks and tasks[0].isRunning()
    b.shutdown()
    assert all(t.isFinished() for t in tasks), "shutdown must not leave a thread running"
    calls = []
    real = b._speed_watch.removePaths
    b._speed_watch.removePaths = lambda paths: calls.append(paths) or real(paths)
    b.shutdown()
    assert calls == [], "the second shutdown does nothing"


# ---- G3: Undo then Put back keeps the Apps switches ------------------------------------------------
def test_put_back_brings_back_the_apps_switches(make_backend):
    b = make_backend()
    b.setTargetEnabled("beta", False)
    b.setProperty("radius", 5)
    b.discardChanges()
    assert b.property("canRestore")
    b.restoreDiscarded()
    assert b.settings().target_enabled("beta") is False
    assert b.property("radius") == 5


def test_put_back_with_only_a_switch(make_backend):
    b = make_backend()
    b.setTargetEnabled("beta", False)
    b.discardChanges()
    assert b.property("canRestore")
    b.restoreDiscarded()
    assert b.property("dirty")


# ---- G4: Undo ends a step back that did not go through ------------------------------------------
def test_undo_clears_a_step(make_backend):
    b = make_backend()
    b._apply_step = "back"
    b.setProperty("radius", 3)
    b.discardChanges()
    assert b._apply_step == ""


# ---- G9: a Remove whose Restore fails leaves the glass as it was ------------------------------------
def test_remove_whose_restore_fails_keeps_glass_live(make_backend, monkeypatch):
    b = make_backend()
    b.waitIdle()
    b._remove_package = "fedora-glass"
    b._glass_live = True
    seen = []
    b.refreshTargets = lambda: seen.append(1)
    monkeypatch.setattr(Engine, "revert", lambda self: (_ for _ in ()).throw(OSError("boom")))
    b.removeApp()
    b.waitIdle()
    assert b.property("glassLive") is True
    assert seen, "the system is checked again"


# ---- G7: the weather frost card tells two states wrongly ---------------------------------------------
def test_automatic_location_with_location_services_off(monkeypatch):
    values = {("org.gnome.shell.weather", "locations"): "@av []",
              ("org.gnome.shell.weather", "automatic-location"): "true",
              ("org.gnome.system.location", "enabled"): "false"}

    class E:
        def gsettings_get(self, schema, key):
            return values[(schema, key)]
    monkeypatch.setattr(backend_mod, "_desktop_entry", lambda env, name: "x")
    assert backend_mod._weather_state(E()) == "no-location"
    values[("org.gnome.system.location", "enabled")] = "true"
    assert backend_mod._weather_state(E()) == "ready"
    values[("org.gnome.shell.weather", "automatic-location")] = "false"
    assert backend_mod._weather_state(E()) == "no-place"


def test_an_old_reading_is_waiting(make_backend, home, monkeypatch):
    b = make_backend()
    cache = b._env.cache
    f_dir = (cache / weather.STATE).parent
    f_dir.mkdir(parents=True, exist_ok=True)
    f = cache / weather.STATE
    now = time.time()
    f.write_text(json.dumps({"status": "ok", "level": "cold", "temp": 3, "feels": 3, "at": int(now - 4 * 3600)}))
    b._read_weather_frost()
    assert b.property("weatherNow")["status"] == "waiting"
    b.setProperty("weatherFrost", True)
    assert b.property("weatherPreview")["level"] == "neutral", "the preview's Now ignores it too"
    f.write_text(json.dumps({"status": "ok", "level": "cold", "temp": 3, "feels": 3, "at": int(now - 600)}))
    b._read_weather_frost()
    assert b.property("weatherNow")["status"] == "ok"
    assert b.property("weatherPreview")["level"] == "cold"


# ---- QML: footer, banners, frozen preview, weather card ------------------------------------------------
def _qml_window(qml, width, lang=""):
    from test_gui_polish import _window
    win = _window(qml)
    m = win.property("margin")
    win.setWidth(width + 2 * m)
    win.setHeight(600 + 2 * m)
    win.show()
    return win


@pytest.fixture
def german(app):
    from fedoraglass import i18n
    i18n.reset("de")
    i18n.install_qt(app)
    yield
    for t in getattr(app, "_fg_translators", []):
        app.removeTranslator(t)
    app._fg_translators = []
    i18n.reset("")


def _backend_of(qml):
    from test_gui_polish import _backend
    return _backend(qml)


def test_footer_status_stays_left_of_the_buttons_in_german(qml, german):
    from test_gui_polish import _find, _spin
    b = _backend_of(qml)
    win = _qml_window(qml, 1000)
    try:
        b._partial = [{"id": "a", "name": "A", "status": "failed", "message": "x"}] * 3
        b.partialChanged.emit()
        for i in range(3):
            b.setProperty("radius", 3 + i)
        _spin(400)
        status, button = _find(win, "statusText"), _find(win, "showChanges")
        # The dot and the sentence, or neither: nothing of the status row may reach the buttons.
        row = status.parentItem()
        end = max(c.mapToItem(None, c.width(), 0).x() for c in row.childItems() if c.isVisible())
        assert end <= button.mapToItem(None, 0, 0).x()
        b._partial = []
        b.partialChanged.emit()
        b.discardChanges()
        b.setProperty("radius", 30)
        b.setProperty("frost", 0.1)
        _spin(400)
        assert status.isVisible()
        right = status.mapToItem(None, status.width(), 0).x()
        assert right <= button.mapToItem(None, 0, 0).x(), "the status is cut short, not under the buttons"
    finally:
        b._partial = []
        b.partialChanged.emit()
        b.discardChanges()
        win.close()


@pytest.mark.parametrize("lang", ["en", "de"])
def test_safe_mode_banner_is_not_cut(qml, app, lang):
    from fedoraglass import i18n
    from test_gui_polish import _find, _spin
    if lang == "de":
        i18n.reset("de")
        i18n.install_qt(app)
    b = _backend_of(qml)
    win = _qml_window(qml, 1280)
    try:
        b._safe = {"reason": "restarts"}
        b.safeModeChanged.emit()
        _spin(700)
        note = _find(win, "safeNote")
        assert note.isVisible() and note.property("text")
        assert note.property("truncated") is False
        banner = _find(win, "safeBanner")
        assert banner.property("height") >= note.property("height") + 16, "the banner grows with its sentence"
    finally:
        b._safe = {}
        b.safeModeChanged.emit()
        win.close()
        for t in getattr(app, "_fg_translators", []):
            app.removeTranslator(t)
        app._fg_translators = []
        i18n.reset("")


def test_frozen_preview_clock_runs_at_about_20_hz(qml):
    from test_gui_polish import _find, _goto, _spin
    b = _backend_of(qml)
    win = _qml_window(qml, 1280)
    try:
        win.requestActivate()
        _spin(300)
        _goto(win, "glass", 1200)
        b.setProperty("weatherFrost", True)
        b.setProperty("weatherTry", "freezing")
        _spin(400)
        todo, desk = [win.contentItem()], None
        while todo and desk is None:
            it = todo.pop()
            mo = it.metaObject()
            if mo.indexOfProperty("iceTime") >= 0 and mo.indexOfProperty("closeUp") >= 0:
                desk = it
            todo.extend(it.childItems())
        assert desk is not None
        assert win.isActive(), "this needs the window in front (offscreen)"
        ticks = []
        desk.iceTimeChanged.connect(lambda: ticks.append(1))
        t0 = desk.property("iceTime")
        _spin(1000)
        assert 10 <= len(ticks) <= 30, len(ticks)
        assert 0.7 < desk.property("iceTime") - t0 < 1.4, "drifts at the same speed as before"
    finally:
        b.setProperty("weatherTry", "")
        b.setProperty("weatherFrost", False)
        win.close()


def test_card_says_what_to_do_when_location_is_off(qml):
    from test_gui_polish import _find, _goto, _spin
    b = _backend_of(qml)
    win = _qml_window(qml, 1280)
    try:
        b.setProperty("weatherFrost", True)
        b._weather_state = "no-location"
        b.weatherChanged.emit()
        _goto(win, "glass", 400)
        _spin(200)
        text = _find(win, "weatherStatusText").property("text")
        assert "Location Services" in text
        assert _find(win, "openWeatherApp").isVisible()
    finally:
        b._weather_state = "ready"
        b.weatherChanged.emit()
        b.setProperty("weatherFrost", False)
        win.close()
