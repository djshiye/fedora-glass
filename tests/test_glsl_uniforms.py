"""Shaders run as Shell.GLSLEffect and get every uniform as a typed float (glsl.js under Node)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from liquidglass.render import glass as rg

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def test_glsl_module_is_installed():
    assert "glsl.js" in rg.FILES
    assert (rg.SOURCE / "glsl.js").is_file()


def test_no_float_nudge_left():
    for f in ("glass.js", "animations.js", "glsl.js"):
        src = (rg.SOURCE / f).read_text()
        assert "+ 1e-6" not in src, f
        assert "set_uniform_value" not in src, f


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_every_uniform_goes_through_the_typed_float_path():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/glsl-uniforms.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
