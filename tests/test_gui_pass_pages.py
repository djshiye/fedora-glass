"""Settings pages that say what the switches really do: Reduce transparency, GNOME motion."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtQuick")

from tests.test_gui_redesign import _find, _probe_backend, _spin, _window  # noqa: E402


def _page(win, pid):
    win.show()
    _spin(200)
    win.setProperty("page", pid)
    _spin(300)


# ---------------------------------------------------------------- Reduce transparency

def test_home_tiles_are_not_lit_while_reduce_transparency_is_on(qml):
    b = _probe_backend(qml)
    win = _window(qml)
    try:
        _page(win, "home")
        for name in ("tileWindows", "tileLock"):
            assert _find(win, name).property("on") is True      # the defaults: glass on
            assert _find(win, name).property("state_") == "On"
        b.setProperty("reduceTransparency", True)
        _spin(100)
        for name in ("tileWindows", "tileLock"):
            tile = _find(win, name)
            assert tile.property("on") is False
            assert tile.property("state_") == "Off"
            assert "Reduce transparency" in tile.property("tip")
        b.setProperty("reduceTransparency", False)
        _spin(100)
        assert _find(win, "tileWindows").property("state_") == "On"
        assert "Reduce transparency" not in _find(win, "tileWindows").property("tip")
    finally:
        b.discardChanges()
        win.close()


def test_a_home_tile_goes_to_reduce_transparency_instead_of_flipping_a_dead_switch(qml):
    b = _probe_backend(qml)
    win = _window(qml)
    try:
        _page(win, "home")
        b.setProperty("reduceTransparency", True)
        _spin(100)
        for name, key in (("tileWindows", "blurAppWindows"), ("tileLock", "lockGlass")):
            before = b.property(key)
            win.setProperty("page", "home")
            _spin(100)
            _find(win, name).clicked.emit()
            _spin(300)
            assert win.property("page") == "advanced"
            assert b.property(key) == before
            assert _find(win, "reduceTransparency") is not None
    finally:
        b.discardChanges()
        win.close()


def test_the_glass_page_says_why_nothing_changes_while_reduce_transparency_is_on(qml):
    b = _probe_backend(qml)
    win = _window(qml)
    try:
        _page(win, "glass")
        assert "Reduce transparency" not in _find(win, "glassStatus").property("text")
        assert _find(win, "glassReduceNote") is None or not _find(win, "glassReduceNote").property("visible")
        b.setProperty("reduceTransparency", True)
        _spin(100)
        text = _find(win, "glassStatus").property("text")
        assert "Reduce transparency" in text
        assert "preview shows these" not in text
        note = _find(win, "glassReduceNote")
        assert note is not None and note.property("visible") and "Reduce transparency" in note.property("text")
        b.setProperty("reduceTransparency", False)
        _spin(100)
        assert "Reduce transparency" not in _find(win, "glassStatus").property("text")
        assert not _find(win, "glassReduceNote").property("visible")
    finally:
        b.discardChanges()
        win.close()


def test_motion_page_says_liquid_motion_is_off_while_reduce_transparency_is_on(qml):
    b = _probe_backend(qml)
    win = _window(qml)
    try:
        _page(win, "motion")
        row = _find(win, "liquidMotion")
        assert "Reduce transparency" not in row.property("caption")
        b.setProperty("reduceTransparency", True)
        _spin(100)
        assert row.property("caption") == "Off while Reduce transparency is on"
        b.setProperty("reduceTransparency", False)
        _spin(100)
        assert "Reduce transparency" not in row.property("caption")
    finally:
        b.discardChanges()
        win.close()
