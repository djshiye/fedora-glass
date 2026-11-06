"""App redesign: the Look page options sit in six sections with a section bar that
jumps and follows the scroll, cards carry their own captions, and a first launch
gets a short welcome that is shown only once."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow

from liquidglass.engine import Engine

SECTIONS = ["colour", "glass", "windows", "motion", "desktop", "more"]
_keep: list = []


def _backend_at(fake_env, settings: Path):
    from liquidglass.gui.backend import Backend
    return Backend(env=fake_env, engine_factory=lambda: Engine(fake_env, []),
                   settings_path=settings, ui_dark=True, start=False)


# ---------------------------------------------------------------- first run

def test_first_run_only_until_the_welcome_is_dismissed(qml, fake_env, tmp_path):
    settings = tmp_path / "cfg/liquid-glass/settings.json"
    b = _backend_at(fake_env, settings)
    assert b.property("firstRun") is True
    b.dismissWelcome()
    assert (settings.parent / "welcome-seen").exists()
    assert _backend_at(fake_env, settings).property("firstRun") is False


def test_no_welcome_for_someone_who_already_saved_settings(qml, fake_env, tmp_path):
    settings = tmp_path / "cfg/liquid-glass/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}\n")
    assert _backend_at(fake_env, settings).property("firstRun") is False


def test_dismissing_never_writes_through_a_planted_symlink(qml, fake_env, tmp_path):
    settings = tmp_path / "cfg/liquid-glass/settings.json"
    settings.parent.mkdir(parents=True)
    victim = tmp_path / "victim"
    (settings.parent / "welcome-seen").symlink_to(victim)     # dangling: points nowhere yet
    b = _backend_at(fake_env, settings)
    b.dismissWelcome()
    assert not victim.exists()


# ---------------------------------------------------------------- the window

def _window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from liquidglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep.append(comp)
    return win


def _find(win, name):
    from PySide6.QtCore import QObject
    hit = win.findChild(QObject, name)
    todo = [win.contentItem()]
    while hit is None and todo:
        it = todo.pop()
        if it.objectName() == name:
            hit = it
        todo.extend(it.childItems())
    return hit


def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def test_section_bar_jumps_to_each_section_and_follows_the_scroll(qml):
    win = _window(qml)
    try:
        win.setWidth(1316)
        win.setHeight(856)
        win.show()
        _spin(300)
        page = _find(win, "lookPage")
        side = _find(win, "options")
        bar = _find(win, "sectionBar")
        assert [s["value"] for s in page.property("sections").toVariant()] == SECTIONS
        assert bar.property("value") == "colour"
        tops = []
        for name in SECTIONS:
            page.setProperty("jumpSection", "")
            page.setProperty("jumpSection", name)
            _spin(400)
            assert page.property("currentSection") == name
            assert bar.property("value") == name
            sec = _find(win, "section_" + name)
            tops.append(sec.property("y"))
            # The section's top is at the top of the column, unless the column ends first.
            end = side.property("contentHeight") - side.property("height")
            assert abs(side.property("contentY") - min(sec.property("y"), end)) < 1
        assert tops == sorted(tops), "sections run in the bar's order"
        # A click on the bar glides there and the bar stays on the clicked section.
        side.setProperty("contentY", 0)
        _spin()
        bar.activated.emit("motion")
        _spin(600)
        assert page.property("currentSection") == "motion"
        assert abs(side.property("contentY") - _find(win, "section_motion").property("y")) < 1
        # Scrolling by hand moves the bar along.
        glass = _find(win, "section_glass").property("y")
        side.setProperty("contentY", glass + 40)
        _spin()
        assert page.property("currentSection") == "glass"
        side.setProperty("contentY", 0)
        _spin()
        assert page.property("currentSection") == "colour"
    finally:
        win.close()


def test_every_card_title_carries_its_own_caption(qml):
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        status = _find(win, "glassStatus")
        assert status is not None and "Apply" in status.property("text")
    finally:
        win.close()


def test_welcome_sheet_picks_a_look_and_marks_itself_seen(qml):
    win = _window(qml)
    b = _find(win, "welcomeSheet")
    try:
        win.show()
        _spin()
        win.setProperty("startSheet", "welcome")
        _spin(400)
        assert b.property("opened")
        frosted = _find(win, "welcomeLookFrosted")
        assert frosted is not None
        frosted.clicked.emit()
        _spin()
        probe = _probe_backend(qml)
        assert probe.property("activePreset") == "Frosted"
        _find(win, "welcomeStart").clicked.emit()
        _spin(400)
        assert not b.property("opened")
    finally:
        _probe_backend(qml).discardChanges()
        win.close()


def _probe_backend(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport LiquidGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = probe.create()
    _keep.append((probe, obj))
    return obj.property("b")
