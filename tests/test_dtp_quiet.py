"""Dash to Panel's attention wiggle: the animator wrap in dtpquiet.js (run with gjs when it is installed)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from liquidglass.render import glass as rg

ROOT = Path(__file__).resolve().parents[1]


def test_dtpquiet_is_installed():
    assert "dtpquiet.js" in rg.FILES and (rg.SOURCE / "dtpquiet.js").is_file()


@pytest.mark.skipif(shutil.which("gjs") is None, reason="gjs is not installed")
def test_dtpquiet_with_gjs():
    r = subprocess.run(["gjs", "-m", str(ROOT / "tests/js/dtpquiet.test.js")], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all checks passed" in r.stdout
