"""Dropdowns used with the keyboard, long names in them, and the sheets and search
that must fit the smallest window in every language."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow

from test_gui_ux_keys import _backend, _find, _goto, _key, _spin, _window


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
    pop = [c for c in dd.findChildren(QObject) if "Popup" in c.metaObject().className()][0]
    out, todo = [], [pop.property("contentItem")]
    while todo:
        it = todo.pop()
        if it.property("modelData") is not None:
            out.append(it)
        todo.extend(it.childItems())
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


def _texts(item):
    out, todo = [], list(item.childItems())
    while todo:
        it = todo.pop()
        if it.metaObject().className().startswith("QQuickText"):
            out.append(it)
        todo.extend(it.childItems())
    return out
