"""The glass holds its picture while windows animate: hold.js under a fake Shell, plus wiring checks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from liquidglass.render import glass as rg

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
EXT = rg.SOURCE


def test_hold_modules_are_installed():
    for f in ("hold.js", "holdstate.js"):
        assert f in rg.FILES and (EXT / f).is_file()


def test_glass_manager_starts_and_stops_the_hold():
    src = (EXT / "surfaces.js").read_text()
    assert "new WindowAnimationHold()" in src
    assert "this._hold?.destroy()" in src and "releaseAllPanes(true)" in src


def test_held_panes_skip_rerendering_and_catch_up_once():
    src = (EXT / "glass.js").read_text()
    # A held pane with a picture of its size paints it again without the dirty flag.
    assert "flags & ~dirty" in src and "this._picture === size" in src
    # Our own window animations hold too, and the hold always ends.
    assert "holdPanes(actor);" in src and "releasePanes(actor);" in src
    assert "new GlassHold(" in src and "HOLD_LIMIT_MS" in (EXT / "holdstate.js").read_text()


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_window_animations_hold_and_release_the_glass():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/window-animation-hold.test.mjs",
         "tests/js/hold-limit.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
