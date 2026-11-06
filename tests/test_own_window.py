"""Fedora Glass's own window gets no window glass: it draws its own, with a shadow margin."""

from __future__ import annotations

import configparser
import re
from pathlib import Path

from liquidglass import APP_ID
from liquidglass.render import glass as rg

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
