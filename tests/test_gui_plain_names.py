"""A name that comes from a file, the system or the person is shown as the plain text it is:
a look called '<b>BIG</b> <font color=red>x</font>' is not shown bold and red, and an
'<img ...>' in a look name does not make part of it vanish."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

QML = Path(__file__).resolve().parents[1] / "fedoraglass/gui/qml/FedoraGlass"
NAME = "<b>BIG</b> <font color=red>x</font>"
PLAIN_TEXT = 1      # Text.PlainText


_WALK = """
import QtQuick
import FedoraGlass
Item {
    property var made: %s
    // Whether every Text under `made` (a Popup's content too) that shows the name is plain text.
    property string formats
    Component.onCompleted: formats = (function() {
        const out = []
        const todo = [made]
        while (todo.length) {
            const it = todo.pop()
            if (it instanceof Text && it.text === "%s") out.push(it.textFormat === Text.PlainText)
            if (it.children) for (let i = 0; i < it.children.length; ++i) todo.push(it.children[i])
            if (it.contentItem) todo.push(it.contentItem)
        }
        return JSON.stringify(out)
    })()
}
"""


def _formats(qml, thing_qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    comp = QQmlComponent(qml)
    comp.setData((_WALK % (thing_qml, NAME)).encode(), QUrl.fromLocalFile(str(QML / "probe.qml")))
    probe = comp.create()
    assert probe is not None, comp.errorString()
    _keep.append((comp, probe))
    return json.loads(probe.property("formats"))


_keep: list = []


def test_a_look_tile_shows_the_name_as_typed(qml):
    got = _formats(qml, 'LookTile { width: 150; hasMenu: true; name: "%s" }' % NAME)
    assert got and all(got), got


def test_a_toast_shows_the_message_as_it_is(qml):
    got = _formats(qml, 'Toast { text: "%s" }' % NAME)
    assert got and all(got), got


def test_a_sheet_shows_its_title_and_subtitle_as_typed(qml):
    got = _formats(qml, 'Sheet { title: "%s"; subtitle: "%s" }' % (NAME, NAME))
    assert len(got) == 2 and all(got), got


def _block(src, expr):
    """The source of the item that holds `text: <expr>`: from its opening brace to the matching one."""
    at = src.index("text: " + expr)
    depth, start = 0, at
    while start > 0:
        start -= 1
        if src[start] == "}":
            depth += 1
        elif src[start] == "{":
            if depth == 0:
                break
            depth -= 1
    depth, end = 0, start
    while True:
        if src[end] == "{":
            depth += 1
        elif src[end] == "}":
            depth -= 1
            if depth == 0:
                break
        end += 1
    return src[start:end]


@pytest.mark.parametrize("page, expr", [
    ("AppPickerSheet.qml", "item.modelData.name"),          # app names come from .desktop files
    ("NoGlassCard.qml", "row.modelData.name"),
    ("ResultsSheet.qml", 'row.modelData.name || ""'),
    ("AppsPage.qml", "mrow.modelData.name || mrow.modelData.id"),
    ("TargetRow.qml", "row.item.name || row.item.id"),
    ("DayNightCard.qml", "pick.label"),                      # the day and night look names
    ("LgDropdown.qml", "row.modelData.label"),
    ("LgDropdown.qml", 'root.currentIndex >= 0 ? root.model[root.currentIndex].label : ""'),
    ("SavedLooks.qml", "row.text"),
    ("WeatherFrostCard.qml", "card.status"),
])
def test_names_from_files_and_the_system_are_plain_text(page, expr):
    block = _block((QML / page).read_text(), expr)
    assert re.search(r"textFormat:\s*Text\.PlainText", block), page
