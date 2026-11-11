"""The settings file: a damaged one never quietly becomes the defaults, a newer version's
settings survive a downgrade, and values only this version reads as numbers stay numbers."""
from __future__ import annotations

import json
import os
import stat

from fedoraglass import settings as sm
from fedoraglass.settings import Settings


def _path(tmp_path):
    return tmp_path / "liquid-glass/settings.json"


def test_save_keeps_the_last_good_file_as_bak(tmp_path):
    p = _path(tmp_path)
    sm.save(Settings(frost=0.2), p)
    assert not p.with_name("settings.json.bak").exists(), "nothing to keep on the first save"
    sm.save(Settings(frost=0.9), p)
    bak = p.with_name("settings.json.bak")
    assert json.loads(bak.read_text())["frost"] == 0.2
    assert stat.S_IMODE(bak.stat().st_mode) == 0o600
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_a_damaged_file_never_overwrites_the_good_bak(tmp_path):
    p = _path(tmp_path)
    sm.save(Settings(frost=0.2), p)
    sm.save(Settings(frost=0.3), p)
    p.write_text('{"frost": 0.9, "rad')         # a half-written file
    sm.save(Settings(frost=0.5), p)
    assert json.loads(p.with_name("settings.json.bak").read_text())["frost"] == 0.2


def test_a_damaged_file_falls_back_to_the_last_good_copy(tmp_path):
    p = _path(tmp_path)
    sm.save(Settings(frost=0.8, radius=30), p)
    sm.save(Settings(frost=0.9, radius=30), p)
    p.write_text('{"frost": 0.9, "radius": 3')      # truncated
    got = sm.load_checked(p)
    assert got.usable and got.problem and "last good copy" in got.problem
    assert (got.settings.frost, got.settings.radius) == (0.8, 30), "not the defaults"
    assert p.with_name("settings.json.damaged").read_text() == '{"frost": 0.9, "radius": 3'
    # The good copy is back in place, and the app can still say what happened until a save.
    assert sm.load(p).frost == 0.8
    assert "damaged" in sm.damage_notice(p)
    sm.save(Settings(frost=0.4), p)
    os.utime(p, ns=(p.stat().st_atime_ns, p.with_name("settings.json.damaged").stat().st_mtime_ns + 1))
    assert sm.damage_notice(p) is None


def test_a_damaged_file_with_no_good_copy_is_not_usable(tmp_path):
    p = _path(tmp_path)
    sm.save(Settings(frost=0.9), p)
    p.write_bytes(b"")                              # a power cut before the data reached the disk
    got = sm.load_checked(p)
    assert got.settings == Settings() and not got.usable and got.problem
    again = sm.load_checked(p)
    assert not again.usable, "still nothing of the user's to go on on the next look"
    assert sm.damage_notice(p)
    sm.save(Settings(frost=0.3), p)
    assert sm.load_checked(p) == (Settings(frost=0.3), None, True)


def test_a_missing_file_is_the_defaults_and_fine(tmp_path):
    assert sm.load_checked(_path(tmp_path)) == (Settings(), None, True)
    assert sm.damage_notice(_path(tmp_path)) is None


def test_only_one_damaged_copy_is_kept(tmp_path):
    p = _path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("{one")
    sm.load(p)
    p.write_text("[two]")
    sm.load(p)
    assert p.with_name("settings.json.damaged").read_text() == "[two]"
    assert sorted(x.name for x in p.parent.iterdir()) == ["settings.json.damaged"]


# ---- downgrade --------------------------------------------------------------------------
def test_a_newer_versions_settings_survive_a_save(tmp_path):
    p = _path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"frost": 0.2, "future_key": 5, "lock_clock": "huge", "scheme": "sepia",
                             "accent": "brown",
                             "parts": {"panel": {"radius": 4, "shine": 0.3}, "dock": {"tint": "#112233"}},
                             "motion": {"open": {"preset": "wobble", "speed": 1.5}, "drag": {"preset": "x"}}}))
    s = sm.load(p)
    # This version reads them as its own defaults ...
    assert (s.lock_clock, s.scheme, s.accent) == ("bold", "auto", "system")
    assert s.parts == {"panel": {"radius": 4}} and s.motion_for("open")["preset"] == "spring"
    sm.save(s, p)
    d = json.loads(p.read_text())
    # ... and gives them back on save.
    assert d["future_key"] == 5 and d["lock_clock"] == "huge" and d["scheme"] == "sepia" and d["accent"] == "brown"
    assert d["parts"] == {"panel": {"radius": 4, "shine": 0.3}, "dock": {"tint": "#112233"}}
    assert d["motion"]["open"] == {"preset": "wobble", "speed": 1.5} and d["motion"]["drag"] == {"preset": "x"}
    assert sm.load(p) == s, "and they still change nothing here"


def test_a_choice_made_in_this_version_wins(tmp_path):
    p = _path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"lock_clock": "huge", "motion": {"open": {"preset": "wobble"}}}))
    s = sm.load(p)
    s.lock_clock = "thin"
    s.motion = {"open": {"preset": "bounce"}}
    sm.save(s, p)
    d = json.loads(p.read_text())
    assert d["lock_clock"] == "thin" and d["motion"]["open"]["preset"] == "bounce"


# ---- cursor size ------------------------------------------------------------------------
def test_a_whole_number_cursor_size_is_an_int():
    s = Settings(cursor_size=24.0).normalized()
    assert s.cursor_size == 24 and type(s.cursor_size) is int
    assert Settings(cursor_size=24.5).normalized().cursor_size == 0
    assert Settings(cursor_size=True).normalized().cursor_size == 0


def test_a_float_cursor_size_reaches_gsettings_as_an_int(tmp_path):
    p = _path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text('{"cursor_size": 32.0, "cursor_theme": "keep"}')
    assert repr(sm.load(p).cursor_size) == "32"


# ---- what the watcher does with a damaged file -------------------------------------------
def _applied_desktop(fake_env):
    from test_wait_for_glass import desktop
    eng = desktop(fake_env)
    mine = Settings(frost=0.9, targets={"glass": False})
    sm.save(mine)
    eng.apply(mine)
    return eng


class _Counting:
    def __init__(self, eng):
        self.eng, self.applies = eng, 0

    def __getattr__(self, name):
        return getattr(self.eng, name)

    def apply(self, *a, **k):
        self.applies += 1
        return self.eng.apply(*a, **k)


def test_the_upgrade_step_never_applies_defaults_from_a_damaged_file(fake_env, capsys):
    from fedoraglass import __main__ as cli
    from fedoraglass.engine import applied_version_path
    eng = _Counting(_applied_desktop(fake_env))
    applied_version_path(fake_env).write_text("1.0.0\n")
    sm.settings_path().write_text("")                  # damaged, and no good copy
    assert cli.update_after_upgrade(eng) is False
    assert eng.applies == 0
    assert cli.update_after_upgrade(eng) is False
    err = capsys.readouterr().err
    assert err.count("not applying anything by itself") == 1, "one line, not one per wake-up"


def test_the_upgrade_step_uses_the_last_good_copy(fake_env):
    from fedoraglass import __main__ as cli
    from fedoraglass.engine import applied_version_path
    eng = _Counting(_applied_desktop(fake_env))
    sm.save(Settings(frost=0.8, targets={"glass": False}))     # the 0.9 file becomes the .bak
    applied_version_path(fake_env).write_text("1.0.0\n")
    sm.settings_path().write_text('{"frost": 0.8, "tar')
    assert cli.update_after_upgrade(eng) is True
    assert eng.applies == 1 and sm.load().frost == 0.9


def test_finish_pending_waits_for_a_good_file(fake_env, monkeypatch):
    from fedoraglass import __main__ as cli
    from fedoraglass import engine as engine_mod
    eng = _Counting(_applied_desktop(fake_env))
    monkeypatch.setattr(engine_mod, "read_pending", lambda: {"shell"})
    sm.settings_path().write_text("{")
    assert cli.finish_pending(eng, sleep=lambda s: None) is False
    assert eng.applies == 0


# ---- while the file is damaged, only Apply writes it -------------------------------------
def test_remove_only_is_kept_beside_a_damaged_file_and_it_stays_unusable(tmp_path):
    p = _path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text('{"frost": 0.9, "scheme": "dark"')     # truncated, no good copy
    assert not sm.load_checked(p).usable
    sm.save_undo_on_remove(False, p)
    got = sm.load_checked(p)
    assert not got.usable, "the watcher must still apply nothing by itself"
    assert got.settings == Settings(undo_on_remove=False)
    assert not p.exists() and sm.damage_notice(p)
    sm.save(Settings(frost=0.4, undo_on_remove=False), p)      # an Apply
    assert sm.load_checked(p) == (Settings(frost=0.4, undo_on_remove=False), None, True)


def test_on_remove_reads_the_choice_kept_beside_a_damaged_file(fake_env, monkeypatch, capsys):
    from fedoraglass import __main__ as cli
    p = sm.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{")
    sm.load_checked()
    sm.save_undo_on_remove(False)
    monkeypatch.setattr(cli, "_engine", lambda: (_ for _ in ()).throw(AssertionError("restored")))
    assert cli.cmd_on_remove(None) == 0
    assert "your look stays" in capsys.readouterr().out


def test_save_without_backup_and_put_back_leave_the_bak_alone(tmp_path):
    p = _path(tmp_path)
    sm.save(Settings(frost=0.2), p)
    sm.save(Settings(frost=0.3), p)
    bak = p.with_name("settings.json.bak")
    before = sm.read_raw(p)
    sm.save(Settings(frost=0.9), p, backup=False)
    assert json.loads(bak.read_text())["frost"] == 0.2
    sm.put_back(before, p)
    assert sm.load(p).frost == 0.3 and json.loads(bak.read_text())["frost"] == 0.2
    sm.put_back(None, tmp_path / "liquid-glass/none.json")     # no file before: none after
    assert sm.read_raw(tmp_path / "liquid-glass/none.json") is None
