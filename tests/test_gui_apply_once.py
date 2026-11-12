"""The app's Apply is one engine call for every part (1.5.28 review): it still shows each
part in the progress line, keeps the latest result per part, and stamps the version."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtGui = pytest.importorskip("PySide6.QtGui")

from fedoraglass.engine import WAITING, Engine, Result, read_applied_version  # noqa: E402
from fedoraglass.i18n import gettext as tr  # noqa: E402

from test_gui_backend import FakeEnv, FakeTarget, _KEEP  # noqa: E402


@pytest.fixture(scope="module")
def app():
    yield QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])


@pytest.fixture
def home(tmp_path, monkeypatch):
    for var, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data")):
        monkeypatch.setenv(var, str(tmp_path / sub))
    return tmp_path


class CountingEngine:
    """The real engine, with each apply call and its progress noted."""

    def __init__(self, env, targets, results=None, fail=None):
        self._real = Engine(env, targets)
        self.env, self.targets = env, targets
        self.calls, self.told = [], []
        self._results, self._fail = results, fail

    def __getattr__(self, name):
        return getattr(self._real, name)

    def apply(self, s, only=None, progress=None, **kw):
        self.calls.append(only)

        def tell(i, n, name):
            self.told.append((i, n, name))
            progress(i, n, name)
        if self._fail is not None:
            raise self._fail
        if self._results is not None:
            for i, t in enumerate(self.targets):
                tell(i, len(self.targets), t.name)
            return list(self._results)
        return self._real.apply(s, only=only, progress=tell, **kw)


def _backend(home, engine):
    from fedoraglass.gui.backend import Backend
    b = Backend(env=engine.env, engine_factory=lambda: engine,
                settings_path=home / "config/liquid-glass/settings.json", ui_dark=True, start=False)
    _KEEP.append(b)
    return b


def _targets(home):
    return [FakeTarget("alpha", "Desktop", path=home / "out/alpha.css"),
            FakeTarget("beta", "Apps", path=home / "out/beta.css"),
            FakeTarget("gamma", "Apps", available=False, path=home / "out/gamma.css")]


def test_one_call_for_every_part_with_each_part_in_the_progress_line(app, home):
    env = FakeEnv(home=home)
    eng = CountingEngine(env, _targets(home))
    b = _backend(home, eng)
    texts, results = [], []
    b.progressChanged.connect(lambda: texts.append(b.property("progressText")))
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    app.processEvents()
    assert eng.calls == [None], "one Apply of every part"
    assert [(i, n) for i, n, _ in eng.told] == [(0, 3), (1, 3), (2, 3)]
    for name in ("Alpha", "Beta", "Gamma"):
        assert name in texts
    assert {r["id"]: r["status"] for r in results[0]} == {"alpha": "applied", "beta": "applied", "gamma": "skipped"}
    assert read_applied_version(env) is not None, "the one call stamps the version"


def test_the_latest_result_for_a_part_counts(app, home):
    env = FakeEnv(home=home)
    first = Result("alpha", "Alpha", "info", tr(WAITING))
    later = Result("alpha", "Alpha", "applied")
    eng = CountingEngine(env, _targets(home)[:1], results=[first, Result("beta", "Beta", "applied"), later])
    b = _backend(home, eng)
    results = []
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    app.processEvents()
    rows = {r["id"]: r for r in results[0]}
    assert rows["alpha"]["status"] == "applied" and rows["alpha"]["restart"] is False
    assert len(results[0]) == 2


def test_a_part_that_waits_for_the_glass_says_so(app, home):
    env = FakeEnv(home=home)
    eng = CountingEngine(env, _targets(home)[:1], results=[Result("alpha", "Alpha", "info", tr(WAITING))])
    b = _backend(home, eng)
    results = []
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    app.processEvents()
    assert results[0][0]["restart"] is True


def test_an_apply_that_stops_says_so(app, home):
    env = FakeEnv(home=home)
    eng = CountingEngine(env, _targets(home), fail=OSError("disk full"))
    b = _backend(home, eng)
    failed, results = [], []
    b.failed.connect(failed.append)
    b.applyFinished.connect(results.append)
    b.apply()
    assert b.waitIdle()
    app.processEvents()
    assert results == [] and failed and "disk full" in failed[0]
    assert eng.calls == [None]
