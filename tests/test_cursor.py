"""The mouse pointer styles: the shipped themes, the cursor target, Restore, and the picker."""

from __future__ import annotations

import hashlib
import os
import struct
import tarfile
from pathlib import Path

import pytest

from fedoraglass import cursors
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.cursor import Cursor

REPO = Path(__file__).resolve().parents[1]
TARS = REPO / "data/cursors"
IFACE = cursors.IFACE


def install(env, *ids: str) -> None:
    """Unpack shipped themes into the fake home, as install.sh does."""
    dest = env.data / "icons"
    dest.mkdir(parents=True, exist_ok=True)
    for tid in ids:
        with tarfile.open(TARS / f"{tid}.tar.xz") as tf:
            tf.extractall(dest, filter="data")


@pytest.fixture
def env(fake_env):
    fake_env.gs[(IFACE, None)].update({"cursor-theme": "'Adwaita'", "cursor-size": "24"})
    return fake_env


def apply(env, **kw):
    eng = Engine(env, [Cursor()])
    results = eng.apply(Settings(**kw))
    return eng, [r for r in results if r.status != "applied"]


# ---- the shipped themes ------------------------------------------------------------
def test_every_style_ships_with_a_checked_archive_and_preview():
    sums = dict(reversed(line.split()) for line in (TARS / "SHA256SUMS").read_text().splitlines())
    assert set(sums) == {f"{s.id}.tar.xz" for s in cursors.STYLES}
    for s in cursors.STYLES:
        tar = TARS / f"{s.id}.tar.xz"
        assert hashlib.sha256(tar.read_bytes()).hexdigest() == sums[tar.name]
        for shape in cursors.PREVIEW_NAMES:
            assert cursors.preview_png(s.id, shape) is not None


@pytest.mark.parametrize("style", cursors.STYLE_IDS)
def test_archives_hold_one_safe_theme_with_every_common_shape(style):
    with tarfile.open(TARS / f"{style}.tar.xz") as tf:
        members = tf.getmembers()
    names = {m.name for m in members}
    for m in members:
        assert m.name == style or m.name.startswith(f"{style}/"), m.name
        assert ".." not in Path(m.name).parts
        assert m.isfile() or m.isdir() or m.issym(), m.name
        if m.issym():   # aliases point at a sibling cursor, never out of the theme
            assert "/" not in m.linkname and m.linkname in {Path(n).name for n in names}
        assert m.uid == 0 and m.mtime == 0
    assert f"{style}/index.theme" in names
    for shape in ("default", "pointer", "text", "progress", "wait", "not-allowed", "grabbing",
                  "col-resize", "nwse-resize", "crosshair", "left_ptr", "xterm", "hand2"):
        assert f"{style}/cursors/{shape}" in names, shape


@pytest.mark.parametrize("style", cursors.STYLE_IDS)
def test_cursor_files_have_gnome_sizes(fake_env, style):
    install(fake_env, style)
    path = cursors.find_cursor(fake_env, style, "left_ptr")
    assert path is not None
    for want in (24, 30, 36, 48):
        img = cursors.read_xcursor(path, want)
        assert img is not None and img.size == want
        assert 0 <= img.xhot < img.width and 0 <= img.yhot < img.height
        assert any(img.argb[3::4]), "the pointer is not see-through all over"


def test_read_xcursor_rejects_damaged_files(tmp_path):
    bad = tmp_path / "bad"
    for data in (b"", b"Xcur", b"PNG\x00" * 10,
                 struct.pack("<4sIII", b"Xcur", 16, 1, 1) + struct.pack("<III", 0xFFFD0002, 24, 1 << 30),
                 struct.pack("<4sIII", b"Xcur", 16, 1, 1) + struct.pack("<III", 0xFFFD0002, 24, 28)
                 + struct.pack("<9I", 36, 0xFFFD0002, 24, 1, 24, 24, 0, 0, 0)):   # pixels missing
        bad.write_bytes(data)
        assert cursors.read_xcursor(bad, 24) is None


def test_theme_names_cannot_leave_the_icon_folders(fake_env):
    for name in ("../../etc", "/etc", ".hidden", ""):
        assert cursors.theme_dir(fake_env, name) is None


# ---- settings ---------------------------------------------------------------------
def test_settings_keep_the_users_pointer_by_default_and_reject_unknown_values():
    assert Settings().cursor_theme == "keep" and Settings().cursor_size == 0
    s = Settings(cursor_theme="../evil", cursor_size=33).normalized()
    assert (s.cursor_theme, s.cursor_size) == ("keep", 0)
    s = Settings(cursor_theme="fedora-glass-dark", cursor_size=48).normalized()
    assert (s.cursor_theme, s.cursor_size) == ("fedora-glass-dark", 48)
    assert Settings(cursor_size=True).normalized().cursor_size == 0


# ---- Apply and Restore ----------------------------------------------------------------
def test_by_default_apply_leaves_the_pointer_alone(env):
    install(env, "fedora-glass-light")
    _, errs = apply(env)
    assert not errs
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'Adwaita'"
    assert env.gs[(IFACE, None)]["cursor-size"] == "24"


def test_apply_sets_the_style_and_size_and_restore_brings_the_users_back(env):
    install(env, "fedora-glass-dark")
    eng, errs = apply(env, cursor_theme="fedora-glass-dark", cursor_size=32)
    assert not errs
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'fedora-glass-dark'"
    assert env.gs[(IFACE, None)]["cursor-size"] == "32"
    assert not eng.revert()
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'Adwaita'"
    assert env.gs[(IFACE, None)]["cursor-size"] == "24"


def test_switching_styles_then_back_to_keep_restores_the_original(env):
    install(env, "fedora-glass-dark", "fedora-glass-light")
    apply(env, cursor_theme="fedora-glass-dark")
    apply(env, cursor_theme="fedora-glass-light")
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'fedora-glass-light'"
    apply(env, cursor_theme="keep")
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'Adwaita'"


def test_a_pointer_the_user_picks_elsewhere_afterwards_stays_on_restore(env):
    install(env, "fedora-glass-light")
    eng, _ = apply(env, cursor_theme="fedora-glass-light")
    env.gs[(IFACE, None)]["cursor-theme"] = "'Breeze_Snow'"     # chosen in GNOME Tweaks
    eng.revert()
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'Breeze_Snow'"


def test_a_style_that_is_not_installed_is_not_set(env):
    _, errs = apply(env, cursor_theme="fedora-glass-whitesur")
    assert not errs
    assert env.gs[(IFACE, None)]["cursor-theme"] == "'Adwaita'"


def test_cursor_target_does_not_follow_dark_and_light():
    assert Cursor().scheme_dependent is False


# ---- the picker ---------------------------------------------------------------------------
def test_picker_pictures_and_trying_a_style(fake_env, qml):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QGuiApplication

    from fedoraglass.gui.cursor_picker import CursorImages, CursorPicker

    install(fake_env, "fedora-glass-light")
    images = CursorImages(fake_env)
    for theme in ("fedora-glass-light", "fedora-glass-whitesur"):   # installed, and picture only
        img = images.requestImage(f"{theme}/left_ptr", QSize(), QSize(64, 64))
        assert img.width() == 64 and any(img.pixelColor(x, y).alpha() > 0
                                         for x in range(64) for y in range(64))
    blank = images.requestImage("fedora-glass-light/../../x", QSize(), QSize(32, 32))
    assert all(blank.pixelColor(x, y).alpha() == 0 for x in range(32) for y in range(32))

    picker = CursorPicker(fake_env)
    assert [s["id"] for s in picker.styles] == list(cursors.STYLE_IDS)
    assert [s["installed"] for s in picker.styles][:2] == [True, False]
    before = QGuiApplication.overrideCursor()
    picker.tryOn("fedora-glass-light")
    assert QGuiApplication.overrideCursor() is not None
    assert not QGuiApplication.overrideCursor().pixmap().isNull()
    picker.tryOn("")
    assert QGuiApplication.overrideCursor() == before


def test_picking_a_tile_changes_only_the_setting_until_apply(qml):
    from tests.test_gui_polish import _backend, _find, _spin, _window
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin()
        grid = _find(win, "cursorGrid")
        assert grid is not None
        names = [it.objectName() for it in grid.childItems() if it.objectName().startswith("cursor_")]
        assert names == ["cursor_keep"] + [f"cursor_{i}" for i in cursors.STYLE_IDS]
        tile = _find(win, "cursor_fedora-glass-dark")
        tile.clicked.emit()
        _spin()
        assert b.property("cursorTheme") == "fedora-glass-dark"
        assert b.property("dirty") is True       # waits for Apply; nothing was set on the desktop
        b.setProperty("cursorSize", 48)
        assert b.property("cursorSize") == 48
    finally:
        b.discardChanges()
        win.setProperty("closeAnyway", True)
        win.close()
