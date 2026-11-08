"""Second frames around glass: Spawn's box pointer and stacked notification cards."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass.render import glass as rg

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "fedoraglass/data/shell/glass.css.tpl"


def test_spawn_box_pointer_paints_no_second_frame():
    css = CSS.read_text()
    block = css[css.index("/* @extension: Spawn"):]
    block = block[:block.index("/* @end-extension */")]
    rule = block[block.index(".spawn-popup, .spawn-context-menu {"):]
    rule = rule[:rule.index("}")]
    assert "-arrow-background-color: transparent;" in rule
    assert "-arrow-border-width: 0;" in rule


def test_stack_clip_ships_and_runs():
    assert "stackclip.js" in rg.FILES
    assert "StackClip" in (rg.SOURCE / "surfaces.js").read_text()


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_cards_behind_a_stack_are_cut_to_their_peeking_strip():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/stack-clip.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
