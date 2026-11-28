"""Dropdowns used with the keyboard, long names in them, and the sheets and search
that must fit the smallest window in every language."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow

from test_gui_backend import app  # noqa: F401 - the fixture
from test_gui_ux_keys import _backend, _find, _goto, _key, _spin, _window

LANGS = ["de", "es", "fr", "it", "pt_BR"]


@pytest.fixture(params=LANGS)
def lang(request, app):
    """The app in each translated language, put back after."""
    from fedoraglass import i18n
    i18n.reset(request.param)
    i18n.install_qt(app)
    yield request.param
    for t in getattr(app, "_fg_translators", []):
        app.removeTranslator(t)
    app._fg_translators = []
    i18n.reset("")


@pytest.fixture
def win(qml):
    b = _backend(qml)
    b.discardChanges()
    w = _window(qml)
    yield w
    b.discardChanges()
    w.setProperty("closeAnyway", True)
    w.close()
    w.deleteLater()
    _spin()


def _dropdown(win, picks):
    from PySide6.QtCore import Qt
    _goto(win, "glass")
    dd = _find(win, "speedQuality")
    dd.activated.connect(lambda v: picks.append(v))
    dd.forceActiveFocus(Qt.TabFocusReason)
    return dd


def _opened(dd):
    return dd.property("opened") is True


def test_enter_down_enter_picks_the_second_entry_and_closes_the_list(qml, win, capfd):
    from PySide6.QtCore import Qt
    picks = []
    dd = _dropdown(win, picks)
    model = dd.property("model")
    model = model.toVariant() if hasattr(model, "toVariant") else model
    _key(win, Qt.Key_Return)
    _spin(300)
    assert _opened(dd)
    start = max(0, dd.property("currentIndex"))
    _key(win, Qt.Key_Down)
    _key(win, Qt.Key_Return)
    _spin(300)
    assert picks == [model[min(start + 1, len(model) - 1)]["value"]]
    assert not _opened(dd)
    assert "Invalid write" not in capfd.readouterr().err


def test_up_at_the_first_and_down_at_the_last_entry_stay_put(qml, win):
    from PySide6.QtCore import Qt
    picks = []
    dd = _dropdown(win, picks)
    model = dd.property("model")
    model = model.toVariant() if hasattr(model, "toVariant") else model
    _key(win, Qt.Key_Return)
    _spin(300)
    _key(win, Qt.Key_Home)
    _key(win, Qt.Key_Up)
    _key(win, Qt.Key_Return)
    _spin(300)
    assert picks == [model[0]["value"]]
    _key(win, Qt.Key_Return)
    _spin(300)
    _key(win, Qt.Key_End)
    _key(win, Qt.Key_Down)
    _key(win, Qt.Key_Space)
    _spin(300)
    assert picks == [model[0]["value"], model[-1]["value"]]
    assert not _opened(dd)


def test_escape_closes_the_list_without_picking(qml, win):
    from PySide6.QtCore import Qt
    picks = []
    dd = _dropdown(win, picks)
    _key(win, Qt.Key_Return)
    _spin(300)
    _key(win, Qt.Key_Down)
    _key(win, Qt.Key_Escape)
    _spin(300)
    assert picks == []
    assert not _opened(dd)


def _rows(dd):
    """The menu rows of the open list, in order."""
    from PySide6.QtCore import QObject
    out = []
    # A tooltip is a popup too: take the one that holds the rows.
    for pop in [c for c in dd.findChildren(QObject) if "Popup" in c.metaObject().className()]:
        out, todo = [], [pop.property("contentItem")]
        while todo:
            it = todo.pop()
            if it is None:
                continue
            if it.property("modelData") is not None:
                out.append(it)
            todo.extend(it.childItems())
        if out:
            break
    return sorted(out, key=lambda r: r.property("index"))


def test_the_mouse_still_picks_from_the_list(qml, win, capfd):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtTest import QTest
    picks = []
    dd = _dropdown(win, picks)
    model = dd.property("model")
    model = model.toVariant() if hasattr(model, "toVariant") else model
    _key(win, Qt.Key_Return)
    _spin(300)
    row = _rows(dd)[len(model) - 1]
    where = row.mapToScene(QPointF(row.width() / 2, row.height() / 2)).toPoint()
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, QPoint(where.x(), where.y()))
    _spin(300)
    assert picks == [model[-1]["value"]]
    assert not _opened(dd)
    assert "Error" not in capfd.readouterr().err


def _label_of(row):
    from PySide6.QtCore import QObject
    todo = [row]
    while todo:
        it = todo.pop()
        if it.property("text") == row.property("modelData")["label"] and it.metaObject().className().startswith("QQuickText"):
            return it
        todo.extend(it.childItems())


def test_a_long_name_stays_inside_its_row_and_clear_of_the_check_mark(qml, win):
    from PySide6.QtCore import Qt
    long_name = "My very own look for long evenings at the desk, " * 2
    picks = []
    dd = _dropdown(win, picks)
    dd.setProperty("model", [{"value": "a", "label": "Short"},
                             {"value": "b", "label": long_name, "tip": ""}])
    dd.setProperty("value", "b")
    dd.setProperty("glyphs", False)
    _spin(100)
    _key(win, Qt.Key_Return)
    _spin(300)
    rows = _rows(dd)
    short, long_, button = _label_of(rows[0]), _label_of(rows[1]), None
    assert short.property("truncated") is False
    assert long_.property("truncated") is True
    check = [c for c in rows[1].childItems() if c.property("name") == "check"][0]
    assert long_.x() + long_.width() <= check.x(), "the name runs under the check mark"
    assert long_.x() + long_.width() <= rows[1].width()
    # The closed button cuts a long name the same way.
    _key(win, Qt.Key_Escape)
    _spin(300)
    closed = [c for c in _texts(dd) if c.property("text") == long_name]
    assert closed and closed[0].property("truncated") is True
    assert closed[0].mapToItem(dd, 0, 0).x() + closed[0].width() <= dd.width()


def _open_list(win, dd, model, value):
    from PySide6.QtCore import Qt
    dd.setProperty("model", model)
    dd.setProperty("value", value)
    _spin(100)
    _key(win, Qt.Key_Return)
    _spin(300)
    return _rows(dd)


def _close_list(win):
    from PySide6.QtCore import Qt
    _key(win, Qt.Key_Escape)
    _spin(300)


def test_the_list_grows_to_show_a_long_name_whole_and_stops_at_its_widest(qml, win):
    """A saved look's name may be 40 characters. The list was 210 px wide whatever stood in it, so such
    a name was cut after about 25 of them although the window had all the room."""
    from fedoraglass.looks import NAME_MAX
    name = "Evening at the desk with the warm lamp on"[:NAME_MAX]
    assert len(name) == NAME_MAX
    dd = _dropdown(win, [])
    dd.setProperty("glyphs", False)
    widest = dd.property("listMax")
    model = [{"value": "a", "label": "Short"}, {"value": "b", "label": name, "tip": ""}]
    for picked in ("a", "b"):               # the picked row is drawn heavier and makes room for its check mark
        rows = _rows_wide = _open_list(win, dd, model, picked)
        label = _label_of(rows[1])
        assert label.property("truncated") is False, f"the name is cut (picked: {picked})"
        assert label.x() + label.width() <= rows[1].width()
        assert 210 < rows[1].width() + 12 <= widest
        # the whole list is inside the window
        left = rows[1].mapToScene(rows[1].boundingRect().topLeft()).x()
        assert 0 <= left and left + rows[1].width() <= win.width()
        _close_list(win)
    assert _rows_wide


def test_a_list_of_short_names_keeps_its_width_and_a_name_too_long_is_cut_at_the_widest(qml, win):
    dd = _dropdown(win, [])
    dd.setProperty("glyphs", False)
    rows = _open_list(win, dd, [{"value": "a", "label": "Short"}, {"value": "b", "label": "Tiny"}], "a")
    assert rows[0].width() + 12 == max(dd.width(), 210)
    _close_list(win)
    rows = _open_list(win, dd, [{"value": "a", "label": "Short"}, {"value": "b", "label": "W" * 60}], "b")
    assert rows[1].width() + 12 == dd.property("listMax")
    assert _label_of(rows[1]).property("truncated") is True
    _close_list(win)
    # with a curve drawn before each name (the motion lists) the name still shows whole
    dd.setProperty("glyphs", True)
    rows = _open_list(win, dd, [{"value": "a", "label": "Short"},
                                {"value": "b", "label": "A longer name of a way to move"}], "b")
    assert _label_of(rows[1]).property("truncated") is False
    _close_list(win)


def _texts(item):
    out, todo = [], list(item.childItems())
    while todo:
        it = todo.pop()
        if it.metaObject().className().startswith("QQuickText"):
            out.append(it)
        todo.extend(it.childItems())
    return out


def _small_window(win, w=1000, h=600):
    m = win.property("margin")
    win.setWidth(w + 2 * m)
    win.setHeight(h + 2 * m)
    win.show()
    _spin(300)


def _open(win, name):
    from PySide6.QtCore import QMetaObject
    sheet = _find(win, name)
    QMetaObject.invokeMethod(sheet, "open")
    _spin(500)
    return sheet


def _button_row(sheet):
    """The row of buttons at the foot of a sheet."""
    return sheet.property("contentItem").childItems()[-1].childItems()[0]


def _flickable(item):
    todo = [item]
    while todo:
        it = todo.pop()
        if it.metaObject().className().startswith("QQuickFlickable"):
            return it
        todo.extend(it.childItems())


def test_a_long_list_of_things_not_restored_scrolls_and_close_stays_in_the_window(qml, win):
    _small_window(win)
    sheet = _find(win, "problemsSheet")
    sheet.setProperty("problems", [f"~/.local/share/some-app/config/file-{i}.css: could not be put back (Permission denied)"
                                   for i in range(25)])
    sheet = _open(win, "problemsSheet")
    row = _button_row(sheet)
    bottom = row.mapToScene(row.boundingRect().bottomLeft()).y()
    assert bottom <= win.height(), "the Close button is below the window"
    fl = _flickable(sheet.property("contentItem"))
    assert fl is not None and fl.property("contentHeight") > fl.height(), "the list cannot be scrolled"


def test_the_leave_sheets_buttons_lie_inside_it_in_every_language(qml, lang):
    win = _window(qml)
    try:
        _small_window(win)
        sheet = _open(win, "leaveSheet")
        left = sheet.property("contentItem").mapToScene(sheet.property("contentItem").boundingRect().topLeft()).x()
        right = left + sheet.property("width")
        row = _button_row(sheet)
        buttons = [b for b in row.childItems() if b.isVisible()]
        assert len(buttons) == 3
        first = buttons[0].mapToScene(buttons[0].boundingRect().topLeft()).x()
        last = buttons[-1].mapToScene(buttons[-1].boundingRect().topRight()).x()
        assert first >= left + 24 - 0.5, "the first button comes too close to the sheet's left edge"
        assert last <= right - 24 + 0.5
        assert right <= win.width() - 32 + 0.5, "the sheet is wider than the window allows"
    finally:
        win.close()


def _texts_under(item):
    out, todo = [], [item]
    while todo:
        it = todo.pop()
        if it.metaObject().className().startswith("QQuickText"):
            out.append(it)
        todo.extend(it.childItems())
    return out


def test_no_keyboard_shortcut_description_is_cut_and_the_sheet_fits_the_window(qml, lang):
    win = _window(qml)
    try:
        _small_window(win)
        sheet = _open(win, "aboutSheet")
        shown = {s["what"] for s in sheet.property("shortcuts").toVariant()}
        texts = [t for t in _texts_under(sheet.property("contentItem")) if t.property("text") in shown]
        assert len(texts) == len(shown)
        assert [t.property("text") for t in texts if t.property("truncated")] == []
        ci = sheet.property("contentItem")
        top = ci.mapToScene(ci.boundingRect().topLeft()).y()
        bottom = ci.mapToScene(ci.boundingRect().bottomLeft()).y()
        m = win.property("margin")
        assert top >= m + 8 and bottom <= win.height() - m - 8, "the sheet touches the window's edge"
        row = _button_row(sheet)
        assert row.mapToScene(row.boundingRect().bottomLeft()).y() <= win.height() - m - 8
        fl = _flickable(ci)
        assert fl.property("contentHeight") <= fl.height() + 0.5, "the list scrolls in the smallest window"
    finally:
        win.close()


def test_search_offers_terminal_colours_only_where_that_box_is_shown(qml):
    from PySide6.QtCore import QMetaObject, Q_ARG
    b = _backend(qml)
    win = _window(qml)
    side = _find(win, "sidebar")
    field = _find(win, "searchField")

    def found():
        field.setProperty("text", "terminal colours")
        _spin(30)
        return [e["name"] for e in side.property("allResults").toVariant()]
    saved = b._terminal_pal
    try:
        b._terminal_pal = ""
        b.targetsChanged.emit()
        _spin()
        assert "terminalColors" not in found()
        b._terminal_pal = "Adwaita"
        b.targetsChanged.emit()
        _spin()
        assert "terminalColors" in found()
        # And it lands on the box, which is shown.
        QMetaObject.invokeMethod(win, "goTo", Q_ARG("QVariant", "windows"), Q_ARG("QVariant", "terminalColors"))
        _spin(900)
        box = _find(win, "terminalColors")
        assert box is not None and box.property("visible") and box.property("height") > 2
    finally:
        field.setProperty("text", "")
        b._terminal_pal = saved
        b.targetsChanged.emit()
        win.close()


def test_a_keyboard_shortcuts_list_that_wraps_a_lot_scrolls_inside_the_window(qml, win):
    _small_window(win)
    sheet = _open(win, "aboutSheet")
    sheet.setProperty("width", 330)      # every description wraps onto several lines
    _spin(300)
    ci = sheet.property("contentItem")
    top = ci.mapToScene(ci.boundingRect().topLeft()).y()
    bottom = ci.mapToScene(ci.boundingRect().bottomLeft()).y()
    m = win.property("margin")
    fl = _flickable(ci)
    assert fl.property("contentHeight") > fl.height() + 0.5, "the list is not long enough to test the cap"
    assert top >= m + 8 and bottom <= win.height() - m - 8, "the sheet touches the window's edge"
