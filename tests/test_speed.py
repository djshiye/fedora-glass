"""The Speed feature, app side: the setting, the shell config key, the status file the
extension writes and the check request the app writes."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from liquidglass import palette
from liquidglass.render import glass as rg
from liquidglass.settings import GLASS_QUALITIES, Settings


def test_glass_quality_is_normalized():
    assert Settings().glass_quality == "auto"
    for q in GLASS_QUALITIES:
        assert Settings(glass_quality=q).normalized().glass_quality == q
    for bad in ("fast", "", None, 3):
        assert Settings(glass_quality=bad).normalized().glass_quality == "auto"


def test_render_config_carries_speed_quality():
    s = Settings(glass_quality="lighter")
    cfg = rg.config(s, palette.build(s, dark=True))
    assert cfg["speed"] == {"quality": "lighter"}
    assert rg.config(Settings(), palette.build(Settings(), dark=True))["speed"] == {"quality": "auto"}


def test_env_cache_honours_xdg(monkeypatch, tmp_path):
    from liquidglass.env import Env
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    assert Env(home=tmp_path).cache == tmp_path / ".cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "c"))
    assert Env(home=tmp_path).cache == tmp_path / "c"


def test_speed_card_is_registered_and_placed():
    from pathlib import Path
    qml = Path(rg.__file__).resolve().parent.parent / "gui/qml/LiquidGlass"
    assert re.search(r"^SpeedCard 1\.0 SpeedCard\.qml$", (qml / "qmldir").read_text(), re.M)
    look = (qml / "LookPage.qml").read_text()
    assert look.index("SpeedCard {") < look.index("MotionCard {")
    card = (qml / "SpeedCard.qml").read_text()
    for name in ("speedQuality", "speedCheck", "speedUse"):
        assert f'objectName: "{name}"' in card


@pytest.mark.skipif(shutil.which("node") is None, reason="needs Node.js")
def test_auto_quality_steps_down_and_back_up_and_scores_a_check():
    r = subprocess.run([shutil.which("node"), "--test", "tests/js/tuning.test.mjs"],
                       cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
