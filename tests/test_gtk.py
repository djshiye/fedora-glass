from __future__ import annotations

import re

import pytest

from liquidglass import palette
from liquidglass.render import gtk3, gtk4
from liquidglass.settings import Settings
from liquidglass.targets import gtk as tg
from liquidglass.targets.base import Context, FlatpakOverride, GSet, WriteFile

CASES = [(d, f) for d in (True, False) for f in (0.0, 0.5, 1.0)]

LIBADWAITA_VARS = (
    "window-bg-color", "view-bg-color", "headerbar-bg-color", "sidebar-bg-color",
    "secondary-sidebar-bg-color", "card-bg-color", "dialog-bg-color", "popover-bg-color",
    "thumbnail-bg-color", "accent-bg-color", "accent-fg-color", "destructive-bg-color",
    "success-bg-color", "warning-bg-color", "shade-color",
)
ADW_GTK3_NAMES = (
    "window_bg_color", "view_bg_color", "headerbar_bg_color", "sidebar_bg_color",
    "card_bg_color", "popover_bg_color", "dialog_bg_color", "accent_bg_color",
    "accent_color", "accent_fg_color", "destructive_bg_color", "success_bg_color",
    "warning_bg_color",
)


def toks(dark, frost, **kw):
    return palette.build(Settings(frost=frost, **kw), dark=dark)


def ctx_for(env, dark=True, frost=0.4, **kw):
    s = Settings(frost=frost, scheme="dark" if dark else "light", **kw)
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d if dark else l, dark=d, light=l, env=env)


def balanced(css: str) -> bool:
    depth = 0
    for ch in re.sub(r"/\*.*?\*/", "", css, flags=re.S):
        depth += ch == "{"
        depth -= ch == "}"
        if depth < 0:
            return False
    return depth == 0


@pytest.mark.parametrize("frost", (0.0, 0.5, 1.0))
def test_gtk4_renders_both_schemes(frost):
    css = gtk4.render(toks(True, frost), toks(False, frost))
    assert "None" not in css and "$" not in css and "nan" not in css
    assert balanced(css)
    assert "@media (prefers-color-scheme: dark)" in css
    assert "@media (prefers-color-scheme: light)" in css
    for name in LIBADWAITA_VARS:
        assert css.count(f"--{name}:") == 2, name
    for name in ADW_GTK3_NAMES[:6]:
        assert css.count(f"@define-color {name} ") == 2, name


def test_gtk4_single_scheme_has_no_media():
    css = gtk4.render(toks(False, 0.3))
    assert "@media" not in css and balanced(css)


def test_gtk4_every_lg_variable_is_defined():
    css = gtk4.render(toks(True, 0.4), toks(False, 0.4))
    used = set(re.findall(r"var\((--lg-[\w-]+)\)", css))
    defined = set(re.findall(r"(--lg-[\w-]+):", css))
    assert used and used <= defined, used - defined


def test_gtk4_surfaces_carry_alpha_and_rim():
    t = toks(True, 0.0)
    css = gtk4.render(t, toks(False, 0.0))
    assert f"--window-bg-color: {t.window.css}" in css
    assert t.window.a < 1
    assert f"--lg-rim: {t.highlight.css}" in css
    assert "inset 0 1px 0 var(--lg-rim)" in css


def test_gtk4_menus_and_dialogs_stay_solid_enough():
    for dark in (True, False):
        t = toks(dark, 0.0)
        assert gtk4.popover_color(t).a >= 0.9
        assert gtk4.dialog_color(t).a >= 0.95


def test_gtk4_does_not_touch_terminal_surface():
    css = gtk4.render(toks(True, 0.4), toks(False, 0.4))
    assert "vte-terminal" not in css


def test_gtk4_radius_follows_settings():
    t = toks(True, 0.4, radius=26)
    assert "--window-radius: 26px" in gtk4.render(t, toks(False, 0.4, radius=26))


def test_gtk4_accent_follows_settings():
    t = toks(True, 0.4, accent="#e62d42")
    assert t.accent.css in gtk4.render(t, toks(False, 0.4, accent="#e62d42"))


@pytest.mark.parametrize("dark,frost", CASES)
def test_gtk3_renders(dark, frost):
    css = gtk3.render(toks(dark, frost))
    assert "None" not in css and "$" not in css
    assert balanced(css)
    for name in ADW_GTK3_NAMES:
        assert f"@define-color {name} " in css, name
    assert "var(" not in css and "color-mix" not in css and "@media" not in css


@pytest.mark.parametrize("dark", (True, False))
def test_gtk3_named_colours_are_all_defined(dark):
    css = gtk3.render(toks(dark, 0.4))
    defined = set(re.findall(r"@define-color (\w+) ", css))
    body = css.split("\n\n", 2)[-1]
    used = set(re.findall(r"@(\w+)", body)) - {"define"}
    assert used <= defined, used - defined


def test_gtk3_theme_name_follows_scheme():
    assert gtk3.theme_name(toks(True, 0.4)) == "adw-gtk3-dark"
    assert gtk3.theme_name(toks(False, 0.4)) == "adw-gtk3"


# ---- targets -------------------------------------------------------------------
def by_id(i):
    return next(t for t in tg.TARGETS if t.id == i)


def test_targets_are_listed_in_desktop_group():
    assert [t.id for t in tg.TARGETS] == ["gtk4", "gtk3", "flatpak"]
    assert {t.group for t in tg.TARGETS} == {"Desktop"}
    assert by_id("gtk4").name == "GTK 4 and libadwaita apps"


def test_gtk4_target_writes_both_files(fake_env):
    acts = by_id("gtk4").plan(ctx_for(fake_env))
    paths = {a.path for a in acts if isinstance(a, WriteFile)}
    assert paths == {fake_env.config / "gtk-4.0/gtk.css", fake_env.config / "gtk-4.0/gtk-dark.css"}
    assert all("@media (prefers-color-scheme: dark)" in a.content for a in acts)


def test_gtk3_works_without_adw_gtk3(fake_env):
    """Without adw-gtk3 the user's GTK 3 theme (Orchis, say) stays and our sheet goes on top."""
    t = by_id("gtk3")
    assert t.detect(fake_env).available
    ctx = ctx_for(fake_env)
    acts = t.plan(ctx)
    assert not [a for a in acts if isinstance(a, GSet)], "the gtk-theme must stay the user's"
    w = next(a for a in acts if isinstance(a, WriteFile))
    assert w.path == fake_env.config / "gtk-3.0/gtk.css" and "headerbar" in w.content
    assert t.live_notes(ctx) == ["Some GTK 3 details need adw-gtk3: sudo dnf install adw-gtk3-theme"]
    (fake_env.data / "themes/adw-gtk3/gtk-3.0").mkdir(parents=True)
    assert t.live_notes(ctx) == []
    assert any(isinstance(a, GSet) for a in t.plan(ctx))


@pytest.mark.parametrize("theme,css,want_dark", [
    ("Orchis-Dark", None, True),                  # the name says so
    ("Orchis-Dark-Compact", None, True),
    ("Foo_dark", None, True),
    ("Adwaita", None, False),                     # GTK 3's built-in theme is light
    ("Mine", "@define-color theme_bg_color #2c2c2c;", True),
    ("Mine", "@define-color window_bg_color #fafafa;", False),
    ("Mine", "window { color: red; }", None),     # can't tell: follow the desktop
    ("Missing", None, None),
])
@pytest.mark.parametrize("desktop_dark", (True, False))
def test_gtk3_sheet_follows_a_kept_themes_darkness(fake_env, theme, css, want_dark, desktop_dark):
    """Orchis-Dark kept in light mode: its tab strip stays dark, so our GTK 3 sheet must be
    the dark one too, or tab labels go dark-on-dark."""
    fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] = f"'{theme}'"
    if css is not None:
        d = fake_env.home / ".themes" / theme / "gtk-3.0"
        d.mkdir(parents=True)
        (d / "gtk.css").write_text(css)
    ctx = ctx_for(fake_env, dark=desktop_dark)
    w = next(a for a in by_id("gtk3").plan(ctx) if isinstance(a, WriteFile))
    dark = desktop_dark if want_dark is None else want_dark
    # A dark sheet on the light desktop sits on light window glass: it gets a denser fill.
    assert w.content.startswith(gtk3.render(ctx.dark if dark else ctx.light, dark and not desktop_dark))


def test_gtk3_dark_sheet_on_light_glass_is_denser():
    """Orchis-Dark kept with the desktop in light mode: white text on the light window
    glass measured 3.1:1 on a white wallpaper; a fill of 0.82 or more gives 4.9:1."""
    t = toks(True, 0.4)
    col = gtk3.named_colors(t, on_light_glass=True)
    for k in ("window_bg_color", "headerbar_bg_color", "theme_bg_color"):
        assert col[k].a >= gtk3.DARK_ON_LIGHT_GLASS_ALPHA
    assert gtk3.named_colors(t)["window_bg_color"].a == t.window.a < gtk3.DARK_ON_LIGHT_GLASS_ALPHA
    # A light sheet never changes: it isn't the one with white text.
    light = toks(False, 0.4)
    assert gtk3.named_colors(light, on_light_glass=True) == gtk3.named_colors(light)


def test_gtk3_check_and_radio_are_small_boxes_on_any_theme():
    """Orchis makes checks 40 px (24 px + 8 px padding) with its own ring glyph, so our fill
    showed as a big blue circle. The sheet resets the box and draws GTK's own marks."""
    css = gtk3.render(toks(True, 0.4))
    rule = re.search(r"\ncheck, radio \{([^}]*)\}", css).group(1)
    for decl in ("min-width: 14px", "min-height: 14px", "padding: 1px", "margin: 0", "-gtk-icon-source: none"):
        assert decl in rule
    for state, icon in (("check:checked", "check-symbolic"), ("radio:checked", "bullet-symbolic"),
                        ("check:indeterminate, radio:indeterminate", "dash-symbolic")):
        assert re.search(re.escape(state) + r" \{ -gtk-icon-source: -gtk-recolor\(url\(\"resource:///org/gtk/libgtk/"
                         r"theme/Adwaita/assets/" + icon + r"\.svg\"\)\); \}", css), state


@pytest.mark.parametrize("desktop_dark", (True, False))
def test_gtk3_with_adw_gtk3_follows_the_desktop(fake_env, desktop_dark):
    (fake_env.data / "themes/adw-gtk3/gtk-3.0").mkdir(parents=True)
    fake_env.gs[("org.gnome.desktop.interface", None)]["gtk-theme"] = "'Orchis-Dark'"
    ctx = ctx_for(fake_env, dark=desktop_dark)
    w = next(a for a in by_id("gtk3").plan(ctx) if isinstance(a, WriteFile))
    assert w.content.startswith(gtk3.render(ctx.tokens))


def test_gtk3_also_found_in_dot_themes(fake_env):
    (fake_env.home / ".themes/adw-gtk3/gtk-3.0").mkdir(parents=True)
    assert "adw-gtk3 found" in by_id("gtk3").detect(fake_env).detail


@pytest.mark.parametrize("dark,theme", [(True, "'adw-gtk3-dark'"), (False, "'adw-gtk3'")])
def test_gtk3_plan(fake_env, dark, theme):
    (fake_env.data / "themes/adw-gtk3/gtk-3.0").mkdir(parents=True)
    acts = by_id("gtk3").plan(ctx_for(fake_env, dark=dark))
    gset = next(a for a in acts if isinstance(a, GSet))
    assert (gset.schema, gset.key, gset.value) == ("org.gnome.desktop.interface", "gtk-theme", theme)
    w = next(a for a in acts if isinstance(a, WriteFile))
    assert w.path == fake_env.config / "gtk-3.0/gtk.css"


def test_flatpak_target(fake_env):
    t = by_id("flatpak")
    assert t.detect(fake_env).available
    (ov,) = t.plan(ctx_for(fake_env))
    assert isinstance(ov, FlatpakOverride)
    assert ov.filesystems == ("xdg-config/gtk-4.0:ro", "xdg-config/gtk-3.0:ro")
    assert any("flatpak install flathub org.gtk.Gtk3theme.adw-gtk3" in n for n in t.notes)


def test_flatpak_absent(fake_env, monkeypatch):
    monkeypatch.setattr(fake_env, "which", lambda n: None)
    assert not by_id("flatpak").detect(fake_env).available


def test_engine_replaces_symlinked_gtk_css(fake_env):
    """A user's gtk.css is often a link into another theme: applying must not write through it."""
    from liquidglass.engine import Engine
    theme = fake_env.home / ".themes/Orchis-Dark/gtk-4.0"
    theme.mkdir(parents=True)
    (theme / "gtk.css").write_text("/* orchis */")
    d = fake_env.config / "gtk-4.0"
    d.mkdir(parents=True)
    (d / "gtk.css").symlink_to(theme / "gtk.css")
    Engine(fake_env, targets=[by_id("gtk4")]).apply(Settings(frost=0.3))
    assert not (d / "gtk.css").is_symlink()
    assert (theme / "gtk.css").read_text() == "/* orchis */"
    assert "Liquid Glass" in (d / "gtk.css").read_text()
    assert Engine(fake_env, targets=[by_id("gtk4")]).revert("gtk4") == []
    assert (d / "gtk.css").is_symlink()


def test_calculator_keys_outrank_the_glass_button_rule():
    # The general glass button selector carries many :not()s, so a plain
    # ".math-buttons button" rule loses to it. The Calculator rule must extend it.
    t = toks(False, 0.4)
    css = gtk4.render(toks(True, 0.4), t)
    head = ".math-buttons " + gtk4._geometry(t)["glass_btn"] + " {"
    assert head in css
    start = css.index(head) + len(head)
    body = css[start:css.index("}", start)]
    assert "var(--card-bg-color)" in body and "background-image: none" in body


def _specificity(selector: str) -> tuple[int, int, int]:
    """CSS specificity (ids, classes and pseudo-classes, elements) of one simple selector chain."""
    s = re.sub(r":not\(([^)]*)\)", r" \1", selector)
    classes = len(re.findall(r"[.:][\w-]+", s))
    elements = len(re.findall(r"(?:^|[\s>+~])([a-z][\w-]*)", s))
    return 0, classes, elements


def test_header_buttons_are_flat_and_outrank_glass_pills():
    t = toks(True, 0.4)
    geo = gtk4._geometry(t)
    pill = _specificity(geo["glass_btn"] + ":hover")
    for sel in geo["hdr_btn_hover"].split(", "):
        assert _specificity(sel) > pill, sel
    for sel in geo["hdr_btn"].split(", "):
        assert _specificity(sel) > _specificity(geo["glass_btn"]), sel
        # Calls to action stay filled.
        assert ":not(.suggested-action)" in sel and ":not(.destructive-action)" in sel
    css = gtk4.render(t)
    rest = css.split(geo["hdr_btn"] + " {", 1)[1].split("}", 1)[0]
    assert "background-color: transparent" in rest and "box-shadow: none" in rest
    assert "border-radius: 8px" in rest
    # Flat but clearly enabled: 90% of the title's colour, not a disabled-looking grey.
    assert "color: color-mix(in srgb, currentColor 90%, transparent)" in rest
    assert geo["hdr_btn_checked"] + " { color: var(--accent-color); }" not in css


def test_window_controls_are_flat_and_close_is_red_only_on_hover():
    css = gtk4.render(toks(True, 0.4))
    assert "windowcontrols > button > image {\n  background-color: var(--lg-glass)" not in css
    red = [line for line in css.splitlines() if "var(--lg-close)" in line]
    assert red and all(":hover" in line for line in red)


@pytest.mark.parametrize("dark", (True, False))
def test_gtk3_header_buttons_are_flat(dark):
    css = gtk3.render(toks(dark, 0.4))
    assert ".titlebutton, headerbar .titlebutton { border-radius: 999px" not in css
    assert "headerbar .titlebutton.close:hover" in css and "@lg_close" in css
    assert "@lg_tile" in css and "@lg_tile_press" in css
    assert "color: alpha(@headerbar_fg_color, 0.9);" in css
    # Selected (checked) header buttons show it with the tile; accent text is too faint on glass.
    assert ":checked { color: @accent_color; }" not in css


def test_unfocused_bars_fade_once_to_65_percent():
    css = gtk4.render(toks(True, 0.4))
    assert "headerbar:backdrop > windowhandle," in css and "filter: opacity(0.65)" in css
    # Icons don't add a second fade of their own on top of the bar's.
    assert ":backdrop { color: color-mix" not in css
    gtk3_css = gtk3.render(toks(True, 0.4))
    assert "alpha(@headerbar_fg_color, 0.65)" in gtk3_css


def test_files_path_bar_is_one_field_with_flat_segments():
    geo = gtk4._geometry(toks(True, 0.4))
    assert _specificity(geo["path_btn"]) > _specificity(geo["glass_btn"])
    assert _specificity(geo["path_btn_hover"]) > _specificity(geo["glass_btn"] + ":hover")
    css = gtk4.render(toks(True, 0.4))
    assert ".nautilus-pathbar .path-bar-box { background: none" in css
