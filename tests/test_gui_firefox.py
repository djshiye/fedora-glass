"""The Firefox theme in the app: off until switched on, and switching it on and off
again is no change to Apply."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")

from tests.test_gui_backend import FakeEngine, FakeEnv, _KEEP, app  # noqa: E402,F401
from fedoraglass import settings as settings_mod  # noqa: E402
from fedoraglass.targets import apps as ta  # noqa: E402


@pytest.fixture
def backend(app, tmp_path, monkeypatch):  # noqa: F811
    from fedoraglass.gui.backend import Backend
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data")):
        monkeypatch.setenv(var, str(tmp_path / sub))
    prof = tmp_path / ".mozilla/firefox/p.default"
    prof.mkdir(parents=True)
    (tmp_path / ".mozilla/firefox/profiles.ini").write_text("[Profile0]\nName=p\nIsRelative=1\nPath=p.default\n")
    env = FakeEnv(home=tmp_path)
    targets = [ta.Firefox()]
    b = Backend(env=env, engine_factory=lambda: FakeEngine(env, targets),
                settings_path=tmp_path / "config/liquid-glass/settings.json", ui_dark=True, start=True)
    _KEEP.append(b)
    assert b.waitIdle()
    yield b, prof
    b.waitIdle()


def test_firefox_row_is_off_until_switched_on(backend):
    b, prof = backend
    items = {t["id"]: t for g in b.property("targets") for t in g["items"]}
    row = items["firefox-theme"]
    assert row["available"] is True and row["enabled"] is False
    assert any("Restart Firefox" in n for n in row["notes"])
    # The row's switch reads targetStates, where a missing id is on: this one is listed.
    assert b.property("targetStates")["firefox-theme"] is False
    assert b.property("activeTargetCount") == 0
    assert b.property("dirty") is False

    b.setTargetEnabled("firefox-theme", True)
    assert b.property("targetStates")["firefox-theme"] is True
    assert b.property("dirty") is True
    b.setTargetEnabled("firefox-theme", False)
    assert b.property("dirty") is False, "on and off again is no change"

    b.setTargetEnabled("firefox-theme", True)
    results = []
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    assert {r["id"]: r["status"] for r in results[0]} == {"firefox-theme": "applied"}
    assert (prof / "chrome/fedora-glass.css").is_file()
    saved = settings_mod.load(b._settings_file())
    assert saved.target_enabled("firefox-theme")


def test_apply_with_the_row_left_off_touches_no_profile(backend):
    b, prof = backend
    results = []
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    assert list(prof.iterdir()) == []
