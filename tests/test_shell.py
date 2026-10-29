"""GNOME Shell targets: CSS renderer, Blur my Shell pipeline merge, extension settings."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from liquidglass import palette
from liquidglass.engine import Engine
from liquidglass.render import shell as rs
from liquidglass.settings import Settings
from liquidglass.targets import shell as ts
from liquidglass.targets.base import GSet, ListEdit, WriteFile

GRID = [(f, d) for f in (0.0, 0.5, 1.0) for d in (True, False)]

EXISTING_PIPELINES = (
    "{'pipeline_default': {'name': <'Default'>, 'effects': <[<{'type': <'dual_kawase_blur'>, 'id': "
    "<'effect_000000000000'>, 'params': <{'unscaled_radius': <30>, 'brightness': <0.59999999999999998>}>}>]>}, "
    "'pipeline_08367353919921': {'name': <'Liquid Glass'>, 'effects': <[<{'type': <'refraction'>, 'id': "
    "<'effect_34845885991376'>, 'params': <{'gloss': <0.37>, 'falloff': <2.3999999999999999>, 'texture_repeat': <0>, "
    "'tint_color': <(1.0, 1.0, 1.0, 1.0)>}>}>]>}}"
)


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


# ---- Blur my Shell pipelines ------------------------------------------------------------
def test_merge_keeps_foreign_pipelines_verbatim():
    ours = rs.our_pipelines(tokens(0.2, True), True)
    out = rs.merge_pipelines(EXISTING_PIPELINES, ours)
    assert "'pipeline_default': {'name': <'Default'>" in out
    assert "<0.59999999999999998>" in out and "<2.3999999999999999>" in out  # untouched numbers
    assert "'tint_color': <(1.0, 1.0, 1.0, 1.0)>" in out
    for pid in rs.PIPELINE_IDS:
        assert f"'{pid}'" in out


def test_merge_is_idempotent_and_replaces_ours():
    ours = rs.our_pipelines(tokens(0.2, True), True)
    once = rs.merge_pipelines(EXISTING_PIPELINES, ours)
    assert rs.merge_pipelines(once, ours) == once
    again = rs.merge_pipelines(once, rs.our_pipelines(tokens(0.9, True), True))
    assert again != once
    assert again.count("'pipeline_liquidglass_panel'") == 1
    assert "'pipeline_default'" in again


@pytest.mark.parametrize("current", [None, "", "@a{sa{sv}} {}", "{}"])
def test_merge_handles_empty(current):
    out = rs.merge_pipelines(current, rs.our_pipelines(tokens(0.5, False), False))
    assert out.startswith("{'pipeline_liquidglass_panel'")
    assert "dual_kawase_blur" in out and "refraction" not in out


def test_merge_refuses_values_it_cannot_read():
    """Unreadable pipelines must fail the target, never be replaced by ours alone."""
    with pytest.raises(ValueError):
        rs.merge_pipelines("not gvariant at all {{", rs.our_pipelines(tokens(0.5, False), False))


def test_merge_keeps_pipelines_with_typed_numbers():
    mine = ("{'p_mine': {'name': <'Mine'>, 'effects': <[<{'type': <'dual_kawase_blur'>, 'id': <'e1'>, "
            "'params': <{'unscaled_radius': <uint32 30>, 'x': <int64 -2>}>}>]>}}")
    out = rs.merge_pipelines(mine, rs.our_pipelines(tokens(0.5, True), True))
    assert "'p_mine'" in out and "uint32 30" in out and "int64 -2" in out


def test_merge_with_nothing_to_add_returns_the_current_value():
    assert rs.merge_pipelines(EXISTING_PIPELINES, {}) == EXISTING_PIPELINES
    assert rs.merge_pipelines(None, {}) == "@a{sa{sv}} {}"


def test_merged_value_is_valid_gvariant():
    try:
        from gi.repository import GLib as glib
    except ImportError:
        pytest.skip("PyGObject not importable here")
    out = rs.merge_pipelines(EXISTING_PIPELINES, rs.our_pipelines(tokens(0.4, True), True))
    v = glib.Variant.parse(glib.VariantType.new("a{sa{sv}}"), out)
    assert v.n_children() == 2 + len(rs.PIPELINE_IDS)


def test_refraction_follows_frost():
    liquid, frosted = (rs.refraction_params(tokens(f, True), "popup") for f in (0.0, 1.0))
    assert liquid["strength"] > frosted["strength"] * 3
    assert liquid["gloss"] > frosted["gloss"]
    assert liquid["rgb_fringing"] > frosted["rgb_fringing"]
    assert liquid["blur_radius"] < frosted["blur_radius"]
    assert liquid["tint"] < frosted["tint"]
    for kind in ("panel", "popup", "overview", "apps"):
        for f in (0.0, 0.5, 1.0):
            p = rs.refraction_params(tokens(f, False), kind)
            assert 0 <= p["strength"] <= 1 and 0 <= p["gloss"] <= 1 and 1 <= p["blur_radius"] <= 48


def test_popup_corner_keys_match_the_css_radii():
    t = tokens(0.5, True, radius=20)
    keys = rs.popup_corner_keys(t)
    assert keys["menu-corner-radius"] == rs.radii(t)["r_menu"]
    assert keys["quick-settings-corner-radius"] == rs.radii(t)["r_big"]


# ---- targets ----------------------------------------------------------------------------------
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
    assert [t.id for t in ts.TARGETS] == ["shell", "blur", "dash-to-panel", "arcmenu"]
    assert [t.group for t in ts.TARGETS] == ["Desktop", "Desktop", "Panel", "Panel"]


def test_detect_needs_the_extension(fake_env):
    for t in ts.TARGETS:
        assert not t.detect(fake_env).available
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


def test_blur_target_adds_pipelines_and_points_components(fake_env):
    install(fake_env, ts.BLUR)
    schema = ts.BlurMyShell.SCHEMA
    fake_env.gs[(schema, None)] = {"pipelines": EXISTING_PIPELINES}
    acts = ts.BlurMyShell().plan(context(fake_env, frost=0.0))
    sets = {(a.schema.removeprefix(schema).lstrip("."), a.key): a.value for a in acts if isinstance(a, GSet)}
    assert "'pipeline_default'" in sets[("", "pipelines")] and "refraction" in sets[("", "pipelines")]
    for comp in ("panel", "popup", "overview", "appfolder", "applications", "window-list",
                 "coverflow-alt-tab", "lockscreen", "screenshot"):
        assert sets[(comp, "pipeline")].strip("'") in rs.PIPELINE_IDS
    assert sets[("popup", "override-background")] == "false"
    assert sets[("popup", "menu-corner-radius")] == str(rs.radii(context(fake_env, frost=0.0).tokens)["r_menu"])


def test_blur_target_falls_back_to_kawase_without_refraction(fake_env):
    install(fake_env, ts.BLUR, refraction=False)
    acts = ts.BlurMyShell().plan(context(fake_env))
    text = next(a.value for a in acts if isinstance(a, GSet) and a.key == "pipelines")
    assert "dual_kawase_blur" in text and "unscaled_radius" in text and "refraction" not in text


def test_blur_target_applications_follow_the_setting(fake_env):
    install(fake_env, ts.BLUR)
    def apps(**kw):
        acts = ts.BlurMyShell().plan(context(fake_env, **kw))
        return {a.key: a.value for a in acts if isinstance(a, GSet) and a.schema.endswith(".applications")}
    on, off = apps(blur_app_windows=True), apps(blur_app_windows=False)
    assert on["enable-all"] == "true" and off["enable-all"] == "false" and off["blur"] == "false"
    t = context(fake_env).tokens
    assert on["opacity"] == "255" and on["dynamic-opacity"] == "false"  # translucency comes from the CSS
    assert "steam" in on["blacklist"]


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
    env.gs[(ts.BlurMyShell.SCHEMA, None)]["pipelines"] = EXISTING_PIPELINES
    env.gs[("org.gnome.shell", None)] = {"enabled-extensions": "['x@y']", "disabled-extensions": f"['{ts.USER_THEME}']"}
    return env


def test_apply_then_revert_restores_everything(fake_env):
    seeded_env(fake_env)
    before = {k: dict(v) for k, v in fake_env.gs.items()}
    engine = Engine(fake_env, ts.TARGETS)
    results = engine.apply(Settings(frost=0.3))
    assert [r.status for r in results] == ["applied"] * 4, results
    gs = fake_env.gs
    assert gs[(ts.BlurMyShell.SCHEMA, None)]["pipelines"] != EXISTING_PIPELINES
    assert ts.USER_THEME in gs[("org.gnome.shell", None)]["enabled-extensions"]
    assert (fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css").is_file()

    assert engine.revert() == []
    assert not (fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css").exists()
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
