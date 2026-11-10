"""fedora-glass watch: stops cleanly, and merges quick switches into one apply."""
from __future__ import annotations

import queue
import threading


import pytest

from fedoraglass import __main__ as cli

_HAS_ACCENT_KEY = cli._has_accent_key


@pytest.fixture(autouse=True)
def _no_accent_key(monkeypatch):
    """Two monitors (dark/light, High Contrast), as on a GNOME without an accent colour;
    the accent tests below ask for the third."""
    monkeypatch.setattr(cli, "_has_accent_key", lambda: False)


class FakeProc:
    def __init__(self, lines=(), hold=False):
        self.killed = False
        self.waited = False
        self._release = threading.Event()
        self._lines, self._hold = list(lines), hold
        self.stdout = self._read()

    def _read(self):
        yield from self._lines
        if self._hold:                  # a monitor that keeps running until killed
            self._release.wait(5)

    def poll(self):
        return 0 if self.killed else None

    def kill(self):
        self.killed = True
        self._release.set()

    def wait(self):
        self.waited = True
        return 0


class FakeEngine:
    targets: tuple = ()

    def __init__(self):
        self.applies = 0

    def is_applied(self):
        return True

    def look_on(self):
        return True

    def apply(self, s, only=None, if_applied=False, applied_only=False):
        self.applies += 1


def test_first_monitor_is_stopped_if_the_second_cannot_start(monkeypatch):
    made = []

    def popen(cmd, **kw):
        if made:
            raise OSError("no gsettings")
        made.append(FakeProc(hold=True))
        return made[-1]

    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    assert cli.cmd_watch(None) == 1
    assert made[0].killed and made[0].waited


def test_watch_exits_non_zero_and_stops_the_other_monitor_when_one_ends(monkeypatch):
    procs = [FakeProc(hold=True), FakeProc()]       # the High Contrast monitor ends at once
    it = iter(procs)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: next(it))
    eng = FakeEngine()
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    assert cli.cmd_watch(None) == 1
    assert procs[0].killed and procs[0].waited
    assert eng.applies == 0


def test_quick_switches_are_taken_together():
    q: queue.Queue = queue.Queue()
    for i in (0, 1, 0, 0):
        q.put(i)
    assert cli._take_all(q) == {0, 1}
    assert q.empty()


def test_a_burst_of_switches_makes_one_apply(monkeypatch):
    # Three dark/light switches arrive before the watcher looks; the monitor then ends.
    gate = threading.Event()

    class Burst(FakeProc):
        def _read(self):
            yield from ("a\n", "b\n", "c\n")
            gate.wait(5)                # end only after the first apply

    procs = [Burst(), FakeProc(hold=True)]
    it = iter(procs)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: next(it))
    eng = FakeEngine()
    real_take = cli._take_all

    def take(q):
        if eng.applies:
            gate.set()
        else:
            while q.qsize() < 3:        # let the whole burst arrive first
                threading.Event().wait(0.01)
        return real_take(q)

    monkeypatch.setattr(cli, "_take_all", take)
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    monkeypatch.setattr(cli.settings_mod, "load", lambda: type("S", (), {"scheme": "auto"})())
    assert cli.cmd_watch(None) == 1
    assert eng.applies == 1


def test_the_watcher_restarts_itself_when_dnf_installs_a_new_version(monkeypatch):
    """The user service then starts the new version's watcher (Restart=on-failure), which
    brings the applied look up to date without waiting for the next login."""
    procs = [FakeProc(hold=True), FakeProc(hold=True)]
    it = iter(procs)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: next(it))
    monkeypatch.setattr(cli, "_engine", lambda: FakeEngine())
    monkeypatch.setattr(cli, "UPGRADE_POLL_S", 0.01)
    monkeypatch.setattr(cli, "disk_version", lambda: "99.0")
    assert cli.cmd_watch(None) == 75
    assert all(p.killed for p in procs), "its monitors are stopped"


def test_the_version_on_disk_is_read_from_the_package():
    from fedoraglass import __version__
    assert cli.disk_version() == __version__


# ---- accent colour ------------------------------------------------------------------
class AccentEngine(FakeEngine):
    def __init__(self):
        super().__init__()
        self.onlys = []
        self.targets = (type("T", (), {"id": "shell", "scheme_dependent": True})(),)

    def apply(self, s, only=None, if_applied=False, applied_only=False):
        assert if_applied and applied_only, "only the look and the parts the user applied"
        self.onlys.append(only)
        super().apply(s, only, if_applied, applied_only)


def _watch_accent(monkeypatch, accent, scheme="dark", lines=("x\n",)):
    """The accent monitor reports a change, then ends (which ends the watcher)."""
    started = []
    gate = threading.Event()

    class Once(FakeProc):
        def _read(self):
            yield from lines
            gate.wait(5)

    procs = [FakeProc(hold=True), FakeProc(hold=True), Once()]
    it = iter(procs)

    def popen(cmd, **kw):
        started.append(cmd[-2:])
        return next(it)
    monkeypatch.setattr(cli, "_has_accent_key", lambda: True)
    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    eng = AccentEngine()
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    monkeypatch.setattr(cli.settings_mod, "load", lambda: type("S", (), {"scheme": scheme, "accent": accent})())
    real_take = cli._take_all

    def take(q):
        got = real_take(q)
        if None not in got:
            gate.set()          # the monitor ends after this round
        return got
    monkeypatch.setattr(cli, "_take_all", take)
    assert cli.cmd_watch(None) == 1
    return started, eng


def test_a_new_system_accent_refreshes_every_applied_part(monkeypatch):
    started, eng = _watch_accent(monkeypatch, "system")
    assert ["org.gnome.desktop.interface", "accent-color"] in started
    assert eng.onlys == [None], "the accent is in every part, not only the dark/light ones"


def test_a_chosen_accent_ignores_the_system_one(monkeypatch):
    _started, eng = _watch_accent(monkeypatch, "#ff8800")
    assert eng.applies == 0
    _started, eng = _watch_accent(monkeypatch, "purple", scheme="auto")
    assert eng.applies == 0, "an accent change is not a dark/light switch"


def test_without_an_accent_setting_it_is_not_watched(monkeypatch):
    procs = [FakeProc(hold=True), FakeProc()]
    started = []
    it = iter(procs)

    def popen(cmd, **kw):
        started.append(cmd[-1])
        return next(it)
    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    monkeypatch.setattr(cli, "_engine", lambda: FakeEngine())
    assert cli.cmd_watch(None) == 1
    assert started == ["color-scheme", "high-contrast"]


def test_the_accent_key_is_found_on_gnome(monkeypatch, fake_env):
    from fedoraglass import env as env_mod
    monkeypatch.setattr(env_mod, "Env", lambda: fake_env)
    assert _HAS_ACCENT_KEY() is True              # FakeEnv knows accent-color
    del fake_env.gs[("org.gnome.desktop.interface", None)]["accent-color"]
    assert _HAS_ACCENT_KEY() is False


def test_the_refresh_brings_the_new_accent_into_the_gtk4_theme(fake_env):
    """What the watcher's refresh does: the applied parts, made again with the system's new accent."""
    from fedoraglass import palette
    from fedoraglass.engine import Engine
    from fedoraglass.settings import Settings
    from fedoraglass.targets.gtk import Gtk4
    s = Settings(accent="system")
    purple = palette.build(s, dark=True, system_accent="purple").accent.css
    eng = Engine(fake_env, [Gtk4()])
    eng.apply(s)

    def theme():
        return "".join(p.read_text() for p in sorted(fake_env.config.joinpath("gtk-4.0").rglob("*.css")))
    assert purple not in theme()
    fake_env.gs[("org.gnome.desktop.interface", None)]["accent-color"] = "'purple'"
    eng.apply(s, only=None, if_applied=True, applied_only=True)
    assert purple in theme()
