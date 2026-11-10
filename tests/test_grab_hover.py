"""Panel hover while a menu holds GNOME's grab (grabhover.js): the icon lift and the
taskbar glide play over a full-screen game, where the panel only shows with a menu open."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass.render import glass as rg

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def test_grab_hover_ships_and_both_panel_effects_use_it():
    assert "grabhover.js" in rg.FILES
    for name in ("animations.js", "glide.js"):
        src = (EXT / name).read_text()
        assert "new GrabHover(" in src, name
        assert "hovered(" in src, name


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_icon_under_the_pointer_counts_as_hovered_while_a_menu_is_open():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/grabhover.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
