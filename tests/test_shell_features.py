"""Shell features: lighter glass on battery, the user's apps without glass, and the Glass
switch in Quick Settings. Settings, the shell-glass.json they render into, and the
extension's own tests under the fake Shell (tests/js)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fedoraglass import palette, settings as sm
from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def cfg(**kw) -> dict:
    s = Settings(**kw)
    return rg.config(s, palette.build(s.normalized(), dark=True))


# ---- settings -----------------------------------------------------------------------
def test_lighter_on_battery_is_on_and_reads_a_hand_edit_as_meant():
    assert Settings().lighter_on_battery is True
    assert Settings(lighter_on_battery="false").normalized().lighter_on_battery is False
    assert Settings(lighter_on_battery="maybe").normalized().lighter_on_battery is True


# ---- shell-glass.json ----------------------------------------------------------------
def test_lighter_on_battery_is_rendered():
    assert cfg()["speed"] == {"quality": "auto", "lighterOnBattery": True}
    assert cfg(lighter_on_battery=False, glass_quality="full")["speed"] == {"quality": "full", "lighterOnBattery": False}


# ---- the extension's files ---------------------------------------------------------------
def test_power_watch_polls_nothing_and_starts_no_service():
    js = (EXT / "power.js").read_text()
    assert "timeout_add" not in js and "DO_NOT_AUTO_START" in js and "_sync" not in js
    assert "net.hadess.PowerProfiles" in js and "org.freedesktop.UPower.PowerProfiles" in js


# ---- under the fake Shell -------------------------------------------------------------------
@pytest.mark.skipif(NODE is None, reason="needs Node.js")
@pytest.mark.parametrize("name", ["power"])
def test_extension_logic_under_the_fake_shell(name):
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", f"tests/js/{name}.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


