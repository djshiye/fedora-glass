"""Taskbar drag (2026-11-11): a press dragged along the taskbar above a maximized window
no longer switches all glass to its "something moves" look (grabmove.js), and the
How liquid slider sets how far the glass gives under a press (1 = the original feel)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"
QML = ROOT / "fedoraglass/gui/qml/FedoraGlass"


def test_glass_switches_to_moving_only_once_a_window_really_moves():
    assert "grabmove.js" in rg.FILES
    for name in ("surfaces.js", "speed.js"):
        src = (EXT / name).read_text()
        assert "new GrabMove(global.display" in src, name
        # No direct grab-op hook left: a held window would count as a moving one again.
        assert "'grab-op-begin'" not in src, name


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_grab_move_unit():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/grabmove.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


def test_liquid_slider_default_is_the_original_feel():
    assert Settings().liquid_strength == 0.4
    assert rg.liquid_factor(0.4) == 1.0
    assert rg.liquid_factor(0.0) == 0.25
    assert rg.liquid_factor(1.0) == 2.5
    assert rg.liquid_factor(7) == 2.5 and rg.liquid_factor(-1) == 0.25
    # Monotonic: right is always more liquid.
    vals = [rg.liquid_factor(i / 20) for i in range(21)]
    assert vals == sorted(vals)


def test_liquid_strength_is_cleaned_and_reaches_the_shell():
    s = Settings(liquid_strength=float("nan")).normalized()
    assert s.liquid_strength == 0.4
    assert Settings(liquid_strength=3).normalized().liquid_strength == 1.0
    from fedoraglass import palette
    cfg = rg.config(Settings(liquid_strength=1.0), palette.build(Settings(), dark=True))
    assert cfg["look"]["liquid"] == 2.5
    cfg = rg.config(Settings(), palette.build(Settings(), dark=True))
    assert cfg["look"]["liquid"] == 1.0


def test_extension_reads_and_bounds_liquid():
    cfg = (EXT / "config.js").read_text()
    assert "liquid: [0.25, 2.5]" in cfg
    glass = (EXT / "glass.js").read_text()
    for u in ("uniform float liquid;", "uniform float pull_x;", "uniform float pull_y;"):
        assert u in glass
    # At liquid 1 and no pull the press is the original one: the factors only multiply.
    assert "(1.0 + deep * tch)" in glass and "0.6 * deep * tch" in glass


def test_press_follows_the_pointer_with_the_pointer_light_off():
    src = (EXT / "motion.js").read_text()
    assert "(w > 0 || st.pressT > 0 || st.press > 0.01) && this._pointer" in src


def test_motion_page_has_the_slider_and_the_preview_shows_the_press():
    page = (QML / "MotionPage.qml").read_text()
    assert 'objectName: "liquidStrength"' in page and "Backend.liquidStrength = v" in page
    assert '"liquid_strength"' in page    # in the card's reset
    pv = (QML / "PreviewDesktop.qml").read_text()
    assert "PointHandler" in pv and "liquidDemo" in pv
    frag = (QML / "shaders/glass.frag").read_text()
    assert "float press;" in frag and "float liquid;" in frag
