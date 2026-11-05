"""Second, deeper pass after 1.5.4: User Themes' lock leak, panel glass after a screen
is unplugged, and Restore keeping files that something else replaced since Apply."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
EXT = ROOT / "liquidglass/data/extension/liquid-glass@djshiye.github.io"


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_user_themes_listeners_left_at_each_lock_are_let_go():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/themetidy.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_user_themes_tidy_ships_and_runs_for_the_whole_extension_life():
    from liquidglass.render import glass
    assert "themetidy.js" in glass.FILES
    ext = (EXT / "extension.js").read_text()
    assert "new UserThemesTidy()" in ext and "this._tidy?.destroy()" in ext


def test_glass_follows_a_panel_moved_to_another_container():
    # Dash to Panel moves a kept panel into a new box when a screen goes away: the
    # follower must move its panes along instead of giving up.
    src = (EXT / "follower.js").read_text()
    assert "'parent-set'" in src
    assert "parent.insert_child_below(p, anchor)" in src
