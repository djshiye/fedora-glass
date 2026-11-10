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


# Every shape a web page or app can ask for by its standard (CSS) name. GNOME falls back to
# Adwaita for a missing one, which works but looks out of place, so the styles added from
# 1.5.20 on must have them all; the first five are allowed a few gaps their upstream has.
CSS_NAMES = ("default", "context-menu", "help", "pointer", "progress", "wait", "cell",
             "crosshair", "text", "vertical-text", "alias", "copy", "move", "no-drop",
             "not-allowed", "grab", "grabbing", "all-scroll", "col-resize", "row-resize",
             "n-resize", "e-resize", "s-resize", "w-resize", "ne-resize", "nw-resize",
             "se-resize", "sw-resize", "ew-resize", "ns-resize", "nesw-resize", "nwse-resize",
             "zoom-in", "zoom-out")
FIRST_FIVE = {"fedora-glass-light", "fedora-glass-dark", "fedora-glass-bibata-ice",
              "fedora-glass-bibata-classic", "fedora-glass-whitesur"}


@pytest.mark.parametrize("style", [s for s in cursors.STYLE_IDS if s not in FIRST_FIVE])
def test_new_styles_have_every_standard_shape(fake_env, style):
    install(fake_env, style)
    root = cursors.theme_dir(fake_env, style)
    missing = [n for n in CSS_NAMES if not (root / "cursors" / n).is_file()]
    assert not missing, missing


def _rgba(img):
    """Straight (not premultiplied) RGBA pixels of a CursorImage, row by row."""
    out = []
    for i in range(0, len(img.argb), 4):
        b, g, r, a = img.argb[i:i + 4]
        out.append((r * 255 // a, g * 255 // a, b * 255 // a, a) if a else (0, 0, 0, 0))
    return out


def _lum(r, g, b):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


@pytest.mark.parametrize("style", cursors.STYLE_IDS)
def test_pointers_read_on_white_and_on_black(fake_env, style):
    """Seen over a white page, some part of the arrow has at least 3:1 contrast with the
    white (the WCAG bar for parts of a control), and the same over black, so it never melts
    into either. Half see-through rims count for what they show over each."""
    install(fake_env, style)
    for shape in ("left_ptr", "hand2", "xterm"):
        img = cursors.read_xcursor(cursors.find_cursor(fake_env, style, shape), 24)
        px = [p for p in _rgba(img) if p[3] > 0]
        assert sum(1 for p in px if p[3] >= 128) > 8, shape

        def over(bg):
            return [_lum(*(round(c * p[3] / 255 + bg * (255 - p[3]) / 255) for c in p[:3])) for p in px]
        on_white = max(1.05 / (lu + 0.05) for lu in over(255))
        on_black = max((lu + 0.05) / 0.05 for lu in over(0))
        assert on_white >= 3 and on_black >= 3, (shape, on_white, on_black)


def _box(img):
    px = _rgba(img)
    pts = [(i % img.width, i // img.width) for i, p in enumerate(px) if p[3] > 40]
    xs, ys = [x for x, _ in pts], [y for _, y in pts]
    return min(xs), min(ys), max(xs), max(ys), px


@pytest.mark.parametrize("style", cursors.STYLE_IDS)
def test_hotspots_sit_where_people_expect(fake_env, style):
    """The arrow and the hand click at their tip (top left of the drawing, on the drawing);
    the text beam, crosshair and busy sign of `wait` click in their middle."""
    install(fake_env, style)
    for shape, where in (("left_ptr", "tip"), ("hand2", "top"), ("xterm", "middle"),
                         ("crosshair", "middle")):
        img = cursors.read_xcursor(cursors.find_cursor(fake_env, style, shape), 48)
        x0, y0, x1, y1, px = _box(img)
        w, h = x1 - x0 + 1, y1 - y0 + 1
        hx, hy = img.xhot, img.yhot
        near = [px[y * img.width + x][3] for x in range(max(0, hx - 3), min(img.width, hx + 4))
                for y in range(max(0, hy - 3), min(img.height, hy + 4))]
        if where != "middle":    # a crosshair may leave its very middle open, to see through
            assert max(near) > 40, f"{shape}: hotspot ({hx},{hy}) is off the drawing"
        if where == "tip":
            assert hx <= x0 + w * 0.3 and hy <= y0 + h * 0.3, (shape, hx, hy, (x0, y0, x1, y1))
        elif where == "top":
            assert hy <= y0 + h * 0.35, (shape, hx, hy, (x0, y0, x1, y1))
        else:
            assert abs(hx - (x0 + x1) / 2) <= w * 0.25 + 2 and abs(hy - (y0 + y1) / 2) <= h * 0.25 + 2, \
                (shape, hx, hy, (x0, y0, x1, y1))


def _frames(path, size):
    b = path.read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    return sum(1 for i in range(n) if struct.unpack_from("<III", b, 16 + 12 * i)[:2] == (0xFFFD0002, size))


@pytest.mark.parametrize("style", cursors.STYLE_IDS)
def test_busy_pointers_move(fake_env, style):
    install(fake_env, style)
    root = cursors.theme_dir(fake_env, style)
    for shape in ("wait", "progress"):
        assert _frames((root / "cursors" / shape).resolve(), 24) >= 6, shape


def test_fun_styles_are_grouped_after_the_plain_ones():
    fun = [s.fun for s in cursors.STYLES]
    assert any(fun) and fun == sorted(fun)
    assert all(s.credit and "·" in s.credit for s in cursors.STYLES)


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
    from tests.test_gui_polish import _backend, _find, _goto, _spin, _window
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _goto(win, "pointer")
        _find(win, "cursorFun").setProperty("expanded", True)      # built when first opened
        _spin()
        grid, fun = _find(win, "cursorGrid"), _find(win, "cursorGridFun")
        assert grid is not None and fun is not None
        names = [it.objectName() for g in (grid, fun) for it in g.childItems()
                 if it.objectName().startswith("cursor_")]
        assert names == ["cursor_keep"] + [f"cursor_{i}" for i in cursors.STYLE_IDS]
        assert all(_find(win, f"cursor_{s.id}").parentItem() == fun for s in cursors.STYLES if s.fun)
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


def test_packages_unpack_only_archives_that_match_their_checksums(tmp_path):
    import shutil
    import subprocess
    import sys
    script = REPO / "packaging/cursors/unpack.py"
    ok = subprocess.run([sys.executable, "-I", str(script), str(REPO), str(tmp_path / "icons")],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert {p.name for p in (tmp_path / "icons").iterdir()} == set(cursors.STYLE_IDS)
    assert (tmp_path / "icons/fedora-glass-light/cursors/default").is_symlink()
    # A changed archive is refused before anything is unpacked from it.
    src = tmp_path / "src"
    shutil.copytree(TARS, src / "data/cursors")
    bad = src / "data/cursors/fedora-glass-dark.tar.xz"
    bad.write_bytes(bad.read_bytes()[:-1] + b"\0")
    r = subprocess.run([sys.executable, "-I", str(script), str(src), str(tmp_path / "icons2")],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "checksum" in r.stderr
