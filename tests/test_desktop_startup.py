"""Overview off must not close GNOME's startup overview before start-up finishes (Node test)."""
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_overview_off_waits_for_startup():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/desktop-startup.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
