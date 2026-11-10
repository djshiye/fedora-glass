"""App redesign: a sidebar of pages built when first shown, one shared preview,
settings search, cards that carry their own captions, and a first-launch welcome
that is shown only once."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow

from fedoraglass.engine import Engine

PAGES = ["home", "colour", "glass", "windows", "motion", "pointer", "lock", "apps", "advanced", "about"]
_keep: list = []


def _backend_at(fake_env, settings: Path):
    from fedoraglass.gui.backend import Backend
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

    from fedoraglass.gui import app as gui_app
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


def test_sidebar_and_ctrl_numbers_open_each_page(qml):
    """Every sidebar item opens its page, built the first time it shows, and Ctrl+1 to
    Ctrl+9 follow the sidebar's order."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    win = _window(qml)
    try:
        win.setWidth(1316)
        win.setHeight(856)
        win.show()
        win.requestActivate()
        _spin(300)
        ids = [p["id"] for p in win.property("pageList").toVariant()]
        assert ids == PAGES
        assert win.property("page") == "home"
        assert _find(win, "glassPage") is None, "pages are built only when first shown"
        for pid in ids:
            _find(win, "nav_" + pid).clicked.emit()
            _spin(80)
            assert win.property("page") == pid
            page = _find(win, pid + "Page")
            assert page is not None and page.property("visible"), pid
        for n, pid in enumerate(ids[:9], start=1):
            QTest.keyClick(win, Qt.Key(Qt.Key_0 + n), Qt.ControlModifier)
            _spin(40)
            assert win.property("page") == pid
    finally:
        win.close()


def test_the_one_preview_follows_the_page(qml):
    """One preview for the whole app: it moves into the slot of each page that has one."""
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        preview = _find(win, "preview")
        for pid in ("home", "colour", "glass", "lock", "advanced"):
            win.setProperty("page", pid)
            _spin(80)
            if pid == "lock":       # the lock page shows its own lock-screen preview
                continue
            slot = _find(win, pid + "PreviewSlot")
            assert slot is not None, pid
            pane = preview.parentItem()
            assert pane.parentItem() == slot, pid
        assert len([1 for _ in _all(win, "preview")]) == 1
    finally:
        win.close()


def _all(win, name):
    todo = [win.contentItem()]
    while todo:
        it = todo.pop()
        if it.objectName() == name:
            yield it
        todo.extend(it.childItems())


def test_every_card_title_carries_its_own_caption(qml):
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        win.setProperty("page", "glass")
        _spin(100)
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
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    obj = probe.create()
    _keep.append((probe, obj))
    return obj.property("b")


def test_every_search_result_lands_on_a_real_control(qml):
    """Each entry in the search index names a control that exists on its page, so a
    search never opens a page and then finds nothing to light up."""
    import re
    from fedoraglass.gui import app as gui_app
    index = (Path(gui_app.QML_DIR) / "FedoraGlass" / "searchindex.js").read_text()
    entries = re.findall(r'page: "(\w+)", name: "(\w+)"', index)
    assert len(entries) >= 50
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        for page in PAGES:
            win.setProperty("page", page)
            _spin(60)
        missing = []
        for page, name in entries:
            root = _find(win, page + "Page")
            hit = None
            todo = [root] if root is not None else []
            while todo and hit is None:
                it = todo.pop()
                if it.objectName() == name:
                    hit = it
                todo.extend(it.childItems())
            if hit is None:
                missing.append(f"{page}/{name}")
        assert not missing, f"search names with no control on their page: {missing}"
    finally:
        win.close()
