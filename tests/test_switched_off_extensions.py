"""An extension the user switched off in GNOME's Extensions app (or Extension List, Extension
Manager, `gnome-extensions disable`) stays off when Fedora Glass applies by itself: the
watcher at a dark/light, accent or High Contrast switch, the update step at login, the step
before login. Only the user's own Apply switches it on again. GNOME switches one off by
taking it off enabled-extensions and putting it on disabled-extensions."""

from __future__ import annotations

import json

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import engine as engine_mod
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Backup, parse_strv, read_pending
from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from test_wait_for_glass import desktop

SHELL = ("org.gnome.shell", None)
IFACE = ("org.gnome.desktop.interface", None)
LISTS = "org.gnome.shell||enabled-extensions"


@pytest.fixture
def env(fake_env, monkeypatch):
    """The fake desktop, with GNOME Shell starting and stopping the glass extension as its
    lists change, as GNOME does at once."""
    real = fake_env.gsettings_set

    def gsettings_set(schema, key, value, path=None):
        r = real(schema, key, value, path)
        if schema == "org.gnome.shell" and key in ("enabled-extensions", "disabled-extensions"):
            fake_env.ext_info[rg.UUID] = ("1.0" if fake_env.extension_on(rg.UUID) else "2.0", "")
        return r
    monkeypatch.setattr(fake_env, "gsettings_set", gsettings_set)
    return fake_env


def lists(env) -> tuple[list[str], list[str]]:
    gs = env.gs[SHELL]
    return parse_strv(gs["enabled-extensions"]), parse_strv(gs["disabled-extensions"])


def switch_off(env, uuid: str, off_list: bool = True) -> None:
    """As GNOME's disableExtension(): off the switched-on list, onto the switched-off one.
    `off_list=False`: only taken out of enabled-extensions (a hand edit, a dconf reset)."""
    on, off = lists(env)
    on.remove(uuid)
    if off_list:
        off.append(uuid)
    env.gs[SHELL]["enabled-extensions"] = engine_mod.format_strv(on)
    env.gs[SHELL]["disabled-extensions"] = engine_mod.format_strv(off)
    if uuid == rg.UUID:
        env.ext_info[uuid] = ("2.0", "")    # GNOME's state for a switched-off extension
    assert not env.extension_on(uuid)


def glass_config(env) -> str:
    return ts.GlassEffects().config_path(env).read_text()


def applied(env, s: Settings | None = None):
    """Dino's kind of desktop with the look applied by the user, in the dark style."""
    eng = desktop(env)
    s = s or Settings(accent="system")
    settings_mod.save(s)
    env.gs[IFACE]["color-scheme"] = "'prefer-dark'"
    eng.apply(s)
    assert env.extension_on(rg.UUID) and env.extension_on(ts.USER_THEME)
    return eng, s


def automatic(env, eng, what: str) -> None:
    """What makes Fedora Glass apply by itself."""
    if what == "scheme":
        env.gs[IFACE]["color-scheme"] = "'default'"
        cli.Watcher(eng).changed({cli.SCHEME})
    elif what == "accent":
        env.gs[IFACE]["accent-color"] = "'teal'"
        cli.Watcher(eng).changed({cli.ACCENT})
    elif what == "contrast":
        env.gs.setdefault(("org.gnome.desktop.a11y.interface", None), {})["high-contrast"] = "true"
        cli.Watcher(eng).changed({cli.CONTRAST})
    elif what == "update":
        engine_mod.applied_version_path(env).write_text("1.7.9\n")    # applied by the version before
        assert cli.update_after_upgrade(eng) is True
    elif what == "before-login":
        (ts.GlassEffects().ext_dir(env) / "extension.js").write_text("// the older version\n")
        cli.update_glass_before_login(eng)
        assert cli.glass_files_current(eng)
    else:
        raise AssertionError(what)


@pytest.mark.parametrize("what", ["scheme", "accent", "contrast", "update"])
def test_the_glass_switched_off_in_extensions_stays_off_when_the_style_changes(env, what):
    eng, s = applied(env)
    switch_off(env, rg.UUID)
    before, config = lists(env), glass_config(env)
    env.naps.clear()
    automatic(env, eng, what)
    assert lists(env) == before, "switched back on without the user asking"
    # Its files still follow the new style, for when the user switches it on again.
    if what != "update":
        assert glass_config(env) != config
    # The Shell parts wait for the glass (finish_pending says why), and nothing waited on a
    # glass that won't start.
    assert {"shell", "dash-to-panel", "arcmenu", "spawn"} <= read_pending()
    assert sum(env.naps) < 1
    # The user's own Apply switches it on again.
    eng.apply(settings_mod.load_checked().settings)
    on, off = lists(env)
    assert rg.UUID in on and rg.UUID not in off


def test_the_glass_switched_off_stays_off_through_the_step_before_login(env):
    eng, s = applied(env)
    switch_off(env, rg.UUID)
    before = lists(env)
    automatic(env, eng, "before-login")
    assert lists(env) == before
    eng.apply(s)
    assert env.extension_on(rg.UUID)


def test_a_part_whose_list_edit_was_skipped_still_counts_as_applied(env):
    eng, s = applied(env)
    switch_off(env, rg.UUID)
    record = json.dumps(Backup(env).data["lists"], sort_keys=True)
    env.gs[IFACE]["color-scheme"] = "'default'"
    got = {r.target: r.status for r in eng.apply(s, if_applied=True, applied_only=True)}
    assert got["glass"] == "applied"
    assert json.dumps(Backup(env).data["lists"], sort_keys=True) == record
    assert "glass" in Backup(env).targets_with_changes()


def test_user_themes_switched_off_in_extensions_stays_off_when_the_style_changes(env):
    eng, s = applied(env)
    switch_off(env, ts.USER_THEME)
    before = lists(env)
    automatic(env, eng, "scheme")
    assert lists(env) == before
    assert env.extension_on(rg.UUID)
    eng.apply(settings_mod.load_checked().settings)
    on, off = lists(env)
    assert ts.USER_THEME in on and ts.USER_THEME not in off


def test_a_glass_that_was_on_before_the_first_apply_stays_off_once_switched_off(env):
    eng = desktop(env)
    ts.GlassEffects().ext_dir(env).mkdir(parents=True)
    env.gs[SHELL]["enabled-extensions"] = env.gs[SHELL]["enabled-extensions"].replace("]", f", '{rg.UUID}']")
    s = Settings()
    settings_mod.save(s)
    eng.apply(s)
    assert rg.UUID not in Backup(env).data["lists"][LISTS]["added"]
    switch_off(env, rg.UUID)
    before = lists(env)
    automatic(env, eng, "scheme")
    assert lists(env) == before


def test_a_glass_only_taken_off_the_switched_on_list_stays_off(env):
    eng, s = applied(env)
    switch_off(env, rg.UUID, off_list=False)
    before = lists(env)
    automatic(env, eng, "scheme")
    assert lists(env) == before


def test_a_record_from_an_older_version_still_says_the_glass_was_added(env):
    eng, s = applied(env)
    b = Backup(env)
    for rec in b.data["lists"].values():
        rec.pop("by", None)
    b.save()
    switch_off(env, rg.UUID, off_list=False)
    before = lists(env)
    automatic(env, eng, "scheme")
    assert lists(env) == before


def test_something_new_a_part_needs_is_still_switched_on_by_itself(env):
    """Missing, never added by Fedora Glass and not switched off: added as before (a part
    that needs one more extension after an update)."""
    eng, s = applied(env)
    b = Backup(env)
    rec = b.data["lists"][LISTS]
    rec["added"].remove(ts.USER_THEME)
    rec["by"].pop(ts.USER_THEME)
    b.save()
    switch_off(env, ts.USER_THEME, off_list=False)
    automatic(env, eng, "scheme")
    assert env.extension_on(ts.USER_THEME)
    assert ts.USER_THEME in Backup(env).data["lists"][LISTS]["added"]


def test_restore_after_that_gives_back_the_lists_from_before_the_first_apply(env):
    eng = desktop(env)
    original = lists(env)
    s = Settings()
    settings_mod.save(s)
    eng.apply(s)
    switch_off(env, rg.UUID)
    switch_off(env, ts.USER_THEME)
    automatic(env, eng, "scheme")
    automatic(env, eng, "update")
    assert eng.revert() == []
    on, off = lists(env)
    assert on == original[0]
    # The user's own switching off stays, once each.
    assert sorted(off) == sorted([rg.UUID, ts.USER_THEME])
    # An Apply after Restore is the user's: it switches both on, as the first one did.
    eng.apply(s)
    on, off = lists(env)
    assert on[:3] == original[0] and sorted(on[3:]) == sorted([ts.USER_THEME, rg.UUID]) and off == []


def test_the_users_own_apply_still_switches_them_on_as_before(env):
    """The same steps as the watcher's Apply, but the user's (if_applied off): today's lists."""
    eng, s = applied(env)
    switch_off(env, rg.UUID)
    switch_off(env, ts.USER_THEME)
    env.gs[IFACE]["color-scheme"] = "'default'"
    eng.apply(s, applied_only=True)
    on, off = lists(env)
    assert on == [ts.DASH_TO_PANEL, ts.ARCMENU, ts.SPAWN, rg.UUID, ts.USER_THEME] and off == []
    rec = Backup(env).data["lists"]["org.gnome.shell||disabled-extensions"]
    assert sorted(rec["removed"]) == sorted([rg.UUID, ts.USER_THEME])


def test_the_first_apply_switches_both_on(env):
    eng = desktop(env)
    env.gs[SHELL]["disabled-extensions"] = f"['{rg.UUID}', '{ts.USER_THEME}']"
    eng.apply(Settings())
    on, off = lists(env)
    assert rg.UUID in on and ts.USER_THEME in on and off == []
