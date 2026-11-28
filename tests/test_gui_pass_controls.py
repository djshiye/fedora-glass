"""The settings app's shared controls: where a dropdown opens, the segmented switch's ring, slider keys."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtQuick")

from test_gui_backend import app  # noqa: F401,E402
from test_gui_ux_keys import _backend, _find, _goto, _key, _spin, _window  # noqa: E402


def _popup(dd):
    from PySide6.QtCore import QObject
    for o in dd.findChildren(QObject):
        if "Popup" in o.metaObject().className() and o.property("cur") is not None:
            return o
    return None


def _close(win):
    win.setProperty("closeAnyway", True)
    win.close()
    win.deleteLater()
    _spin()


def _box(item, win):
    from PySide6.QtCore import QPointF
    p = item.mapToItem(win.contentItem(), QPointF(0, 0))
    return p.y(), p.y() + item.height()


# --- a dropdown opens where there is room, however the page was scrolled ------------------------

@pytest.mark.parametrize("ev", ["hover", "launch"])
def test_dropdown_opened_again_after_scrolling_keeps_off_its_button(qml, ev):
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    _goto(win, "motion", 600)
    _find(win, "eachAnimation").setProperty("expanded", True)
    _spin(900)
    dd = _find(win, "motionDropdown-" + ev)
    flick = _find(win, "motionScroller")
    pop = _popup(dd)
    maxy = flick.property("contentHeight") - flick.property("height")
    for cy in [maxy, maxy - 40, maxy - 80, maxy - 120, maxy - 160, maxy - 200, maxy - 240]:
        flick.setProperty("contentY", max(0, cy))
        _spin(400)
        top, bottom = _box(dd, win)
        dd.metaObject().invokeMethod(dd, "open")
        _spin(400)
        ptop, pbottom = _box(pop.property("background"), win)
        # the window's own edge, inside its transparent shadow margin
        edge = win.height() - win.property("margin")
        assert pbottom <= edge, (cy, ptop, pbottom, edge)
        assert pbottom <= top or ptop >= bottom, f"the list covers its button at scroll {cy}: button {top}..{bottom}, list {ptop}..{pbottom}"
        dd.metaObject().invokeMethod(dd, "close")
        _spin(300)
    _close(win)


def test_long_dropdown_list_scrolls_inside_the_window(qml):
    from PySide6.QtCore import Qt
    b = _backend(qml)
    b.discardChanges()
    ids = [b.saveLook(f"Look number {i}") for i in range(24)]
    try:
        b.setProperty("scheme", "auto")
        win = _window(qml)
        win.resize(1036, 636)
        _spin(600)
        _goto(win, "home", 600)
        dd = _find(win, "dayNightDark")
        flick = dd.parentItem()
        while flick.property("contentY") is None:
            flick = flick.parentItem()
        flick.setProperty("contentY", max(0, flick.property("contentHeight") - flick.property("height")))
        _spin(800)
        pop = _popup(dd)
        dd.metaObject().invokeMethod(dd, "open")
        _spin(600)
        ptop, pbottom = _box(pop.property("background"), win)
        edge = win.height() - win.property("margin")
        assert ptop >= win.property("margin") and pbottom <= edge, (ptop, pbottom, edge)
        # the last row cannot be on screen yet; keys carry it there
        count = len(dd.property("model").toVariant())
        _key(win, Qt.Key_End)
        _spin(400)
        assert pop.property("cur") == count - 1
        last = _row(pop, count - 1)
        rtop, rbottom = _box(last, win)
        assert ptop <= rtop and rbottom <= pbottom, (rtop, rbottom, ptop, pbottom)
        _key(win, Qt.Key_Home)
        _spin(400)
        rtop, rbottom = _box(_row(pop, 0), win)
        assert ptop <= rtop and rbottom <= pbottom, (rtop, rbottom, ptop, pbottom)
        dd.metaObject().invokeMethod(dd, "close")
        _spin(300)
        _close(win)
    finally:
        for i in ids:
            b.deleteLook(i)
        b.discardChanges()


def _row(pop, index):
    """The list row with this index (the rows are the items that carry `modelData`)."""
    todo = [pop.property("contentItem")]
    while todo:
        it = todo.pop()
        if it.property("modelData") is not None and it.property("index") == index:
            return it
        todo.extend(it.childItems())
    raise AssertionError(index)
