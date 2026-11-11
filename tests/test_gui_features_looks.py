"""Feature stream "looks", in the app: saved and shared looks, See changes in plain words with
a dot on each page that has changes, one Apply back (and forward), and the glass tint taken
from the wallpaper."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")

from fedoraglass import settings as settings_mod  # noqa: E402
from fedoraglass.engine import Engine  # noqa: E402
from fedoraglass.settings import Settings  # noqa: E402
from fedoraglass.targets.base import Detection, Target, WriteFile  # noqa: E402

_keep: list = []


class _Part(Target):
    def __init__(self, tid, home):
        super().__init__(id=tid, name=tid.title(), group="Apps", summary=f"{tid} summary")
        self._home = home

    def detect(self, env):
        return Detection(True, "")

    def plan(self, ctx):
        return [WriteFile(self._home / f"out/{self.id}.css", f"tint {ctx.tokens.chrome.css}\n")]


class _Engine(Engine):
    crash = False

    def apply(self, s, *a, **k):
        if self.crash:
            raise OSError("disk full")
        return super().apply(s, *a, **k)


def _cfg(tmp_path) -> Path:
    return tmp_path / "cfg/liquid-glass/settings.json"


def _backend(fake_env, tmp_path):
    from fedoraglass.gui.backend import Backend
    eng = _Engine(fake_env, [_Part("alpha", fake_env.home)])
    b = Backend(env=fake_env, engine_factory=lambda: eng, settings_path=_cfg(tmp_path), ui_dark=True, start=False)
    b._test_engine = eng
    _keep.append(b)
    return b


def _spin(ms=60):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


def _settle(cond, ms=8000):
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while not cond() and t.elapsed() < ms:
        QCoreApplication.processEvents()
    return cond()


def _apply(b):
    got: list = []
    b.applyFinished.connect(lambda rs: got.append(rs))
    b.apply()
    for _ in range(6):          # the wallpaper colour, Apply, then the re-check after it
        b.waitIdle()
        _spin(20)
    assert b.waitIdle()
    return got[-1] if got else None


def _on_disk(tmp_path) -> dict:
    return json.loads(_cfg(tmp_path).read_text())


# ---------------------------------------------------------------- 1. saved and shared looks

def test_save_pick_rename_and_delete_a_look(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.2)
    b.setProperty("tint", "#6f9be0")
    b.setProperty("accent", "teal")
    look_id = b.saveLook("Evening blue")
    assert look_id == "evening-blue" and b.property("activeLook") == look_id
    tiles = b.property("savedLooks")
    assert [t["name"] for t in tiles] == ["Evening blue"]
    assert tiles[0]["tint"] == "#6f9be0" and tiles[0]["accent"] == "#2190a4"
    assert (_cfg(tmp_path).parent / "looks/evening-blue.json").is_file()
    # Picking it changes the editor only, as a preset does: nothing is applied or saved.
    b.setProperty("frost", 0.9)
    b.setTargetEnabled("alpha", False)
    assert b.property("activeLook") == ""
    b.useLook(look_id)
    assert b.settings().frost == 0.2 and b.settings().tint == "#6f9be0"
    assert b.settings().target_enabled("alpha") is False       # the apps chosen stay the user's
    assert b.property("activeLook") == look_id and b.property("dirty")
    assert not _cfg(tmp_path).exists()
    assert b.suggestLookName() == "My look"
    new_id = b.renameLook(look_id, "Night")
    assert new_id == "night" and [t["name"] for t in b.property("savedLooks")] == ["Night"]
    problems: list = []
    b.lookProblem.connect(problems.append)
    assert b.saveLook("   ") == "" and problems == ["Give the look a name."]
    b.deleteLook("night")
    assert b.property("savedLooks") == [] and b.property("activeLook") == ""


def test_export_and_import_a_look_file(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    (fake_env.home / "Documents").mkdir()
    from PySide6.QtCore import QUrl
    assert b.property("looksFolder") == QUrl.fromLocalFile(str(fake_env.home / "Documents")).toString()
    b.setProperty("frost", 0.75)
    b.setProperty("lockMessage", "my phone number")
    look_id = b.saveLook("Warm frost")
    dest = fake_env.home / "Documents/warm"
    assert b.exportLook(look_id, QUrl.fromLocalFile(str(dest)))
    shared = json.loads((fake_env.home / "Documents/warm.json").read_text())
    assert shared["settings"]["frost"] == 0.75 and "lock_message" not in json.dumps(shared)
    b.deleteLook(look_id)
    problems: list = []
    b.lookProblem.connect(problems.append)
    bad = fake_env.home / "Documents/bad.json"
    bad.write_text('{"format": "fedora-glass-look", "settings": {}}')
    assert b.importLook(QUrl.fromLocalFile(str(bad))) == "" and "no version" in problems[-1]
    big = fake_env.home / "Documents/big.json"
    big.write_bytes(b" " * (70 * 1024))
    assert b.importLook(QUrl.fromLocalFile(str(big))) == "" and "too big" in problems[-1]
    added = b.importLook(QUrl.fromLocalFile(str(fake_env.home / "Documents/warm.json")))
    assert added == "warm-frost" and [t["name"] for t in b.property("savedLooks")] == ["Warm frost"]
    b.setProperty("frost", 0.1)
    b.useLook(added)
    assert b.settings().frost == 0.75 and b.settings().lock_message == "my phone number"


def test_home_shows_saved_looks_after_the_presets(qml):
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    made = []
    try:
        win.show()
        _spin(200)
        assert not _find(win, "savedLooks").property("visible")
        assert _find(win, "saveLook").property("visible") and _find(win, "importLook").property("visible")
        b.setProperty("tint", "#e0a070")
        made.append(b.saveLook("Warm"))
        _spin(200)
        assert _find(win, "savedLooks").property("visible")
        tile = _find(win, "savedLook_warm")
        assert tile is not None and tile.property("selected") and tile.property("tintHex") == "#e0a070"
        presets = _find(win, "presetRow")
        assert abs(tile.width() - presets.property("tileW")) < 0.5
        # The menu: rename, save as a file, delete.
        btn = next(c for c in tile.childItems() if c.objectName() == "lookMenuButton")
        btn.clicked.emit()
        _spin(300)
        assert _find(win, "savedLooks").property("menuOpen")
    finally:
        for look_id in made:
            b.deleteLook(look_id)
        b.discardChanges()
        win.close()


# ---------------------------------------------------------------- 2. See changes in plain words

def test_change_list_counts_like_the_footer_and_names_the_pages(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    assert b.property("changeList") == [] and b.property("changedPages") == []
    b.setProperty("frost", 0.6)
    b.setProperty("accent", "purple")
    b.setProperty("blurAppWindows", False)
    rows = b.property("changeList")
    assert [(r["label"], r["before"], r["after"]) for r in rows] == [
        ("Accent", "System (Blue)", "Purple"), ("Frost", "45 %", "60 %"), ("Window glass", "On", "Off")]
    assert b.property("changeCount") == 3
    assert b.property("changedPages") == ["colour", "glass"]
    b.setMotionStyle("playful")
    assert b.property("changeCount") == 4      # one motion style, not five animations
    # Switching the wallpaper match on and off again is no change.
    b.setProperty("tintFromWallpaper", True)
    b.setProperty("tintFromWallpaper", False)
    assert b.property("changeCount") == 4


def test_see_changes_lists_each_change_and_a_click_goes_to_it(qml):
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        assert not _find(win, "changedDot_glass").property("visible")
        b.setProperty("frost", 0.6)
        b.setProperty("lockClock", "thin")
        _spin(100)
        assert _find(win, "changedDot_glass").property("visible")
        assert _find(win, "changedDot_lock").property("visible")
        assert not _find(win, "changedDot_colour").property("visible")
        b.requestPlan()
        assert b.waitIdle()
        _spin(400)
        sheet = _find(win, "changesSheet")
        assert sheet.property("opened")
        assert sheet.property("subtitle") == "2 changes not applied yet. Click one to go to it."
        groups = sheet.property("groups")
        groups = groups.toVariant() if hasattr(groups, "toVariant") else groups
        assert [g["label"] for g in groups] == ["Glass", "Lock and login"]
        assert [r["after"] for r in groups[0]["rows"]] == ["60 %"]
        row = _find(win, "change_frost")
        assert row is not None
        row.clicked.emit()
        _spin(400)
        assert not sheet.property("opened") and win.property("page") == "glass"
        assert _find(win, "searchFlash") is not None
    finally:
        b.discardChanges()
        win.close()


def test_every_change_row_lands_on_a_real_control(qml):
    """Like search: each control a change row goes to exists on its page."""
    from fedoraglass.gui import changes
    from tests.test_gui_reliability import _find, _items, _window
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        for page in changes.PAGE_ORDER:
            win.setProperty("page", page)
            _spin(60)
        targets = {(page, name) for _l, page, name, _f in changes.FIELDS.values() if name}
        targets |= {("motion", "motionStyle"), ("motion", "motionSpeed"), ("motion", "eachAnimation"),
                    ("advanced", "partRow"), ("apps", "appsList")}
        missing = [f"{p}/{n}" for p, n in sorted(targets)
                   if not any(it.objectName() == n for it in _items(_find(win, p + "Page")))]
        assert not missing
    finally:
        win.close()


# ---------------------------------------------------------------- 3. one Apply back

def test_apply_keeps_the_look_before_and_going_back_swaps_them(qml, fake_env, tmp_path):
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.3)
    _apply(b)
    assert not b.property("hasPrevious")       # the defaults of a first start were never applied
    b.setProperty("frost", 0.6)
    _apply(b)
    prev = settings_mod.load_previous(_cfg(tmp_path))
    assert prev.settings.frost == 0.3 and not prev.forward
    assert b.property("hasPrevious") and not b.property("previousIsForward")
    assert b.property("previousWhen").startswith("today at ")
    bak = json.loads((_cfg(tmp_path).parent / "settings.json.bak").read_text())
    assert bak["frost"] == 0.3          # the engine stream's last good copy still works
    # Apply again with no change: the way back stays.
    _apply(b)
    assert settings_mod.load_previous(_cfg(tmp_path)).settings.frost == 0.3
    results: list = []
    b.applyFinished.connect(results.append)
    b.goToPrevious()
    for _ in range(4):
        b.waitIdle()
        _spin(20)
    assert results, "going back shows the usual results"
    assert _on_disk(tmp_path)["frost"] == 0.3 and not b.property("dirty")
    assert b.property("previousIsForward") and settings_mod.load_previous(_cfg(tmp_path)).settings.frost == 0.6
    b.goToPrevious()
    for _ in range(4):
        b.waitIdle()
        _spin(20)
    assert _on_disk(tmp_path)["frost"] == 0.6
    assert not b.property("previousIsForward") and settings_mod.load_previous(_cfg(tmp_path)).settings.frost == 0.3


def test_an_apply_that_stops_keeps_the_way_back_as_it_was(qml, fake_env, tmp_path):
    settings_mod.save(Settings(frost=0.3), _cfg(tmp_path))
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.6)
    _apply(b)
    assert settings_mod.load_previous(_cfg(tmp_path)).settings.frost == 0.3
    b._test_engine.crash = True
    b.setProperty("frost", 0.9)
    _apply(b)
    assert settings_mod.load_previous(_cfg(tmp_path)).settings.frost == 0.3
    assert _on_disk(tmp_path)["frost"] == 0.6


def test_about_offers_the_way_back_only_when_there_is_one(qml):
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    keep = b._previous
    try:
        win.show()
        win.setProperty("page", "about")
        _spin(200)
        b._previous = None
        b.previousChanged.emit()
        _spin(50)
        assert not _find(win, "previousCard").property("visible")
        b._previous = settings_mod.Previous(Settings(frost=0.8), time.time() - 60, False)
        b.previousChanged.emit()
        _spin(50)
        assert _find(win, "previousCard").property("visible")
        assert _find(win, "previousTitle").property("text") == "Go back to the look before your last Apply"
        assert _find(win, "goToPrevious").property("text") == "Go back"
        assert "today at" in _find(win, "previousWhen").property("text")
        b._previous = settings_mod.Previous(Settings(frost=0.8), time.time() - 60, True)
        b.previousChanged.emit()
        _spin(50)
        assert _find(win, "goToPrevious").property("text") == "Go forward"
    finally:
        b._previous = keep
        b.previousChanged.emit()
        win.close()


# ---------------------------------------------------------------- 4. tint from the wallpaper

def _picture(path: Path, colour: str) -> Path:
    from PySide6.QtGui import QColor, QImage
    img = QImage(64, 36, QImage.Format_RGB32)
    img.fill(QColor("#0a0a10"))         # mostly near-black: skipped
    for x in range(20, 50):
        for y in range(8, 30):
            img.setPixelColor(x, y, QColor(colour))
    assert img.save(str(path))
    return path


def _hue(hex_: str) -> float:
    import colorsys
    return colorsys.rgb_to_hls(*(int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)))[0] * 360


def test_tint_matches_the_wallpaper_live_and_again_on_apply(qml, fake_env, tmp_path):
    pic = _picture(tmp_path / "wall.png", "#8a2be2")         # violet
    bg = fake_env.gs.setdefault(("org.gnome.desktop.background", None), {})
    bg["picture-uri"] = bg["picture-uri-dark"] = f"'file://{pic}'"
    b = _backend(fake_env, tmp_path)
    own = b.settings().tint
    b.setProperty("tintFromWallpaper", True)
    assert b.property("wallpaperMatchBusy")            # worked out on a worker thread
    assert _settle(lambda: b.settings().tint != own)
    assert 260 < _hue(b.settings().tint) < 290 and b.settings().tint_own == own
    assert not b.property("wallpaperMatchBusy") and b.property("wallpaperMatchNote") == ""
    # Off again: the user's own tint comes back.
    b.setProperty("tintFromWallpaper", False)
    assert b.settings().tint == own and not b.property("dirty")
    b.setProperty("tintFromWallpaper", True)
    b.setProperty("accentFromWallpaper", True)
    _settle(lambda: b.settings().accent.startswith("#"))
    _apply(b)
    disk = _on_disk(tmp_path)
    assert disk["tint_from_wallpaper"] and 260 < _hue(disk["tint"]) < 290 and 260 < _hue(disk["accent"]) < 290
    assert disk["wallpaper_match"].startswith(str(pic) + "|")
    assert not b.property("wallpaperChangedSince")
    # A new wallpaper: said, but nothing changes until Apply.
    time.sleep(0.01)
    _picture(pic, "#2e8b57")                           # sea green, same file
    os.utime(pic, ns=(time.time_ns(), time.time_ns() + 10**9))
    assert b.property("wallpaperChangedSince")
    assert 260 < _hue(b.settings().tint) < 290
    _apply(b)                                          # works the colour out first, then applies
    disk = _on_disk(tmp_path)
    assert 130 < _hue(disk["tint"]) < 170 and not b.property("wallpaperChangedSince")
    assert not b.property("dirty")


def test_picking_a_tint_by_hand_stops_matching(qml, fake_env, tmp_path):
    pic = _picture(tmp_path / "wall.png", "#ff8c00")
    fake_env.gs.setdefault(("org.gnome.desktop.background", None), {})["picture-uri"] = f"'file://{pic}'"
    b = _backend(fake_env, tmp_path)
    b.setProperty("tintFromWallpaper", True)
    _settle(lambda: not b.property("wallpaperMatchBusy"))
    b.setProperty("tint", "#123456")
    assert b.settings().tint == "#123456" and not b.property("tintFromWallpaper")


def test_a_wallpaper_without_colour_keeps_the_tint_and_says_so(qml, fake_env, tmp_path):
    from PySide6.QtGui import QColor, QImage
    img = QImage(32, 18, QImage.Format_RGB32)
    img.fill(QColor("#777777"))
    img.save(str(tmp_path / "grey.png"))
    fake_env.gs.setdefault(("org.gnome.desktop.background", None), {})["picture-uri"] = f"'file://{tmp_path}/grey.png'"
    b = _backend(fake_env, tmp_path)
    own = b.settings().tint
    b.setProperty("tintFromWallpaper", True)
    _settle(lambda: not b.property("wallpaperMatchBusy"))
    assert b.settings().tint == own and "hardly any colour" in b.property("wallpaperMatchNote")


def test_colour_page_has_the_wallpaper_switches_and_note(qml):
    from tests.test_gui_reliability import _find, _probe, _window
    b = _probe(qml)
    win = _window(qml)
    try:
        win.show()
        win.setProperty("page", "colour")
        _spin(200)
        assert _find(win, "wallpaperTint").property("label") == "Match my wallpaper"
        assert _find(win, "wallpaperAccent").property("label") == "Accent matches my wallpaper"
        assert not _find(win, "wallpaperNote").property("visible")
        b.setProperty("tintFromWallpaper", True)     # the session's fake desktop has no wallpaper
        _spin(100)
        assert _find(win, "wallpaperNote").property("visible")
        assert "no wallpaper picture" in _find(win, "wallpaperNoteText").property("text")
        assert _find(win, "tintCaption").property("text") == "Taken from your wallpaper"
    finally:
        b.setProperty("tintFromWallpaper", False)
        b.discardChanges()
        win.close()


def test_going_back_while_the_app_still_checks_the_system_waits_for_it(qml, fake_env, tmp_path):
    settings_mod.save(Settings(frost=0.3), _cfg(tmp_path))
    b = _backend(fake_env, tmp_path)
    b.setProperty("frost", 0.6)
    _apply(b)
    b.refreshTargets()                  # the check that runs after a start or an Apply
    assert b._task is not None
    b.goToPrevious()
    for _ in range(6):
        b.waitIdle()
        _spin(20)
    assert _on_disk(tmp_path)["frost"] == 0.3
