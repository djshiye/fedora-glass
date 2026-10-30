"""GNOME Shell targets: CSS renderer, the glass extension, extension settings."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from liquidglass import palette
from liquidglass.color import Color
from liquidglass.engine import Engine
from liquidglass.render import glass as rg
from liquidglass.render import shell as rs
from liquidglass.settings import Settings
from liquidglass.targets import shell as ts
from liquidglass.targets.base import GSet, ListEdit, WriteFile

GRID = [(f, d) for f in (0.0, 0.5, 1.0) for d in (True, False)]

def tokens(frost: float, dark: bool, **kw):
    return palette.build(Settings(frost=frost, **kw), dark=dark)


# ---- CSS ---------------------------------------------------------------------------------
@pytest.mark.parametrize("frost,dark", GRID)
def test_css_renders_cleanly(frost, dark):
    css = rs.render_css(tokens(frost, dark))
    assert css.count("{") == css.count("}") > 100
    assert f"gnome-shell-{'dark' if dark else 'light'}.css" in css.splitlines()[4]
    for bad in ("None", "$", "nan", "inf"):
        assert bad not in css
    # every colour we emit is a valid CSS colour
    for m in re.finditer(r"rgba\(([^)]*)\)", css):
        r, g, b, a = (float(x) for x in m.group(1).split(","))
        assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255 and 0 <= a <= 1


@pytest.mark.parametrize("frost,dark", GRID)
def test_css_never_asks_for_multiple_shadows(frost, dark):
    """St draws one box-shadow per node; a comma-separated list would be dropped."""
    css = rs.render_css(tokens(frost, dark))
    for m in re.finditer(r"box-shadow:([^;}]*)", css):
        depth, value = 0, m.group(1)
        for ch in value:
            depth += ch == "("
            depth -= ch == ")"
            assert not (ch == "," and depth == 0), value


def test_css_uses_token_colours_and_radius():
    t = tokens(0.3, True, radius=22)
    css = rs.render_css(t)
    assert rs.surfaces(t)["popover"].css in css
    assert t.accent.css in css
    assert f"border-radius: {rs.radii(t)['r_menu']}px" in css
    assert "border-radius: 24px" in css  # r_menu = 22 + 2


def test_shell_surfaces_are_thinner_than_tokens_only_when_blur_is_real():
    t = tokens(0.0, True)
    assert rs.surfaces(t)["popover"].a < t.popover.a
    solid = palette.build(Settings(frost=0, reduce_transparency=True), dark=True)
    assert rs.surfaces(solid)["popover"].a == solid.popover.a


def test_extension_rules_outrank_extension_stylesheets():
    css = rs.render_css(tokens(0.5, True))
    for sel in ("#uiGroup .popup-menu-content.wg-menu", "#uiGroup #dashtopanelScrollview .overview-tile:hover .dtp-container"):
        assert sel in css
    # core theme rules are not boosted
    assert "\n.popup-menu-content, .candidate-popup-content {" in css


def test_frost_changes_the_css():
    assert rs.render_css(tokens(0, True)) != rs.render_css(tokens(1, True))
    assert rs.render_css(tokens(0.5, True)) != rs.render_css(tokens(0.5, False))


def install(env, *uuids, refraction=True):
    for u in uuids:
        d = env.data / "gnome-shell/extensions" / u
        d.mkdir(parents=True, exist_ok=True)
        (d / "metadata.json").write_text("{}")
        if u == ts.BLUR and refraction:
            (d / "effects/refraction").mkdir(parents=True)


def context(env, frost=0.5, dark=True, **kw):
    e = Engine(env, ts.TARGETS)
    return e.context(Settings(frost=frost, scheme="dark" if dark else "light", **kw))


def test_targets_order_and_ids():
    assert [t.id for t in ts.TARGETS] == ["shell", "glass", "dash-to-panel", "arcmenu"]
    assert [t.group for t in ts.TARGETS] == ["Desktop", "Desktop", "Panel", "Panel"]


def test_detect_needs_the_extension(fake_env):
    for t in ts.TARGETS:
        assert t.detect(fake_env).available == (t.id == "glass")   # ours ships with Liquid Glass
    install(fake_env, ts.USER_THEME, ts.BLUR, ts.DASH_TO_PANEL, ts.ARCMENU)
    for t in ts.TARGETS:
        assert t.detect(fake_env).available


def test_shell_target_writes_theme_and_enables_user_themes(fake_env):
    install(fake_env, ts.USER_THEME)
    fake_env.gs[("org.gnome.shell", None)] = {
        "enabled-extensions": "['arcmenu@arcmenu.com']",
        "disabled-extensions": f"['{ts.USER_THEME}', 'other@x']",
    }
    acts = ts.GnomeShell().plan(context(fake_env))
    write = next(a for a in acts if isinstance(a, WriteFile))
    assert write.path == fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css"
    sets = {(a.schema, a.key): a.value for a in acts if isinstance(a, GSet)}
    edits = {(a.schema, a.key): (a.add, a.remove) for a in acts if isinstance(a, ListEdit)}
    assert edits[("org.gnome.shell", "enabled-extensions")] == ((ts.USER_THEME,), ())
    assert edits[("org.gnome.shell", "disabled-extensions")] == ((), (ts.USER_THEME,))
    assert sets[("org.gnome.shell.extensions.user-theme", "name")] == "'LiquidGlass'"
    # Through the engine: only our item is added/removed, and revert undoes only that.
    gs = fake_env.gs[("org.gnome.shell", None)]
    Engine(fake_env, [ts.GnomeShell()]).apply(Settings())
    assert gs["enabled-extensions"] == f"['arcmenu@arcmenu.com', '{ts.USER_THEME}']"
    assert gs["disabled-extensions"] == "['other@x']"
    gs["enabled-extensions"] = f"['arcmenu@arcmenu.com', '{ts.USER_THEME}', 'later@x']"   # user enables one more
    Engine(fake_env, [ts.GnomeShell()]).revert()
    assert gs["enabled-extensions"] == "['arcmenu@arcmenu.com', 'later@x']"
    assert gs["disabled-extensions"] == f"['other@x', '{ts.USER_THEME}']"


def test_shell_target_leaves_extension_lists_alone_when_already_enabled(fake_env):
    install(fake_env, ts.USER_THEME)
    fake_env.gs[("org.gnome.shell", None)] = {"enabled-extensions": f"['{ts.USER_THEME}']", "disabled-extensions": "@as []"}
    Engine(fake_env, [ts.GnomeShell()]).apply(Settings())
    assert fake_env.gs[("org.gnome.shell", None)] == {"enabled-extensions": f"['{ts.USER_THEME}']",
                                                     "disabled-extensions": "@as []"}
    Engine(fake_env, [ts.GnomeShell()]).revert()
    assert fake_env.gs[("org.gnome.shell", None)]["enabled-extensions"] == f"['{ts.USER_THEME}']"


def test_shell_target_bounces_the_theme_name_only_when_css_changed(fake_env):
    install(fake_env, ts.USER_THEME)
    schema = ("org.gnome.shell.extensions.user-theme", None)
    fake_env.gs[schema] = {"name": "'LiquidGlass'"}
    target, ctx = ts.GnomeShell(), context(fake_env)
    names = lambda: [a.value for a in target.plan(ctx) if isinstance(a, GSet) and a.key == "name"]  # noqa: E731
    assert names() == ["''", "'LiquidGlass'"]       # new CSS: bounce so User Themes reloads it
    path = target.css_path(fake_env)
    path.parent.mkdir(parents=True)
    path.write_text(rs.render_css(ctx.tokens))
    assert names() == ["'LiquidGlass'"]             # same CSS: nothing to reload


def test_glass_target_installs_extension_and_config(fake_env):
    acts = ts.GlassEffects().plan(context(fake_env, frost=0.0))
    d = fake_env.data / "gnome-shell/extensions" / rg.UUID
    writes = {a.path: a.content for a in acts if isinstance(a, WriteFile)}
    for name in rg.FILES:
        assert d / name in writes
    meta = json.loads(writes[d / "metadata.json"])
    assert meta["uuid"] == rg.UUID and "50" in meta["shell-version"]
    cfg = json.loads(writes[fake_env.config / "liquid-glass/shell-glass.json"])
    assert cfg["panel"]["enabled"] and cfg["menus"]["behind"] == "windows"
    assert cfg["look"]["bend"] > 0 and cfg["look"]["refraction"] > 0
    edits = {(a.schema, a.key): (a.add, a.remove) for a in acts if isinstance(a, ListEdit)}
    assert edits[("org.gnome.shell", "enabled-extensions")] == ((rg.UUID,), ())
    # Without Blur my Shell there is nothing of it to switch off.
    assert not [a for a in acts if isinstance(a, GSet)]


def test_glass_target_switches_off_overlapping_blur_my_shell_parts(fake_env):
    install(fake_env, ts.BLUR)
    acts = ts.GlassEffects().plan(context(fake_env))
    offs = {a.schema.rsplit(".", 1)[1] for a in acts if isinstance(a, GSet) and a.key == "blur" and a.value == "false"}
    assert {"panel", "popup", "overview", "applications"} <= offs


def test_glass_config_follows_frost_and_settings(fake_env):
    liquid = rg.config(Settings(frost=0.0), context(fake_env, frost=0.0).tokens)
    frosted = rg.config(Settings(frost=1.0), context(fake_env, frost=1.0).tokens)
    assert liquid["look"]["bend"] > frosted["look"]["bend"]
    assert liquid["look"]["blur"] < frosted["look"]["blur"]
    assert liquid["look"]["dispersion"] > frosted["look"]["dispersion"]
    s = Settings(glass_panel=False, glass_see_windows=False, blur_app_windows=False)
    cfg = rg.config(s, context(fake_env, glass_panel=False, glass_see_windows=False, blur_app_windows=False).tokens)
    assert not cfg["panel"]["enabled"] and cfg["menus"]["behind"] == "wallpaper" and not cfg["windows"]["enabled"]
    calm = Settings(reduce_transparency=True)
    cfg = rg.config(calm, context(fake_env, reduce_transparency=True).tokens)
    assert not any(cfg[k]["enabled"] for k in ("panel", "menus", "windows", "overview"))
    assert "steam" in cfg["windows"]["skip"]


def test_window_glass_has_a_lens_and_no_bleed(fake_env):
    cfg = rg.config(Settings(), context(fake_env).tokens)
    win = cfg["windows"]
    assert win["behind"] == "windows"
    assert win["look"]["refraction"] > 0 and win["look"]["bend"] > 0 and win["look"]["highlight"] > 0
    assert win["look"]["bleed"] == 0 and win["terminalLook"]["bleed"] == 0
    # Windows get a narrower lens than the menus, and their own part controls drive it.
    assert win["look"]["refraction"] < cfg["parts"]["quicksettings"]["look"]["refraction"]
    s = Settings(parts={"windows": {"refraction": 0.0, "reflections": 0.0}, "terminal": {"reflections": 1.0}})
    own = rg.config(s, context(fake_env, parts=s.parts).tokens)["windows"]
    assert own["look"]["bend"] == 0 and own["look"]["highlight"] == 0
    assert own["terminalLook"]["highlight"] > win["terminalLook"]["highlight"]
    seen = rg.config(Settings(glass_see_windows=False), context(fake_env, glass_see_windows=False).tokens)
    assert seen["windows"]["behind"] == "wallpaper"


def test_content_views_let_a_little_glass_through():
    from liquidglass.render.gtk4 import view_color
    for dark in (True, False):
        for f in (0.0, 0.45, 1.0):
            t = palette.build(Settings(frost=f), dark=dark)
            layer = view_color(t)
            total = 1 - (1 - t.window.a) * (1 - layer.a)        # the view on the window background
            assert total == pytest.approx(t.view.a, abs=2e-3) and 0.85 <= total <= 0.94
    calm = palette.build(Settings(reduce_transparency=True), dark=True)
    assert 1 - (1 - calm.window.a) * (1 - view_color(calm).a) >= 0.97 - 1e-3


def test_dash_to_panel_floating_and_docked(fake_env):
    install(fake_env, ts.DASH_TO_PANEL)
    def values(style):
        acts = ts.DashToPanel().plan(context(fake_env, panel_style=style, panel_margin=10, radius=18))
        return {a.key: a.value for a in acts if isinstance(a, GSet)}
    floating, docked = values("floating"), values("docked")
    assert floating["panel-top-bottom-margins"] == floating["panel-side-margins"] == "10"
    assert floating["global-border-radius"] == "4"   # steps of 4 px
    assert docked["panel-top-bottom-margins"] == docked["panel-side-margins"] == "0"
    assert docked["global-border-radius"] == "0"
    layout = ("panel-sizes", "panel-element-positions", "panel-positions", "dot-position", "appicon-margin")
    assert not set(floating) & set(layout)
    assert floating["trans-use-custom-bg"] == "true" and floating["trans-use-dynamic-opacity"] == "false"


def test_arcmenu_values_have_the_schema_types(fake_env):
    install(fake_env, ts.ARCMENU)
    acts = ts.ArcMenu().plan(context(fake_env, frost=0.0, dark=False))
    v = {a.key: a.value for a in acts if isinstance(a, GSet)}
    assert v["override-menu-theme"] == "true"
    assert re.fullmatch(r"'rgba\(\d+,\d+,\d+,[\d.]+\)'", v["menu-background-color"])
    assert v["search-entry-border-radius"] == "(true, 999)"
    assert re.fullmatch(r"\(true, 'rgba?\([^)]*\)'\)", v["menu-button-bg-color"])
    assert v["menu-button-border-radius"] == "(true, 999)"
    assert v["menu-border-radius"].isdigit()


# ---- through the engine -------------------------------------------------------------------------
def seeded_env(env):
    """A fake gsettings store that knows every key the shell targets set."""
    install(env, ts.USER_THEME, ts.BLUR, ts.DASH_TO_PANEL, ts.ARCMENU)
    ctx = context(env)
    for t in ts.TARGETS:
        for a in t.plan(ctx):
            if isinstance(a, GSet):
                env.gs.setdefault((a.schema, a.path), {}).setdefault(a.key, "0")
    env.gs[("org.gnome.shell", None)] = {"enabled-extensions": "['x@y']", "disabled-extensions": f"['{ts.USER_THEME}']"}
    return env


def test_apply_then_revert_restores_everything(fake_env):
    seeded_env(fake_env)
    before = {k: dict(v) for k, v in fake_env.gs.items()}
    engine = Engine(fake_env, ts.TARGETS)
    results = engine.apply(Settings(frost=0.3))
    assert [r.status for r in results] == ["applied"] * 4, results
    gs = fake_env.gs
    assert gs[(ts.GlassEffects.BLUR_SCHEMA + ".panel", None)]["blur"] == "false"
    assert rg.UUID in gs[("org.gnome.shell", None)]["enabled-extensions"]
    assert (fake_env.data / "gnome-shell/extensions" / rg.UUID / "extension.js").is_file()
    assert ts.USER_THEME in gs[("org.gnome.shell", None)]["enabled-extensions"]
    assert (fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css").is_file()

    assert engine.revert() == []
    assert not (fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css").exists()
    assert not (fake_env.data / "gnome-shell/extensions" / rg.UUID / "extension.js").exists()
    assert not (fake_env.config / "liquid-glass/shell-glass.json").exists()
    assert {k: dict(v) for k, v in fake_env.gs.items()} == before


def test_reapplying_changes_nothing(fake_env):
    seeded_env(fake_env)
    engine = Engine(fake_env, ts.TARGETS)
    engine.apply(Settings(frost=0.6, scheme="light"))
    first = {k: dict(v) for k, v in fake_env.gs.items()}
    css = (fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css").read_text()
    engine.apply(Settings(frost=0.6, scheme="light"))
    assert {k: dict(v) for k, v in fake_env.gs.items()} == first
    assert (fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css").read_text() == css


def test_template_has_no_hardcoded_colours_outside_neutral_ones():
    """Colours come from tokens; the template may only use white for the switch handle and `transparent`."""
    raw = (Path(rs.__file__).resolve().parent.parent / "data/shell/glass.css.tpl").read_text()
    assert not re.findall(r"rgba?\(", raw)
    assert set(re.findall(r"#[0-9a-fA-F]{3,8}\b", raw)) <= {"#ffffff"}


def test_glass_running_reads_the_shell_state(fake_env, monkeypatch):
    from liquidglass.env import RunResult
    for out, code, want in (("({'uuid': <'x'>, 'state': <1.0>, 'path': <'/p'>},)", 0, True),
                            ("({'uuid': <'x'>, 'state': <6.0>},)", 0, False),   # initialized, not running yet
                            ("({},)", 0, False), ("", 1, False)):
        monkeypatch.setattr(fake_env, "run", lambda argv, timeout=30, o=out, c=code: RunResult(c, o, ""))
        assert ts.GlassEffects.running(fake_env) is want


def test_glass_surfaces_drop_the_drawn_outline():
    def block(css, sel):
        i = css.index("\n" + sel + " {")
        return css[i:css.index("}", i)]

    on = palette.build(Settings(), dark=True)
    css = rs.render_css(on)
    for sel in (".quick-settings", ".osd-window", ".switcher-list", ".notification-banner"):
        assert "border: 1px solid rgba(0,0,0,0)" in block(css, sel), sel
    # Surfaces the extension doesn't cover keep theirs.
    assert on.edge.css in block(css, ".workspace-switcher, .resize-popup, .screenshot-ui-panel, #LookingGlassDialog")
    assert rs.dtp_values(on)["trans-use-border"] == "false"
    assert "rgba(0,0,0,0)" in rs.arcmenu_values(on)["menu-border-color"]

    off = palette.build(Settings(glass_menus=False, glass_panel=False), dark=True)
    assert on.edge.css in block(rs.render_css(off), ".quick-settings")
    assert rs.dtp_values(off)["trans-use-border"] == "true"
    no_ext = palette.build(Settings(targets={"glass": False}), dark=True)
    assert on.edge.css in block(rs.render_css(no_ext), ".quick-settings")


# ---- per-part rendering and the light veil on glass-drawn surfaces -----------------------
def test_parts_reach_the_shell_css_and_gsettings():
    t = palette.build(Settings(radius=18, parts={
        "arcmenu": {"radius": 6}, "quicksettings": {"radius": 24}, "calendar": {"radius": 10},
        "panel": {"radius": 0}}), dark=True)
    css = rs.render_css(t)
    assert f"border-radius: {rs.radii(t)['r_big']}px" in css            # quick settings: 48
    assert f"border-radius: {rs.radii(t, 10)['r_cal']}px" in css        # calendar
    assert "${" not in css
    arc = rs.arcmenu_values(t)
    assert arc["menu-border-radius"] == str(rs.radii(t, 6)["r_menu"])
    assert rs.dtp_values(t)["global-border-radius"] == "0"
    assert rs.arcmenu_values(palette.build(Settings(), dark=True))["menu-border-radius"] == "20"


def test_glass_config_has_parts_and_bleed():
    s = Settings(parts={"panel": {"refraction": 0.0, "tint": "#102030"}})
    cfg = rg.config(s, palette.build(s, dark=True))
    assert cfg["look"]["bleed"] > 0
    assert set(cfg["parts"]) == {"panel", "arcmenu", "quicksettings", "calendar", "overview"}
    assert cfg["parts"]["panel"]["look"]["bend"] == 0 < cfg["parts"]["calendar"]["look"]["bend"]
    assert cfg["parts"]["panel"]["tint"][:3] == pytest.approx([0x10 / 255, 0x20 / 255, 0x30 / 255])
    for k in ("blur", "refraction", "bend", "bleed", "highlight"):
        assert k in cfg["parts"]["arcmenu"]["look"]
    assert cfg["menus"]["look"]["brightness"] < 1 and "panel" in cfg and "overview" in cfg


def test_veil_is_light_and_text_stays_readable():
    """The extension darkens the backdrop (brightness in glass.py), then the theme lays a
    thin veil. Assumed backdrop: an average photo (50% grey) scaled by that brightness."""
    for dark in (True, False):
        for f in (0.0, 0.45, 1.0):
            t = palette.build(Settings(frost=f), dark=dark)
            assert t.glass_menu_edges and t.glass_panel_edges
            surf = rs.surfaces(t)
            assert surf["popover"].a == pytest.approx(rs.veil(t, "menu"), abs=1e-6)
            assert surf["chrome"].a == pytest.approx(rs.veil(t, "panel"), abs=1e-6)
            assert surf["popover"].a <= 0.62 and surf["chrome"].a <= 0.45
            b = rg._brightness(t, f)
            assert (b < 1) if dark else (b >= 1)
            grey = Color(*(min(1.0, 0.5 * b),) * 3)
            for name in ("popover", "dialog", "osd", "chrome"):
                over = grey.mix(surf[name].with_alpha(1), surf[name].a)
                assert t.fg.contrast(over) >= 4.5, (name, dark, f)
    solid = palette.build(Settings(frost=1.0, opacity=0.95), dark=True)
    assert rs.surfaces(solid)["popover"].a >= 0.95                      # solid presets are left alone


def test_menus_never_wait_long_for_their_glass():
    # A menu is held invisible until its glass paints; that hold must always end on its own.
    js = (Path(rg.__file__).parent.parent / "data/extension/liquid-glass@djshiye.github.io/surfaces.js").read_text()
    limit = int(re.search(r"const HOLD_MAX_MS = (\d+);", js).group(1))
    assert limit <= 100
    hold = js[js.index("    _hold() {"):js.index("    _release() {")]
    assert "GLib.timeout_add(GLib.PRIORITY_HIGH, HOLD_MAX_MS" in hold        # wall-clock safety net
    assert "'after-paint'" in hold and "frames >= 4" in hold                 # and a frame-count one
    release = js[js.index("    _release() {"):js.index("    update(settings) {")]
    assert "source_remove" in release and "disconnect(this._holdPaint)" in release
    destroy = js[js.index("    destroy() {\n        if (this._later)"):]
    assert "this._release();" in destroy[:destroy.index("\n    }\n")]


def test_desktop_options_reach_the_extension(fake_env):
    t = context(fake_env).tokens
    assert rg.config(Settings(), t)["desktop"] == {"startOnDesktop": True, "overviewOff": False}
    assert rg.config(Settings(start_on_desktop=False), t)["desktop"] == {"startOnDesktop": False, "overviewOff": False}
    # With the overview off there is nothing to start in.
    assert rg.config(Settings(start_on_desktop=False, overview_off=True), t)["desktop"] == {
        "startOnDesktop": True, "overviewOff": True}


def test_start_on_desktop_keeps_dash_to_panel_and_just_perfection_in_step(fake_env):
    dtp, jp = "org.gnome.shell.extensions.dash-to-panel", "org.gnome.shell.extensions.just-perfection"
    # Without them installed, their settings are left alone.
    acts = ts.GlassEffects().plan(context(fake_env))
    assert not [a for a in acts if getattr(a, "schema", "") in (dtp, jp)]

    install(fake_env, ts.DASH_TO_PANEL, ts.JUST_PERFECTION)
    fake_env.gs[(dtp, None)] = {"hide-overview-on-startup": "false"}
    fake_env.gs[(jp, None)] = {"startup-status": "1"}
    engine = Engine(fake_env, [ts.GlassEffects()])
    engine.apply(Settings())
    assert fake_env.gs[(dtp, None)]["hide-overview-on-startup"] == "true"
    assert fake_env.gs[(jp, None)]["startup-status"] == "0"
    # Turning it off puts back what they had.
    engine.apply(Settings(start_on_desktop=False))
    assert fake_env.gs[(dtp, None)]["hide-overview-on-startup"] == "false"
    assert fake_env.gs[(jp, None)]["startup-status"] == "1"
    # A choice the user made there themselves is kept.
    fake_env.gs[(dtp, None)]["hide-overview-on-startup"] = "true"
    engine.apply(Settings(start_on_desktop=False))
    assert fake_env.gs[(dtp, None)]["hide-overview-on-startup"] == "true"


def test_desktop_options_are_checked_in_the_extension():
    js = (rg.SOURCE / "config.js").read_text()
    assert "desktop: {startOnDesktop: false, overviewOff: false}" in js
    ext = (rg.SOURCE / "extension.js").read_text()
    assert "DesktopBehaviour" in ext and "this._desktop?.destroy()" in ext


def test_their_own_start_up_choice_comes_back_not_the_default(fake_env):
    """A value the user picked before Liquid Glass came along is what Restore original and
    turning ours off put back, never the schema default."""
    dtp, jp = "org.gnome.shell.extensions.dash-to-panel", "org.gnome.shell.extensions.just-perfection"
    install(fake_env, ts.DASH_TO_PANEL, ts.JUST_PERFECTION)
    for undo in ("switch off", "restore original"):
        fake_env.gs[(dtp, None)] = {"hide-overview-on-startup": "false"}
        fake_env.gs[(jp, None)] = {"startup-status": "1"}
        engine = Engine(fake_env, [ts.GlassEffects()])
        engine.apply(Settings(overview_off=True))
        assert fake_env.gs[(dtp, None)]["hide-overview-on-startup"] == "true"
        assert fake_env.gs[(jp, None)]["startup-status"] == "0"
        engine.apply(Settings(overview_off=True))      # applying again keeps the first backup
        if undo == "switch off":
            engine.apply(Settings(start_on_desktop=False, overview_off=False))
        else:
            assert engine.revert() == []
        assert fake_env.gs[(dtp, None)]["hide-overview-on-startup"] == "false", undo
        assert fake_env.gs[(jp, None)]["startup-status"] == "1", undo


def test_turning_the_overview_off_never_changes_has_overview():
    """Only the start-up step touches sessionMode.hasOverview, and it always restores it."""
    js = (rg.SOURCE / "desktop.js").read_text()
    writes = [line.strip() for line in js.splitlines() if re.search(r"hasOverview\s*=[^=]", line)]
    assert writes == ["Main.sessionMode.hasOverview = false;",
                      "Main.sessionMode.hasOverview = this._realHasOverview;"]
    block = js[js.index("_blockOverview() {"):js.index("_allowOverview() {")]
    assert "hasOverview" not in block and "settings" not in block   # in memory only, gone on a Shell restart
    destroy = js[js.index("    destroy() {"):]
    assert "this._endStartup();" in destroy and "this._allowOverview();" in destroy


def test_a_change_made_in_their_settings_while_ours_is_on_is_kept(fake_env):
    """The user had it on, we set it (on), then they switched it off in Dash to Panel while ours
    was on: switching ours off, or Restore original, must not force it back on."""
    dtp, jp = "org.gnome.shell.extensions.dash-to-panel", "org.gnome.shell.extensions.just-perfection"
    install(fake_env, ts.DASH_TO_PANEL, ts.JUST_PERFECTION)
    for undo in ("switch off", "restore original"):
        fake_env.gs[(dtp, None)] = {"hide-overview-on-startup": "true"}
        fake_env.gs[(jp, None)] = {"startup-status": "0"}
        engine = Engine(fake_env, [ts.GlassEffects()])
        engine.apply(Settings())
        fake_env.gs[(dtp, None)]["hide-overview-on-startup"] = "false"     # changed in Dash to Panel
        fake_env.gs[(jp, None)]["startup-status"] = "1"                    # changed in Just Perfection
        if undo == "switch off":
            engine.apply(Settings(start_on_desktop=False))
        else:
            assert engine.revert() == []
        assert fake_env.gs[(dtp, None)]["hide-overview-on-startup"] == "false", undo
        assert fake_env.gs[(jp, None)]["startup-status"] == "1", undo
        # Nothing of ours is left to undo later.
        assert not [k for k in engine_backup_keys(fake_env) if dtp in k or jp in k], undo


def engine_backup_keys(env):
    from liquidglass.engine import Backup
    return list(Backup(env).data["gsettings"])
