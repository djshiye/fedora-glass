"""Logic breaks found on purpose and fixed: the watcher in a process an update left behind,
a wallpaper whose name has a ' in it, and `fedora-glass apply` with settings it can't save."""
from __future__ import annotations

import errno

from fedoraglass import __main__ as cli
from fedoraglass import engine
from fedoraglass import looks
from fedoraglass import settings as settings_mod
from fedoraglass import wallcolour
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.gtk import Gtk4
from tests.test_day_night_looks import _saved, _style
from tests.test_watch_wallpaper import BLUE, RED, Eng as WallEng, _pic, _reader


# ---- an update on disk, the older watcher still running -----------------------------------
class RefusingEng:
    """As Engine.apply: a process older than the version on disk changes nothing."""
    targets: tuple = ()

    def __init__(self, env):
        self.env, self.applied = env, []

    def look_on(self):
        return True

    def apply(self, s, only=None, if_applied=False, applied_only=False):
        if not engine.runs_installed_version():
            return []
        self.applied.append({"frost": s.frost, "tint": s.tint, "only": only})
        return []


def _updated_on_disk(monkeypatch, newer: bool) -> None:
    monkeypatch.setattr(engine, "disk_version", lambda: "99.0.0" if newer else None)


def test_a_switch_seen_by_the_older_watcher_is_still_put_on_by_the_new_one(fake_env, monkeypatch):
    """The user applied in light (the new app, so the stamp is this version's), then switched
    to dark in the minute before the older watcher restarts as the new version. The older
    one's Apply is refused; it must not note dark (or save the night look), or the new
    watcher finds nothing to catch up on and the day look stays on in dark."""
    lib = looks.Library(looks.looks_dir())
    lib.save("Day", Settings(frost=0.1, tint="#e0e8f0"))
    lib.save("Night", Settings(frost=0.9, tint="#102040"))
    settings_mod.save(Settings(frost=0.1, tint="#e0e8f0", look_for_light="day", look_for_dark="night"))
    _style(fake_env, False)
    engine.note_applied_style(fake_env)
    monkeypatch.setattr(cli, "update_after_upgrade", lambda *a, **k: False)     # stamped already
    monkeypatch.setattr(cli, "finish_pending", lambda *a, **k: True)

    old = RefusingEng(fake_env)
    w = cli.Watcher(old)
    w.only = {"shell"}
    _updated_on_disk(monkeypatch, True)
    _style(fake_env, True)
    w.changed({cli.SCHEME})
    assert old.applied == []
    assert engine.read_applied_style(fake_env) is False, "nothing was put on: nothing noted"
    assert _saved().frost == 0.1, "settings.json still holds the look on the desktop"

    # The new version's watcher starts (Watcher.poll ended the old one with 75).
    _updated_on_disk(monkeypatch, False)
    new = RefusingEng(fake_env)
    w2 = cli.Watcher(new)
    w2.only = {"shell"}
    w2.start()
    assert new.applied == [{"frost": 0.9, "tint": "#102040", "only": None}]
    assert engine.read_applied_style(fake_env) is True


def test_a_switch_without_day_and_night_looks_is_caught_up_too(fake_env, monkeypatch):
    settings_mod.save(Settings(frost=0.3))
    _style(fake_env, False)
    engine.note_applied_style(fake_env)
    monkeypatch.setattr(cli, "update_after_upgrade", lambda *a, **k: False)
    monkeypatch.setattr(cli, "finish_pending", lambda *a, **k: True)
    w = cli.Watcher(RefusingEng(fake_env))
    _updated_on_disk(monkeypatch, True)
    _style(fake_env, True)
    w.changed({cli.SCHEME})
    _updated_on_disk(monkeypatch, False)
    new = RefusingEng(fake_env)
    w2 = cli.Watcher(new)
    w2.only = {"shell"}
    w2.start()
    assert new.applied == [{"frost": 0.3, "tint": Settings().tint, "only": {"shell"}}]


def test_an_update_landing_while_a_switch_is_handled_is_still_caught_up(fake_env, monkeypatch):
    """dnf writes the new version after the older watcher's first look at the disk: its Apply
    is refused, so the switch must not be noted, or the new watcher finds nothing to catch up."""
    settings_mod.save(Settings(frost=0.4))
    _style(fake_env, False)
    engine.note_applied_style(fake_env)
    monkeypatch.setattr(cli, "finish_pending", lambda *a, **k: True)
    checks = []

    def installed():
        checks.append(1)
        return len(checks) == 1
    monkeypatch.setattr(engine, "runs_installed_version", installed)
    old = RefusingEng(fake_env)
    w = cli.Watcher(old)
    w.only = {"shell"}
    _style(fake_env, True)
    w.changed({cli.SCHEME})
    assert old.applied == []
    assert engine.read_applied_style(fake_env) is False, "noted dark, though the desktop still shows light"


# ---- a wallpaper with a ' in its name ------------------------------------------------------
def test_a_picture_with_an_apostrophe_is_read_as_gsettings_prints_it(fake_env):
    pic = _pic(fake_env.home, "Dino's beach.png")
    uri = "file://" + str(pic).replace(" ", "%20")
    # GSettings (and `gsettings get`) print a string holding a ' in double quotes.
    assert wallcolour.picture_path(f'"{uri}"') == str(pic)
    assert wallcolour.picture_path("'" + uri.replace("'", "\\'") + "'") == str(pic)
    assert wallcolour.picture_path(f"'file://{fake_env.home}/x.png'") == ""        # not there
    assert wallcolour.picture_path("'file:///broken") == ""


def test_the_watcher_follows_a_wallpaper_with_an_apostrophe(fake_env):
    red = _pic(fake_env.home, "red.png")
    blue = _pic(fake_env.home, "Dino's blue.png")
    s = Settings(tint_from_wallpaper=True, tint=wallcolour.as_tint(RED),
                 wallpaper_match=wallcolour.mark(wallcolour.picture_key(str(red)), True))
    settings_mod.save(s)
    uri = f'"file://{blue}"'.replace(" ", "%20")
    fake_env.gs[("org.gnome.desktop.background", None)] = {"picture-uri": uri, "picture-uri-dark": uri}
    eng = WallEng(fake_env)
    w = cli.Watcher(eng)
    w.read_pixels = _reader({"red.png": RED, "Dino's blue.png": BLUE})
    w.changed({cli.WALLPAPER})
    assert _saved().tint == wallcolour.as_tint(BLUE)
    assert [a["tint"] for a in eng.applied] == [wallcolour.as_tint(BLUE)]
    assert fake_env.wallpaper() == blue


# ---- `fedora-glass apply` with a settings file it can't write ------------------------------
def test_apply_that_cannot_save_the_settings_changes_nothing(fake_env, monkeypatch, capsys):
    """Saved only after the Apply, the desktop took frost 0.9 while settings.json kept 0.2
    (and a traceback showed): the watcher then put 0.2 back on some parts at the next switch."""
    eng = Engine(fake_env, [Gtk4()])
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    settings_mod.save(Settings(frost=0.2))

    def read_only(*_a, **_k):
        raise OSError(errno.EROFS, "Read-only file system")
    monkeypatch.setattr(settings_mod, "save", read_only)
    assert cli.main(["apply", "--frost", "0.9"]) == 1
    assert "could not save the settings" in capsys.readouterr().err
    assert not eng.is_applied(), "the desktop is left as it was"
    assert settings_mod.load().frost == 0.2
    # `--only` never saves, so it still applies.
    assert cli.main(["apply", "--only", "gtk4"]) == 0
    assert eng.is_applied()


# ---- the app's Apply while the watcher reads a new wallpaper -------------------------------
def test_an_apply_from_the_app_while_the_picture_is_read_is_not_undone(fake_env):
    """GNOME shows a new picture; the watcher waits for it to settle and decodes it. Meanwhile
    the user presses Apply in the app (frost 0.8 and the new picture's colours, saved first).
    The watcher must not save the look it worked out from the settings before that Apply,
    nor apply it over the user's."""
    red, blue = _pic(fake_env.home, "red.png"), _pic(fake_env.home, "blue.png")
    settings_mod.save(Settings(frost=0.3, tint_from_wallpaper=True, tint=wallcolour.as_tint(RED),
                               wallpaper_match=wallcolour.mark(wallcolour.picture_key(str(red)), True)))
    fake_env.gs[("org.gnome.desktop.background", None)] = {
        "picture-uri": f"'file://{blue}'", "picture-uri-dark": f"'file://{blue}'"}
    eng = WallEng(fake_env)
    w = cli.Watcher(eng)
    w.read_pixels = _reader({"red.png": RED, "blue.png": BLUE})
    users = Settings(frost=0.8, tint_from_wallpaper=True, tint=wallcolour.as_tint(BLUE),
                     wallpaper_match=wallcolour.mark(wallcolour.picture_key(str(blue)), True))
    real, calls = w.rematch, []

    def slow_rematch(s):
        out = real(s)
        if not calls:
            settings_mod.save(users)        # the app's Apply, while the picture was decoded
        calls.append(s.frost)
        return out
    w.rematch = slow_rematch
    w.changed({cli.WALLPAPER})
    assert _saved() == users.normalized()
    assert eng.applied == [], "the user's own Apply has this picture's colours already"
    assert calls == [0.3, 0.8], "started again from the settings the app saved"


# ---- the glass extension switched off by the user in the Extensions app --------------------
def test_login_does_not_wait_for_a_glass_the_user_switched_off(fake_env, capsys):
    """Applied mid-session (the Shell parts wait for the glass), then the user switched the
    glass off in the Extensions app: GNOME will never start it, so the watcher must not hang
    two minutes at every login before it catches up on anything else."""
    from tests.test_wait_for_glass import desktop
    from fedoraglass.engine import read_pending
    from fedoraglass.render import glass as rg
    engine_ = desktop(fake_env)
    fake_env.glass_loaded = False
    engine_.apply(Settings())
    assert read_pending()
    gs = fake_env.gs[("org.gnome.shell", None)]
    gs["enabled-extensions"] = gs["enabled-extensions"].replace(f"'{rg.UUID}', ", "").replace(f", '{rg.UUID}'", "")
    assert not fake_env.extension_on(rg.UUID)
    naps = []
    assert cli.finish_pending(engine_, wait_s=120, step_s=2, sleep=naps.append) is False
    assert naps == []
    assert "switched off" in capsys.readouterr().err
    assert read_pending(), "the Shell parts still wait, for when the user switches it on"
    # Switched on again (GNOME starts it at once): the next wake-up finishes them.
    gs["enabled-extensions"] = gs["enabled-extensions"].replace("]", f", '{rg.UUID}']")
    fake_env.glass_loaded = True
    assert cli.finish_pending(engine_, wait_s=0, sleep=naps.append) is True


# ---- the first login after an update, with a style switch missed while logged out ----------
class StampingEng(RefusingEng):
    """As Engine: an Apply of every part (only None) stamps this version."""

    def apply(self, s, only=None, if_applied=False, applied_only=False):
        super().apply(s, only, if_applied, applied_only)
        if only is None:
            engine.applied_version_path(self.env).parent.mkdir(parents=True, exist_ok=True)
            engine.applied_version_path(self.env).write_text(f"{cli.__version__}\n")
        return []


def test_the_first_login_after_an_update_never_puts_the_other_styles_look_on(fake_env, monkeypatch):
    """Day and night looks, the day look applied by 1.7.7 in light; the PC was updated and
    started again in dark. One Apply of the night look, not the day look on every part first
    and the night look after it."""
    lib = looks.Library(looks.looks_dir())
    lib.save("Day", Settings(frost=0.1, tint="#e0e8f0"))
    lib.save("Night", Settings(frost=0.9, tint="#102040"))
    settings_mod.save(Settings(frost=0.1, tint="#e0e8f0", look_for_light="day", look_for_dark="night"))
    _style(fake_env, False)
    engine.note_applied_style(fake_env)
    engine.applied_version_path(fake_env).write_text("1.7.7\n")
    monkeypatch.setattr(cli, "finish_pending", lambda *a, **k: True)
    _style(fake_env, True)
    eng = StampingEng(fake_env)
    w = cli.Watcher(eng)
    w.only = {"shell"}
    w.start()
    assert eng.applied == [{"frost": 0.9, "tint": "#102040", "only": None}]
    assert engine.read_applied_version(fake_env) == cli.__version__


# ---- `dnf remove` for someone whose environment.d puts the value in quotes ------------------
def test_undo_for_users_reads_a_quoted_value_as_systemd_does(tmp_path):
    """XDG_STATE_HOME="$HOME/st" in ~/.config/environment.d is what GNOME's apps get as
    ~/st, so the backup is there; the removal skipped this person and left their look on."""
    from tests.test_remove import _undo_with_env_d
    home, calls = _undo_with_env_d(tmp_path, {
        "10.conf": 'XDG_STATE_HOME="$HOME/st"\nXDG_CONFIG_HOME=\'${HOME}/cfg\'\n'
                   'XDG_DATA_HOME="$HOME/a"b"\nXDG_CACHE_HOME="$(touch x)"\n',
    }, "st")
    assert len(calls) == 1
    assert f"XDG_STATE_HOME={home}/st " in calls[0] and f"XDG_CONFIG_HOME={home}/cfg " in calls[0]
    assert "XDG_DATA_HOME" not in calls[0] and "XDG_CACHE_HOME" not in calls[0]
    assert not (tmp_path / "x").exists() and not (home / "x").exists()
