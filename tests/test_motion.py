"""Window and panel animations: settings, the Shell config, Dash to Panel's own hover animation,
and the curve maths (run with gjs when it is installed)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from liquidglass import palette
from liquidglass.render import glass as rg
from liquidglass.settings import MOTION_DEFAULTS, MOTION_EVENTS, MOTION_PRESETS, Settings, load, save
from liquidglass.targets import shell as ts
from liquidglass.targets.base import Context, GReset, GSet

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "liquidglass/data/extension" / rg.UUID


def test_defaults_match_the_extension():
    """settings.py and curves.js hold the same lists and defaults."""
    js = (EXT / "curves.js").read_text(encoding="utf-8")
    for ev, presets in MOTION_PRESETS.items():
        assert f"{ev}: [{', '.join(repr(p) for p in presets)}]" in js
        d = MOTION_DEFAULTS[ev]
        assert (f"{ev}: Object.freeze({{preset: '{d['preset']}', intensity: {d['intensity']}, "
                f"speed: {int(d['speed'])}}})") in js


def test_motion_is_cleaned():
    s = Settings(motion={"open": {"preset": "explode", "intensity": 7, "speed": 0.1},
                         "close": {"preset": "bounce", "speed": "x"},
                         "hover": {"preset": "jelly", "intensity": float("nan")},
                         "nonsense": {"preset": "spring"}, "launch": "bad"}).normalized()
    assert s.motion == {"open": {"intensity": 1.0, "speed": 0.5}, "hover": {"preset": "jelly"}}
    assert s.motion_for("open") == {"preset": "spring", "intensity": 1.0, "speed": 0.5}
    assert s.motion_for("close") == MOTION_DEFAULTS["close"]   # a close never bounces
    assert Settings(motion="junk").normalized().motion == {}


def test_motion_round_trips(tmp_path):
    p = tmp_path / "settings.json"
    save(Settings(motion={"minimize": {"preset": "bounce", "intensity": 0.8, "speed": 1.5}}), p)
    assert load(p).motion_for("minimize") == {"preset": "bounce", "intensity": 0.8, "speed": 1.5}


def test_config_carries_every_event():
    s = Settings(motion={"hover": {"preset": "off"}})
    cfg = rg.config(s, palette.build(s, dark=True))
    assert set(cfg["animations"]) == set(MOTION_EVENTS)
    assert cfg["animations"]["hover"]["preset"] == "off"
    assert cfg["animations"]["open"] == MOTION_DEFAULTS["open"]
    json.dumps(cfg)


def test_extension_ships_the_animation_files():
    files = rg.extension_files()
    assert "animations.js" in files and "curves.js" in files


@pytest.mark.parametrize("off,hover,expect", [
    (True, "spring", GSet), (False, "spring", GReset), (True, "off", GReset)])
def test_dash_to_panel_hover_only_changes_when_asked(fake_env, off, hover, expect):
    s = Settings(motion_dtp_hover_off=off, motion={"hover": {"preset": hover}})
    t = palette.build(s, dark=True)
    ctx = Context(settings=s, tokens=t, dark=t, light=palette.build(s, dark=False), env=fake_env)
    acts = [a for a in ts.DashToPanel().plan(ctx) if getattr(a, "key", "") == "animate-appicon-hover"]
    assert len(acts) == 1 and isinstance(acts[0], expect)
    if expect is GSet:
        # Their own setting: undoing leaves a later change of theirs alone.
        assert acts[0].value == "false" and acts[0].keep_user_change


@pytest.mark.skipif(shutil.which("gjs") is None, reason="gjs is not installed")
def test_curves_with_gjs():
    r = subprocess.run(["gjs", "-m", str(ROOT / "tests/js/curves.test.js")], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout
