"""The flow after Apply: "Restart to finish" until the glass runs (footer, results sheet and a
way to GNOME's own restart dialog), skipped parts folded into one row, a welcome that can
apply the look it shows, "Apply and lock" on the Lock screen page, and a plain sentence per
part in "Show changes"."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from fedoraglass.engine import WAITING, Engine  # noqa: E402
from fedoraglass.targets.base import Detection, Target, WriteFile  # noqa: E402
from fedoraglass.targets.shell import GlassEffects  # noqa: E402

_keep: list = []


class _Part(Target):
    """A themed app: one file, no glass needed."""

    def __init__(self, tid, home, available=True, plain="", fail=False):
        super().__init__(id=tid, name=tid.title(), group="Apps", summary=f"{tid} summary", plain=plain)
        self._home, self._available, self._fail = home, available, fail

    def detect(self, env):
        return Detection(self._available, "" if self._available else f"{self.name} is not installed")

    def plan(self, ctx):
        if self._fail:
            raise RuntimeError("broken on purpose")
        return [WriteFile(self._home / f"out/{self.id}.css", f"chrome {ctx.tokens.chrome.css}\n")]


def _backend(fake_env, targets, tmp_path):
    from fedoraglass.gui.backend import Backend
    b = Backend(env=fake_env, engine_factory=lambda: Engine(fake_env, targets),
                settings_path=tmp_path / "cfg/liquid-glass/settings.json", ui_dark=True, start=False)
    _keep.append(b)
    return b


def _apply(b) -> list:
    got: list = []
    b.applyFinished.connect(lambda rs: got.append(rs))
    b.apply()
    assert b.waitIdle()
    assert b.waitIdle()        # the re-check Apply starts afterwards
    assert got, "Apply never finished"
    return got[-1]


# ---------------------------------------------------------------- restart to finish

def test_restart_needed_after_applying_the_glass_until_it_runs_and_not_after_restore(qml, fake_env, tmp_path):
    fake_env.glass_loaded = False          # a brand-new extension: GNOME starts it at the next login
    b = _backend(fake_env, [GlassEffects(), _Part("alpha", fake_env.home)], tmp_path)
    assert b.property("restartNeeded") is False
    seen: list = []
    b.restartNeededChanged.connect(lambda: seen.append(b.property("restartNeeded")))
    results = _apply(b)
    assert any(r["id"] == "glass" and r["status"] == "applied" for r in results)
    assert b.property("glassLive") is False
    assert b.property("restartNeeded") is True
    assert seen and seen[0] is True        # already known when applyFinished arrives
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("restartNeeded") is True
    b.revert()
    assert b.waitIdle()
    assert b.property("restartNeeded") is False


def test_no_restart_needed_when_the_glass_already_runs(qml, fake_env, tmp_path):
    fake_env.glass_loaded = True
    b = _backend(fake_env, [GlassEffects(), _Part("alpha", fake_env.home)], tmp_path)
    _apply(b)
    assert b.property("glassLive") is True
    assert b.property("restartNeeded") is False


def test_no_restart_needed_with_the_glass_off(qml, fake_env, tmp_path):
    fake_env.glass_loaded = False
    b = _backend(fake_env, [GlassEffects(), _Part("alpha", fake_env.home)], tmp_path)
    b.setTargetEnabled("glass", False)
    _apply(b)
    assert b.property("restartNeeded") is False


def test_parts_waiting_for_the_glass_need_a_restart(qml, fake_env, tmp_path):
    from fedoraglass.engine import pending_path
    fake_env.glass_loaded = True
    b = _backend(fake_env, [GlassEffects(), _Part("alpha", fake_env.home)], tmp_path)
    _apply(b)
    assert b.property("restartNeeded") is False
    pending_path().parent.mkdir(parents=True, exist_ok=True)
    pending_path().write_text(json.dumps(["dash-to-panel"]))
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("restartNeeded") is True


def test_restart_opens_gnomes_own_dialog_and_never_forces(qml, fake_env, tmp_path):
    b = _backend(fake_env, [], tmp_path)
    calls: list = []
    b._detach = lambda program, args: calls.append((program, list(args))) or True
    errors: list = []
    b.failed.connect(errors.append)
    b.restartPC()
    assert calls == [("/usr/bin/gnome-session-quit", ["--reboot"])]
    assert not errors
    fake_env.which = lambda name: None
    b.restartPC()
    assert len(calls) == 1
    assert errors and "system menu" in errors[0]


# ---------------------------------------------------------------- the window

def _probe(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = comp.create()
    _keep.append((comp, obj))
    return obj.property("b")


def _create(qml, *parts):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR).joinpath(*parts))))
    obj = comp.create()
    assert obj is not None, comp.errorString()
    _keep.append(comp)
    return obj


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


def test_footer_says_restart_to_finish_with_a_restart_button(qml):
    b = _probe(qml)
    win = _create(qml, "Main.qml")
    try:
        assert not b.property("dirty")
        text, button = _find(win, "statusText"), _find(win, "restartButton")
        assert text.property("text") in ("Not applied yet", "Up to date")
        assert not button.property("visible")
        b._set_restart_needed(True)
        _spin()
        assert text.property("text") == "Restart to finish"
        assert button.property("visible")
        assert button.property("text") == "Restart…"
        assert "GNOME asks" in button.property("tip")
        b.setProperty("frost", 0.91 if b.property("frost") != 0.91 else 0.5)    # unapplied changes win
        _spin()
        assert text.property("text") == "1 change not applied yet"
        assert not button.property("visible")
    finally:
        b._set_restart_needed(False)
        b.discardChanges()
        win.close()
        win.deleteLater()


def _open_sheet(qml, name, **props):
    win = _create(qml, "Main.qml")
    win.show()
    _spin()
    sheet = _find(win, name)
    for k, v in props.items():
        sheet.setProperty(k, v)
    sheet.open()
    _spin(400)
    return win, sheet


def _rows(sheet):
    return sheet.property("rows").toVariant()


def test_results_sheet_offers_restart_now_or_later(qml):
    b = _probe(qml)
    gtk = {"id": "gtk4", "name": "GTK 4", "status": "applied", "message": ""}
    win, sheet = _open_sheet(qml, "resultsSheet", results=[gtk])
    try:
        items = _items(sheet.property("contentItem"))
        main = next(i for i in items if i.objectName() in ("resultsDone", "restartNow"))
        later = next(i for i in items if i.objectName() == "restartLater")
        assert main.property("text") == "Done" and not later.property("visible")
        b._set_restart_needed(True)
        _spin()
        assert sheet.property("title") == "Applied. Restart your PC to finish"
        assert main.property("text") == "Restart now…" and main.objectName() == "restartNow"
        assert main.property("kind") == "primary"
        assert later.property("visible") and later.property("text") == "Later"
        assert later.property("kind") == "secondary"
        b._set_restart_needed(False)
        waiting = {"id": "shell", "name": "GNOME Shell", "status": "info", "message": WAITING, "restart": True}
        sheet.setProperty("results", [gtk, waiting])      # the results alone still say so
        assert sheet.property("needsRestart") is True
    finally:
        b._set_restart_needed(False)
        win.close()
        win.deleteLater()


def test_results_sheet_folds_many_skipped_parts_into_one_row(qml):
    applied = [{"id": f"a{i}", "name": f"A{i}", "status": "applied", "message": ""} for i in range(3)]
    notes = [{"id": "n", "name": "N", "status": "info", "message": "a note"}]
    skipped = [{"id": f"s{i}", "name": f"S{i}", "status": "skipped", "message": "not installed"} for i in range(23)]
    win, sheet = _open_sheet(qml, "resultsSheet", results=skipped[:5] + applied + notes + skipped[5:])
    try:
        rows = _rows(sheet)
        assert sheet.property("shownRows") == 3 + 1 + 1   # applied, the note, one folded row
        assert rows[4].get("fold") is True and all(r["status"] == "skipped" for r in rows[5:])
        items = _items(sheet.property("contentItem"))
        fold = next(i for i in items if i.objectName() == "skippedFold" and i.property("visible"))
        label = next(i for i in items if i.objectName() == "skippedFoldText" and i.property("visible"))
        assert label.property("text") == "23 parts not installed here, skipped"
        names = [i.property("text") for i in _items(sheet.property("contentItem"))
                 if i.property("visible") and str(i.property("text") or "").startswith("S")]
        assert names == []                                # the skipped ones stay folded away
        fold.clicked.emit()
        _spin()
        assert sheet.property("skippedOpen") is True
        assert sheet.property("shownRows") == 5 + 23     # opened inline, after the folded row
        assert fold.property("visible")                   # the same row: it keeps the focus
        fold.forceActiveFocus()
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        QTest.keyClick(win, Qt.Key_Space)
        _spin()
        assert sheet.property("skippedOpen") is False     # and the keyboard folds it again
        QTest.keyClick(win, Qt.Key_Return)
        _spin()
        assert sheet.property("skippedOpen") is True
        # One or two skipped parts: shown as they are, no fold.
        sheet.setProperty("results", applied + skipped[:2])
        rows = _rows(sheet)
        assert len(rows) == 5 and sheet.property("shownRows") == 5 and not any(r.get("fold") for r in rows)
        assert sheet.property("skippedOpen") is False
    finally:
        win.close()
        win.deleteLater()


def test_welcome_apply_button_applies_and_customise_only_closes(qml):
    b = _probe(qml)
    win = _create(qml, "Main.qml")
    sheet = _find(win, "welcomeSheet")
    try:
        win.show()
        _spin()
        win.setProperty("startSheet", "welcome")
        _spin(400)
        assert sheet.property("opened")
        start, apply = _find(win, "welcomeStart"), _find(win, "welcomeApply")
        assert start.property("text") == "Customise first" and start.property("kind") == "secondary"
        assert apply.property("text") == "Apply this look" and apply.property("kind") == "primary"
        got: list = []
        b.applyFinished.connect(lambda rs: got.append(rs))
        start.clicked.emit()
        _spin(400)
        assert not sheet.property("opened") and not got and not b.property("busy")
        sheet.open()
        _spin(400)
        apply.clicked.emit()
        assert b.waitIdle()
        _spin(400)
        assert not sheet.property("opened")
        assert got, "Apply this look did not apply"
    finally:
        win.close()
        win.deleteLater()


def test_welcome_says_what_it_found(qml, fake_env, tmp_path):
    def with_extensions(*uuids):
        for u in uuids:
            d = fake_env.data / "gnome-shell/extensions" / u
            d.mkdir(parents=True, exist_ok=True)
            (d / "metadata.json").write_text("{}")
        fake_env.gs.setdefault(("org.gnome.shell", None), {})["enabled-extensions"] = repr(list(uuids))

    from fedoraglass.targets.shell import DashToPanel
    b = _backend(fake_env, [DashToPanel()], tmp_path)
    assert b.property("foundSummary") == ""             # nothing said before the check
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("foundSummary") == "Found on this PC: GNOME's own top bar."
    with_extensions("ubuntu-dock@ubuntu.com")
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("foundSummary") == "Found on this PC: GNOME's own top bar and Ubuntu Dock."
    with_extensions("dash-to-panel@jderose9.github.com", "arcmenu@arcmenu.com")
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("foundSummary") == "Found on this PC: Dash to Panel and ArcMenu."


def test_lock_button_reads_apply_and_lock_with_unapplied_changes(qml):
    b = _probe(qml)
    win = _create(qml, "Main.qml")
    try:
        win.setProperty("page", "lock")
        _spin()
        lock = _find(win, "lockNow")
        assert lock.property("kind") == "secondary"
        assert lock.property("text") == "Lock now"
        b.setProperty("frost", 0.91 if b.property("frost") != 0.91 else 0.5)
        _spin()
        assert b.property("dirty")
        assert lock.property("text") == "Apply and lock"
        assert "then locks" in lock.property("tip")
        status = _find(win, "lockStatus")
        assert "after Apply" in status.property("text")
    finally:
        b.discardChanges()
        win.close()
        win.deleteLater()


def _lock_counter(b):
    locks: list = []
    b.lockScreenNow = lambda: locks.append(1)
    return locks


def test_apply_and_lock_locks_once_the_apply_went_well(qml, fake_env, tmp_path):
    fake_env.glass_loaded = True
    b = _backend(fake_env, [_Part("alpha", fake_env.home)], tmp_path)
    locks = _lock_counter(b)
    b.applyAndLock()                       # nothing to apply: just locks
    assert locks == [1]
    b.setProperty("frost", 0.9)
    assert b.property("dirty")
    b.applyAndLock()
    assert locks == [1]                    # not before the Apply is done
    assert b.waitIdle() and b.waitIdle()
    assert locks == [1, 1]
    assert not b.property("dirty") and (fake_env.home / "out/alpha.css").exists()
    b.setProperty("frost", 0.4)
    _apply(b)                              # a plain Apply never locks
    assert locks == [1, 1]


def test_apply_and_lock_does_not_lock_after_a_failure_or_before_a_restart(qml, fake_env, tmp_path):
    b = _backend(fake_env, [_Part("alpha", fake_env.home, fail=True)], tmp_path)
    locks = _lock_counter(b)
    b.setProperty("frost", 0.9)
    b.applyAndLock()
    assert b.waitIdle() and b.waitIdle()
    assert locks == []
    fake_env.glass_loaded = False
    b2 = _backend(fake_env, [GlassEffects()], tmp_path / "b2")
    locks2 = _lock_counter(b2)
    b2.setProperty("frost", 0.9)
    b2.applyAndLock()
    assert b2.waitIdle() and b2.waitIdle()
    assert b2.property("restartNeeded") is True and locks2 == []


# ---------------------------------------------------------------- Show changes

def test_plan_carries_a_plain_sentence_per_part(qml, fake_env, tmp_path):
    b = _backend(fake_env, [_Part("alpha", fake_env.home, plain="Gives Alpha the glass colours."),
                            _Part("beta", fake_env.home)], tmp_path)
    got: list = []
    b.planReady.connect(lambda plan: got.append(plan))
    b.requestPlan()
    assert b.waitIdle()
    plan = {p["id"]: p for p in got[-1]}
    assert plan["alpha"]["plain"] == "Gives Alpha the glass colours."
    assert plan["beta"]["plain"] == ""
    assert plan["alpha"]["actions"]                   # the raw lines are still there


def test_every_part_says_in_plain_words_what_apply_changes():
    from fedoraglass.targets import all_targets
    from fedoraglass.targets.shell import GnomeShell
    for t in all_targets():
        assert t.plain.strip(), t.id
        assert t.plain.endswith("."), t.id
        assert t.plain != t.summary, t.id
    assert "User Themes" in GnomeShell().plain


def test_changes_sheet_shows_the_plain_sentence_above_the_lines(qml):
    plan = [{"id": "shell", "name": "GNOME Shell", "plain": "Turns on User Themes.",
             "actions": [{"kind": "GSet", "text": "org.gnome.shell x: y"}]},
            {"id": "gtk4", "name": "GTK 4", "plain": "",
             "actions": [{"kind": "WriteFile", "text": "~/.config/gtk-4.0/gtk.css"}]}]
    win, sheet = _open_sheet(qml, "changesSheet", plan=plan)
    try:
        items = _items(sheet.property("contentItem"))
        shell = next(i for i in items if i.objectName() == "plain_shell")
        gtk = next(i for i in items if i.objectName() == "plain_gtk4")
        assert shell.property("visible") and shell.property("text") == "Turns on User Themes."
        assert not gtk.property("visible")
        line = next(i for i in items if i.property("text") == "org.gnome.shell x: y")
        assert line.mapToItem(sheet.property("contentItem"), 0, 0).y() > \
            shell.mapToItem(sheet.property("contentItem"), 0, 0).y()      # above the raw lines
    finally:
        sheet.close()
        win.close()
        win.deleteLater()
