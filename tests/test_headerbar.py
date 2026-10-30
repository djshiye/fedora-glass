from __future__ import annotations

import json

import pytest

from liquidglass import palette, settings as settings_mod
from liquidglass.render import headerbar
from liquidglass.settings import Settings
from liquidglass.targets import gtk as tg
from liquidglass.targets.base import Context, WriteFile

from test_gtk import balanced


def both(s: Settings):
    return palette.build(s, dark=True), palette.build(s, dark=False)


def ctx_for(env, **kw):
    s = Settings(scheme="dark", **kw)
    d, l = both(s)
    return Context(settings=s, tokens=d, dark=d, light=l, env=env)


def gtk_css(env, target_id, **kw):
    target = next(t for t in tg.TARGETS if t.id == target_id)
    return next(a for a in target.plan(ctx_for(env, **kw)) if isinstance(a, WriteFile)).content


def test_defaults_leave_gnome_alone():
    s = Settings()
    assert s.header_height == headerbar.GNOME_HEIGHT and s.header_opacity is None
    assert headerbar.gtk4_css(s, *both(s)) == ""
    assert headerbar.gtk3_css(s, both(s)[0]) == ""


@pytest.mark.parametrize("raw,height", [(10, 36), (200, 64), ("x", 47), (float("nan"), 47), (52.6, 52)])
def test_height_is_clamped(raw, height):
    assert Settings(header_height=raw).normalized().header_height == height


@pytest.mark.parametrize("raw,opacity", [(0.0, 0.1), (2.0, 1.0), (float("nan"), None), (None, None), (0.4, 0.4)])
def test_opacity_is_clamped(raw, opacity):
    assert Settings(header_opacity=raw).normalized().header_opacity == opacity


@pytest.mark.parametrize("height", range(36, 65))
def test_height_rules_add_up(height):
    """Padding plus button height always gives exactly the requested bar."""
    top, bottom, bpad = headerbar._padding(height)
    button = 24 + 2 * bpad
    assert top >= 0 and bottom >= 0 and abs(top - bottom) <= 1
    assert top + bottom + button == height
    css = headerbar.gtk4_css(Settings(header_height=height), *both(Settings()))
    if height != 47:
        assert f"min-height: {height}px" in css and balanced(css)


def test_gnome_height_matches_libadwaita():
    # libadwaita 1.9: headerbar > windowhandle > box { padding: 6px 7px 7px 7px } around 34 px buttons
    assert headerbar._padding(47) == (6, 7, 5)


def test_slim_bars_slim_the_buttons():
    css = headerbar.gtk4_css(Settings(header_height=38), *both(Settings()))
    assert "padding-top: 3px; padding-bottom: 3px" in css
    assert ".default-decoration" in css   # title-only dialog bars are left out


def test_see_through_paints_a_header_band_per_scheme():
    s = Settings(header_opacity=0.3, header_height=44)
    css = headerbar.gtk4_css(s, *both(s))
    assert balanced(css)
    assert css.count("--lg-header-bg:") == 2
    assert "@media (prefers-color-scheme: dark)" in css and "@media (prefers-color-scheme: light)" in css
    assert "var(--lg-header-bg) 44px, var(--window-bg-color) 44px" in css
    assert ",0.300)" in css


def test_reduce_transparency_wins():
    s = Settings(header_opacity=0.2, reduce_transparency=True)
    assert headerbar.gtk4_css(s, *both(s)) == ""
    s = Settings(header_opacity=0.2, header_height=40, reduce_transparency=True)
    assert "--lg-header-bg" not in headerbar.gtk4_css(s, *both(s))


def test_targets_append_header_rules(fake_env):
    css4 = gtk_css(fake_env, "gtk4", header_height=56, header_opacity=0.5)
    assert css4.rstrip().endswith("}") and "min-height: 56px" in css4 and "--lg-header-bg" in css4
    css3 = gtk_css(fake_env, "gtk3", header_height=40, header_opacity=0.5)
    assert "min-height: 40px" in css3 and "headerbar, .titlebar, headerbar:backdrop" in css3
    assert "min-height: 56px" not in gtk_css(fake_env, "gtk4")


def test_old_settings_files_still_load(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"frost": 0.3}))
    s = settings_mod.load(p)
    assert s.header_height == 47 and s.header_opacity is None
    settings_mod.save(Settings(header_height=40, header_opacity=0.25), p)
    s = settings_mod.load(p)
    assert (s.header_height, s.header_opacity) == (40, 0.25)
