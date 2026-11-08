"""App window bug hunt after 1.5.7: readability fixes in GTK 4, GTK 3, gedit and Qt."""

from __future__ import annotations

import re

import pytest

from fedoraglass import palette
from fedoraglass.color import Color
from fedoraglass.render import gtk3, gtk4, kvantum
from fedoraglass.settings import Settings
from fedoraglass.targets import gtk as tg
from fedoraglass.targets.base import GReset, GSet, WriteFile

from test_gtk import ctx_for


def toks(dark: bool, frost: float = 0.4):
    return palette.build(Settings(frost=frost), dark=dark)


def over(c: Color, bg: Color) -> Color:
    return Color(*(c.a * x + (1 - c.a) * y for x, y in zip((c.r, c.g, c.b), (bg.r, bg.g, bg.b))), 1.0)


@pytest.mark.parametrize("dark", (True, False))
@pytest.mark.parametrize("frost", (0.0, 0.5, 1.0))
def test_destructive_buttons_are_solid_and_readable(dark, frost):
    """libadwaita 1.6+ draws a Delete button as red text on a 15 % tint of the text colour.
    Our destructive text colour is made to sit on red (white in light, near-black in dark), so
    the label read white on near-white and black on dark red. The button is now solid red."""
    t = toks(dark, frost)
    css = gtk4.render(t)
    rule = re.search(r"button\.destructive-action:not\(\.flat\), button\.destructive-action:not\(\.flat\):hover,"
                     r"\s*button\.destructive-action:not\(\.flat\):active, button\.destructive-action:not\(\.flat\):checked"
                     r" \{([^}]*)\}", css)
    assert rule, "destructive buttons need their own fill in every state"
    assert "background-color: var(--destructive-bg-color)" in rule.group(1)
    assert "color: var(--destructive-fg-color)" in rule.group(1)
    assert "\nbutton.destructive-action { color: var(--destructive-fg-color); }" not in css
    cols = gtk4.adwaita_colors(t)
    assert cols["destructive-fg-color"].contrast(cols["destructive-bg-color"]) >= 4.5


@pytest.mark.parametrize("frost", (0.0, 0.5, 1.0))
def test_active_toggle_is_light_in_light_mode(frost):
    """The chosen toggle of a toggle group (One | Two | Three) was the text colour at 90 %:
    a near-black tile under near-black text in light mode."""
    t = toks(False, frost)
    css = gtk4.scheme_vars(t)
    bg = Color(1, 1, 1, 0.9)
    assert f"--active-toggle-bg-color: {bg.css};" in css
    assert t.fg.contrast(over(bg, t.window.with_alpha(1))) >= 7
    d = toks(True, frost)
    assert f"--active-toggle-bg-color: {d.fg.with_alpha(0.22).css};" in gtk4.scheme_vars(d)


def test_spin_row_field_is_part_of_the_row():
    css = gtk4.render(toks(True))
    rule = re.search(r"\nrow\.spin spinbutton, row\.spin spinbutton:focus-within \{([^}]*)\}", css)
    assert rule and "background-color: transparent" in rule.group(1) and "box-shadow: none" in rule.group(1)


@pytest.mark.parametrize("render", ("gtk4", "gtk3"))
def test_tabs_on_every_side_round_toward_their_page(render):
    css = gtk4.render(toks(True)) if render == "gtk4" else gtk3.render(toks(True))
    for side in ("bottom", "left", "right"):
        assert f"notebook > header.{side} > tabs > tab {{ border-radius:" in css


def test_gedit_gutter_takes_the_text_glass():
    css = gtk3.render(toks(True))
    assert "textview border { background-color: transparent; color: @lg_fg_dim; }" in css


GEDIT = ("org.gnome.gedit.preferences.editor", None)


@pytest.mark.parametrize("theme,desktop_dark,key,value", [
    ("Orchis-Dark", False, "style-scheme-for-light-theme-variant", "'solarized-dark'"),
    ("Orchis-Dark", True, "style-scheme-for-light-theme-variant", "'solarized-dark'"),
    ("Adwaita", True, "style-scheme-for-dark-theme-variant", "'tango'"),
])
def test_gedit_scheme_follows_the_kept_gtk3_theme(fake_env, theme, desktop_dark, key, value):
    """gedit picks its scheme by the desktop's light/dark, but draws with the GTK 3 theme.
    Orchis-Dark on a light desktop gave Tango: a white gutter with white numbers and dark
    syntax colours on dark glass."""
    fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] = f"'{theme}'"
    fake_env.gs[GEDIT] = {"style-scheme-for-dark-theme-variant": "'solarized-dark'",
                          "style-scheme-for-light-theme-variant": "'tango'"}
    acts = tg.Gtk3().plan(ctx_for(fake_env, dark=desktop_dark))
    sets = [a for a in acts if isinstance(a, GSet) and a.schema == GEDIT[0]]
    assert [(a.key, a.value, a.keep_user_change) for a in sets] == [(key, value, True)]
    assert any(isinstance(a, WriteFile) for a in acts)


def test_gedit_left_alone_when_absent_or_already_matching(fake_env):
    fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] = "'Orchis-Dark'"
    acts = tg.Gtk3().plan(ctx_for(fake_env, dark=False))
    assert not [a for a in acts if isinstance(a, GSet)], "gedit not installed: nothing to set"
    fake_env.gs[GEDIT] = {"style-scheme-for-dark-theme-variant": "'cobalt'",
                          "style-scheme-for-light-theme-variant": "'cobalt'"}
    assert not [a for a in tg.Gtk3().plan(ctx_for(fake_env, dark=False)) if isinstance(a, GSet)]


def test_gedit_put_back_when_the_theme_darkness_is_unknown(fake_env):
    fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] = "'Unknown'"
    acts = tg.Gtk3().plan(ctx_for(fake_env, dark=False))
    assert {a.key for a in acts if isinstance(a, GReset)} == set(tg._GEDIT_KEYS.values())


@pytest.mark.parametrize("dark", (True, False))
@pytest.mark.parametrize("frost", (0.0, 0.5, 1.0))
def test_qt_button_colour_keeps_text_readable(dark, frost):
    """Kvantum's button colour was the card colour forced to 50 % alpha: in dark mode that
    turned a 7 % white card into a mid grey (#949597) under white button text (2.9:1)."""
    cfg = kvantum.build_config(toks(dark, frost))
    get = lambda k: Color.hex(re.search(rf"\n{re.escape(k)}=(#[0-9a-f]{{6}})", cfg).group(1))
    assert get("button.text.color").contrast(get("button.color")) >= 7
