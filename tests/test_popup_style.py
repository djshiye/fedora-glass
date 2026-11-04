"""The pop-up stylesheet is unloaded before its file goes, and only plain CSS gets in (Node test)."""
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_popup_style_lifecycle():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/popupstyle.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
