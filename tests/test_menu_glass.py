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
