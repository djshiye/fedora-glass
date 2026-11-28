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


# --- the segmented switch shows its ring for the keyboard only ------------------------------

def test_segmented_switch_clicked_with_the_mouse_shows_no_focus_ring(qml):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    _goto(win, "glass", 800)
    seg = _find(win, "previewScene")
    p = seg.mapToItem(win.contentItem(), QPointF(seg.width() * 0.375, seg.height() / 2))
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, p.toPoint())
    _spin(500)
    ring = seg.childItems()[-1]
    assert seg.hasActiveFocus()
    assert ring.property("opacity") == 0
    # the keyboard brings it back
    _key(win, Qt.Key_Right)
    _spin(400)
    assert ring.property("opacity") == 1
    _close(win)


# --- sliders answer Up, Down, Page Up, Page Down, Home and End as well as Left and Right ----

_SLIDERS = b"""
import QtQuick
import QtQuick.Window
import FedoraGlass
Window {
    width: 600; height: 300; visible: true
    property real held: 0.5
    property int hits: 0
    property real frostHeld: 0.5
    property int frostHits: 0
    property bool on: true
    LgSlider { id: sl; objectName: "sl"; y: 10; width: 300; from: 0; to: 1; stepSize: 0.01; value: held; enabled: on
               onMoved: hits++ }
    FrostSlider { id: fs; objectName: "fs"; y: 100; width: 500; value: frostHeld; enabled: on
                  onMoved: (v) => { frostHits++; frostHeld = v } }
}"""

_KEYS = [("Up", 0.51, 1), ("Down", 0.49, 1), ("PageUp", 0.6, 1), ("PageDown", 0.4, 1), ("Home", 0.0, 1), ("End", 1.0, 1),
         ("Right", 0.51, 1), ("Left", 0.49, 1)]


def _slider_window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    comp = QQmlComponent(qml)
    comp.setData(_SLIDERS, QUrl.fromLocalFile(os.path.abspath("fedoraglass/gui/qml/x.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep_alive.append(comp)
    win.requestActivate()
    _spin(200)
    return win


_keep_alive: list = []


@pytest.mark.parametrize("name,want,hits", _KEYS)
def test_slider_keys_move_the_value_and_say_so_once(qml, name, want, hits):
    from PySide6.QtCore import QObject, Qt
    win = _slider_window(qml)
    sl = win.findChild(QObject, "sl")
    sl.forceActiveFocus()
    _key(win, getattr(Qt, "Key_" + name))
    assert round(sl.property("value"), 4) == want
    assert win.property("hits") == hits
    # still bound to the setting it shows
    win.setProperty("held", 0.25)
    _spin(40)
    assert round(sl.property("value"), 4) == 0.25
    win.close()
    win.deleteLater()
    _spin()


@pytest.mark.parametrize("name,want,hits", _KEYS)
def test_frost_slider_keys_move_the_value_and_say_so_once(qml, name, want, hits):
    from PySide6.QtCore import QObject, Qt
    win = _slider_window(qml)
    fs = win.findChild(QObject, "fs")
    fs.forceActiveFocus()
    _key(win, getattr(Qt, "Key_" + name))
    assert round(win.property("frostHeld"), 4) == want
    assert win.property("frostHits") == hits
    win.close()
    win.deleteLater()
    _spin()


def test_slider_at_its_end_does_not_say_it_moved(qml):
    from PySide6.QtCore import QObject, Qt
    win = _slider_window(qml)
    sl = win.findChild(QObject, "sl")
    win.setProperty("held", 1.0)
    sl.forceActiveFocus()
    _spin(40)
    _key(win, Qt.Key_End)
    _key(win, Qt.Key_Up)
    assert win.property("hits") == 0
    win.close()
    win.deleteLater()
    _spin()


def test_disabled_sliders_ignore_the_keys(qml):
    from PySide6.QtCore import QObject, Qt
    win = _slider_window(qml)
    sl = win.findChild(QObject, "sl")
    fs = win.findChild(QObject, "fs")
    sl.forceActiveFocus()
    win.setProperty("on", False)
    _spin(60)
    for k in (Qt.Key_Up, Qt.Key_End, Qt.Key_PageDown):
        _key(win, k)
    assert win.property("held") == 0.5 and win.property("hits") == 0
    assert win.property("frostHeld") == 0.5 and win.property("frostHits") == 0
    win.close()
    win.deleteLater()
    _spin()
