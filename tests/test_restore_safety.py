"""Restore keeps what changed since Apply, private files stay private, a cut-short
Restore can run again, and a gone app doesn't keep Fedora Glass "applied" for ever."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from liquidglass import unmerge
from liquidglass.engine import Backup, Engine
from liquidglass.render import apps as ra
from liquidglass.render import glass as rg
from liquidglass import palette
from liquidglass.settings import Settings
from liquidglass.targets.base import Command, Target, WriteFile


@dataclass
class EditTarget(Target):
    """Sets one key in another app's JSON settings, like the VS Code target."""
    path: Path = field(default=Path("/nonexistent"))

    def plan(self, ctx):
        text = ra.read_text(self.path) if self.path.exists() else None
        return [WriteFile(self.path, ra.merge_json_text(text, {"theme": "Fedora Glass"}),
                          edits=("json", ("theme",)))]


def edit_engine(env, path):
    return Engine(env, [EditTarget(id="t", name="Test", path=path)])


def test_restore_keeps_settings_changed_since_apply(fake_env):
    sp = fake_env.config / "Code/User/settings.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"theme": "Old", "fontSize": 12}))
    eng = edit_engine(fake_env, sp)
    eng.apply(Settings())
    assert json.loads(sp.read_text())["theme"] == "Fedora Glass"
    # The user changes a setting after Apply.
    d = json.loads(sp.read_text())
    d["fontSize"] = 16
    sp.write_text(json.dumps(d))
    assert eng.revert() == []
    assert json.loads(sp.read_text()) == {"theme": "Old", "fontSize": 16}
    assert not eng.is_applied()


def test_restore_takes_a_key_away_that_was_not_there(fake_env):
    sp = fake_env.config / "micro/settings.json"
    eng = edit_engine(fake_env, sp)
    eng.apply(Settings())
    d = json.loads(sp.read_text())
    d["tabsize"] = 2
    sp.write_text(json.dumps(d))
    assert eng.revert() == []
    assert json.loads(sp.read_text()) == {"tabsize": 2}


def test_restore_untouched_file_is_byte_identical(fake_env):
    sp = fake_env.config / "Code/User/settings.json"
    sp.parent.mkdir(parents=True)
    original = '{\n    "theme": "Old"\n}\n'
    sp.write_text(original)
    eng = edit_engine(fake_env, sp)
    eng.apply(Settings())
    assert eng.revert() == []
    assert sp.read_text() == original


def test_restore_leaves_an_unreadable_changed_file_and_lets_go(fake_env):
    sp = fake_env.config / "Code/User/settings.json"
    sp.parent.mkdir(parents=True)
    sp.write_text('{"theme": "Old"}')
    eng = edit_engine(fake_env, sp)
    eng.apply(Settings())
    sp.write_text('// my comment\n{"theme": "Fedora Glass", "fontSize": 20}')
    problems = eng.revert()
    assert problems and "left as it is" in problems[0]
    assert "my comment" in sp.read_text()
    assert not eng.is_applied()


def test_unmerge_ini_and_conf():
    before = "[Preferences]\nGeneral\\Locale=en\n"
    after = ra.ini_set(before, "Preferences", {"General\\UseCustomUITheme": "true", "General\\Locale": "fr"})
    changed = after + "[Other]\nx=1\n"
    out = unmerge.unmerge(changed, before, ("ini", "Preferences", ("General\\UseCustomUITheme", "General\\Locale")))
    assert "UseCustomUITheme" not in out and "General\\Locale=en" in out and "[Other]\nx=1" in out
    conf_before = 'color_theme = "Default"\nupdate_ms = 2000\n'
    conf_after = ra.conf_set(conf_before, {"color_theme": '"fedora-glass"', "theme_background": "False"})
    conf_changed = conf_after.replace("2000", "1000")
    out = unmerge.unmerge(conf_changed, conf_before, ("conf", ("color_theme", "theme_background")))
    assert out == 'color_theme = "Default"\nupdate_ms = 1000\n'


def test_apply_keeps_a_private_file_private(fake_env):
    sp = fake_env.config / "qBittorrent/qBittorrent.conf"
    sp.parent.mkdir(parents=True)
    sp.write_text("{}")
    os.chmod(sp, 0o600)
    edit_engine(fake_env, sp).apply(Settings())
    assert sp.stat().st_mode & 0o777 == 0o600


def test_cut_short_restore_can_run_again(fake_env):
    sp = fake_env.config / "app/settings.json"
    sp.parent.mkdir(parents=True)
    sp.write_text('{"theme": "Old"}')
    edit_engine(fake_env, sp).apply(Settings())
    b = Backup(fake_env)
    copy = b.data["files"][str(sp)]["copy"]
    # Restore puts the file back, but stops before it saves the manifest.
    b._restore_file(str(sp), b.data["files"][str(sp)], set())
    assert Path(copy).exists()
    assert Engine(fake_env, [EditTarget(id="t", name="Test", path=sp)]).revert() == []
    assert json.loads(sp.read_text()) == {"theme": "Old"}
    assert not Path(copy).exists()


@dataclass
class CmdTarget(Target):
    def plan(self, ctx):
        return [Command(("code", "--install-extension", "x.vsix"), "theme", undo=("code", "--uninstall-extension", "x"))]


def test_a_removed_app_does_not_keep_the_look_applied(fake_env, monkeypatch):
    eng = Engine(fake_env, [CmdTarget(id="c", name="Cmd")])
    eng.apply(Settings())
    assert eng.is_applied()
    monkeypatch.setattr(type(fake_env), "which", lambda self, name: None if name == "code" else f"/usr/bin/{name}")
    assert eng.revert() == []
    assert not eng.is_applied()


def test_glass_config_carries_the_marker():
    s = Settings()
    text = rg.render_config(s, palette.build(s, dark=True))
    assert b"Fedora Glass" in text.encode()[:512]
    assert Backup._has_header  # live preview rewrites stay recognised as ours


def test_turning_terminal_colours_off_puts_the_palette_back(fake_env):
    from liquidglass.targets.terminal import Ptyxis
    from liquidglass.targets.base import GReset
    t = Ptyxis()
    eng = Engine(fake_env, [t])
    ctx = eng.context(Settings(terminal_colors=False))
    monkey_profiles = ["0123456789abcdef0123456789abcdef"]
    t.profiles = lambda env: monkey_profiles
    acts = t.plan(ctx)
    assert any(isinstance(a, GReset) and a.key == "palette" for a in acts)


@dataclass
class CssTarget(Target):
    """Writes one generated style sheet, like the GTK target."""
    path: Path = field(default=Path("/nonexistent"))

    def plan(self, ctx):
        return [WriteFile(self.path, "/* Fedora Glass */\nwindow {}\n")]


def css_engine(env, path):
    return Engine(env, [CssTarget(id="t", name="Test", path=path)])


def test_restore_keeps_a_file_a_theme_wrote_since_apply(fake_env):
    # Before: no gtk.css. After Apply, a theme installer writes its own.
    p = fake_env.config / "gtk-4.0/gtk.css"
    eng = css_engine(fake_env, p)
    eng.apply(Settings())
    p.write_text("@import 'theme.css';\n")
    assert eng.revert() == []
    assert p.read_text() == "@import 'theme.css';\n"
    assert not eng.is_applied()


def test_restore_does_not_put_an_older_original_over_a_newer_file(fake_env):
    p = fake_env.config / "gtk-4.0/gtk.css"
    p.parent.mkdir(parents=True)
    p.write_text("old theme\n")
    eng = css_engine(fake_env, p)
    eng.apply(Settings())
    p.write_text("theme update\n")
    assert eng.revert() == []
    assert p.read_text() == "theme update\n"
    assert not list((fake_env.state / "liquid-glass/backup/files").iterdir())


def test_restore_keeps_a_link_put_in_place_of_our_file(fake_env, tmp_path):
    # A link planted where we wrote (a theme linking gtk.css, or someone in a shared
    # folder): never followed, never deleted.
    other = tmp_path / "someone-elses.css"
    other.write_text("keep me\n")
    p = fake_env.config / "gtk-4.0/gtk.css"
    eng = css_engine(fake_env, p)
    eng.apply(Settings())
    p.unlink()
    p.symlink_to(other)
    assert eng.revert() == []
    assert p.is_symlink() and other.read_text() == "keep me\n"


def test_restore_still_removes_our_own_file_after_a_dark_light_switch(fake_env):
    p = fake_env.config / "gtk-4.0/gtk.css"
    eng = css_engine(fake_env, p)
    eng.apply(Settings())
    eng.apply(Settings())        # the watcher re-applies
    assert eng.revert() == []
    assert not p.exists()
