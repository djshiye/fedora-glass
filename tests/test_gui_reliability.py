"""The reliability release, app side: "applied" means applied, nothing runs over a package
removal or the login screen step, one source for the presets, search that only finds what
is there, a window that fits a 1280x720 screen, and the slow parts off the UI thread."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from fedoraglass import settings as settings_mod  # noqa: E402
from fedoraglass.engine import Engine  # noqa: E402
from fedoraglass.targets.base import Detection, Target, WriteFile  # noqa: E402

_keep: list = []


class _Part(Target):
    """A themed app: one file. `fail` makes its part of Apply fail."""

    def __init__(self, tid, home, fail=False):
        super().__init__(id=tid, name=tid.title(), group="Apps", summary=f"{tid} summary")
        self._home, self.fail = home, fail

    def detect(self, env):
        return Detection(True, "")

    def plan(self, ctx):
        if self.fail:
            raise RuntimeError("broken on purpose")
        return [WriteFile(self._home / f"out/{self.id}.css", f"chrome {ctx.tokens.chrome.css}\n")]


class _Engine(Engine):
    """An Engine that can stop dead in the middle of Apply (a crash, not a failed part)."""

    crash = False

    def apply(self, s, *a, **k):
        if self.crash:
            raise OSError("disk full")
        return super().apply(s, *a, **k)


def _backend(fake_env, tmp_path, targets=None):
    from fedoraglass.gui.backend import Backend
    targets = targets if targets is not None else [_Part("alpha", fake_env.home), _Part("beta", fake_env.home)]
    eng = _Engine(fake_env, targets)
    b = Backend(env=fake_env, engine_factory=lambda: eng,
                settings_path=tmp_path / "cfg/liquid-glass/settings.json", ui_dark=True, start=False)
    b._test_engine = eng
    _keep.append(b)
    return b


def _apply(b) -> list | None:
    got: list = []
    b.applyFinished.connect(lambda rs: got.append(rs))
    b.apply()
    assert b.waitIdle()
    assert b.waitIdle()        # the re-check Apply starts afterwards
    return got[-1] if got else None


def _on_disk(tmp_path) -> dict:
    return json.loads((tmp_path / "cfg/liquid-glass/settings.json").read_text())


# ---------------------------------------------------------------- 1. applied means applied

def test_apply_that_stops_keeps_the_changes_unapplied_and_the_file_on_the_applied_look(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    assert _apply(b) is not None
    assert _on_disk(tmp_path)["frost"] == 0.3
    b.setProperty("frost", 0.9)
    b.setProperty("radius", 30)
    assert b.property("changeCount") == 2
    errors: list = []
    b.failed.connect(errors.append)
    b._test_engine.crash = True
    assert _apply(b) is None
    assert errors and "Apply stopped" in errors[0]
    # The watcher re-applies settings.json on a dark/light flip: it must hold the look applied.
    assert _on_disk(tmp_path)["frost"] == 0.3 and _on_disk(tmp_path)["radius"] != 30
    assert b.property("dirty") and b.property("changeCount") == 2
    assert b.property("partlyApplied") == 0
    b.discardChanges()
    assert b.settings().frost == 0.3 and not b.property("dirty")


def test_apply_with_failed_parts_says_so_and_undo_goes_to_the_last_full_look(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    _apply(b)
    assert b.property("partlyApplied") == 0
    b._test_engine.targets[1].fail = True
    b.setProperty("frost", 0.7)
    rows = _apply(b)
    assert [r["status"] for r in rows].count("failed") == 1
    # What did apply is the applied look, and settings.json says so (the watcher keeps it).
    assert not b.property("dirty")
    assert _on_disk(tmp_path)["frost"] == 0.7
    assert b.property("partlyApplied") == 1
    assert [r["status"] for r in b.property("partialResults")] == [r["status"] for r in rows]
    # Undo: back to the last look that applied fully, to apply again.
    b.discardChanges()
    assert b.settings().frost == 0.3 and b.property("dirty")
    b._test_engine.targets[1].fail = False
    _apply(b)
    assert b.property("partlyApplied") == 0 and not b.property("dirty")
    assert _on_disk(tmp_path)["frost"] == 0.3


def test_remove_only_switch_during_apply_survives_both_endings(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.6)
    b._test_engine.crash = True
    b.apply()
    b.setProperty("undoOnRemove", False)          # saved at once, while Apply runs
    assert _on_disk(tmp_path)["frost"] == 0.6     # the file still holds the look being applied
    assert b.waitIdle()
    assert _on_disk(tmp_path)["undo_on_remove"] is False
    assert _on_disk(tmp_path)["frost"] != 0.6
    b._test_engine.crash = False
    b.apply()
    b.setProperty("undoOnRemove", True)
    assert b.waitIdle() and b.waitIdle()
    assert _on_disk(tmp_path)["undo_on_remove"] is True and _on_disk(tmp_path)["frost"] == 0.6


def _probe(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = comp.create()
    _keep.append((comp, obj))
    return obj.property("b")


def _window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep.append(comp)
    return win


def _items(root):
    todo, out = [root], []
    while todo:
        it = todo.pop()
        out.append(it)
        todo.extend(it.childItems())
    return out


def _find(win, name):
    from PySide6.QtCore import QObject
    hit = win.findChild(QObject, name)
    if hit is None:
        hit = next((it for it in _items(win.contentItem()) if it.objectName() == name), None)
    return hit


def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def test_footer_says_partly_applied_and_opens_the_results(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        rows = [{"id": "a", "name": "A", "status": "applied", "message": ""},
                {"id": "b", "name": "B", "status": "failed", "message": "no room"},
                {"id": "c", "name": "C", "status": "failed", "message": "no room"}]
        b._set_partial(rows)
        _spin()
        assert _find(win, "statusText").property("text") == "2 parts didn't change."
        see = _find(win, "partialButton")
        assert see.property("visible") and see.property("text") == "See what happened"
        assert _find(win, "discardButton").property("visible")
        see.clicked.emit()
        _spin(400)
        sheet = _find(win, "resultsSheet")
        assert sheet.property("opened")
        assert sheet.property("failedCount") == 2
        sheet.close()
    finally:
        b._set_partial([])
        win.close()


# ---------------------------------------------------------------- 2. nothing runs over a removal

def test_removing_counts_as_busy_and_blocks_apply_restore_and_plan(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    seen: list = []
    b.busyChanged.connect(lambda: seen.append(b.property("busy")))
    b._set_removing(True)
    try:
        assert b.property("busy") and b.property("busyKind") == "remove" and seen == [True]
        b.setProperty("frost", 0.2)
        b.apply()
        b.revert()
        b.requestPlan()
        assert b._task is None and b._pending_action is None
        assert not (tmp_path / "cfg/liquid-glass/settings.json").exists()
    finally:
        b._set_removing(False)
    assert not b.property("busy")


def test_window_does_not_close_while_the_app_is_being_removed(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b._set_removing(True)
        _spin()
        assert _find(win, "applyButton").property("enabled") is False
        win.close()
        _spin(400)
        assert win.isVisible()
        sheet = _find(win, "waitSheet")
        assert sheet.property("opened") and sheet.property("title") == "Fedora Glass is being removed"
        assert not _find(win, "closeWhenDone").property("visible")
        sheet.close()
    finally:
        b._set_removing(False)
        win.close()


def test_apply_starts_the_login_screen_step_before_it_reports(qml, fake_env, tmp_path, monkeypatch):
    from fedoraglass.gui.backend import Backend
    pkexec = tmp_path / "pkexec"
    pkexec.write_text("#!/bin/sh\nsleep 0.3\nexit 0\n")
    pkexec.chmod(0o755)
    monkeypatch.setattr(Backend, "PKEXEC", pkexec)
    b = _backend(fake_env, tmp_path)
    b._login_available = lambda: True
    b._read_login_state = lambda: "on"
    b._login_stale = lambda s=None: True
    states: list = []
    b.applyFinished.connect(lambda rs: states.append(b.property("loginGlass")))
    _apply(b)
    assert states == ["busy"]
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while b.property("loginGlass") == "busy" and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    assert b.property("loginGlass") == "on" and not b.property("loginGlassFailed")


def test_apply_and_close_waits_for_the_login_screen_step(qml):
    b = _probe(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        win.setProperty("closeAfterApply", True)
        b._login_proc = object()           # the login screen step asks for the password
        b.loginGlassChanged.emit()
        b.applyFinished.emit([])
        _spin(200)
        assert win.isVisible() and win.property("closeAfterLogin")
        win.close()                        # pressing close meanwhile asks to wait too
        _spin(300)
        assert win.isVisible() and _find(win, "waitSheet").property("what") == "login"
        _find(win, "waitSheet").close()
        b._login_proc = None
        b.loginGlassChanged.emit()
        _spin(200)
        assert not win.isVisible()
    finally:
        b._login_proc = None
        win.setProperty("closeAfterLogin", False)
        win.close()


# ---------------------------------------------------------------- 3. the login screen gets the applied look

def test_login_glass_button_uses_the_applied_look_not_the_sliders(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    _apply(b)
    assert not b.property("loginGlassBehind")
    b.setProperty("frost", 0.95)
    assert b.property("loginGlassBehind")
    b.setProperty("glassQuality", "lightest")       # not on the login screen: no note for it
    ran: list = []
    b._run_login = lambda args, done: ran.append(args)
    b.turnOnLoginGlass()
    assert ran and ran[0][0] == "apply" and ran[0][-1] == "0.300"
    b.setProperty("frost", 0.3)
    assert not b.property("loginGlassBehind")
