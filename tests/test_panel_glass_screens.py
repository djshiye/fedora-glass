"""Panels on two screens look the same, whatever windows sit next to them.

A docked panel touches every maximized window on its screen. Its glass used to reach
past its own edge for windows (the padding menus use for their edge reflections), so a
maximized window lit and tinted the panel on its screen only: on Dino's two screens the
panel over the screen with a maximized app looked lighter and different.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"
NODE = shutil.which("node")


def test_panels_ask_only_for_windows_really_behind_them():
    panels = (EXT / "panels.js").read_text()
    assert re.search(r"new Follower\([^;]*\{onlyBehind: true\}\)", panels, re.S)
    follower = (EXT / "follower.js").read_text()
    assert "const reach = this._onlyBehind ? 0 : p;" in follower
    # Menus keep their reach (popups.js passes no options).
    popups = (EXT / "popups.js").read_text()
    assert "onlyBehind" not in popups


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_window_touching_the_panel_edge_is_not_in_its_glass():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/menu-wallpaper-source.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
