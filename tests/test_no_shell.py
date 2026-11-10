"""With no GNOME Shell on the bus (Restore for a logged-out user while the package is
removed, under dbus-run-session), asking it about ArcMenu returns at once instead of
waiting 15 seconds for an answer that can't come."""
from __future__ import annotations

import pytest

from fedoraglass.env import RunResult
from fedoraglass.targets import shell as ts

NO_SHELL = ("Error: GDBus.Error:org.freedesktop.DBus.Error.ServiceUnknown: "
            "The name org.gnome.Shell was not provided by any .service files\n")


class Bus:
    def __init__(self, env, err, code=1):
        self.env, self.err, self.code, self.calls = env, err, code, 0

    def __call__(self, argv, timeout=30):
        if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv:
            self.calls += 1
            return RunResult(self.code, "", self.err)
        return RunResult(0, "", "")


@pytest.mark.parametrize("err,code", [
    (NO_SHELL, 1),
    ("Error: GDBus.Error:org.freedesktop.DBus.Error.NameHasNoOwner: Could not get owner of name\n", 1),
    ("Error connecting: Could not connect: No such file or directory\n", 1),
    ("[Errno 2] No such file or directory: 'gdbus'", 127),
])
def test_no_shell_is_known_at_once(fake_env, monkeypatch, err, code):
    bus = Bus(fake_env, err, code)
    monkeypatch.setattr(fake_env, "run", bus)
    assert ts.park_arcmenu(fake_env) is False
    assert bus.calls == 1 and sum(fake_env.naps) == 0


def test_a_busy_shell_is_still_asked_again(fake_env, monkeypatch):
    bus = Bus(fake_env, "Command '['gdbus']' timed out after 5 seconds", 127)
    monkeypatch.setattr(fake_env, "run", bus)
    assert ts._known_state(fake_env, ts.ARCMENU, wait_s=1.0) is None
    assert bus.calls > 1 and sum(fake_env.naps) >= 1.0
    bus = Bus(fake_env, "Error: GDBus.Error:org.freedesktop.DBus.Error.NoReply: Timeout was reached\n")
    monkeypatch.setattr(fake_env, "run", bus)
    assert ts._known_state(fake_env, ts.ARCMENU, wait_s=1.0) is None and bus.calls > 1


def test_restore_with_no_shell_does_not_wait(fake_env, monkeypatch):
    from fedoraglass.engine import Engine
    from fedoraglass.settings import Settings
    from test_wait_for_glass import desktop
    eng = desktop(fake_env)
    eng.apply(Settings())
    fake_env.naps.clear()
    real = fake_env.run

    def run(argv, timeout=30):
        if "--dest" in argv and "org.gnome.Shell" in argv:
            return RunResult(1, "", NO_SHELL)
        return real(argv, timeout)
    monkeypatch.setattr(fake_env, "run", run)
    assert isinstance(eng, Engine) and eng.revert() == []
    assert sum(fake_env.naps) < 1.0
