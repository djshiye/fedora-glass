"""Bugs found in the bug bounty pass after 1.7.8 (settings app and settings model)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from fedoraglass.settings import Settings


def test_dtp_hover_switch_is_checked_like_every_other_switch():
    """The only switch not checked when the settings file is read: "false" (text) counted as on,
    and Apply then turned Dash to Panel's own hover animation off."""
    assert Settings(motion_dtp_hover_off="false").normalized().motion_dtp_hover_off is False
    assert Settings(motion_dtp_hover_off=[]).normalized().motion_dtp_hover_off is False
    assert Settings(motion_dtp_hover_off=True).normalized().motion_dtp_hover_off is True


def test_match_my_lock_screen_off_and_on_again_is_no_change():
    """Switching it off copies the lock screen's values into the login screen's own; switching it
    back on left them there, and the app said "2 changes not applied yet" for a login screen that
    would look exactly the same."""
    pytest.importorskip("PySide6")
    from fedoraglass.gui import changes
    from fedoraglass.gui.backend import _effective

    was = Settings(lock_blur=30, lock_message="call me").normalized()
    now = replace(was, login_blur=30, login_message="call me").normalized()      # off, then on again
    assert _effective(now) == _effective(was)
    assert changes.change_rows(now, was) == []
    # With the match off the login screen's own values do count.
    off_was, off_now = replace(was, login_match_lock=False), replace(now, login_match_lock=False)
    assert _effective(off_now) != _effective(off_was)
    assert [r["key"] for r in changes.change_rows(off_now, off_was)] == ["login_blur", "login_message"]


def test_terminal_colours_can_be_switched_off_again_after_apply(qml):
    """After Apply Terminal is on the Fedora Glass palette; the box with the only switch for it was
    shown just while Terminal had another palette, so there was no way back but a Reset."""
    pytest.importorskip("PySide6")
    import test_gui_polish as g

    b, win = g._backend(qml), g._window(qml)
    try:
        g._goto(win, "windows", 300)
        was = b._terminal_pal, b.property("terminalColors")
        b._terminal_pal = "gnome"
        b.targetsChanged.emit()
        g._find(win, "terminalQtFold").setProperty("expanded", True)
        g._spin(600)
        box, btn = g._find(win, "terminalColors"), g._find(win, "useTerminalColors")
        assert box.property("visible") is True
        b.setProperty("terminalColors", True)
        b._terminal_pal = "Fedora Glass"          # what Terminal reports after Apply
        b.targetsChanged.emit()
        g._spin(100)
        assert box.property("visible") is True
        assert btn.property("text") == "Go back to my own colours"
        btn.clicked.emit()
        g._spin(50)
        assert b.property("terminalColors") is False
        assert box.property("visible") is True, "and it can be chosen again before Apply"
        assert btn.property("text") == "Use Fedora Glass terminal colours"
        b._terminal_pal = ""                      # no Terminal profile: nothing to offer
        b.targetsChanged.emit()
        g._spin(50)
        assert box.property("visible") is False
    finally:
        b._terminal_pal = was[0]
        b.setProperty("terminalColors", was[1])
        b.targetsChanged.emit()
        win.close()
