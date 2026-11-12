"""Review 1528, app side: Remove waits for the background check instead of doing nothing,
Restore checks the system again, GNOME's accent is followed while the app is open, and the
values many bindings read on every slider tick are worked out once per change."""

from __future__ import annotations

import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from tests.test_gui_reliability import _apply, _backend, _spin  # noqa: E402


def _hold_check(monkeypatch, problems=None):
    """The background system check waits on the returned event; it reports `problems` in turn
    (then nothing). Returns (event, number of checks run)."""
    from fedoraglass.gui.backend import Backend
    gate = threading.Event()
    gate.set()
    runs = [0]
    problems = list(problems or [])

    def glass_problem(engine, s):
        gate.wait(10)
        runs[0] += 1
        return problems.pop(0) if problems else ("", "", "")
    monkeypatch.setattr(Backend, "_glass_problem", staticmethod(glass_problem))
    return gate, runs


def _wait(cond, ms=10000):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while not cond() and t.elapsed() < ms:
        QCoreApplication.processEvents()
    return cond()


# ---------------------------------------------------------------- B1: Remove during the check

def test_remove_while_the_background_check_runs_waits_then_removes(qml, fake_env, tmp_path, monkeypatch):
    from fedoraglass.gui.backend import Backend
    pkexec = tmp_path / "pkexec"
    pkexec.write_text("#!/bin/sh\nexit 0\n")
    pkexec.chmod(0o755)
    monkeypatch.setattr(Backend, "PKEXEC", pkexec)
    gate, _runs = _hold_check(monkeypatch)
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.6)
    _apply(b)
    assert (fake_env.home / "out/alpha.css").exists()
    b._remove_package = "fedora-glass"
    done: list = []
    b.removeFinished.connect(done.append)
    gate.clear()
    b.refreshTargets()                  # as after every Apply
    assert b._task is not None
    b.removeApp()
    # Not dropped: it waits, and the window says it is busy removing meanwhile.
    assert b._pending_action == "removeApp"
    assert b.property("busy") is True and b.property("busyKind") == "remove"
    assert (fake_env.home / "out/alpha.css").exists()
    gate.set()
    assert _wait(lambda: done)
    assert done == [True]
    assert not (fake_env.home / "out/alpha.css").exists()     # Restore original ran first
    assert b._pending_action is None and b.property("removing") is False


# ---------------------------------------------------------------- B2: Restore checks again

def test_restore_checks_the_system_again(qml, fake_env, tmp_path, monkeypatch):
    _gate, runs = _hold_check(monkeypatch, problems=[("error", "Glass hit an error", "boom")])
    b = _backend(fake_env, tmp_path)
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("glassProblem") == "error"
    seen: list = []
    b.targetsChanged.connect(lambda: seen.append(b.property("glassProblem")))
    b.revert()
    assert b.waitIdle()
    assert runs[0] == 2
    assert b.property("glassProblem") == "" and seen[-1] == ""


def test_restore_that_stops_puts_the_glass_back_as_it_was_and_checks_again(qml, fake_env, tmp_path, monkeypatch):
    _gate, runs = _hold_check(monkeypatch)
    b = _backend(fake_env, tmp_path)
    b._glass_live = True

    def broken():
        raise OSError("disk full")
    b._test_engine.revert = broken
    live_after: list = []
    errors: list = []
    b.failed.connect(lambda e: (errors.append(e), live_after.append(b._glass_live)))
    monkeypatch.setattr(type(b), "_restart_state", staticmethod(lambda engine, wanted: (True, False)))
    b.revert()
    assert b._glass_live is False          # while it runs, nothing writes the extension's config
    assert b.waitIdle()
    assert errors and "Restore stopped" in errors[0]
    assert live_after == [True]            # as it was before Restore
    assert runs[0] == 1                    # and checked again


# ---------------------------------------------------------------- B3: GNOME's accent

def test_a_new_gnome_accent_is_followed_while_the_app_is_open(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("accent", "system")
    assert b.property("systemAccent") == "blue"
    blue = b.property("uiAccent").name()
    heard: list = []
    tokens: list = []
    b.systemAccentChanged.connect(lambda: heard.append(b.property("systemAccent")))
    b.tokensChanged.connect(lambda: tokens.append(1))
    b._accent_lines("accent-color: 'teal'\n")
    assert heard == ["teal"] and b.property("systemAccent") == "teal"
    assert tokens and b.property("uiAccent").name() != blue
    assert b.property("uiAccent").name() == b.property("tokens")["accent"].name()
    # Lines about anything else, or the same accent again, change nothing.
    b._accent_lines("color-scheme: 'prefer-dark'\nnonsense\n")
    b._accent_lines("accent-color: 'teal'\n")
    assert heard == ["teal"]


def test_accent_watch_follows_gsettings_and_survives_a_missing_key(qml, fake_env, tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gs = bindir / "gsettings"
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setattr(type(fake_env), "which", lambda self, name: str(gs) if name == "gsettings" else None)
    # GNOME without the key: gsettings says so on stderr and stops.
    gs.write_text("#!/bin/sh\necho 'No such key “accent-color”' >&2\nexit 1\n")
    gs.chmod(0o755)
    b = _backend(fake_env, tmp_path)
    b._watch_accent()
    assert b._accent_monitor is not None and b._accent_monitor.waitForFinished(5000)
    _spin(50)
    assert b.property("systemAccent") == "blue"
    # A real change, as `gsettings monitor` prints it.
    gs.write_text("#!/bin/sh\n[ \"$*\" = 'monitor org.gnome.desktop.interface accent-color' ] || exit 2\n"
                  "echo \"accent-color: 'pink'\"\nsleep 5\n")
    b._watch_accent()
    assert _wait(lambda: b.property("systemAccent") == "pink", 5000)
    b.shutdown()
    assert b._accent_monitor is None
    # No gsettings at all: no watch.
    monkeypatch.setattr(type(fake_env), "which", lambda self, name: None)
    b._watch_accent()
    assert b._accent_monitor is None


# ---------------------------------------------------------------- S1: once per change

_CACHED = ("dirty", "changeCount", "changeList", "changedPages", "changedFromDefault", "canResetAll", "activeLook")


def _js(v):
    return v.toVariant() if hasattr(v, "toVariant") else v


def _uncached(b) -> dict:
    """The values as they were worked out before they were kept: every read from scratch."""
    from fedoraglass.gui import backend as bm
    from fedoraglass.gui import changes, looks
    from fedoraglass.settings import Settings
    dtp = b.hasDashToPanel
    dirty = bm._effective(b._s, dtp) != bm._effective(b._saved.normalized(), dtp)
    names = {t["id"]: t["name"] for t in b._targets}
    rows = changes.change_rows(b._s, b._saved, has_dash_to_panel=dtp, target_names=names,
                               system_accent=b._system_accent or "blue") if dirty else []
    pages: list = []
    for r in rows:
        if r["page"] not in pages:
            pages.append(r["page"])
    d, now = bm._effective(Settings(), dtp), bm._effective(b._s, dtp)
    from dataclasses import fields
    from_default = [f.name for f in fields(Settings) if f.name in now and f.name != "targets" and now[f.name] != d[f.name]]
    active = ""
    for look in b._look_list():
        if looks.holds(looks.look_values(look["settings"], b._cursor_installed), b._s):
            active = look["id"]
            break
    return {"dirty": dirty, "changeCount": len(rows), "changeList": rows, "changedPages": pages,
            "changedFromDefault": from_default,
            "canResetAll": bm._effective(b._all_reset(), dtp) != bm._effective(b._s, dtp),
            "activeLook": active}


def _read(b) -> dict:
    return {k: _js(b.property(k)) for k in _CACHED}


def test_kept_values_are_always_what_working_them_out_gives(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.refreshTargets()
    assert b.waitIdle()

    def check():
        for _ in range(3):           # the first read works it out, the others are kept
            assert _read(b) == _uncached(b)

    steps = [
        lambda: b.setProperty("frost", 0.61),
        lambda: b.setProperty("frost", 0.62),
        lambda: b.setProperty("radius", 30),
        lambda: b.setProperty("tint", "#335577"),
        lambda: b.saveLook("Mine"),
        lambda: b.setProperty("frost", 0.2),
        lambda: b.useLook(b.property("savedLooks")[0]["id"]),
        lambda: _apply(b),
        lambda: b.setTargetEnabled("alpha", False),
        lambda: b.setProperty("accent", "system"),
        lambda: b._accent_lines("accent-color: 'green'\n"),
        lambda: b.saveLook("Second"),
        lambda: b.setProperty("lockClock", "thin"),
        lambda: b.discardChanges(),
        lambda: b.resetDefaults(),
        lambda: b.renameLook(b.property("savedLooks")[0]["id"], "Renamed"),
        lambda: b.deleteLook(b.property("savedLooks")[0]["id"]),
        lambda: _apply(b),
        lambda: b.setProperty("frost", 0.9),
    ]
    check()
    for step in steps:
        step()
        check()
    # Dash to Panel found by the check after a start: "start on the desktop" may follow it.
    b._has_dtp = not b._has_dtp
    check()
    b.targetsChanged.emit()
    check()


def test_one_change_is_worked_out_once_however_often_it_is_read(qml, fake_env, tmp_path, monkeypatch):
    from fedoraglass.gui import backend as bm
    from fedoraglass.gui import looks
    b = _backend(fake_env, tmp_path)
    for n in range(5):
        b.setProperty("frost", 0.1 * (n + 1))
        b.saveLook(f"Look {n}")
    calls = {"rows": 0, "compared": 0}
    rows, compared = bm.changes_mod.change_rows, looks.compared

    def counted_rows(*a, **k):
        calls["rows"] += 1
        return rows(*a, **k)

    def counted_compared(*a, **k):
        calls["compared"] += 1
        return compared(*a, **k)
    monkeypatch.setattr(bm.changes_mod, "change_rows", counted_rows)
    monkeypatch.setattr(looks, "compared", counted_compared)
    b.setProperty("frost", 0.77)
    for _ in range(50):
        assert b.property("changedPages") == ["glass"]
        b.property("changeCount")
        b.property("changeList")
        b.property("dirty")
        b.property("activeLook")
    assert calls == {"rows": 1, "compared": 1}       # one look held against all five saved ones
    b.setProperty("frost", 0.78)
    b.property("changedPages")
    b.property("activeLook")
    assert calls == {"rows": 2, "compared": 2}


def test_bindings_on_every_tick_work_the_changes_out_once(qml, fake_env, tmp_path, monkeypatch):
    """As the sidebar's dots and the footer read them: one slider tick, one working out."""
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import backend as bm
    from tests.test_gui_reliability import _probe
    b = _probe(qml)
    calls = [0]
    rows = bm.changes_mod.change_rows

    def counted(*a, **k):
        calls[0] += 1
        return rows(*a, **k)
    monkeypatch.setattr(bm.changes_mod, "change_rows", counted)
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass.Core\nItem {\n"
                 b"  Repeater { model: 10; Item { property bool a: Backend.changedPages.indexOf('glass') >= 0 } }\n"
                 b"  property int n: Backend.changeCount\n  property bool d: Backend.dirty\n}", QUrl())
    obj = comp.create()
    assert obj is not None, comp.errorString()
    try:
        before = b.property("frost")
        calls[0] = 0
        b.setProperty("frost", 0.31 if before != 0.31 else 0.32)
        assert calls[0] == 1
        assert obj.property("n") == b.property("changeCount")
    finally:
        b.discardChanges()
        obj.deleteLater()
        _spin(20)


def test_closed_changes_sheet_reads_no_changes_and_open_shows_them(qml):
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        b.setProperty("frost", 0.66)
        sheet = _find(win, "changesSheet")
        assert _js(sheet.property("changes")) == []          # closed: not followed
        sheet.open()
        _spin(400)
        assert sheet.property("opened")
        assert [r["key"] for r in _js(sheet.property("changes"))] == ["frost"]
        assert sheet.property("detailsOpen") is False        # aboutToShow already saw the change
        assert sheet.property("subtitle") == "1 change not applied yet. Click one to go to it."
        sheet.close()
        _spin(400)
    finally:
        b.discardChanges()
        win.close()


def test_saved_look_tiles_read_the_active_look_once(qml):
    from fedoraglass.gui import app as gui_app
    from pathlib import Path
    text = (Path(gui_app.QML_DIR) / "FedoraGlass/SavedLooks.qml").read_text()
    assert text.count("Backend.activeLook") == 1
    assert "selected: root.activeLook === modelData.id" in text
