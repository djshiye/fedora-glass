"""Bugs found in the 1.5.8 analysis: upgrade after a 1.5.7 Restore, folders 1.5.7 damaged,
settings the user changed after us, re-linked folders, the watcher's reach, hand-edited
switches."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from liquidglass import __main__ as cli
from liquidglass.engine import Backup, Engine, applied_version_path, restored_path
from liquidglass.settings import Settings
from liquidglass.targets.base import GSet, Target, WriteFile
from test_linked_folders import gtk4, link_config, orchis


# ---- E2/E3: a 1.5.7 Restore that had to keep a folder ----------------------------
def _restored_by_157(env) -> tuple[Engine, Path, Path]:
    """Apply gtk4 into a linked folder, add a file of the user's, then leave the state a
    1.5.7 Restore left: the theme links taken out of the folder, its record kept, the
    applied-version kept, and no 'restored' mark (1.5.7 had none)."""
    theme = orchis(env)
    d = link_config(env, "gtk-4.0", theme)
    eng = Engine(env, targets=[gtk4()])
    eng.apply(Settings())
    (d / "mine.css").write_text("/* the user's */")
    assert eng.revert() != []                   # the folder is kept for their file
    restored_path(env).unlink()
    for q in d.iterdir():
        if q.is_symlink():
            q.unlink()                          # what 1.5.7's Restore took away
    applied_version_path(env).write_text("1.5.7\n")
    return eng, d, theme


def test_upgrade_after_a_157_restore_with_problems_does_not_bring_the_look_back(fake_env):
    eng, d, _theme = _restored_by_157(fake_env)
    assert eng.look_on() is False
    assert cli.update_after_upgrade(eng) is False
    assert not (d / "gtk.css").exists(), "no glass sheet written again"


def test_a_partial_revert_still_counts_as_on(fake_env):
    a, b = Probe("a", fake_env.config / "a/a.css"), Probe("b", fake_env.config / "b/b.css")
    eng = Engine(fake_env, targets=[a, b])
    eng.apply(Settings())
    assert eng.revert("a") == []
    assert eng.look_on() is True


def test_restore_repairs_a_folder_157_damaged(fake_env):
    eng, d, theme = _restored_by_157(fake_env)
    probs = eng.revert()
    assert probs and "Kept your gtk-4.0 folder" in probs[0]
    assert (d / "mine.css").read_text() == "/* the user's */"
    for name in ("gtk.css", "gtk-dark.css", "assets"):
        assert (d / name).is_symlink() and (d / name).resolve() == (theme / name).resolve()
    assert (theme / "gtk.css").read_text() == "/* orchis */"


def test_restore_never_replaces_a_users_own_file_with_a_link(fake_env):
    eng, d, _theme = _restored_by_157(fake_env)
    (d / "gtk.css").write_text("/* their own sheet */")
    eng.revert()
    assert not (d / "gtk.css").is_symlink()
    assert (d / "gtk.css").read_text() == "/* their own sheet */"
    assert (d / "gtk-dark.css").is_symlink()


# ---- E4: keep_user_change is kept on re-apply too --------------------------------
class Keep(Target):
    def __init__(self, value="'ours'"):
        super().__init__(id="keep", name="Keep")
        self.value = value

    def plan(self, ctx):
        return [GSet("org.example", "k", self.value, keep_user_change=True)]


def test_a_value_the_user_picks_after_apply_is_kept_on_the_next_apply(fake_env):
    fake_env.gs[("org.example", None)] = {"k": "'before'"}
    eng = Engine(fake_env, targets=[Keep()])
    eng.apply(Settings())
    assert fake_env.gs[("org.example", None)]["k"] == "'ours'", "the first Apply sets it"
    fake_env.gs[("org.example", None)]["k"] = "'theirs'"
    eng.apply(Settings())
    eng.apply(Settings(), if_applied=True)      # the dark/light watcher
    assert fake_env.gs[("org.example", None)]["k"] == "'theirs'"
    assert eng.revert() == []
    assert fake_env.gs[("org.example", None)]["k"] == "'theirs'"


def test_an_untouched_value_still_follows_our_new_one(fake_env):
    fake_env.gs[("org.example", None)] = {"k": "'before'"}
    Engine(fake_env, targets=[Keep("'ours'")]).apply(Settings())
    Engine(fake_env, targets=[Keep("'ours2'")]).apply(Settings())
    assert fake_env.gs[("org.example", None)]["k"] == "'ours2'"
    assert Engine(fake_env, targets=[Keep("'ours2'")]).revert() == []
    assert fake_env.gs[("org.example", None)]["k"] == "'before'"


# ---- E5: a folder linked again after Apply -----------------------------------------
def test_a_folder_relinked_after_apply_is_never_written_through(fake_env):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    eng = Engine(fake_env, targets=[gtk4()])
    eng.apply(Settings())
    shutil.rmtree(d)
    d.symlink_to(theme)                         # a theme installer links it again
    eng.apply(Settings())
    assert (theme / "gtk.css").read_text() == "/* orchis */"
    assert (theme / "gtk-dark.css").read_text() == "/* orchis dark */"
    assert not d.is_symlink() and "Fedora Glass" in (d / "gtk.css").read_text()
    assert eng.revert() == []
    assert d.is_symlink() and os.readlink(d) == str(theme)
    assert (theme / "gtk.css").read_text() == "/* orchis */"
    assert (theme / "gtk-dark.css").read_text() == "/* orchis dark */"


def test_a_theme_an_older_version_wrote_through_is_repaired(fake_env, monkeypatch):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    eng = Engine(fake_env, targets=[gtk4()])
    eng.apply(Settings())
    shutil.rmtree(d)
    d.symlink_to(theme)
    real = Backup.unlink_folder
    with monkeypatch.context() as m:            # what 1.5.7 did: wrote into the theme
        m.setattr(Backup, "unlink_folder",
                  lambda self, t, f: None if str(f) in self.data["dirlinks"] else real(self, t, f))
        eng.apply(Settings())
    assert "Fedora Glass" in (theme / "gtk.css").read_text()
    eng.apply(Settings())
    assert (theme / "gtk.css").read_text() == "/* orchis */"
    assert (theme / "gtk-dark.css").read_text() == "/* orchis dark */"
    assert not d.is_symlink() and "Fedora Glass" in (d / "gtk.css").read_text()


# ---- E6: the watcher only re-applies what is applied --------------------------------
class Probe(Target):
    def __init__(self, tid, path: Path):
        super().__init__(id=tid, name=tid)
        self.path = path

    def plan(self, ctx):
        return [WriteFile(self.path, f"/* {'dark' if ctx.tokens is ctx.dark else 'light'} */")]


def _watch_once(monkeypatch, eng, got):
    class Proc:
        stdout = iter(())

        def poll(self):
            return 0

        def kill(self):
            pass

        def wait(self):
            return 0

    rounds = iter([got, {None}])
    monkeypatch.setattr(cli.subprocess, "Popen", lambda *a, **k: Proc())
    monkeypatch.setattr(cli, "_take_all", lambda q: next(rounds))
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    assert cli.cmd_watch(None) == 1


def test_a_dark_light_switch_leaves_restored_and_never_applied_parts_alone(fake_env, monkeypatch):
    a = Probe("a", fake_env.config / "a/a.css")
    b = Probe("b", fake_env.config / "b/b.css")
    c = Probe("c", fake_env.config / "c/c.css")
    eng = Engine(fake_env, targets=[a, b, c])
    eng.apply(Settings(), only={"a", "b"})
    assert eng.revert("b") == []
    fake_env.gs[("org.gnome.desktop.interface", None)]["color-scheme"] = "'default'"
    _watch_once(monkeypatch, eng, {0})
    assert a.path.read_text() == "/* light */", "the applied part follows the switch"
    assert not b.path.exists(), "the part restored one by one stays restored"
    assert not c.path.exists(), "a part never applied stays untouched"


def test_high_contrast_also_only_touches_applied_parts(fake_env, monkeypatch):
    a = Probe("a", fake_env.config / "a/a.css")
    c = Probe("c", fake_env.config / "c/c.css")
    eng = Engine(fake_env, targets=[a, c])
    eng.apply(Settings(), only={"a"})
    _watch_once(monkeypatch, eng, {1})
    assert a.path.exists() and not c.path.exists()


# ---- E8: hand-edited switches -------------------------------------------------------
def test_switch_strings_are_read_as_words():
    s = Settings(glass_panel="false", overview_off="TRUE", start_on_desktop="0", menu_grow="off",
                 lock_widget_weather="false", lock_greeting="yes", undo_on_remove="no",
                 lock_card="maybe", targets={"gtk4": "false", "qt": "On", "x": "junk"}).normalized()
    assert s.glass_panel is False and s.overview_off is True
    assert s.start_on_desktop is False and s.menu_grow is False
    # The lock widgets keep #82's stricter rule: only a real true shows one (the weather
    # names a place), so "yes" there is the default.
    assert s.lock_widget_weather is False and s.lock_greeting is False
    assert s.undo_on_remove is False
    assert s.lock_card is Settings.lock_card, "anything else is the default"
    assert s.targets == {"gtk4": False, "qt": True, "x": True}
    assert not Settings(targets={"gtk4": "false"}).normalized().target_enabled("gtk4")


def test_real_switch_values_are_unchanged():
    s = Settings(glass_panel=False, overview_off=True, lock_widget_weather=True).normalized()
    assert s.glass_panel is False and s.overview_off is True and s.lock_widget_weather is True
