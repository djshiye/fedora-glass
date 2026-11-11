"""Every change in the app has a visible way back to the default.

A friend dragged Corner roundness to 0 px and could not find the way back: the desktop
followed every Apply, but the app never said what the default was, and the only reset
was "Reset all to defaults" at the bottom of a closed expander. Now every slider marks its
default and shows a "Default" pill while it is elsewhere, every card has a "Reset" pill
while something in it changed, and "Reset all to defaults" has its own card."""

from __future__ import annotations

import os
from dataclasses import fields

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtQuick")
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401 - the window comes back as a QQuickWindow

from fedoraglass.settings import Settings  # noqa: E402
from tests.test_gui_backend import app, home, make_backend  # noqa: E402,F401 - fixtures
from tests.test_gui_polish import _backend, _spin, _visit_all, _window  # noqa: E402


def _items(win):
    todo = [win.contentItem()]
    while todo:
        it = todo.pop()
        yield it
        todo.extend(it.childItems())


def _child(item, name):
    todo = list(item.childItems())
    while todo:
        it = todo.pop()
        if it.objectName() == name:
            return it
        todo.extend(it.childItems())
    return None


def _slider_row(win, label):
    return next(it for it in _items(win)
                if it.property("label") == label and it.property("hasDefault") is not None)


def _title(win, text):
    return next(it for it in _items(win)
                if it.property("resetKeys") is not None and it.property("text") == text)


def test_backend_knows_every_default_and_what_changed(make_backend):
    b = make_backend()
    d = b.property("defaults")
    assert d["radius"] == 18 and d["opacity"] == -1 and d["lock_blur"] == 60
    assert b.property("changedFromDefault") == []
    b.setProperty("radius", 0)
    b.setProperty("glassMenus", False)
    b.setTargetEnabled("gtk4", False)          # which apps get the look is not a look setting
    assert set(b.property("changedFromDefault")) == {"radius", "glass_menus"}
    b.resetSettings(["radius", "targets", "nonsense"])
    assert b.property("radius") == 18
    assert b.property("glassMenus") is False   # only what was asked for
    assert b._s.targets == {"gtk4": False}     # targets can't be reset from here
    b.resetSettings(["glass_menus"])
    assert b.property("changedFromDefault") == []


def test_every_setting_can_be_put_back(make_backend):
    """resetSettings takes every look setting back, one at a time."""
    b = make_backend()
    for f in fields(Settings):
        # Not look settings: the apps that get the look, the remove switch (saved at once), and
        # bookkeeping that follows another setting (what the wallpaper match put back or used).
        from fedoraglass.gui.backend import _BOOKKEEPING
        if f.name in ("targets", "undo_on_remove", *_BOOKKEEPING):
            continue
        b.resetDefaults()
        changed = {"parts": {"panel": {"radius": 0}}, "motion": {"open": {"preset": "off"}}}.get(f.name)
        if changed is None:
            v = getattr(Settings(), f.name)
            changed = (not v if isinstance(v, bool) else
                       "light" if f.name == "scheme" else "red" if f.name == "accent" else
                       "#ff0000" if f.name == "tint" else "hello" if f.name == "lock_message" else
                       "lightest" if f.name == "glass_quality" else "docked" if f.name == "panel_style" else
                       "thin" if f.name == "lock_clock" else "top" if f.name == "lock_clock_position" else
                       "smooth" if f.name == "lock_slide" else "plain" if f.name == "lock_widget_style" else
                       "fedora-glass-dark" if f.name == "cursor_theme" else 48 if f.name == "cursor_size" else
                       False if f.name == "start_on_desktop" else 0.5 if v is None else
                       (v + 7 if isinstance(v, int) else round(1 - v, 2) if v != 0.5 else 0.9))
        b._set(f.name, changed)
        assert f.name in b.property("changedFromDefault"), f.name
        b.resetSettings([f.name])
        assert f.name not in b.property("changedFromDefault"), f.name


def test_corner_roundness_shows_its_default_and_goes_back(qml):
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _visit_all(win, "colour")
        row = _slider_row(win, "Corner roundness")
        pill = _child(row, "sliderDefault")
        mark = _child(row, "defaultMark")
        assert row.property("defaultValue") == 18
        assert mark is not None and mark.property("visible")
        assert not pill.property("visible"), "no pill while the slider is at its default"
        b.setProperty("radius", 0)
        _spin()
        assert pill.property("visible")
        assert "18 px" in pill.property("tip")
        pill.clicked.emit()
        _spin()
        assert b.property("radius") == 18
        assert not pill.property("visible")
    finally:
        b.discardChanges()


def test_card_reset_puts_back_only_its_own_card(qml):
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _visit_all(win, "colour")
        title = _title(win, "Tint and corners")
        reset = _child(title, "cardReset")
        assert not reset.property("visible")
        b.setProperty("radius", 2)
        b.setProperty("tintStrength", 0.5)
        b.setProperty("refraction", 0.1)        # another card's setting
        _spin()
        assert reset.property("visible")
        reset.clicked.emit()
        _spin()
        assert b.property("radius") == 18 and abs(b.property("tintStrength") - 0.06) < 1e-9
        assert abs(b.property("refraction") - 0.1) < 1e-9
        assert not reset.property("visible")
    finally:
        b.discardChanges()


def test_every_slider_and_card_has_a_way_back(qml):
    """Guards the next new slider or card: each LabeledSlider says its default, and every
    card title with settings under it can reset them."""
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _visit_all(win)
        sliders = [it for it in _items(win) if it.property("hasDefault") is not None]
        assert len(sliders) >= 10
        missing = [it.property("label") for it in sliders if not it.property("hasDefault")]
        assert not missing, f"sliders without a default: {missing}"
        keys = set()
        for it in _items(win):
            rk = it.property("resetKeys")
            if rk is None and it.objectName() == "cardReset":     # a Reset pill of its own
                rk = it.property("keys")
            if rk is not None:
                keys.update(rk.toVariant() if hasattr(rk, "toVariant") else rk)
        # Settings with their own way back elsewhere: the Auto/Global chips (opacity, blur,
        # terminal opacity), Reset fine-tune, the presets (frost, highlight), and the
        # switches on the Apps page and the Remove card (targets, undo_on_remove).
        own_way = {"frost", "highlight", "opacity", "blur", "terminal_opacity", "reduce_transparency",
                   "undo_on_remove", "targets"}
        uncovered = {f.name for f in fields(Settings)} - keys - own_way
        assert not uncovered, f"settings no card can reset: {sorted(uncovered)}"
    finally:
        b.discardChanges()


def test_reset_all_is_in_plain_sight(qml):
    b = _backend(qml)
    win = _window(qml)
    try:
        win.show()
        _spin(200)
        _visit_all(win, "advanced")
        btn = next(it for it in _items(win) if it.objectName() == "resetAll")
        assert not btn.property("enabled"), "nothing to reset at the defaults"
        b.setProperty("radius", 0)
        b.setProperty("lockBlur", 20)
        _spin()
        assert btn.property("enabled")
        # Not inside the Fine-tune expander any more.
        p = btn.parentItem()
        while p is not None:
            assert p.property("title") != "Fine-tune"
            p = p.parentItem()
        btn.clicked.emit()
        _spin()
        assert b.property("radius") == 18 and b.property("lockBlur") == 60
    finally:
        b.discardChanges()
