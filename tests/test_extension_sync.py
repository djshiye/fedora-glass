"""The glass extension's _sync guards every part it starts, desktop behaviour included,
so one failing part can't take the whole extension down (Node test)."""
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_a_failing_desktop_behaviour_leaves_the_glass_running():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/extension.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
