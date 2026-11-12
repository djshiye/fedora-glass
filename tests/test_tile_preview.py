"""Glass behind the snap preview (a window dragged to a screen edge): tile.js puts a
pane behind GNOME's TilePreview and marks it .fedora-glass-tile; the Shell theme then
makes the box nearly clear with a thin accent rim and the menus' corners. Without the
glass (paused, safe mode, menu glass off) it stays a tinted box. The extension side runs
in Node (tests/js/tile-preview.test.mjs)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass.palette import build
from fedoraglass.render import glass as rg
from fedoraglass.render import shell
from fedoraglass.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def _rule(css: str, selector: str) -> dict[str, str]:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert m, selector
    return dict(re.findall(r"([\w-]+)\s*:\s*([^;]+);", m.group(1)))


def _alpha(colour: str) -> float:
    return float(colour.split(",")[-1].strip(" )"))


@pytest.mark.parametrize("dark", [True, False])
def test_the_theme_makes_the_preview_nearly_clear_only_with_glass_behind(dark):
    t = build(Settings(), dark=dark)
    css = shell.render_css(t)
    plain, glass = _rule(css, ".tile-preview "), _rule(css, ".tile-preview.fedora-glass-tile")
    r = shell.radii(t)["r_m"]
    assert plain["border-radius"] == glass["border-radius"] == f"{r}px", "the menus' corners"
    assert _alpha(glass["background-color"]) <= 0.15, "nearly clear over its glass"
    assert _alpha(plain["background-color"]) >= 0.3, "without glass it still shows where the window goes"
    assert glass["border"].startswith("1px solid rgba(") and _alpha(glass["border"]) >= 0.6, "a thin accent rim"


@pytest.mark.parametrize("dark", [True, False])
def test_paused_or_safe_mode_gives_it_a_tinted_box(dark):
    t = build(Settings(), dark=dark)
    css = shell.render_paused_css(t)
    rule = _rule(css, "#uiGroup .tile-preview.fedora-glass-tile")
    assert _alpha(rule["background-color"]) >= 0.3
    assert len(css.encode()) < 16 * 1024 and not re.search(r"@|url\s*\(|\\\\", css)


def test_tile_js_ships_with_the_extension():
    assert "tile.js" in rg.FILES
    assert "tile.js" in rg.extension_files()
    surfaces = (rg.SOURCE / "surfaces.js").read_text()
    assert "TileGlass" in surfaces


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_extension_puts_glass_behind_the_snap_preview_and_cleans_up():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/tile-preview.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
