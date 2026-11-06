"""Theming logic review after 1.5.7: Restore, the watcher and the backup.

Each test here failed before its fix:
- Restore with your own file in a linked GTK folder took away every link to the theme
  (its gtk.css, gtk-dark.css and assets), so GTK 4 apps lost Orchis.
- After a Restore that couldn't put everything back, a dark/light switch, an upgrade or
  the next login brought the glass look back.
- A slider moved in the app (shown live on the desktop) made the app say "Another app
  replaced the Fedora Glass look", which wasn't true.
- With the backup lost (the state folder wiped), the next Apply saved our own files as
  "your original", so Restore put the glass back instead of taking it away.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from liquidglass import __main__ as cli
from liquidglass.engine import Backup, Engine
from liquidglass.settings import Settings
from liquidglass.targets.base import Target, WriteFile
from tests.test_linked_folders import gtk4, link_config, orchis


class Writes(Target):
    def __init__(self, path: Path, text: str = "/* Fedora Glass, generated */\n", tid: str = "probe",
                 edits: tuple = ()):
        super().__init__(id=tid, name="Probe")
        self.path, self.text, self.edits = path, text, edits

    def plan(self, ctx):
        return [WriteFile(self.path, self.text, edits=self.edits)]


# ---- 1. a kept folder keeps the theme's links ------------------------------------------
def test_restore_with_your_own_file_keeps_the_theme_links(fake_env):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    (d / "mine.css").write_text("/* the user's */")
    problems = Engine(fake_env, targets=[gtk4()]).revert()
    assert problems and "Kept your gtk-4.0 folder" in problems[0]
    # The folder stays, and GTK still finds everything the theme gave it.
    assert sorted(os.listdir(d)) == ["assets", "gtk-dark.css", "gtk.css", "mine.css"]
    assert (d / "gtk.css").read_text() == "/* orchis */"
    assert (d / "gtk-dark.css").read_text() == "/* orchis dark */"
    assert (d / "assets/check.png").read_bytes() == b"png"
    # Once the user's file goes, the next Restore puts the link back.
    (d / "mine.css").unlink()
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert d.is_symlink() and d.resolve() == theme.resolve()


# ---- 2. Restore original sticks, even when something was left behind --------------------
def _restore_with_a_kept_folder(env) -> Path:
    theme = orchis(env)
    d = link_config(env, "gtk-4.0", theme)
    Engine(env, targets=[gtk4()]).apply(Settings())
    (d / "mine.css").write_text("/* the user's */")
    assert Engine(env, targets=[gtk4()]).revert()      # a problem: the folder stays
    return d


def test_dark_light_switch_after_restore_with_leftovers_stays_restored(fake_env):
    d = _restore_with_a_kept_folder(fake_env)
    eng = Engine(fake_env, targets=[gtk4()])
    assert eng.is_applied()                             # something is still ours...
    assert not eng.look_on()                            # ...but the user asked for their look back
    assert eng.apply(Settings(), if_applied=True) == []   # what the watcher does on a switch
    assert (d / "gtk.css").read_text() == "/* orchis */"


def test_upgrade_after_restore_with_leftovers_does_not_bring_the_look_back(fake_env, monkeypatch):
    d = _restore_with_a_kept_folder(fake_env)
    eng = Engine(fake_env, targets=[gtk4()])
    from liquidglass import engine as engine_mod
    engine_mod.atomic_write(engine_mod.applied_version_path(fake_env), b"1.0.0\n", 0o600)
    monkeypatch.setattr(cli.settings_mod, "load", lambda path=None: Settings())
    assert cli.update_after_upgrade(eng) is False
    assert (d / "gtk.css").read_text() == "/* orchis */"


def test_apply_after_restore_turns_the_look_back_on(fake_env):
    _restore_with_a_kept_folder(fake_env)
    eng = Engine(fake_env, targets=[gtk4()])
    eng.apply(Settings())
    assert eng.look_on()
    assert eng.apply(Settings(), if_applied=True)       # the watcher follows it again


def test_turning_one_part_off_is_not_restore_original(fake_env):
    eng = Engine(fake_env, targets=[gtk4(), Writes(fake_env.config / "probe.css")])
    eng.apply(Settings())
    eng.revert("probe")
    assert eng.look_on()


def test_dnf_remove_still_cleans_up_leftovers(fake_env):
    """on-remove asks is_applied, not look_on: what was left behind still gets a try."""
    _restore_with_a_kept_folder(fake_env)
    assert Engine(fake_env, targets=[gtk4()]).is_applied()


# ---- 3. the live preview is not "another app" ---------------------------------------------
def test_live_preview_write_is_not_reported_as_replaced(fake_env):
    from liquidglass.render import glass as rg
    from liquidglass import palette
    path = fake_env.config / "liquid-glass/shell-glass.json"
    s = Settings()
    Engine(fake_env, targets=[Writes(path, rg.render_config(s, palette.build(s, dark=True)), "glass")]).apply(s)
    # The app rewrites it while a slider moves (backend._write_live_glass).
    moved = Settings(frost=0.9)
    path.write_text(rg.render_config(moved, palette.build(moved, dark=True)))
    assert Backup(fake_env).overwritten() == []
    # A file someone else wrote is still noticed.
    path.write_text('{"theirs": true}\n')
    assert Backup(fake_env).overwritten() == ["glass"]


# ---- 4. a lost backup never makes our files "the original" ----------------------------------
def test_lost_backup_does_not_keep_our_file_as_the_original(fake_env):
    import shutil
    path = fake_env.config / "probe/style.css"
    eng = Engine(fake_env, targets=[Writes(path)])
    eng.apply(Settings())
    shutil.rmtree(fake_env.state / "liquid-glass")       # the state folder wiped
    eng.apply(Settings())
    assert eng.revert() == []
    assert not path.exists()


def test_lost_backup_keeps_a_settings_file_that_names_us(fake_env):
    """An app's own settings file can mention Fedora Glass near the top (VS Code's theme
    name): it is still the user's file and must survive Restore."""
    import shutil
    path = fake_env.config / "Code/User/settings.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"workbench.colorTheme": "Fedora Glass Dark", "editor.fontSize": 15}\n')
    new = json.dumps({"workbench.colorTheme": "Fedora Glass Dark", "editor.fontSize": 15}, indent=2) + "\n"
    eng = Engine(fake_env, targets=[Writes(path, new, "vscode", ("json", ("workbench.colorTheme",)))])
    shutil.rmtree(fake_env.state / "liquid-glass", ignore_errors=True)
    eng.apply(Settings())
    eng.revert()
    assert path.exists() and json.loads(path.read_text())["editor.fontSize"] == 15


# ---- 5. small bookkeeping -------------------------------------------------------------------
def test_an_empty_list_record_does_not_count_as_applied(fake_env):
    b = Backup(fake_env)
    b.data["lists"]["org.gnome.shell||enabled-extensions"] = {"target": "shell", "added": [], "removed": []}
    b.save()
    assert Backup(fake_env).targets_with_changes() == set()
