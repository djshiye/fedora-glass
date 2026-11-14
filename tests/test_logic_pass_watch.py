"""Day and night looks in the watcher: the tint of a look that follows the wallpaper, and a
switch that happened while the watcher wasn't listening (told from a look applied on purpose
by the style noted at the last Apply or switch)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import engine
from fedoraglass import looks
from fedoraglass import settings as settings_mod
from fedoraglass import wallcolour
from fedoraglass.settings import Settings
from tests.test_day_night_looks import Eng, _saved, _style
from tests.test_watch_wallpaper import BLUE, GREY, RED, _pic, _reader, _show


def _watcher(env):
    eng = Eng(env)
    w = cli.Watcher(eng)
    w.only = {"shell"}
    return eng, w


@pytest.mark.parametrize("two_pictures", [False, True])
def test_a_night_look_that_follows_the_wallpaper_gets_the_current_pictures_tint(fake_env, two_pictures):
    env = fake_env
    red = _pic(env.home, "red.png")
    blue = _pic(env.home, "blue.png") if two_pictures else red
    _show(env, red, blue)
    lib = looks.Library(looks.looks_dir())
    lib.save("Day", Settings(tint="#e0e8f0"))
    lib.save("Night", Settings(frost=0.9, tint_from_wallpaper=True, tint="#ff0000"))   # an old picture's tint
    # The day desktop follows the wallpaper and holds this picture's colours already.
    settings_mod.save(Settings(tint_from_wallpaper=True, tint=wallcolour.as_tint(RED), accent="system",
                               wallpaper_match=wallcolour.mark(wallcolour.picture_key(str(red)), False),
                               look_for_light="day", look_for_dark="night"))
    _style(env, True)
    eng, w = _watcher(env)
    w.read_pixels = _reader({"red.png": RED, "blue.png": BLUE})
    w.changed({cli.SCHEME})
    want = wallcolour.as_tint(BLUE if two_pictures else RED)
    assert _saved().tint == want != "#ff0000"
    assert eng.applied[-1]["tint"] == want


def _quiet_start(monkeypatch):
    monkeypatch.setattr(cli, "update_after_upgrade", lambda *a, **k: False)
    monkeypatch.setattr(cli, "finish_pending", lambda *a, **k: True)


def _day_look_on(env, applied_in_dark: bool, now_dark: bool):
    """Day and night looks picked, the day look on the desktop: put on while GNOME showed
    dark or light (noted, as an Apply does), and the style GNOME shows now."""
    lib = looks.Library(looks.looks_dir())
    lib.save("Day", Settings(frost=0.1, tint="#e0e8f0"))
    lib.save("Night", Settings(frost=0.9, tint="#102040"))
    settings_mod.save(Settings(frost=0.1, tint="#e0e8f0", look_for_light="day", look_for_dark="night"))
    _style(env, applied_in_dark)
    engine.note_applied_style(env)
    _style(env, now_dark)


def _settings_files() -> dict:
    return {p.name: p.read_bytes() for p in settings_mod.settings_path().parent.glob("settings*")}


def test_start_puts_on_the_look_for_a_style_that_changed_while_not_listening(fake_env, monkeypatch):
    _quiet_start(monkeypatch)
    _day_look_on(fake_env, applied_in_dark=False, now_dark=True)
    eng, w = _watcher(fake_env)
    w.start()
    assert (_saved().frost, _saved().tint) == (0.9, "#102040")
    assert eng.applied == [{"frost": 0.9, "tint": "#102040", "only": None}]
    # Caught up once: the next login finds the style it noted.
    assert engine.read_applied_style(fake_env) is True
    w.start()
    assert len(eng.applied) == 1


def test_start_leaves_the_other_styles_look_alone_when_the_user_applied_it_on_purpose(fake_env, monkeypatch):
    # GNOME shows dark all along. The user picked the day look and pressed Apply: no switch
    # happened, so a login must not take it away again.
    _quiet_start(monkeypatch)
    _day_look_on(fake_env, applied_in_dark=True, now_dark=True)
    before = _settings_files()
    eng, w = _watcher(fake_env)
    w.start()
    assert eng.applied == []
    assert _settings_files() == before


def test_start_with_no_note_yet_notes_the_style_and_changes_nothing(fake_env, monkeypatch):
    _quiet_start(monkeypatch)
    _day_look_on(fake_env, applied_in_dark=False, now_dark=True)
    engine.applied_style_path(fake_env).unlink()       # as after an update from an older version
    before = _settings_files()
    eng, w = _watcher(fake_env)
    w.start()
    assert eng.applied == [] and _settings_files() == before
    assert engine.read_applied_style(fake_env) is True
    # From now on a switch nobody listened to is caught.
    _style(fake_env, False)
    w.start()
    assert eng.applied == [{"frost": 0.1, "tint": "#e0e8f0", "only": {"shell"}}]
    assert engine.read_applied_style(fake_env) is False


def test_start_does_nothing_after_restore_or_with_a_style_that_does_not_follow_gnome(fake_env, monkeypatch):
    _quiet_start(monkeypatch)
    _day_look_on(fake_env, applied_in_dark=False, now_dark=True)
    eng, w = _watcher(fake_env)
    eng.on = False
    w.start()
    assert eng.applied == []
    # ... and writes no note either: after Restore nothing of ours appears again.
    engine.applied_style_path(fake_env).unlink()
    w.start()
    assert eng.applied == [] and not engine.applied_style_path(fake_env).exists()
    eng.on = True
    _style(fake_env, False)
    engine.note_applied_style(fake_env)
    _style(fake_env, True)
    settings_mod.save(Settings(frost=0.1, tint="#e0e8f0", scheme="light", look_for_light="day", look_for_dark="night"))
    before = _settings_files()
    w.start()
    assert eng.applied == [] and _settings_files() == before


def test_a_missed_switch_without_day_and_night_looks_brings_the_parts_that_follow_the_style(fake_env, monkeypatch):
    _quiet_start(monkeypatch)
    settings_mod.save(Settings(frost=0.4))
    _style(fake_env, False)
    engine.note_applied_style(fake_env)
    _style(fake_env, True)
    before = _settings_files()
    eng, w = _watcher(fake_env)
    w.start()
    assert eng.applied == [{"frost": 0.4, "tint": Settings().tint, "only": {"shell"}}]      # as a live switch
    assert _settings_files() == before
    w.start()
    assert len(eng.applied) == 1


@pytest.mark.parametrize("picks", [{"look_for_light": "night", "look_for_dark": "night"},
                                   {"look_for_light": "night"}, {"look_for_dark": "night"}, {}])
@pytest.mark.parametrize("dark", [False, True])
def test_start_never_applies_at_a_login_where_the_style_did_not_change(fake_env, monkeypatch, picks, dark):
    _quiet_start(monkeypatch)
    lib = looks.Library(looks.looks_dir())
    lib.save("Night", Settings(frost=0.9, tint="#102040"))
    settings_mod.save(Settings(frost=0.9, tint="#102040", **picks))
    _style(fake_env, dark)
    engine.note_applied_style(fake_env)
    before = _settings_files()
    eng, w = _watcher(fake_env)
    for _login in range(3):
        w.start()
    assert eng.applied == []
    assert _settings_files() == before


def test_a_live_switch_notes_the_style_and_other_changes_do_not(fake_env):
    _day_look_on(fake_env, applied_in_dark=False, now_dark=False)
    eng, w = _watcher(fake_env)
    _style(fake_env, True)
    w.changed({cli.CONTRAST})
    assert engine.read_applied_style(fake_env) is False
    w.changed({cli.SCHEME})
    assert engine.read_applied_style(fake_env) is True


def test_the_users_own_apply_notes_the_style_and_the_watchers_does_not(fake_env):
    from fedoraglass.engine import Engine
    from tests.test_linked_folders import gtk4
    eng = Engine(fake_env, [gtk4()])
    _style(fake_env, True)
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    assert engine.read_applied_style(fake_env) is True
    _style(fake_env, False)
    # The upgrade step and the watcher: the look is on, so this Apply really runs.
    assert [r.status for r in eng.apply(Settings(), if_applied=True, applied_only=True)] == ["applied"]
    assert engine.read_applied_style(fake_env) is True
    assert [r.status for r in eng.apply(Settings(), only={"gtk4"})] == ["applied"]
    assert engine.read_applied_style(fake_env) is False
    # Restore original takes the note away with the rest.
    assert eng.revert() == [] and not engine.applied_style_path(fake_env).exists()


def test_a_note_that_is_not_ours_counts_as_no_note(fake_env):
    p = engine.applied_style_path(fake_env)
    p.parent.mkdir(parents=True, exist_ok=True)
    for junk in (b"", b"blue\n", b"dark" * 9, b"\xff\xfe"):
        p.write_bytes(junk)
        assert engine.read_applied_style(fake_env) is None
    p.unlink()
    p.symlink_to(fake_env.home / "elsewhere")
    assert engine.read_applied_style(fake_env) is None


# ---- per-app "Clearer" / "Solid" on a terminal ------------------------------------------------
def _windows(s, dark=True):
    from fedoraglass.palette import build
    from fedoraglass.render import glass
    return glass.config(s, build(s, dark=dark))["windows"]


@pytest.mark.parametrize("dark", [True, False])
def test_clearer_on_a_terminal_is_clearer_than_the_terminals_own_look(dark):
    # The windows frosty, the terminal clear: the variants must follow the terminal.
    w = _windows(Settings(frost=0.9, app_glass={"org.gnome.Ptyxis": "clearer"}), dark)
    term, win = w["terminalLook"], w["look"]
    t_clearer, t_solid = w["terminalAppLooks"]["clearer"], w["terminalAppLooks"]["solid"]
    assert t_clearer["blur"] <= term["blur"] and t_solid["blur"] >= term["blur"]
    assert t_clearer["refraction"] >= term["refraction"] and t_solid["refraction"] <= term["refraction"]
    if term["blur"] != win["blur"]:
        assert t_clearer["blur"] != w["appLooks"]["clearer"]["blur"], "not made from the windows' look"


def test_a_terminal_with_a_clearer_look_than_the_windows_does_not_get_frostier():
    from fedoraglass.palette import build
    from fedoraglass.render import glass
    t = build(Settings(), dark=True)
    win = dict(glass._window_look(t, "windows"), blur=90)
    term = dict(glass._window_look(t, "terminal"), blur=10)
    assert glass.window_variants(t, win)["clearer"]["blur"] > term["blur"], "the old way: frostier"
    assert glass.window_variants(t, term)["clearer"]["blur"] <= term["blur"]


def test_ordinary_windows_keep_their_variants():
    import json
    w = _windows(Settings(), True)
    from fedoraglass.palette import build
    from fedoraglass.render import glass
    assert w["appLooks"] == glass.window_variants(build(Settings(), dark=True), w["look"])
    assert json.dumps(w["appLooks"], sort_keys=True) == json.dumps(
        glass.window_variants(build(Settings(), dark=True), glass._window_look(build(Settings(), dark=True), "windows")), sort_keys=True)
