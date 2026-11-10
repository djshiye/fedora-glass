"""Keyboard use: Enter presses the focused button, sheets open on their safe button and
give focus back, rows of chips and swatches are one Tab stop, the section bar's Tab goes
into the section it shows, F1 opens About, Ctrl+Z undoes; and a few wording fixes."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: F401 - the window comes back as a QQuickWindow

QML = Path(__file__).resolve().parents[1] / "fedoraglass/gui/qml/FedoraGlass"
LOOK = QML / "GlassPage.qml"


def _backend(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    return probe.create().property("b")


_keep: list = []


def _window(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    _keep.append(comp)
    win.show()
    win.requestActivate()
    _spin(400)
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


def _goto(win, page, ms=200):
    win.setProperty("page", page)
    _spin(ms)


def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def _key(win, k, mod=None, n=1):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    for _ in range(n):
        QTest.keyClick(win, k, mod if mod is not None else Qt.NoModifier)
        _spin(40)


def _inside(it, root):
    while it is not None:
        if it == root:
            return True
        it = it.parentItem()
    return False


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


def test_enter_presses_the_focused_button_and_the_sheet_gives_focus_back(qml, win):
    from PySide6.QtCore import Qt
    _goto(win, "about")
    about, button = _find(win, "aboutSheet"), _find(win, "shortcutsButton")
    button.forceActiveFocus(Qt.TabFocusReason)
    _key(win, Qt.Key_Return)
    _spin(500)
    assert about.property("opened"), "Enter on Keyboard shortcuts opens the sheet"
    # About opens on its Close button, with the ring showing (opened from the keyboard).
    focus = win.activeFocusItem()
    assert focus.property("text") == "Close" and focus.property("visualFocus")
    _key(win, Qt.Key_Return)
    _spin(500)
    assert not about.property("visible")
    assert win.activeFocusItem() == button, "closing a sheet gives focus back to where it was"


def test_enter_leaves_dropdowns_their_own_enter(qml, win):
    from PySide6.QtCore import Qt
    _goto(win, "motion")
    _find(win, "eachAnimation").setProperty("expanded", True)
    _spin(400)
    dd = _find(win, "motionDropdown-open")
    dd.forceActiveFocus(Qt.TabFocusReason)
    _key(win, Qt.Key_Return)
    _spin(300)
    assert dd.property("opened") is True
    _key(win, Qt.Key_Escape)


def test_text_fields_keep_question_mark_and_enter(qml, win):
    from PySide6.QtCore import Qt
    _goto(win, "lock")
    _find(win, "lockMore").setProperty("expanded", True)
    _spin(400)
    field = _find(win, "lockMessage")
    before = field.property("text")
    field.forceActiveFocus(Qt.TabFocusReason)
    field.setProperty("cursorPosition", len(before))
    _key(win, Qt.Key_Question)
    _key(win, Qt.Key_Return)
    _spin(300)
    assert not _find(win, "aboutSheet").property("visible")
    assert field.property("text") == before + "?"
    assert win.activeFocusItem() == field
    field.setProperty("text", before)
    _goto(win, "home")


def test_enter_picks_a_welcome_look(qml, win):
    from PySide6.QtCore import Qt
    b = _backend(qml)
    win.setProperty("startSheet", "welcome")
    _spin(600)
    sheet = _find(win, "welcomeSheet")
    assert win.activeFocusItem().objectName() == "welcomeStart"
    want = "Frosted" if b.property("activePreset") != "Frosted" else "Liquid"
    _find(win, "welcomeLook" + want).forceActiveFocus(Qt.TabFocusReason)
    _key(win, Qt.Key_Return)
    assert b.property("activePreset") == want
    assert sheet.property("opened"), "picking a look keeps the welcome open"
    sheet.close()
    _spin(400)
    win.setProperty("startSheet", "")


def test_sheets_open_on_their_safe_button(qml, win):
    from PySide6.QtCore import Qt
    b = _backend(qml)
    bar = _find(win, "searchField")
    bar.forceActiveFocus(Qt.TabFocusReason)
    b.setProperty("frost", 0.9 if b.property("frost") < 0.85 else 0.2)
    win.close()
    _spin(500)
    leave = _find(win, "leaveSheet")
    assert leave.property("opened")
    assert win.activeFocusItem().property("text") == "Apply and close"
    _key(win, Qt.Key_Escape)
    _spin(500)
    assert not leave.property("visible")
    assert win.activeFocusItem() == bar
    # Restore original: Cancel, never the red Restore.
    win.setProperty("startSheet", "restore")
    _spin(500)
    assert win.activeFocusItem().property("text") == "Cancel"
    _key(win, Qt.Key_Escape)
    _spin(400)
    win.setProperty("startSheet", "")


def _group(win, name):
    row = _find(win, name)
    return row, [c for c in row.childItems() if c.property("rovingGroup") is not None]


@pytest.mark.parametrize("name", ["swatches", "presetRow", "partRow"])
def test_chip_and_swatch_rows_are_one_tab_stop(qml, win, name):
    _goto(win, "advanced" if name == "partRow" else "home")
    if name == "swatches":
        row = _find(win, "accentSystem").parentItem()
        items = [c for c in row.childItems() if c.property("rovingGroup") is not None]
    else:
        row, items = _group(win, name)
    assert len(items) >= 5
    stops = [c for c in items if c.property("activeFocusOnTab")]
    assert len(stops) == 1, f"{name}: {len(stops)} Tab stops"


def test_arrows_move_along_the_swatches_and_enter_picks(qml, win):
    from PySide6.QtCore import Qt
    b = _backend(qml)
    first = _find(win, "accentSystem")
    b.setProperty("accent", "system")
    _spin()
    first.forceActiveFocus(Qt.TabFocusReason)
    _key(win, Qt.Key_Right, n=2)
    focus = win.activeFocusItem()
    assert focus.objectName().startswith("accent_") and focus.property("visualFocus")
    assert b.property("accent") == "system", "moving does not pick"
    _key(win, Qt.Key_Return)
    picked = b.property("accent")
    assert picked == focus.objectName()[len("accent_"):]
    _key(win, Qt.Key_End)
    assert win.activeFocusItem().objectName() == "accentCustom"
    _key(win, Qt.Key_Home)
    assert win.activeFocusItem() == first
    # Tab leaves the row; Shift+Tab comes back to the chosen colour.
    _key(win, Qt.Key_Tab)
    assert win.activeFocusItem().property("rovingGroup") is None
    _key(win, Qt.Key_Backtab)
    assert win.activeFocusItem().objectName() == "accent_" + picked


def test_arrows_pick_the_part(qml, win):
    from PySide6.QtCore import Qt
    _goto(win, "advanced")
    row, items = _group(win, "partRow")
    stop = next(c for c in items if c.property("activeFocusOnTab"))
    stop.forceActiveFocus(Qt.TabFocusReason)
    _key(win, Qt.Key_Right)
    assert win.activeFocusItem() != stop
    assert win.activeFocusItem().property("selected") is True


def test_search_finds_a_setting_and_lights_it_up(qml, win):
    """Typing in search lists matching settings; Enter opens the page, opens the fold
    around the control and hands it the keyboard."""
    from PySide6.QtCore import Qt
    field = _find(win, "searchField")
    field.forceActiveFocus(Qt.TabFocusReason)
    for ch in "bend":
        _key(win, getattr(Qt, "Key_" + ch.upper()))
    _spin(200)
    assert _find(win, "searchResults").property("visible")
    _key(win, Qt.Key_Return)
    _spin(1200)
    assert win.property("page") == "glass"
    assert _find(win, "glassEffects").property("expanded") is True
    bend = _find(win, "bend")
    assert _inside(win.activeFocusItem(), bend), "the control gets the keyboard"


def test_f1_and_question_mark_open_about_and_ctrl_z_undoes(qml, win):
    from PySide6.QtCore import Qt
    from fedoraglass import __version__
    b = _backend(qml)
    about = _find(win, "aboutSheet")
    assert b.property("version") == __version__
    assert about.property("subtitle") == "Version " + __version__
    _key(win, Qt.Key_F1)
    _spin(400)
    assert about.property("opened")
    _key(win, Qt.Key_Escape)
    _spin(400)
    _key(win, Qt.Key_Question)
    _spin(400)
    assert about.property("opened")
    _key(win, Qt.Key_Escape)
    _spin(400)
    before = b.property("frost")
    b.setProperty("frost", 0.9 if before < 0.85 else 0.2)
    assert b.property("dirty")
    _key(win, Qt.Key_Z, Qt.ControlModifier)
    assert not b.property("dirty") and b.property("frost") == pytest.approx(before)


def test_wording():
    text = LOOK.read_text()
    assert "Glass strength" not in text, "the part slider is Bend, as in Glass effects"
    assert "in the Glass card" not in text, "tint and corners live in the Tint and corners card"
    assert "Backend.frostName" in text      # named from settings.PRESETS (Solid at the top)


def test_frost_badge_says_solid_at_the_top(qml, win):
    from PySide6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt
    _goto(win, "glass")
    look = _find(win, "glassPage")

    def name(v):
        return QMetaObject.invokeMethod(look, "frostName", Qt.DirectConnection,
                                        Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", v))
    assert name(1.0) == "Solid"
    assert name(0.8) == "Frosted"
    assert name(0.45) == "Balanced"


def test_menu_captions_follow_the_start_menu(qml, win):
    b = _backend(qml)
    _goto(win, "motion")
    grow = _find(win, "menuGrow")
    assert ("start menu" in grow.property("tip")) == bool(b.property("hasStartMenu"))
