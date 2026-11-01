"""Shell parts wait for the glass extension: GNOME only starts a new extension at login, so a
first Apply mid-session must not leave a see-through panel and menus with no glass behind
them, or change Dash to Panel and ArcMenu for nothing. `liquid-glass watch` finishes them."""

from __future__ import annotations

from liquidglass import __main__ as cli
from liquidglass.engine import WAITING, Engine, pending_path, read_pending
from liquidglass.render import shell as rs
from liquidglass.settings import Settings
from liquidglass.targets import shell as ts
from test_shell import install

DTP = "org.gnome.shell.extensions.dash-to-panel"
ARC = "org.gnome.shell.extensions.arcmenu"
BLUR_PANEL = f"{ts.GlassEffects.BLUR_SCHEMA}.panel"


def desktop(env):
    """Dino's kind of desktop: User Themes, Blur my Shell, Dash to Panel and ArcMenu, with
    their own settings in place before Liquid Glass."""
    install(env, ts.USER_THEME, ts.BLUR, ts.DASH_TO_PANEL, ts.ARCMENU)
    t = Engine(env, ts.TARGETS).context(Settings()).tokens
    env.gs[(DTP, None)] = {k: "'theirs'" for k in rs.dtp_values(t)} | {"animate-appicon-hover": "true"}
    env.gs[(ARC, None)] = {k: "'theirs'" for k in rs.arcmenu_values(t)}
    for part in ts.GlassEffects.BLUR_OVERLAP:
        env.gs[(f"{ts.GlassEffects.BLUR_SCHEMA}.{part}", None)] = {"blur": "true"}
    env.gs[("org.gnome.shell.extensions.user-theme", None)] = {"name": "''"}
    env.gs[("org.gnome.shell", None)] = {"enabled-extensions": "@as []", "disabled-extensions": "@as []"}
    return Engine(env, ts.TARGETS)


def statuses(results):
    return {r.target: (r.status, r.message) for r in results}


def test_first_apply_mid_session_holds_the_shell_parts(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    got = statuses(engine.apply(Settings()))
    for tid in ("shell", "dash-to-panel", "arcmenu"):
        assert got[tid] == ("info", WAITING)
    assert got["glass"][0] == "applied"
    # Their panel, menu and blur are untouched, so nothing looks half done.
    assert set(fake_env.gs[(DTP, None)].values()) <= {"'theirs'", "true"}
    assert set(fake_env.gs[(ARC, None)].values()) == {"'theirs'"}
    assert fake_env.gs[(BLUR_PANEL, None)]["blur"] == "true"
    assert fake_env.gs[("org.gnome.shell.extensions.user-theme", None)]["name"] == "''"
    # The glass extension itself is installed and switched on for the next login.
    assert ts.GlassEffects().ext_dir(fake_env).joinpath("extension.js").exists()
    assert "liquid-glass@djshiye.github.io" in fake_env.gs[("org.gnome.shell", None)]["enabled-extensions"]
    assert read_pending() == {"shell", "dash-to-panel", "arcmenu"}


def test_the_watcher_finishes_them_once_the_glass_runs(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    fake_env.glass_loaded = True                     # after the restart
    assert cli.finish_pending(engine, sleep=lambda s: None)
    assert not pending_path().exists()
    assert "'theirs'" not in fake_env.gs[(ARC, None)].values()
    assert fake_env.gs[(DTP, None)]["trans-use-custom-bg"] == "true"
    assert fake_env.gs[(BLUR_PANEL, None)]["blur"] == "false"    # our glass took over
    assert fake_env.gs[("org.gnome.shell.extensions.user-theme", None)]["name"] == f"'{ts.THEME_NAME}'"


def test_the_watcher_gives_up_quietly_if_the_glass_never_starts(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    naps = []
    assert not cli.finish_pending(engine, wait_s=6, step_s=2, sleep=naps.append)
    assert naps == [2, 2, 2]
    assert read_pending() == {"shell", "dash-to-panel", "arcmenu"}
    assert set(fake_env.gs[(ARC, None)].values()) == {"'theirs'"}


def test_with_the_glass_running_everything_applies_at_once(fake_env):
    engine = desktop(fake_env)
    got = statuses(engine.apply(Settings()))
    assert {got[t][0] for t in ("shell", "glass", "dash-to-panel", "arcmenu")} == {"applied"}
    assert not pending_path().exists()


def test_without_glass_wanted_nothing_waits(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    s = Settings()
    s.targets["glass"] = False
    got = statuses(engine.apply(s))
    assert got["arcmenu"][0] == "applied" and got["dash-to-panel"][0] == "applied"
    assert not pending_path().exists()


def test_restore_original_forgets_what_was_waiting(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    engine.revert()
    assert not pending_path().exists()
    fake_env.glass_loaded = True
    assert cli.finish_pending(engine, sleep=lambda s: None)   # nothing left to do
    assert set(fake_env.gs[(ARC, None)].values()) == {"'theirs'"}
