"""Stock GNOME (no Dash to Panel, Dash to Dock or ArcMenu): the overview's dash, docks and search results."""
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass import palette
from fedoraglass.render import shell as rs
from fedoraglass.settings import Settings

NODE = shutil.which("node")
ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_dash_keeps_its_icons_when_starting_on_the_desktop():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/dash-repair.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def _rule(css: str, selector: str) -> str:
    i = css.index(selector + " {")
    return css[i:css.index("}", i)]


@pytest.mark.parametrize("dark", (True, False))
def test_search_results_follow_the_glass_text_colour(dark):
    """GNOME gives the provider name and descriptions fixed light colours: on light glass they vanished."""
    t = palette.build(Settings(), dark=dark)
    css = rs.render_css(t)
    for sel in (".search-provider-icon .list-search-provider-content .list-search-provider-details,\n"
                ".list-search-result .list-search-result-title",
                ".list-search-result .list-search-result-description"):
        assert sel in css, sel
    assert f"color: {t.fg.css}" in _rule(css, ".list-search-result .list-search-result-title")
    assert f"color: {t.fg_dim.css}" in _rule(css, ".list-search-result .list-search-result-description")
    # Rows sit flat on their section's card.
    assert "background-color: transparent" in _rule(css, ".list-search-result, .search-provider-icon")


def test_overview_workspaces_are_lifted():
    css = rs.render_css(palette.build(Settings(), dark=True))
    assert "box-shadow" in _rule(css, ".workspace-background")


@pytest.mark.parametrize("enabled, installed, want", [
    ("@as []", {"spawn@djshiye.github.io"}, (False, False, False)),           # stock: Spawn only installed
    ("['dash-to-dock@micxgx.gmail.com']", {"dash-to-dock@micxgx.gmail.com"}, (True, False, False)),
    ("['ubuntu-dock@ubuntu.com', 'arcmenu@arcmenu.com']", {"ubuntu-dock@ubuntu.com", "arcmenu@arcmenu.com"}, (True, True, False)),
    ("['arcmenu@arcmenu.com']", set(), (False, False, False)),                 # switched on, but not installed
    ("@as []", {"dash-to-panel@jderose9.github.com"}, (False, False, False)),  # Dash to Panel installed, off
    ("['dash-to-panel@jderose9.github.com']", {"dash-to-panel@jderose9.github.com"}, (False, False, True)),
])
def test_the_app_knows_which_dock_and_menu_are_in_use(fake_env, enabled, installed, want):
    """The preview draws a dock, a start menu and Dash to Panel only for extensions that
    are installed AND on."""
    pytest.importorskip("PySide6")
    from fedoraglass.gui.backend import Backend
    from test_shell import install
    install(fake_env, *installed, on=False)
    fake_env.gs[("org.gnome.shell", None)] = {"enabled-extensions": enabled}

    class E:
        env = fake_env
    assert Backend._extensions_on(E) == want
    fake_env.gs[("org.gnome.shell", None)]["disable-user-extensions"] = "true"   # extensions switched off altogether
    assert Backend._extensions_on(E) == (False, False, False)
