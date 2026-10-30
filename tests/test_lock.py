"""The glass lock screen: settings stay in range, the Shell gets a safe config, and
the lock screen code never touches the session behind the lock."""
from __future__ import annotations

import json
import re

import pytest

from liquidglass import palette
from liquidglass.render import glass as rg
from liquidglass.settings import LOCK_CHOICES, Settings

EXT = rg.SOURCE


def lock_cfg(**kw):
    s = Settings(**kw)
    return rg.config(s, palette.build(s, dark=True))["lock"]


def test_lock_settings_are_clamped():
    s = Settings(lock_blur=500, lock_dim=0.99, lock_tint=-3, lock_slide_ms=99999, lock_bounce=float("nan"),
                 lock_clock="huge", lock_clock_position="left", lock_slide="teleport").normalized()
    assert (s.lock_blur, s.lock_dim, s.lock_tint, s.lock_slide_ms) == (100, 0.65, 0.0, 1200)
    assert s.lock_bounce == Settings.lock_bounce
    for k in LOCK_CHOICES:
        assert getattr(s, k) == getattr(Settings, k)
    low = Settings(lock_blur=0, lock_slide_ms=1).normalized()
    assert (low.lock_blur, low.lock_slide_ms) == (10, 250)


def test_lock_config_stays_inside_what_the_extension_accepts():
    c = lock_cfg(lock_dim=0.65, lock_tint=1.0)
    # The extension clamps dim to 0.35..1 and tint alpha to 0.6: never black, never opaque colour.
    assert 0.35 <= c["dim"] <= 1 and c["tint"][3] <= 0.6
    assert set(c) == {"enabled", "blur", "dim", "tint", "card", "clockStyle", "clockPosition", "slide", "slideMs",
                      "bounce"}
    json.dumps(c)


def test_reduce_transparency_or_switching_it_off_turns_the_lock_glass_off():
    assert lock_cfg()["enabled"] is True
    assert lock_cfg(lock_glass=False)["enabled"] is False
    assert lock_cfg(reduce_transparency=True)["enabled"] is False


def test_every_lock_key_is_clamped_in_the_extension():
    js = (EXT / "config.js").read_text()
    body = js[js.index("function cleanLock("):js.index("export function parse(")]
    for key in ("enabled", "card", "blur", "dim", "slideMs", "bounce", "tint"):
        assert re.search(rf"\b{key}\b", body), key
    for key in ("clockStyle", "clockPosition", "slide"):
        assert key in js[js.index("const CHOICES"):js.index("function cleanLock(")], key


def test_the_extension_runs_on_the_lock_screen_only_for_the_lock_glass():
    meta = json.loads((EXT / "metadata.json").read_text())
    assert meta["session-modes"] == ["user", "unlock-dialog"]
    ext = (EXT / "extension.js").read_text()
    assert "Main.sessionMode.connect('updated'" in ext
    sync = ext[ext.index("    _sync() {"):ext.index("    _stopSession() {")]
    assert sync.index("this._stopSession();") < sync.index("new LockGlass(")
    disable = ext[ext.index("    disable() {"):]
    assert "unlock-dialog" in ext[ext.index("    // GNOME keeps"):ext.index("    disable() {")]
    for gone in ("this._lock?.destroy()", "this._leaving?.destroy()", "this._stopSession()"):
        assert gone in disable, gone


@pytest.mark.parametrize("forbidden", [
    "window_group", "get_window_actors", "Main.panel", "messageTray", "Main.uiGroup.get_children",
    "reactive: true", "can_focus", "pushModal", "grab(", "key-press-event", "captured-event",
    "set_cursor", "set_progress_func",
])
def test_lock_glass_never_reaches_the_session_or_takes_input(forbidden):
    js = (EXT / "lock.js").read_text()
    assert forbidden not in js


def test_lock_glass_only_copies_the_wallpaper_and_falls_back_on_errors():
    js = (EXT / "lock.js").read_text()
    assert re.findall(r"setSources\(\[([^\]]*)\]\)", js) == ["this._wall.actor", "this._wall.actor"]
    assert "console.error" in js[js.index("    _safe(fn) {"):js.index("    _attach() {")]
    assert "this._detach();" in js[js.index("    _safe(fn) {"):js.index("    _attach() {")]


def test_spring_curve_dips_more_with_more_bounce():
    js = (EXT / "lock.js").read_text()
    assert "return [[0.3, -0.5 * b], [0.2, 1]];" in js


def test_lock_glass_keeps_white_text_readable_on_any_wallpaper():
    js = (EXT / "lock.js").read_text()
    sheet = float(re.search(r"const SHEET_CEILING = ([\d.]+);", js).group(1))
    card = float(re.search(r"const CARD_CEILING = ([\d.]+);", js).group(1))
    # White on the brightest the glass may get: at least 4.5:1.
    for y in (sheet, card):
        assert 1.05 / (y + 0.05) >= 4.5
    assert "ceiling: SHEET_CEILING" in js and "ceiling: CARD_CEILING" in js


def test_password_field_keeps_a_focus_ring_and_caret():
    from liquidglass.render import shell as rs
    for dark in (True, False):
        css = rs.render_css(palette.build(Settings(), dark=dark))
        i = css.index(".unlock-dialog .login-dialog-prompt-entry:focus")
        block = css[i:css.index("}", i)]
        assert "box-shadow: inset 0 0 0 2px" in block
        entry = css[css.index(".unlock-dialog .login-dialog-prompt-entry, "):]
        assert "caret-color:" in entry[:entry.index("}")]


def test_unlock_defaults_are_quick():
    assert (Settings.lock_slide_ms, Settings.lock_bounce) == (450, 0.2)
    js = (EXT / "config.js").read_text()
    assert "slideMs: 450, bounce: 0.2}" in js
