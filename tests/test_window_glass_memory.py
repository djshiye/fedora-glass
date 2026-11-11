"""Window glass steps out of full-screen windows, lets go of glass nobody can see, and
copies only the windows behind that show (1.5.17 performance review)."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"
NODE = shutil.which("node")


def body(name: str) -> str:
    src = (EXT / "windows.js").read_text()
    m = re.search(r"^    %s\([^)]*\) \{\n(.*?)^    \}\n" % re.escape(name), src, re.M | re.S)
    assert m, f"windows.js lost {name}()"
    return m.group(1)


def test_full_screen_window_keeps_its_actor_to_itself():
    # Mutter scans a full-screen window out (and runs VRR) only while the top child of
    # its actor is the window's surface: the glass must leave the actor, not just hide.
    why = body("_whyNot")
    assert "w.fullscreen" in why and "return 'out';" in why
    hide = body("_hide")
    assert "if (why === 'out')" in hide and "this._attach(false);" in hide
    attach = body("_attach")
    assert "parent.remove_child(h);" in attach
    assert "this.actor.insert_child_at_index(h, 0);" in attach and "this.actor.add_child(h);" in attach
    assert "this._attach(true);" in body("sync")


def test_glass_out_of_sight_lets_go_of_its_pictures():
    hide = body("_hide")
    assert "DROP_MS" in hide and "this._release();" in hide
    # Only if still out of sight when the time is up.
    assert "if (!this._dead && this._whyNot())" in hide
    why = body("_whyNot")
    for reason in ("w.minimized", "located_on_workspace", "coveredBy("):
        assert reason in why
    # Made again when the window can be seen.
    sync = body("sync")
    assert sync.index("this._build();") < sync.rindex("this._place();")
    rel = body("_release")
    for piece in ("pane?.destroy();", "rims?.forEach(r => r.destroy());", "h?.destroy();", "this._pieceSignals.clear();"):
        assert piece in rel
    src = (EXT / "windows.js").read_text()
    assert "'active-workspace-changed', () => this.sync()" in src


def test_still_glass_is_not_restacked_for_other_windows_moving():
    place = body("_place")
    assert "pane.setSources(sources, moved);" in place and "g.setSources(sources, moved);" in place
    g = (EXT / "glass.js").read_text()
    assert "setSources(actors, restack = true)" in g


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_hidden_windows_behind_are_not_copied():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/window-sources.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_glass_stays_for_window_previews():
    # The overview, Alt+Tab, the screenshot tool and a touchpad swipe paint copies of
    # windows from every workspace, covered ones too.
    src = (EXT / "windows.js").read_text()
    for hook in ("Main.overview, 'showing'", "Main.overview, 'hidden'", "Main.screenshotUI, 'notify::visible'",
                 "c instanceof SwitcherPopup", "swipe, 'begin'", "swipe, 'end'"):
        assert hook in src
    why = body("_whyNot")
    assert why.index("if (this.owner.previewing)") < why.index("located_on_workspace")
    # The focused window shows the windows behind it through its glass: it hides none of them.
    covers = body("covers")
    assert "this.owner.seesWindows(this.win)" in covers and "return [];" in covers
    assert "glassOf(a)?.covers()" in src
