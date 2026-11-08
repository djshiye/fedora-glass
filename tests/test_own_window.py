"""Fedora Glass's own window gets no window glass: it draws its own, with a shadow margin."""

from __future__ import annotations

import configparser
import shutil
import subprocess
import re
from pathlib import Path

import pytest

from fedoraglass import APP_ID
from fedoraglass.render import glass as rg

ROOT = Path(__file__).resolve().parents[1]


def _own_app_regex() -> re.Pattern[str]:
    src = (rg.SOURCE / "windows.js").read_text()
    m = re.search(r"^const OWN_APP = /(.+)/;$", src, re.M)
    assert m, "windows.js lost OWN_APP"
    return re.compile(m.group(1))


def test_own_app_is_never_given_window_glass():
    src = (rg.SOURCE / "windows.js").read_text()
    assert "OWN_APP.test(id)" in src


def test_own_app_pattern_matches_the_app_ids_the_shell_sees():
    rx = _own_app_regex()
    desktop = configparser.ConfigParser(interpolation=None)
    desktop.read(ROOT / "data" / f"{APP_ID}.desktop")
    # Wayland app id (desktopFileName) and the window class the desktop file promises.
    assert rx.match(APP_ID)
    assert rx.match(desktop["Desktop Entry"]["StartupWMClass"])
    # Other apps keep their glass.
    for other in ("org.gnome.Nautilus", "io.github.djshiye.LiquidGlassy", "fedora-glass-helper", "ptyxis"):
        assert not rx.match(other)


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_frameless_apps_get_glass_on_their_card_not_their_shadow_margin():
    """RGBeast and Wheelguard: glass on the card inside their shadow margin (Node test)."""
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/client-card.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
