"""Menu glass under a fake Shell: the real popups.js and follower.js run in Node."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_a_menu_always_shows_even_when_its_glass_fails():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/menu-first-open.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_taskbar_hover_highlight_glides_and_cleans_up():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/glide.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr


def test_glide_setting_reaches_the_extension():
    from liquidglass.settings import Settings
    from liquidglass.palette import build
    from liquidglass.render import glass
    s = Settings()
    assert s.hover_glide is True
    t = build(s, dark=True)
    cfg = glass.config(s, t)
    from liquidglass.render.shell import dtp_values
    # The same tile as Dash to Panel's own hover highlight would have drawn.
    assert cfg["glide"] == {"enabled": True, "color": t.hover.css,
                            "radius": int(dtp_values(t)["highlight-appicon-hover-border-radius"])}
    assert "glide.js" in glass.FILES
    s.hover_glide = False
    assert glass.config(s, t)["glide"]["enabled"] is False
