"""Logic breaks in the settings app, found on purpose and kept as regression tests: the
unapplied-changes model, saved looks, and sequences that cross each other."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from fedoraglass.engine import Engine  # noqa: E402
from fedoraglass.targets.base import Detection, Target, WriteFile  # noqa: E402

_keep: list = []


class _Part(Target):
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


def _apply(b):
    got: list = []
    b.applyFinished.connect(lambda rs: got.append(rs))
    b.apply()
    assert b.waitIdle()
    assert b.waitIdle()
    return got[-1] if got else None


def _on_disk(tmp_path) -> dict:
    return json.loads((tmp_path / "cfg/liquid-glass/settings.json").read_text())


def _probe(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = comp.create()
    _keep.append((comp, obj))
    return obj.property("b")


def _window(qml):
    from pathlib import Path

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


# ---------------------------------------------------------------- "Close when done" never hides a problem

def test_close_when_done_after_restore_with_problems_keeps_the_window_open(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b._busy = "revert"             # Restore runs
        b.busyChanged.emit()
        _spin()
        win.close()
        _spin(300)
        sheet = _find(win, "waitSheet")
        assert win.isVisible() and sheet.property("what") == "revert"
        _find(win, "closeWhenDone").clicked.emit()
        _spin(300)
        # Restore ends as the backend ends it: busy first, then what it found.
        b._busy = ""
        b.busyChanged.emit()
        b.revertFinished.emit(["/home/me/.config/gtk-4.0/gtk.css: permission denied"])
        _spin(400)
        assert win.isVisible(), "the problems Restore found were never shown"
        assert _find(win, "problemsSheet").property("opened")
    finally:
        b._busy = ""
        b.busyChanged.emit()
        win.setProperty("closeWhenIdle", False)
        _find(win, "problemsSheet").close()
        win.setProperty("closeAnyway", True)
        win.close()


def test_close_when_done_during_a_login_step_that_fails_shows_the_error(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b._login_proc = object()       # the login screen step waits for the password
        b.loginGlassChanged.emit()
        _spin()
        win.close()
        _spin(300)
        assert win.isVisible() and _find(win, "waitSheet").property("what") == "login"
        _find(win, "closeWhenDone").clicked.emit()
        _spin(300)
        b._login_proc = None
        b._login_failed = True
        b._login_note = "Nothing was changed: the login screen did not take these settings"
        b.loginGlassChanged.emit()
        _spin(400)
        assert win.isVisible(), "the login screen step failed and the window closed without a word"
        assert _find(win, "toast").property("text") == b._login_note
    finally:
        b._login_proc = None
        b._login_failed = False
        b._login_note = ""
        b.loginGlassChanged.emit()
        win.setProperty("closeWhenIdle", False)
        win.setProperty("closeAfterLogin", False)
        win.setProperty("closeAnyway", True)
        win.close()


def test_close_when_done_after_restore_waits_for_the_login_step_it_starts(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b._busy = "revert"
        b.busyChanged.emit()
        _spin()
        win.close()
        _spin(300)
        _find(win, "closeWhenDone").clicked.emit()
        _spin(300)
        # Restore ends and, in the same breath, starts turning the login screen's glass off.
        b._busy = ""
        b.busyChanged.emit()
        b.revertFinished.emit([])
        b._login_proc = object()
        b.loginGlassChanged.emit()
        _spin(400)
        # Still waiting quietly (no second "please wait" sheet to answer again)...
        assert win.isVisible() and not _find(win, "waitSheet").property("opened")
        b._login_proc = None
        b.loginGlassChanged.emit()
        _spin(400)
        # ...and closed once the login screen step is done.
        assert not win.isVisible()
    finally:
        b._busy = ""
        b._login_proc = None
        b.busyChanged.emit()
        b.loginGlassChanged.emit()
        win.setProperty("closeWhenIdle", False)
        win.setProperty("closeAfterLogin", False)
        win.setProperty("closeAnyway", True)
        win.close()


def test_close_when_done_after_a_restore_that_stops_shows_why(qml):
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b._busy = "revert"
        b.busyChanged.emit()
        _spin()
        win.close()
        _spin(300)
        _find(win, "closeWhenDone").clicked.emit()
        _spin(300)
        b._busy = ""
        b.busyChanged.emit()
        b.failed.emit("Restore stopped: disk full")
        _spin(400)
        assert win.isVisible() and _find(win, "toast").property("text") == "Restore stopped: disk full"
    finally:
        b._busy = ""
        b.busyChanged.emit()
        win.setProperty("closeWhenIdle", False)
        win.setProperty("closeAnyway", True)
        win.close()


# ---------------------------------------------------------------- saved looks

def test_renaming_a_look_to_another_looks_name_is_refused(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    evening = b.saveLook("Evening")
    b.setProperty("frost", 0.2)
    morning = b.saveLook("Morning")
    problems: list = []
    b.lookProblem.connect(problems.append)
    assert b.renameLook(morning, " evening ") == ""
    assert problems and "Evening" in problems[0]
    assert sorted(x["name"] for x in b.property("savedLooks")) == ["Evening", "Morning"]
    # Its own name in other letters is fine, and so is a new one.
    assert b.renameLook(evening, "EVENING") == evening
    assert b.renameLook(morning, "Dawn")
    assert sorted(x["name"] for x in b.property("savedLooks")) == ["Dawn", "EVENING"]


# ---------------------------------------------------------------- the weather card tells the truth

def test_weather_card_does_not_ask_for_apply_again_when_the_glass_is_not_running(qml):
    """Weather frost applied, but the glass isn't running (it starts after a restart, or
    GNOME's extensions are off): Apply was pressed already, so the card must not ask for it."""
    from dataclasses import replace
    b = _probe(qml)
    win = _window(qml)
    saved, live, frost = b._saved, b._glass_live, getattr(b, "_weather_frost", None)
    why = getattr(b, "_weather_state", None)
    try:
        win.show()
        win.setProperty("page", "glass")
        _spin(300)
        while getattr(b, "_weather_task", None) is not None:     # the look at GNOME Weather
            _spin(20)
        b._weather_state = "ready"          # GNOME Weather has a place
        b.weatherChanged.emit()
        text = _find(win, "weatherStatusText")
        b._weather_frost = {}               # the extension never wrote a reading
        b.setProperty("weatherFrost", True)     # not applied yet
        b.weatherFrostChanged.emit()
        _spin()
        assert text.property("text") == "Apply, and the glass starts following the weather."
        b._saved = replace(b._saved, weather_frost=True)    # applied
        b._glass_live = False
        b.settingsChanged.emit()
        b.targetsChanged.emit()
        _spin()
        assert not b.property("dirty")
        assert text.property("text") == "Apply, then restart your PC once to start the glass."
    finally:
        b._saved, b._glass_live, b._weather_frost, b._weather_state = saved, live, frost, why
        b.weatherChanged.emit()
        b.discardChanges()
        b.targetsChanged.emit()
        win.setProperty("closeAnyway", True)
        win.close()


# ---------------------------------------------------------------- "Apply and lock" with the login screen's glass on

def test_apply_and_lock_waits_for_the_login_screen_password(qml, fake_env, tmp_path, monkeypatch):
    """Apply brings the login screen along and asks for the password: locking the screen at
    that same moment would put the lock screen over the password prompt."""
    from PySide6.QtCore import QCoreApplication, QElapsedTimer

    from fedoraglass.gui.backend import Backend
    pkexec = tmp_path / "pkexec"
    pkexec.write_text("#!/bin/sh\nsleep 0.3\nexit 0\n")
    pkexec.chmod(0o755)
    monkeypatch.setattr(Backend, "PKEXEC", pkexec)
    b = _backend(fake_env, tmp_path)
    b._login_available = lambda: True
    b._read_login_state = lambda: "on"
    b._login_stale = lambda s=None: True
    locked: list = []
    b.lockScreenNow = lambda: locked.append(b.property("loginGlass"))
    b.setProperty("lockBlur", 40)
    b.applyAndLock()
    assert b.waitIdle() and b.waitIdle()
    assert b.property("loginGlass") == "busy" and locked == [], "locked while the password is asked for"
    t = QElapsedTimer()
    t.start()
    while b.property("loginGlass") == "busy" and t.elapsed() < 5000:
        QCoreApplication.processEvents()
    QCoreApplication.processEvents()
    assert locked == ["on"]
    # Once only: later login screen changes don't lock the screen again.
    b.loginGlassChanged.emit()
    assert locked == ["on"]


def test_adding_a_look_file_twice_gives_two_names_not_two_tiles_that_read_the_same(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    look = b.saveLook("Evening")
    out = tmp_path / "evening.json"
    assert b.exportLook(look, str(out))
    said: list = []
    b.noticed.connect(said.append)
    first = b.importLook(str(out))
    second = b.importLook(str(out))
    assert first and second and len({look, first, second}) == 3
    names = sorted(x["name"] for x in b.property("savedLooks"))
    assert names == ["Evening", "Evening 2", "Evening 3"]
    assert said[-1] == "Added “Evening 3”. Pick it to try it."


# ---------------------------------------------------------------- Undo is the look applied last

def test_undo_after_a_new_wallpaper_goes_back_to_the_applied_colours(qml, fake_env, tmp_path):
    """Tint follows the wallpaper, and the wallpaper changed since Apply (the app says so and
    keeps the applied colour until Apply). Changing the style and pressing Undo must leave
    nothing unapplied: Undo is the look applied last, not that look with the new picture's colour."""
    import time

    from tests.test_gui_features_looks import _hue, _picture, _settle
    pic = _picture(tmp_path / "wall.png", "#8a2be2")         # violet
    bg = fake_env.gs.setdefault(("org.gnome.desktop.background", None), {})
    bg["picture-uri"] = bg["picture-uri-dark"] = f"'file://{pic}'"
    b = _backend(fake_env, tmp_path)
    own = b.settings().tint
    b.setProperty("tintFromWallpaper", True)
    assert _settle(lambda: b.settings().tint != own)
    _apply(b)
    applied = b.settings().tint
    assert 260 < _hue(applied) < 290
    time.sleep(0.01)
    _picture(pic, "#2e8b57")                           # sea green, same file
    os.utime(pic, ns=(time.time_ns(), time.time_ns() + 10**9))
    assert b.property("wallpaperChangedSince") and not b.property("dirty")
    b.setProperty("scheme", "light")                   # the preview takes the new picture's colour
    assert _settle(lambda: b.settings().tint != applied)
    b.discardChanges()
    _settle(lambda: False, 300)
    assert b.settings().tint == applied
    assert not b.property("dirty") and b.property("changeCount") == 0
