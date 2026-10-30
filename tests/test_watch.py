"""liquid-glass watch: stops cleanly, and merges quick switches into one apply."""
from __future__ import annotations

import queue
import threading


from liquidglass import __main__ as cli


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

    def apply(self, s, only=None):
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
