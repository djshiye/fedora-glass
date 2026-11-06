"""App polish after 1.5.7: closing with unapplied changes asks first, Undo changes,
Tab scrolls the focused control into view, the window fits small screens, and the
results sheet only asks for a restart when one is needed."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow


def _backend(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport LiquidGlass.Core\nQtObject { property var b: Backend }", QUrl())
    return probe.create().property("b")


def _window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from liquidglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep.append(comp)      # the window lives only as long as its component
    return win


_keep: list = []


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


def test_closing_with_unapplied_changes_asks_first(qml):
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin()
        sheet = _find(win, "leaveSheet")
        b.setProperty("frost", 0.9 if b.property("frost") < 0.85 else 0.2)
        assert b.property("dirty") is True
        win.close()
        _spin(400)
        assert win.isVisible(), "unapplied changes must not be lost without a word"
        assert sheet.property("opened") or sheet.property("visible")
        # "Close without applying" closes for real.
        win.setProperty("closeAnyway", True)
        win.close()
        _spin()
        assert not win.isVisible()
    finally:
        b.discardChanges()
        win.deleteLater()


def test_closing_with_nothing_unapplied_just_closes(qml):
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        win.show()
        _spin()
        assert b.property("dirty") is False
        win.close()
        _spin()
        assert not win.isVisible()
        assert not _find(win, "leaveSheet").property("visible")
    finally:
        win.deleteLater()


def test_undo_changes_shows_only_with_unapplied_changes(qml):
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        win.show()
        _spin()
        undo = _find(win, "discardButton")
        assert undo.property("visible") is False
        before = b.property("frost")
        b.setProperty("frost", 0.9 if before < 0.85 else 0.2)
        assert undo.property("visible") is True
        undo.clicked.emit()
        assert b.property("dirty") is False and b.property("frost") == pytest.approx(before)
        assert undo.property("visible") is False
    finally:
        b.discardChanges()
        win.deleteLater()


def test_tab_scrolls_the_focused_control_into_view(qml):
    from PySide6.QtCore import QObject, Qt
    from PySide6.QtTest import QTest
    b = _backend(qml)
    win = _window(qml)
    try:
        win.setProperty("pageIndex", 2)          # Lock screen: a long options column
        win.setWidth(1036)
        win.setHeight(716)
        win.show()
        win.requestActivate()
        _spin(600)
        side = win.findChild(QObject, "lockOptions")
        assert side.property("contentHeight") > side.property("height")
        worst = 0
        for _ in range(40):
            QTest.keyClick(win, Qt.Key_Tab)
            _spin(20)
            it = win.activeFocusItem()
            if it is None:
                continue
            p, inside = it.parentItem(), False
            while p is not None:
                if p is side:
                    inside = True
                    break
                p = p.parentItem()
            if not inside:
                continue
            top = it.mapToItem(side, 0, 0).y()
            out = max(0, -top, top + it.height() - side.property("height"))
            worst = max(worst, out)
        assert side.property("contentY") > 0, "Tab never reached the controls below the fold"
        assert worst == 0, f"a focused control sat {worst}px outside the visible column"
    finally:
        b.discardChanges()
        win.deleteLater()


def test_results_sheet_asks_for_a_restart_only_when_needed(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from liquidglass.engine import WAITING
    from liquidglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "LiquidGlass" / "ResultsSheet.qml")))
    sheet = comp.create()
    assert sheet is not None, comp.errorString()
    _keep.append(comp)
    b = _backend(qml)
    assert b.property("glassLive") is False

    def title(results):
        sheet.setProperty("results", results)
        return sheet.property("title")

    gtk = {"id": "gtk4", "name": "GTK 4", "status": "applied", "message": ""}
    assert title([gtk]) == "Your new look is applied"
    assert "Restart" not in sheet.property("subtitle")
    glass = {"id": "glass", "name": "Fedora Glass effects", "status": "applied", "message": ""}
    assert title([gtk, glass]) == "Applied. Restart your PC to finish"
    waiting = {"id": "shell", "name": "GNOME Shell", "status": "info", "message": WAITING}
    assert title([gtk, waiting]) == "Applied. Restart your PC to finish"
    skipped = {"id": "glass", "name": "Fedora Glass effects", "status": "skipped", "message": "GNOME Shell is not installed"}
    assert title([gtk, skipped]) == "Your new look is applied"
    sheet.deleteLater()


def test_header_bar_slider_says_what_it_does(qml):
    win = _window(qml)
    try:
        o = _find(win, "headerOpacity")
        assert o.property("label") == "Opacity"
        assert o.property("format").call([0.65]).toString() == "65% solid"
    finally:
        win.deleteLater()


class _Rect:
    def __init__(self, w, h):
        self._w, self._h = w, h

    def width(self):
        return self._w

    def height(self):
        return self._h


@pytest.mark.parametrize("screen, want", [
    ((2560, 1440), (1280, 820)),        # big screen: the full size
    ((2048, 1152), (1280, 820)),        # 1440p at 125%
    ((1536, 864), (1280, 716)),         # 1080p at 125%: fits under the top bar and the panel
    ((1366, 768), (1280, 680)),         # small laptop: never below the minimum
    (None, (1280, 820)),
])
def test_first_window_size_fits_the_screen(screen, want):
    from liquidglass.gui.app import fit_size
    avail = None if screen is None else _Rect(*screen)
    w, h = fit_size(avail, 18)
    assert (w, h) == want
    if screen is not None:
        assert w >= 1000 and h >= 680


def test_apply_and_close_applies_then_closes(qml):
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin()
        before = b.property("frost")
        b.setProperty("frost", 0.9 if before < 0.85 else 0.2)
        win.close()
        _spin(300)
        assert win.isVisible()
        sheet = _find(win, "leaveSheet")
        from PySide6.QtCore import QObject
        apply_btn = [c for c in sheet.findChildren(QObject) if c.property("text") == "Apply and close"]
        assert apply_btn, "the sheet offers Apply and close"
        apply_btn[0].clicked.emit()
        for _ in range(200):
            _spin(50)
            if not win.isVisible():
                break
        assert not win.isVisible(), "closes once Apply has finished"
        assert b.property("dirty") is False, "the changes were applied, not dropped"
    finally:
        b.setProperty("frost", before)
        b.apply()
        _spin(500)
        win.deleteLater()
