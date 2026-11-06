"""Shell parts wait for the glass extension: GNOME only starts a new extension at login, so a
first Apply mid-session must not leave a see-through panel and menus with no glass behind
them, or change Dash to Panel, ArcMenu and Spawn for nothing. `fedora-glass watch` finishes them."""

from __future__ import annotations

from liquidglass import __main__ as cli
from liquidglass.engine import WAITING, Engine, pending_path, read_pending
from liquidglass.render import shell as rs
from liquidglass.settings import Settings
from liquidglass.targets import shell as ts
from test_shell import install

DTP = "org.gnome.shell.extensions.dash-to-panel"
ARC = "org.gnome.shell.extensions.arcmenu"
SPW = "org.gnome.shell.extensions.spawn"
BLUR_PANEL = f"{ts.GlassEffects.BLUR_SCHEMA}.panel"


def desktop(env):
    """Dino's kind of desktop: User Themes, Blur my Shell, Dash to Panel, ArcMenu and Spawn, with
    their own settings in place before Fedora Glass."""
    install(env, ts.USER_THEME, ts.BLUR, ts.DASH_TO_PANEL, ts.ARCMENU, ts.SPAWN)
    t = Engine(env, ts.TARGETS).context(Settings()).tokens
    env.gs[(DTP, None)] = {k: "'theirs'" for k in rs.dtp_values(t)} | {"animate-appicon-hover": "true"}
    env.gs[(ARC, None)] = {k: "'theirs'" for k in rs.arcmenu_values(t)}
    env.gs[(SPW, None)] = {k: "'theirs'" for k in rs.arcmenu_values(t)}
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
    for tid in ("shell", "dash-to-panel", "arcmenu", "spawn"):
        assert got[tid] == ("info", WAITING)
    assert got["glass"][0] == "applied"
    # Their panel, menu and blur are untouched, so nothing looks half done.
    assert set(fake_env.gs[(DTP, None)].values()) <= {"'theirs'", "true"}
    assert set(fake_env.gs[(ARC, None)].values()) == {"'theirs'"}
    assert set(fake_env.gs[(SPW, None)].values()) == {"'theirs'"}
    assert fake_env.gs[(BLUR_PANEL, None)]["blur"] == "true"
    assert fake_env.gs[("org.gnome.shell.extensions.user-theme", None)]["name"] == "''"
    # The glass extension itself is installed and switched on for the next login.
    assert ts.GlassEffects().ext_dir(fake_env).joinpath("extension.js").exists()
    assert "liquid-glass@djshiye.github.io" in fake_env.gs[("org.gnome.shell", None)]["enabled-extensions"]
    assert read_pending() == {"shell", "dash-to-panel", "arcmenu", "spawn"}


def test_the_watcher_finishes_them_once_the_glass_runs(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    fake_env.glass_loaded = True                     # after the restart
    assert cli.finish_pending(engine, sleep=lambda s: None)
    assert not pending_path().exists()
    assert "'theirs'" not in fake_env.gs[(ARC, None)].values()
    assert "'theirs'" not in fake_env.gs[(SPW, None)].values()
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
    assert read_pending() == {"shell", "dash-to-panel", "arcmenu", "spawn"}
    assert set(fake_env.gs[(ARC, None)].values()) == {"'theirs'"}


def test_with_the_glass_running_everything_applies_at_once(fake_env):
    engine = desktop(fake_env)
    got = statuses(engine.apply(Settings()))
    assert {got[t][0] for t in ("shell", "glass", "dash-to-panel", "arcmenu", "spawn")} == {"applied"}
    assert not pending_path().exists()


def test_without_glass_wanted_nothing_waits(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    s = Settings()
    s.targets["glass"] = False
    got = statuses(engine.apply(s))
    assert got["arcmenu"][0] == "applied" and got["spawn"][0] == "applied" and got["dash-to-panel"][0] == "applied"
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
    assert set(fake_env.gs[(SPW, None)].values()) == {"'theirs'"}



def _toggles(env):
    return [c[-2].rsplit(".", 1)[-1] for c in env.commands
            if any(m in " ".join(c) for m in ("DisableExtension", "EnableExtension"))]


def test_restore_original_starts_arcmenu_again_after_dash_to_panel(fake_env):
    """GNOME restarts the extensions after the glass one when it goes, and ArcMenu
    restarted before Dash to Panel fails: it is set aside and started again last."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("1.0", ""), ts.DASH_TO_PANEL: ("1.0", ""), rg_uuid(): ("1.0", "")}
    seen = []
    real_set = fake_env.gsettings_set

    def gset(schema, key, value, path=None):
        if key == "enabled-extensions":
            seen.append(("list", _toggles(fake_env)[:]))
        return real_set(schema, key, value, path)
    fake_env.gsettings_set = gset
    fake_env.commands.clear()
    engine.revert()
    assert _toggles(fake_env) == ["DisableExtension", "EnableExtension"]
    # ArcMenu was off before the glass extension was taken off the list.
    assert seen and all(t == ["DisableExtension"] for _, t in seen)
    assert "liquid-glass@djshiye.github.io" not in fake_env.gs[("org.gnome.shell", None)]["enabled-extensions"]


def test_turning_the_glass_off_starts_arcmenu_again_after_dash_to_panel(fake_env):
    """Turning off just "Fedora Glass effects" and pressing Apply takes the glass
    extension away mid-session too, so ArcMenu is set aside the same way (1.5.2 left
    it red: GNOME restarted it before Dash to Panel)."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("1.0", ""), ts.DASH_TO_PANEL: ("1.0", ""), rg_uuid(): ("1.0", "")}
    seen = []
    real_set = fake_env.gsettings_set

    def gset(schema, key, value, path=None):
        if key == "enabled-extensions":
            seen.append(_toggles(fake_env)[:])
        return real_set(schema, key, value, path)
    fake_env.gsettings_set = gset
    fake_env.commands.clear()
    results = engine.apply(Settings(targets={"glass": False}))
    assert any(r.target == "glass" and r.status == "reverted" for r in results)
    assert _toggles(fake_env) == ["DisableExtension", "EnableExtension"]
    assert seen and all(t == ["DisableExtension"] for t in seen)
    assert rg_uuid() not in fake_env.gs[("org.gnome.shell", None)]["enabled-extensions"]


def test_restore_original_with_the_glass_not_running_leaves_arcmenu_alone(fake_env):
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("1.0", ""), rg_uuid(): ("6.0", "")}
    fake_env.commands.clear()
    engine.revert()
    assert _toggles(fake_env) == []


def test_restore_original_leaves_arcmenu_alone_when_it_is_not_running(fake_env):
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("2.0", ""), rg_uuid(): ("1.0", "")}
    fake_env.commands.clear()
    engine.revert()
    assert _toggles(fake_env) == []


def test_restore_and_glass_off_never_touch_spawn(fake_env):
    """Spawn has none of ArcMenu's restart bug: neither Restore original nor turning the glass
    off switches it off and on (only ArcMenu is set aside), whether or not it runs."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("1.0", ""), ts.SPAWN: ("1.0", ""), ts.DASH_TO_PANEL: ("1.0", ""),
                         rg_uuid(): ("1.0", "")}
    fake_env.commands.clear()
    engine.apply(Settings(targets={"glass": False}))
    assert _toggles(fake_env) == ["DisableExtension", "EnableExtension"]
    assert not any(ts.SPAWN in " ".join(c) and ("DisableExtension" in c or "EnableExtension" in c)
                   for c in fake_env.commands)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("1.0", ""), ts.SPAWN: ("1.0", ""), ts.DASH_TO_PANEL: ("1.0", ""),
                         rg_uuid(): ("1.0", "")}
    fake_env.commands.clear()
    engine.revert()
    assert not any(ts.SPAWN in " ".join(c) and ("DisableExtension" in c or "EnableExtension" in c)
                   for c in fake_env.commands)


def test_without_arcmenu_but_with_spawn_nothing_is_set_aside(fake_env):
    """A desktop with Spawn as its only start menu: turning the glass off toggles no extension."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("2.0", ""), ts.SPAWN: ("1.0", ""), ts.DASH_TO_PANEL: ("1.0", ""),
                         rg_uuid(): ("1.0", "")}
    fake_env.commands.clear()
    engine.revert()
    assert _toggles(fake_env) == []


def rg_uuid():
    from liquidglass.render import glass as rg
    return rg.UUID


def test_reads_the_error_as_gnome_prints_it(fake_env):
    # A message holding ' comes back quoted with ".
    from liquidglass.env import RunResult
    out = ("({'uuid': <'arcmenu@arcmenu.com'>, 'error': <\"TypeError: can't access property "
           "\\\"statusArea\\\", this.panel is undefined\">, 'state': <3.0>},)")
    fake_env.run = lambda argv, timeout=30: RunResult(0, out, "")
    state, error = ts.extension_info(fake_env, ts.ARCMENU)
    assert state == 3.0
    assert "this.panel is undefined" in error


def _enabled(env):
    from liquidglass.engine import parse_strv
    return parse_strv(env.gs[("org.gnome.shell", None)]["enabled-extensions"])


def test_turning_one_shell_part_off_keeps_the_other_parts_extension(fake_env):
    """The Shell theme and the glass both add an extension to GNOME's list. Turning one
    of them off takes away only its own (1.5.2 kept both or dropped both, depending on
    which part had touched the list first)."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    assert set(_enabled(fake_env)) == {ts.USER_THEME, rg_uuid()}
    engine.apply(Settings(targets={"glass": False}))
    assert _enabled(fake_env) == [ts.USER_THEME]
    engine.apply(Settings())
    engine.apply(Settings(targets={"shell": False}))
    assert _enabled(fake_env) == [rg_uuid()]
    from liquidglass.engine import Backup
    changed = Backup(fake_env).targets_with_changes()
    assert "glass" in changed and "shell" not in changed
    engine.revert()
    assert _enabled(fake_env) == []


def test_a_list_record_from_an_older_version_is_split_by_owner(fake_env):
    """Dino's backup from 1.5.2 and older has one record for enabled-extensions, tagged with
    the Shell theme, holding the glass extension too."""
    import json
    from liquidglass.engine import Backup
    engine = desktop(fake_env)
    engine.apply(Settings())
    b = Backup(fake_env)
    for rec in b.data["lists"].values():
        rec.pop("by", None)
        rec["target"] = "shell"
    b.save()
    assert "glass" in Backup(fake_env).targets_with_changes()
    engine.apply(Settings(targets={"glass": False}))
    assert _enabled(fake_env) == [ts.USER_THEME]
    manifest = json.loads(Backup(fake_env).manifest_path.read_text())
    assert all(rg_uuid() not in r["added"] for r in manifest["lists"].values())


def test_a_part_turned_off_before_the_restart_is_not_left_waiting(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    assert "arcmenu" in read_pending()
    engine.apply(Settings(targets={"arcmenu": False}))
    assert "arcmenu" not in read_pending() and "dash-to-panel" in read_pending()


def test_spawn_turned_off_before_the_restart_is_not_left_waiting(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    assert "spawn" in read_pending()
    engine.apply(Settings(targets={"spawn": False}))
    assert "spawn" not in read_pending() and {"arcmenu", "dash-to-panel"} <= read_pending()
    assert set(fake_env.gs[(SPW, None)].values()) == {"'theirs'"}


def test_a_busy_shell_that_misses_an_answer_still_gets_arcmenu_set_aside(fake_env):
    """Apply reloads the Shell theme just before the glass goes, and a slow Shell can then
    miss the question "is ArcMenu running?" (the release check caught that)."""
    from liquidglass.env import RunResult
    engine = desktop(fake_env)
    engine.apply(Settings())
    fake_env.ext_info = {ts.ARCMENU: ("1.0", ""), ts.DASH_TO_PANEL: ("1.0", ""), rg_uuid(): ("1.0", "")}
    real_run, busy = fake_env.run, {"left": 3}

    def run(argv, timeout=30):
        if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv and busy["left"] > 0:
            busy["left"] -= 1
            fake_env.commands.append(list(argv))
            return RunResult(1, "", "Timeout was reached")
        return real_run(argv, timeout)
    fake_env.run = run
    fake_env.commands.clear()
    engine.apply(Settings(targets={"glass": False}))
    assert _toggles(fake_env) == ["DisableExtension", "EnableExtension"]


def test_without_arcmenu_turning_the_glass_off_does_not_wait(fake_env):
    """A Shell that answers "no such extension" is an answer: nothing to wait for."""
    from liquidglass.env import RunResult
    engine = desktop(fake_env)
    engine.apply(Settings())
    real_run = fake_env.run

    def run(argv, timeout=30):
        if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv and argv[-1] == ts.ARCMENU:
            return RunResult(0, "({},)", "")
        return real_run(argv, timeout)
    fake_env.run = run
    fake_env.naps.clear()
    engine.apply(Settings(targets={"glass": False}))
    assert sum(fake_env.naps) < 1



def shell_starts_glass_after(env, asks):
    """The fake Shell reports the glass extension as switched off (but known) until it has
    been asked `asks` more times, then as running: GNOME starting it a moment after Apply."""
    env.glass_loaded = False
    seen = []
    _run = env.run

    def run(argv, timeout=30):
        if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv and argv[-1] == GLASS and not env.glass_loaded:
            seen.append(1)
            env.glass_loaded = len(seen) > asks
        return _run(argv, timeout)
    env.run = run


GLASS = "liquid-glass@djshiye.github.io"


def test_apply_after_restore_finishes_the_shell_parts_at_once(fake_env):
    """Restore original switches the glass extension off; GNOME Shell still knows it, so the
    next Apply starts it again live. The Shell theme, panel and menus must not wait for a restart."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    engine.revert()
    shell_starts_glass_after(fake_env, 2)
    got = statuses(engine.apply(Settings()))
    for tid in ("shell", "dash-to-panel", "arcmenu", "spawn"):
        assert got[tid][0] == "applied", (tid, got[tid])
    assert not read_pending()
    assert fake_env.gs[("org.gnome.shell.extensions.user-theme", None)]["name"] == f"'{ts.THEME_NAME}'"
    assert "'theirs'" not in fake_env.gs[(ARC, None)].values()


def test_app_style_apply_one_part_at_a_time_after_restore(fake_env):
    """The app applies part by part, and the Shell theme comes before the glass: the glass
    part finishes it once GNOME runs the extension again."""
    engine = desktop(fake_env)
    engine.apply(Settings())
    engine.revert()
    shell_starts_glass_after(fake_env, 2)
    out = {}
    for t in engine.targets:
        for r in engine.apply(Settings(), only={t.id}):
            out[r.target] = r
    assert out["shell"].status == "applied"
    assert not read_pending()


def test_a_brand_new_extension_still_waits_without_delay(fake_env):
    """First Apply ever: the Shell doesn't know the extension (it finds new ones at login), so
    the Shell parts wait for the restart and Apply doesn't sit waiting for it."""
    from liquidglass.env import RunResult
    engine = desktop(fake_env)
    _run = fake_env.run
    fake_env.run = lambda argv, timeout=30: (RunResult(0, "(@a{sv} {},)", "")
                                             if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv else _run(argv, timeout))
    got = statuses(engine.apply(Settings()))
    assert got["shell"] == ("info", WAITING)
    assert fake_env.naps == []
    assert read_pending() == {"shell", "dash-to-panel", "arcmenu", "spawn"}


def test_gives_up_after_a_few_seconds_if_the_glass_does_not_start(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False       # known (6 = initialized) but never starts
    got = statuses(engine.apply(Settings()))
    assert got["shell"] == ("info", WAITING)
    assert sum(fake_env.naps) <= 6.0
