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


def _long_list(qml, ids_out):
    """A window with 24 saved looks and the long Day and night list open at its scrolled-down page."""
    b = _backend(qml)
    b.discardChanges()
    ids_out.extend(b.saveLook(f"Look number {i}") for i in range(24))
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
    return b, win, dd, pop


def _rest_pointer_on(win, pop, index):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtTest import QTest
    r = _row(pop, index)
    p = r.mapToItem(win.contentItem(), QPointF(r.width() / 2, r.height() / 2))
    # off the window's corner first: a pointer already on that spot makes no move
    QTest.mouseMove(win, QPoint(2, 2))
    _spin(100)
    QTest.mouseMove(win, p.toPoint())
    # a busy machine may be slow to deliver the hover
    for _ in range(40):
        _spin(100)
        if pop.property("cur") == index:
            break


def test_long_dropdown_keys_ignore_a_pointer_resting_on_a_row(qml):
    from PySide6.QtCore import Qt
    ids = []
    b = None
    try:
        b, win, dd, pop = _long_list(qml, ids)
        count = len(dd.property("model").toVariant())
        _rest_pointer_on(win, pop, 2)
        assert pop.property("cur") == 2
        # the list scrolls under the still pointer: the keys keep their row
        _key(win, Qt.Key_End)
        _spin(400)
        assert pop.property("cur") == count - 1
        _key(win, Qt.Key_Home)
        _spin(400)
        assert pop.property("cur") == 0
        for _ in range(12):
            _key(win, Qt.Key_Down)
            _spin(150)
        assert pop.property("cur") == 12
        # Enter takes the row the keys are on
        chosen = []
        dd.activated.connect(chosen.append)
        _key(win, Qt.Key_End)
        _spin(400)
        _key(win, Qt.Key_Return)
        _spin(300)
        assert chosen == [dd.property("model").toVariant()[count - 1]["value"]]
        _close(win)
    finally:
        for i in ids:
            b.deleteLook(i)
        b.discardChanges()


def test_long_dropdown_pointer_takes_the_row_again_after_keys(qml):
    from PySide6.QtCore import Qt, QPoint, QPointF
    from PySide6.QtTest import QTest
    ids = []
    b = None
    try:
        b, win, dd, pop = _long_list(qml, ids)
        _rest_pointer_on(win, pop, 2)
        _key(win, Qt.Key_Down)
        _spin(300)
        assert pop.property("cur") == 3
        # a real move of the pointer to another row hands the row back to it
        r = _row(pop, 5)
        p = r.mapToItem(win.contentItem(), QPointF(r.width() / 2, r.height() / 2))
        QTest.mouseMove(win, p.toPoint() + QPoint(3, 0))
        _spin(300)
        assert pop.property("cur") == 5
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


# --- the Glass tile picture on the Glass page is a second target for the switch beside it ---

def test_quick_settings_tile_picture_toggles_the_switch_beside_it(qml):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    _goto(win, "glass", 600)
    sc = _find(win, "glassScroller")
    sc.setProperty("contentY", sc.property("contentHeight") - sc.property("height"))
    _spin(300)
    tile = _find(win, "quickTogglePreview")
    assert tile is not None and tile.isVisible()
    before = b.property("quickToggle")
    p = tile.mapToScene(tile.boundingRect().center()).toPoint()
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, p)
    _spin(300)
    assert b.property("quickToggle") == (not before)
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, p)
    _spin(300)
    assert b.property("quickToggle") == before
    _close(win)


# --- the Motion page says why Speed and "Menus grow" are greyed ---------------------------------

def test_motion_page_says_why_speed_is_greyed_for_gnomes_own_animations(qml):
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        _goto(win, "motion", 600)
        note = _find(win, "motionSpeedNote")
        assert note is not None
        b.setMotionStyle("lively")
        _spin(150)
        assert not note.property("visible")
        b.setMotionStyle("gnome")
        _spin(150)
        assert not _find(win, "motionSpeed").property("enabled")
        assert note.property("visible") and "GNOME" in note.property("text")
        # everything off: nothing to explain, GNOME is not drawing anything either
        b.setMotionStyle("off")
        _spin(150)
        assert not note.property("visible")
    finally:
        b.discardChanges()
        _close(win)


def test_motion_page_says_why_menus_grow_is_greyed_without_liquid_motion(qml):
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        _goto(win, "motion", 600)
        row = _find(win, "menuGrow")
        b.setProperty("liquidMotion", True)
        _spin(150)
        assert row.property("caption") == ""
        b.setProperty("liquidMotion", False)
        _spin(150)
        assert not row.property("enabled")
        assert row.property("caption") != ""
    finally:
        b.discardChanges()
        _close(win)


# --- Home: every look's name is shown whole, even in the smallest window ---------------------

def _walk(item):
    yield item
    for k in item.childItems():
        yield from _walk(k)


def _tiles(win):
    row = _find(win, "presetRow")
    return row, [k for k in row.childItems() if k.property("shownName") is not None]


@pytest.mark.parametrize("lang", ["", "de", "es", "fr", "it", "pt_BR"])
def test_home_look_names_are_not_cut_in_the_smallest_window(qml, lang):
    from PySide6.QtGui import QGuiApplication

    from fedoraglass import i18n
    app = QGuiApplication.instance()
    i18n.reset(lang)
    i18n.install_qt(app)
    win = None
    try:
        b = _backend(qml)
        b.discardChanges()
        win = _window(qml)
        win.resize(1036, 636)
        _spin(600)
        _goto(win, "home", 600)
        row, tiles = _tiles(win)
        assert len(tiles) == 5
        for t in tiles:
            labels = [o for o in _walk(t.property("contentItem")) if o.property("truncated") is not None
                      and o.property("text") == t.property("shownName")]
            assert len(labels) == 1, t.property("shownName")
            assert not labels[0].property("truncated"), f"{lang or 'en'}: {t.property('shownName')} is cut"
    finally:
        if win is not None:
            _close(win)
        for tr in list(getattr(app, "_fg_translators", [])):
            app.removeTranslator(tr)
        i18n.reset("")
def test_arrow_keys_move_between_the_home_looks_in_order(qml):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    from fedoraglass import i18n
    app = QGuiApplication.instance()
    i18n.reset("de")
    i18n.install_qt(app)
    win = None
    try:
        b = _backend(qml)
        b.discardChanges()
        win = _window(qml)
        win.resize(1036, 636)
        _spin(600)
        _goto(win, "home", 600)
        row, tiles = _tiles(win)
        assert row.property("columns") == 3      # the long German names need the two rows
        tiles[0].forceActiveFocus(Qt.TabFocusReason)
        _spin(60)
        assert win.activeFocusItem() == tiles[0]
        for i in range(1, 5):
            _key(win, Qt.Key_Right)
            assert win.activeFocusItem() == tiles[i], i
        for i in range(3, -1, -1):
            _key(win, Qt.Key_Left)
            assert win.activeFocusItem() == tiles[i], i
    finally:
        if win is not None:
            _close(win)
        for tr in list(getattr(app, "_fg_translators", [])):
            app.removeTranslator(tr)
        i18n.reset("")


def test_arrow_keys_move_along_the_saved_looks(qml):
    from PySide6.QtCore import Qt
    b = _backend(qml)
    b.discardChanges()
    ids = [b.saveLook(f"Mine {c}") for c in "abcdefghijkl"]
    win = None
    try:
        win = _window(qml)
        _goto(win, "home", 600)
        row = _find(win, "savedLooksRow")
        first = next(k for k in _walk(row) if k.objectName() == "savedLook_" + ids[0])
        first.forceActiveFocus(Qt.TabFocusReason)
        _spin(60)
        for i in range(1, 12):
            _key(win, Qt.Key_Right)
            _spin(30)
            assert win.activeFocusItem().objectName() == "savedLook_" + ids[i], i
        _key(win, Qt.Key_Left)
        assert win.activeFocusItem().objectName() == "savedLook_" + ids[10]
    finally:
        if win is not None:
            _close(win)
        for i in ids:
            b.deleteLook(i)
        b.discardChanges()


# --- a column cut by a small window fades out at the bottom while there is more below ---------

def test_columns_fade_at_the_bottom_while_there_is_more_below(qml):
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        win.resize(1036, 636)
        _spin(600)
        _goto(win, "home", 600)
        side = _find(win, "homeSideScroller")
        fade = _find(win, "homeSideMoreBelow")
        assert side.property("overflows"), "the small window cuts the side column"
        side.setProperty("contentY", 0)
        _spin(100)
        assert fade.property("visible")
        side.setProperty("contentY", side.property("contentHeight") - side.property("height"))
        _spin(100)
        assert not fade.property("visible")
        _goto(win, "windows", 600)
        main = _find(win, "windowsScroller")
        fade = _find(win, "windowsMoreBelow")
        assert main.property("contentHeight") > main.property("height") + 2
        main.setProperty("contentY", 0)
        _spin(100)
        assert fade.property("visible")
        main.setProperty("contentY", main.property("contentHeight") - main.property("height"))
        _spin(100)
        assert not fade.property("visible")
    finally:
        _close(win)


def test_the_bottom_fade_stays_off_a_focused_control(qml):
    from PySide6.QtCore import QPointF, Qt
    b = _backend(qml)
    b.discardChanges()
    win = _window(qml)
    try:
        win.resize(1036, 636)
        _spin(600)
        _goto(win, "windows", 600)
        main = _find(win, "windowsScroller")
        fade = _find(win, "windowsMoreBelow")
        page = fade.parentItem()
        zone_top = fade.y()
        # a focusable control that sits in the fade's strip once scrolled to the right place
        target = None
        for cy in range(0, int(main.property("contentHeight") - main.property("height")), 6):
            main.setProperty("contentY", cy)
            _spin(30)
            for it in _walk(main.property("contentItem")):
                if it.property("activeFocusOnTab") and it.isVisible() and it.width() > 0:
                    y = it.mapToItem(page, QPointF(0, 0)).y()
                    if y + it.height() > zone_top and y < zone_top + fade.height():
                        target = it
                        break
            if target is not None:
                break
        assert target is not None
        assert fade.property("visible")
        target.forceActiveFocus(Qt.MouseFocusReason)      # a click does not scroll it away
        _spin(100)
        assert not fade.property("visible")
        _find(win, "searchField").forceActiveFocus(Qt.TabFocusReason)      # focus moves off the page
        _spin(100)
        assert fade.property("visible")
    finally:
        _close(win)
