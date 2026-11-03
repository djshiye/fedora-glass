"""Menus grow out of the button that opened them: the setting, its config key, and the switch."""
from __future__ import annotations

import json
from pathlib import Path

from liquidglass import palette
from liquidglass.render import glass as rg
from liquidglass.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "liquidglass/data/extension/liquid-glass@djshiye.github.io"


def test_menus_grow_by_default_and_the_setting_reaches_the_extension():
    s = Settings().normalized()
    assert s.menu_grow is True
    t = palette.build(s, dark=True)
    assert json.loads(rg.render_config(s, t))["grow"] == {"enabled": True}
    off = Settings(menu_grow=0).normalized()
    assert off.menu_grow is False
    assert json.loads(rg.render_config(off, palette.build(off, dark=True)))["grow"] == {"enabled": False}


def test_the_extension_reads_grow_and_only_turns_it_off_when_asked():
    src = (EXT / "config.js").read_text()
    assert "cfg.grow = {enabled: !(raw.grow" in src and "raw.grow.enabled === false" in src


def test_a_menu_is_its_own_size_again_once_closed():
    src = (EXT / "follower.js").read_text()
    hide = src[src.index("const hide = () => {"):src.index("};", src.index("const hide = () => {"))]
    assert "target.set_scale(1, 1)" in hide
    # and destroy() still puts the scale back
    assert "this.target.set_scale(1, 1)" in src[src.index("    destroy() {"):]


def test_the_app_has_a_switch_for_it():
    qml = (ROOT / "liquidglass/gui/qml/LiquidGlass/LookPage.qml").read_text()
    assert 'objectName: "menuGrow"' in qml and "Backend.menuGrow = on" in qml
