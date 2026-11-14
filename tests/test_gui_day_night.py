"""In the app: day and night looks (picked on Home, saved at once, followed when the watcher
switches the look), a saved look updated with the editor's settings, saving under a name
a look has already (Replace / Keep both / Cancel), the Edge reflections slider, and one way
of writing percentages."""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from fedoraglass import looks  # noqa: E402
from fedoraglass import settings as settings_mod  # noqa: E402
from fedoraglass.settings import Settings  # noqa: E402
from tests.test_gui_features_looks import _apply, _backend, _cfg, _spin  # noqa: E402


def _bump(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))


def _disk(tmp_path) -> dict:
    return json.loads(_cfg(tmp_path).read_text())


# ---------------------------------------------------------------- picks, saved at once

def test_picks_are_saved_at_once_and_are_never_an_unapplied_change(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.2)
    day = b.saveLook("Day")
    b.setProperty("frost", 0.8)
    night = b.saveLook("Night")
    _apply(b)
    b.setProperty("lookForDark", night)
    b.setProperty("lookForLight", day)
    assert (b.property("lookForLight"), b.property("lookForDark")) == (day, night)
    assert (_disk(tmp_path)["look_for_light"], _disk(tmp_path)["look_for_dark"]) == (day, night)
    assert b.property("dirty") is False and b.property("changeList") == []
    assert _disk(tmp_path)["frost"] == 0.8, "only the picks are saved, not the editor's look"
    # Only a saved look can be picked; "" is "Same look".
    b.setProperty("lookForDark", "../../etc/passwd")
    b.setProperty("lookForDark", "not-a-look")
    assert b.property("lookForDark") == night
    b.setProperty("lookForDark", "")
    assert b.property("lookForDark") == "" and _disk(tmp_path)["look_for_dark"] == ""
    # Reset all and Undo keep them: they are this PC's own choices.
    b.setProperty("frost", 0.4)
    b.resetDefaults()
    b.discardChanges()
    assert b.property("lookForLight") == day and b.settings().look_for_light == day
    # And an Apply saves them with the look.
    b.setProperty("frost", 0.5)
    _apply(b)
    assert _disk(tmp_path)["look_for_light"] == day


def test_deleting_a_look_clears_its_pick_and_renaming_keeps_it(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    _apply(b)
    day = b.saveLook("Day")
    b.setProperty("frost", 0.8)
    night = b.saveLook("Night")
    b.setProperty("lookForLight", day)
    b.setProperty("lookForDark", night)
    new_id = b.renameLook(night, "Late evening")
    assert new_id == "late-evening" and new_id != night
    assert b.property("lookForDark") == new_id and _disk(tmp_path)["look_for_dark"] == new_id
    b.deleteLook(day)
    assert b.property("lookForLight") == "" and _disk(tmp_path)["look_for_light"] == ""
    assert b.property("lookForDark") == new_id


def test_the_app_follows_the_look_the_watcher_put_on(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.9)
    night = b.saveLook("Night")
    b.setProperty("frost", 0.1)
    _apply(b)
    b.setProperty("lookForDark", night)
    path = _cfg(tmp_path)
    # The watcher: GNOME went dark, the night look is saved and applied.
    on = looks.day_night(settings_mod.load(path), True, looks.Library(path.parent / "looks"))
    settings_mod.save(on, path)
    _bump(path)
    b._poll_saved_colours()
    assert b.settings().frost == pytest.approx(0.9), "the editor shows the look on the desktop"
    assert b.property("dirty") is False and b.property("activeLook") == night


def test_the_watchers_look_never_takes_unapplied_changes_away(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.9)
    night = b.saveLook("Night")
    b.setProperty("frost", 0.1)
    _apply(b)
    b.setProperty("lookForDark", night)
    b.setProperty("radius", 5)          # the user is busy with something
    path = _cfg(tmp_path)
    settings_mod.save(looks.day_night(settings_mod.load(path), True, looks.Library(path.parent / "looks")), path)
    _bump(path)
    b._poll_saved_colours()
    assert b.settings().radius == 5 and b.settings().frost == pytest.approx(0.1), "the editor is left alone"
    assert b.property("dirty"), "and reads as changes from the look on the desktop now"
    labels = {r["key"] for r in b.property("changeList")}
    assert {"radius", "frost"} <= labels
    # A pick saved now keeps the watcher's look in settings.json.
    b.setProperty("lookForLight", night)
    assert _disk(tmp_path)["frost"] == pytest.approx(0.9)


def test_a_new_wallpapers_colour_reaches_the_editor_with_looks_picked(qml, fake_env, tmp_path):
    """Day and night looks picked, unapplied changes in the editor, and the watcher took the
    tint of a new wallpaper (nothing else changed): the editor takes that tint too, so
    See changes does not offer to put the old one back."""
    b = _backend(fake_env, tmp_path)
    night = b.saveLook("Night")
    b.setProperty("scheme", "auto")
    b.setProperty("tintFromWallpaper", True)
    _apply(b)
    b.setProperty("lookForDark", night)
    b.setProperty("radius", 5)          # the user is busy with something
    path = _cfg(tmp_path)
    s = settings_mod.load(path)
    assert s.tint_from_wallpaper and s.look_for_dark == night
    new_tint = "#cc8899" if s.tint != "#cc8899" else "#336699"
    settings_mod.save(replace(s, tint=new_tint, wallpaper_match="/new.png|1|2|dark"), path)
    _bump(path)
    b._poll_saved_colours()
    assert b.settings().tint == new_tint and b.property("tint") == new_tint
    assert b.settings().radius == 5, "the unapplied change stays"
    keys = {r["key"] for r in b.property("changeList")}
    assert "radius" in keys and "tint" not in keys


def test_other_changes_on_disk_are_still_left_alone(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    night = b.saveLook("Night")
    _apply(b)
    b.setProperty("lookForDark", night)
    path = _cfg(tmp_path)
    settings_mod.save(replace(settings_mod.load(path), frost=0.95, undo_on_remove=False, lighter_on_battery=False), path)
    _bump(path)
    b._poll_saved_colours()
    assert b.settings().frost != 0.95, "a change outside the look: not the watcher's doing"


# ---------------------------------------------------------------- update, same names

def test_update_a_look_and_save_under_a_name_it_has(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.2)
    look_id = b.saveLook("Evening blue")
    b.setProperty("frost", 0.7)
    assert b.property("activeLook") == ""
    said: list = []
    b.noticed.connect(said.append)
    assert b.updateLook(look_id) is True
    assert said[-1] == "Updated “Evening blue”"
    assert b.property("activeLook") == look_id
    assert [(t["id"], t["name"], t["frost"]) for t in b.property("savedLooks")] == [(look_id, "Evening blue", 0.7)]
    assert b.lookNamed("EVENING blue") == look_id and b.lookNamed("Morning") == ""
    assert b.uniqueLookName("evening blue") == "evening blue 2"
    b.setProperty("frost", 0.3)
    assert b.replaceLook(look_id) is True
    assert [(t["name"], t["frost"]) for t in b.property("savedLooks")] == [("Evening blue", 0.3)]
    problems: list = []
    b.lookProblem.connect(problems.append)
    assert b.updateLook("gone") is False and problems == ["That look isn't there any more."]


def test_the_replace_sheet_asks_and_each_answer_does_what_it_says(qml):
    from PySide6.QtCore import QMetaObject, QObject, Qt
    from PySide6.QtTest import QTest
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    made = []
    try:
        win.show()
        _spin(200)
        b.setProperty("frost", 0.25)
        made.append(b.saveLook("Evening blue"))
        _spin(150)
        saved = _find(win, "savedLooks")
        name_sheet = saved.findChild(QObject, "lookNameSheet")
        ask = saved.findChild(QObject, "lookReplaceSheet")

        def save_as(text):
            QMetaObject.invokeMethod(saved, "saveNew")
            _spin(300)
            field = name_sheet.findChild(QObject, "lookNameField")
            field.setProperty("text", text)
            QMetaObject.invokeMethod(name_sheet, "done")
            _spin(400)

        b.setProperty("frost", 0.6)
        save_as("evening BLUE")
        assert ask.property("opened") and not name_sheet.property("opened")
        assert ask.property("title") == "Replace “Evening blue”?"
        assert "“evening BLUE 2”" in ask.property("subtitle")
        assert win.activeFocusItem().objectName() == "lookKeepBoth", "Enter keeps both: nothing is lost"
        # Cancel: nothing saved.
        ask.findChild(QObject, "lookReplaceCancel").clicked.emit()
        _spin(300)
        assert [t["name"] for t in b.property("savedLooks")] == ["Evening blue"]
        assert b.property("savedLooks")[0]["frost"] == pytest.approx(0.25)
        # Keep both, with Enter: a second tile with its own name.
        save_as("Evening blue")
        QTest.keyClick(win, Qt.Key_Return)
        _spin(300)
        names = [t["name"] for t in b.property("savedLooks")]
        assert names == ["Evening blue", "Evening blue 2"]
        made.append(b.lookNamed("Evening blue 2"))
        # Replace: the first one takes the editor's settings, and keeps its name and id.
        b.setProperty("frost", 0.9)
        save_as("Evening blue")
        ask.findChild(QObject, "lookReplace").clicked.emit()
        _spin(300)
        tiles = {t["name"]: t for t in b.property("savedLooks")}
        assert sorted(tiles) == ["Evening blue", "Evening blue 2"]
        assert tiles["Evening blue"]["id"] == made[0] and tiles["Evening blue"]["frost"] == pytest.approx(0.9)
    finally:
        for look_id in made:
            b.deleteLook(look_id)
        b.discardChanges()
        win.close()


def test_the_look_menu_offers_update_unless_the_editor_holds_it(qml):
    from PySide6.QtCore import QMetaObject, QObject
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    made = []
    try:
        win.show()
        _spin(200)
        b.setProperty("frost", 0.33)
        made.append(b.saveLook("Mine"))
        _spin(200)
        tile = _find(win, "savedLook_mine")
        btn = next(c for c in tile.childItems() if c.objectName() == "lookMenuButton")
        saved = _find(win, "savedLooks")
        menu = saved.findChild(QObject, "lookMenu")
        btn.clicked.emit()
        _spin(300)
        update = _find(win, "lookUpdate") or menu.findChild(QObject, "lookUpdate")
        assert update.property("text") == "Update with current settings"
        assert not update.property("enabled"), "the editor holds this look: nothing to update"
        QMetaObject.invokeMethod(menu, "close")
        _spin(200)
        b.setProperty("frost", 0.66)
        btn.clicked.emit()
        _spin(300)
        assert update.property("enabled")
        update.clicked.emit()
        _spin(300)
        assert not menu.property("opened")
        assert b.property("savedLooks")[0]["frost"] == pytest.approx(0.66)
        assert b.property("activeLook") == "mine"
    finally:
        for look_id in made:
            b.deleteLook(look_id)
        b.discardChanges()
        win.close()


# ---------------------------------------------------------------- the Day and night card

def test_day_and_night_card_hint_picks_and_forced_style(qml):
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    made = []
    try:
        win.show()
        _spin(200)
        card = _find(win, "dayNight")
        caption = _find(win, "dayNightCaption")
        assert card.property("visible")
        assert caption.property("text") == "Save two looks to switch between them with GNOME's light and dark style."
        assert _find(win, "dayNightDark") is None or not _find(win, "dayNightDark").isVisible()
        made.append(b.saveLook("Night"))
        _spin(200)
        dark = _find(win, "dayNightDark")
        assert dark.isVisible() and dark.property("enabled")
        choices = dark.property("model")
        choices = choices.toVariant() if hasattr(choices, "toVariant") else choices
        assert [c["label"] for c in choices] == ["Same look", "Night"]
        assert dark.property("value") == ""
        assert "without Apply" in caption.property("text"), "the one change without Apply says so"
        dark.activated.emit("night")
        _spin(100)
        assert b.property("lookForDark") == "night" and dark.property("value") == "night"
        b.setProperty("scheme", "dark")
        _spin(100)
        assert not dark.property("enabled") and not _find(win, "dayNightLight").property("enabled")
        assert caption.property("text") == "Works only when Style is Auto, so it follows GNOME."
        b.setProperty("scheme", "auto")
        _spin(100)
        assert dark.property("enabled")
    finally:
        b.setProperty("lookForDark", "")
        for look_id in made:
            b.deleteLook(look_id)
        b.discardChanges()
        win.close()


# ---------------------------------------------------------------- Edge reflections

def test_edge_reflections_slider_moves_the_highlight_and_the_preview(qml):
    from fedoraglass.gui import changes
    from tests.test_gui_polish import _goto
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _goto(win, "glass", 300)
        slider = _find(win, "edgeReflections")
        assert slider is not None and slider.property("label") == "Edge reflections"
        assert slider.property("hasDefault") and slider.property("defaultValue") == pytest.approx(0.7)
        before = b.property("tokens")["highlight"]
        slider.moved.emit(0.2)
        _spin(100)
        assert b.property("highlight") == pytest.approx(0.2)
        assert b.property("tokens")["highlight"] != before, "the preview's rim follows"
        assert "highlight" in b.property("changedFromDefault")
        row = next(r for r in b.property("changeList") if r["key"] == "highlight")
        assert (row["page"], row["name"], row["before"], row["after"]) == ("glass", "edgeReflections", "70%", "20%")
        assert changes.FIELDS["highlight"][1:3] == ("glass", "edgeReflections")
        b.resetSettings(["highlight"])
        assert b.property("highlight") == pytest.approx(0.7)
    finally:
        b.discardChanges()
        win.close()


def test_percentages_read_one_way_everywhere():
    from fedoraglass.gui import changes
    assert changes.pct(0.45) == "45%"
    rows = changes.change_rows(Settings(frost=0.454), Settings(frost=0.452))
    assert [(r["before"], r["after"]) for r in rows] == [("45.2%", "45.4%")]
    root = Path(__file__).resolve().parents[1] / "fedoraglass/gui"
    for p in [*root.glob("*.py"), *(root / "qml").rglob("*.qml"), *(root / "qml").rglob("*.js")]:
        for line in p.read_text(encoding="utf-8").splitlines():
            code = line.split("//")[0] if p.suffix != ".py" else line.split("#")[0]
            assert not re.search(r'(\d|\}|") %"', code), f"{p.name}: {line.strip()}"
