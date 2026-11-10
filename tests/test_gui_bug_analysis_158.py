"""Bug analysis fixes: Undo refreshes the Apps page, dirty ignores no-op changes, a queued
Apply shows as busy, the weather state refreshes."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")

from fedoraglass import settings as settings_mod  # noqa: E402

from test_gui_backend import _KEEP, FakeEnv, FakeEngine, FakeTarget, app, home  # noqa: E402,F401


@pytest.fixture
def backend(app, home):
    from fedoraglass.gui.backend import Backend
    env = FakeEnv(home=home)
    targets = [FakeTarget("alpha", "Desktop", path=home / "out/alpha.css"),
               FakeTarget("beta", "Apps", path=home / "out/beta.css")]
    b = Backend(env=env, engine_factory=lambda: FakeEngine(env, targets),
                settings_path=home / "config/liquid-glass/settings.json", ui_dark=True, start=False)
    _KEEP.append(b)   # alive for the whole run, as the app's one is (see test_gui_backend)
    yield b
    if b._task is None or hasattr(b._task, "wait"):   # one test puts a stand-in there
        b.waitIdle()


def test_discard_emits_targets_changed(backend):
    # The switches follow the saved state through targetStatesChanged (rows are kept).
    seen = []
    backend.targetStatesChanged.connect(lambda: seen.append(1))
    backend.setTargetEnabled("alpha", False)
    seen.clear()
    backend.discardChanges()
    assert seen
    assert backend._s.target_enabled("alpha")
    backend.setTargetEnabled("alpha", False)   # no longer a no-op
    assert not backend._s.target_enabled("alpha")


def test_toggle_off_and_on_is_not_dirty(backend):
    backend.setTargetEnabled("alpha", False)
    assert backend.property("dirty")
    backend.setTargetEnabled("alpha", True)
    assert not backend.property("dirty")


def test_motion_back_to_default_is_not_dirty(backend):
    default = settings_mod.MOTION_DEFAULTS["open"]["preset"]
    other = next(p for p in settings_mod.MOTION_PRESETS["open"] if p != default)
    backend.setMotion("open", "preset", other)
    assert backend.property("dirty")
    backend.setMotion("open", "preset", default)
    assert not backend.property("dirty")


def test_queued_apply_shows_busy(backend):
    backend._task = object()           # the system check is still running
    backend._task_busy = False
    assert not backend.property("busy")
    backend.apply()
    assert backend.property("busy") and backend.property("busyKind") == "apply"
    backend._pending_action = None
    assert not backend.property("busy")


def test_refresh_weather_updates(backend, monkeypatch):
    from fedoraglass.gui import backend as bmod
    states = iter(["no-app", "ready"])
    monkeypatch.setattr(bmod, "_weather_state", lambda env: next(states))
    assert backend.property("weatherState") == "no-app"
    seen = []
    backend.weatherChanged.connect(lambda: seen.append(1))
    backend.refreshWeather()
    assert backend.property("weatherState") == "ready" and seen
