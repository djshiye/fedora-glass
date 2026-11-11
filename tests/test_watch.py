"""fedora-glass watch: stops cleanly, and merges quick switches into one apply."""
from __future__ import annotations

import queue
import threading
from pathlib import Path


import pytest

from fedoraglass import __main__ as cli

_HAS_ACCENT_KEY = cli._has_accent_key
_GIO = cli._gio         # before the tests' stand-in (see conftest.py)


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
    monkeypatch.setattr(cli.settings_mod, "load_checked", lambda: (type("S", (), {"scheme": "auto"})(), None, True))
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
    monkeypatch.setattr(cli.settings_mod, "load_checked", lambda: (type("S", (), {"scheme": scheme, "accent": accent})(), None, True))
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


# ---- one failure never ends the watcher ---------------------------------------------
class FailingEngine(AccentEngine):
    def apply(self, s, only=None, if_applied=False, applied_only=False):
        self.applies += 1
        raise OSError(28, "No space left on device")


def test_a_failing_apply_is_logged_once_and_the_watcher_goes_on(monkeypatch, capsys):
    """1.5.22: an OSError out of Apply ended the watcher, and its user service (Restart=
    on-failure) started it again every 5 seconds, failing the same way each time."""
    class Proc(FakeProc):
        pass
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: Proc(hold=True))
    eng = FailingEngine()
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    monkeypatch.setattr(cli.settings_mod, "load_checked", lambda: (type("S", (), {"scheme": "auto"})(), None, True))
    rounds = iter([{0}, {0}, {None}])
    monkeypatch.setattr(cli, "_take_all", lambda q: next(rounds))
    assert cli.cmd_watch(None) == 1, "it ends only because the monitor did"
    assert eng.applies == 2
    assert capsys.readouterr().err.count("No space left") == 1


def test_a_failing_start_does_not_end_the_watcher(monkeypatch):
    def boom(*a, **k):
        raise OSError(5, "Input/output error")
    monkeypatch.setattr(cli, "update_after_upgrade", boom)
    monkeypatch.setattr(cli, "finish_pending", boom)
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: FakeProc(hold=True))
    monkeypatch.setattr(cli, "_engine", lambda: FakeEngine())
    rounds = iter([{None}])
    monkeypatch.setattr(cli, "_take_all", lambda q: next(rounds))
    assert cli.cmd_watch(None) == 1


# ---- the GSettings signal path (PyGObject), with a fake Gio and GLib ------------------
class FakeGLib:
    """A main loop on a pretend clock: callbacks run in time order, at once."""

    def __init__(self):
        self.now, self.queue, self.seq, self.stopped = 0.0, [], 0, False
        outer = self

        class MainLoop:
            def run(self):
                while outer.queue and not outer.stopped:
                    outer.queue.sort()
                    at, _seq, fn, every = outer.queue.pop(0)
                    outer.now = at
                    if fn() is True and every:
                        outer.at(at + every, fn, every)

            def quit(self):
                outer.stopped = True
        self.MainLoop = MainLoop

    def at(self, t, fn, every=0.0):
        self.seq += 1
        self.queue.append((t, self.seq, fn, every))
        return self.seq

    def timeout_add(self, ms, fn):
        return self.at(self.now + ms / 1000, fn, ms / 1000)

    def timeout_add_seconds(self, s, fn):
        return self.at(self.now + s, fn, s)


class FakeGio:
    def __init__(self, keys):
        self.keys = keys            # {schema: {key, ...}}
        self.made = {}
        gio = self

        class Schema:
            def __init__(self, keys):
                self._keys = keys

            def has_key(self, key):
                return key in self._keys

        class Source:
            def lookup(self, schema, recursive):
                return Schema(gio.keys[schema]) if schema in gio.keys else None

        class SettingsSchemaSource:
            @staticmethod
            def get_default():
                return Source()

        class Settings:
            def __init__(self, schema):
                self.schema, self.handlers, self.read = schema, {}, set()

            @classmethod
            def new(cls, schema):
                assert schema in gio.keys, "Gio aborts the process on a missing schema"
                gio.made.setdefault(schema, []).append(cls(schema))
                return gio.made[schema][-1]

            def connect(self, signal, fn):
                self.handlers[signal] = fn

            def get_value(self, key):
                self.read.add(key)

            def emit(self, key):
                fn = self.handlers.get(f"changed::{key}")
                if fn and key in self.read:     # as GSettings: only keys read once report changes
                    fn(self, key)
        self.SettingsSchemaSource, self.Settings = SettingsSchemaSource, Settings

    def change(self, schema, key):
        for s in self.made[schema]:
            s.emit(key)


GNOME = {"org.gnome.desktop.interface": {"color-scheme", "accent-color"},
         "org.gnome.desktop.a11y.interface": {"high-contrast"}}


def _gio_watch(monkeypatch, eng, script, keys=GNOME, upgrade_at=None, accent="system"):
    """Run the watcher on the fake loop; `script` is [(time, schema, key)] of switches.
    It ends when a new version appears on disk at `upgrade_at` (or right after the script)."""
    glib, gio = FakeGLib(), FakeGio({k: set(v) for k, v in keys.items()})
    for t, schema, key in script:
        glib.at(t, lambda schema=schema, key=key: gio.change(schema, key))
    end = upgrade_at or (max((t for t, *_ in script), default=0) + 1)
    monkeypatch.setattr(cli, "disk_version", lambda: "99.0" if glib.now >= end else cli.__version__)
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    monkeypatch.setattr(cli.settings_mod, "load_checked",
                        lambda: (type("S", (), {"scheme": "auto", "accent": accent})(), None, True))
    monkeypatch.setattr(cli, "_gio", lambda: (gio, glib))
    return cli.cmd_watch(None), gio, glib


def test_signals_a_burst_of_switches_makes_one_apply(monkeypatch):
    eng = AccentEngine()
    code, gio, _ = _gio_watch(monkeypatch, eng, [(1.0, "org.gnome.desktop.interface", "color-scheme")] * 3)
    assert code == 75, "a new version on disk ends it, for the user service to start that one"
    assert eng.onlys == [{"shell"}], "one Apply, of the parts that can't switch by themselves"
    assert set(gio.made) == set(GNOME)


def test_signals_switches_apart_make_one_apply_each(monkeypatch):
    eng = AccentEngine()
    _gio_watch(monkeypatch, eng, [(1.0, "org.gnome.desktop.interface", "color-scheme"),
                                  (5.0, "org.gnome.desktop.a11y.interface", "high-contrast"),
                                  (9.0, "org.gnome.desktop.interface", "accent-color")])
    assert eng.onlys == [{"shell"}, None, None]


def test_signals_without_an_accent_setting_it_is_not_watched(monkeypatch):
    eng = AccentEngine()
    keys = {**GNOME, "org.gnome.desktop.interface": {"color-scheme"}}
    code, gio, _ = _gio_watch(monkeypatch, eng, [(1.0, "org.gnome.desktop.interface", "color-scheme")], keys=keys)
    assert code == 75 and eng.onlys == [{"shell"}]
    assert [s.handlers.keys() for s in gio.made["org.gnome.desktop.interface"]] == [{"changed::color-scheme"}]


def test_signals_a_missing_schema_ends_the_watcher_with_1(monkeypatch):
    keys = {"org.gnome.desktop.interface": {"color-scheme"}}
    code, gio, _ = _gio_watch(monkeypatch, AccentEngine(), [], keys=keys)
    assert code == 1 and not gio.made


def test_signals_a_failing_apply_does_not_end_the_watcher(monkeypatch, capsys):
    eng = FailingEngine()
    code, _, _ = _gio_watch(monkeypatch, eng, [(1.0, "org.gnome.desktop.a11y.interface", "high-contrast"),
                                               (5.0, "org.gnome.desktop.a11y.interface", "high-contrast")])
    assert code == 75 and eng.applies == 2
    assert capsys.readouterr().err.count("No space left") == 1


def test_signals_the_upgrade_poll_runs_every_minute(monkeypatch):
    code, _, glib = _gio_watch(monkeypatch, AccentEngine(), [], upgrade_at=150)
    assert code == 75 and glib.now == 180.0


def test_signals_without_pygobject_the_monitors_are_used(monkeypatch):
    monkeypatch.setattr(cli, "_gio", lambda: None)
    monkeypatch.setattr(cli, "_watch_monitors", lambda: 42)
    assert cli.cmd_watch(None) == 42


def test_without_gi_there_is_no_gio(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "gi", None)        # import gi then raises ImportError
    assert _GIO() is None


# ---- the Shell parts that wait for the glass: looked at again for a while --------------
def test_waiting_shell_parts_are_finished_at_a_later_wake_up(monkeypatch):
    calls = []
    results = iter([False, False, True])

    def finish(eng, wait_s=120.0, **k):
        calls.append(wait_s)
        return next(results)
    monkeypatch.setattr(cli, "finish_pending", finish)
    code, _, _ = _gio_watch(monkeypatch, AccentEngine(), [], upgrade_at=300)
    assert code == 75
    assert calls == [120.0, 0.0, 0.0], "at login (waiting), then a quick look each minute until done"


def test_waiting_shell_parts_are_looked_at_only_for_a_while(monkeypatch):
    now = [0.0]
    calls = []
    monkeypatch.setattr(cli, "finish_pending", lambda eng, **k: calls.append(1) and False)
    w = cli.Watcher(AccentEngine(), clock=lambda: now[0])
    w.start()
    w.retry_pending()
    now[0] = cli.PENDING_RETRY_S + 1
    w.retry_pending()
    w.changed({cli.CONTRAST})
    assert len(calls) == 2, "at login and once more, then no longer"


SCHEMAS = """<schemalist>
  <schema id="org.gnome.desktop.interface" path="/org/gnome/desktop/interface/">
    <key name="color-scheme" type="s"><default>'default'</default></key>
    <key name="accent-color" type="s"><default>'blue'</default></key>
  </schema>
  <schema id="org.gnome.desktop.a11y.interface" path="/org/gnome/desktop/a11y/interface/">
    <key name="high-contrast" type="b"><default>false</default></key>
  </schema>
</schemalist>
"""


def test_signals_with_the_real_gio(tmp_path):
    """The same, on PyGObject's own Gio and GLib (GSettings' memory backend, and schemas
    of our own). Runs in a python that has gi; the test runner's may not."""
    import os
    import shutil
    import subprocess
    import sys
    if not shutil.which("glib-compile-schemas"):
        pytest.skip("needs glib-compile-schemas")
    py = next((p for p in (sys.executable, "/usr/bin/python3", "/usr/bin/python3.12") if shutil.which(p) and
               subprocess.run([p, "-c", "import gi; from gi.repository import Gio"], capture_output=True).returncode == 0),
              None)
    if py is None:
        pytest.skip("no python with gi here")
    (tmp_path / "s.gschema.xml").write_text(SCHEMAS)
    subprocess.run(["glib-compile-schemas", str(tmp_path)], check=True)
    script = """
import sys
from fedoraglass import __main__ as cli
from gi.repository import GLib, Gio
class Eng:
    targets = (type("T", (), {"id": "shell", "scheme_dependent": True})(),)
    onlys = []
    def look_on(self): return True
    def apply(self, s, only=None, if_applied=False, applied_only=False): self.onlys.append(only)
eng = Eng()
cli._engine = lambda: eng
cli.update_after_upgrade = cli.finish_pending = lambda *a, **k: True
cli.settings_mod.load_checked = lambda: (type("S", (), {"scheme": "auto", "accent": "system"})(), None, True)
cli.UPGRADE_POLL_S = 1
done = []
cli.disk_version = lambda: "99.0" if done else cli.__version__
mine = Gio.Settings.new("org.gnome.desktop.interface")
def switch():
    mine.set_string("color-scheme", "prefer-dark")
    mine.set_string("color-scheme", "default")
    return False
def later():
    Gio.Settings.new("org.gnome.desktop.a11y.interface").set_boolean("high-contrast", True)
    return False
GLib.timeout_add(100, switch)
GLib.timeout_add(500, later)
GLib.timeout_add(800, lambda: done.append(1))
code = cli._watch_gio(Gio, GLib)
print(code, eng.onlys)
"""
    env = {**os.environ, "GSETTINGS_SCHEMA_DIR": str(tmp_path), "GSETTINGS_BACKEND": "memory",
           "PYTHONPATH": str(Path(cli.__file__).resolve().parents[1])}
    r = subprocess.run([py, "-c", script], capture_output=True, text=True, env=env, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.split("\n")[0] == "75 [{'shell'}, None]", r.stdout + r.stderr
