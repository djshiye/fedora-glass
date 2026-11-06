"""Bug run after 1.5.6: a removed app never keeps Restore failing, and an app that rewrites
its own settings file between two Applies keeps those changes at Restore."""
from __future__ import annotations

import json

from liquidglass import unmerge
from liquidglass.engine import Backup, Engine
from liquidglass.settings import Settings
from liquidglass.targets import shell as ts
from liquidglass.targets.apps import QBittorrent
from liquidglass.env import RunResult

from test_restore_safety import edit_engine
from test_shell import seeded_env


def _remove_spawn(env):
    """`dnf remove gnome-shell-extension-spawn`: its folder and its schema are gone."""
    import shutil
    shutil.rmtree(env.data / "gnome-shell/extensions" / ts.SPAWN)
    env.gs.pop((ts.Spawn.SCHEMA, None), None)
    real_set = env.gsettings_set

    def gone_set(schema, key, value, path=None):
        if schema == ts.Spawn.SCHEMA:
            return RunResult(1, "", f"No such schema “{schema}”\n")
        return real_set(schema, key, value, path)
    env.gsettings_set = gone_set
    env.gsettings_reset = lambda schema, key, path=None: gone_set(schema, key, "", path)


def test_restore_after_spawn_was_removed_is_clean(fake_env):
    seeded_env(fake_env)
    eng = Engine(fake_env, ts.TARGETS)
    eng.apply(Settings())
    assert any(k.startswith(ts.Spawn.SCHEMA) for k in Backup(fake_env).data["gsettings"])
    _remove_spawn(fake_env)
    assert eng.revert() == []
    assert not eng.is_applied()        # else the watcher brings the look back at sunset
    assert eng.revert() == []


def test_a_failed_put_back_of_a_key_that_still_exists_is_kept(fake_env):
    seeded_env(fake_env)
    eng = Engine(fake_env, ts.TARGETS)
    eng.apply(Settings())
    real_set = fake_env.gsettings_set
    fake_env.gsettings_set = lambda s, k, v, p=None: (
        RunResult(1, "", "dconf busy\n") if s == ts.Spawn.SCHEMA else real_set(s, k, v, p))
    fake_env.gsettings_reset = lambda s, k, p=None: fake_env.gsettings_set(s, k, "", p)
    assert eng.revert()                # reported, and kept for the next try
    assert any(k.startswith(ts.Spawn.SCHEMA) for k in Backup(fake_env).data["gsettings"])


def test_qbittorrent_rewriting_its_conf_between_applies(fake_env):
    conf = fake_env.config / "qBittorrent/qBittorrent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("[Application]\nFileLogger\\Enabled=true\n\n[Preferences]\nGeneral\\Locale=en\n")
    eng = Engine(fake_env, [QBittorrent()])
    eng.apply(Settings())
    # qBittorrent saves its settings on exit; the user changed the language.
    conf.write_text(conf.read_text().replace("General\\Locale=en", "General\\Locale=de"))
    eng.apply(Settings(), if_applied=True)      # a dark/light switch
    assert eng.revert() == []
    text = conf.read_text()
    assert "General\\Locale=de" in text
    assert "UseCustomUITheme" not in text and "CustomUIThemePath" not in text


def test_changes_between_first_and_last_apply_survive_restore(fake_env):
    sp = fake_env.config / "Code/User/settings.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"theme": "Dark+", "fontSize": 12}))
    eng = edit_engine(fake_env, sp)
    eng.apply(Settings())
    d = json.loads(sp.read_text())
    d["fontSize"] = 14
    sp.write_text(json.dumps(d))
    eng.apply(Settings())
    assert eng.revert() == []
    assert json.loads(sp.read_text()) == {"theme": "Dark+", "fontSize": 14}


def test_untouched_file_comes_back_byte_for_byte(fake_env):
    sp = fake_env.config / "Code/User/settings.json"
    sp.parent.mkdir(parents=True)
    raw = '{"theme":"Dark+",   "fontSize": 12}'
    sp.write_text(raw)
    eng = edit_engine(fake_env, sp)
    eng.apply(Settings())
    eng.apply(Settings())
    assert eng.revert() == []
    assert sp.read_text() == raw


def test_an_original_that_already_held_our_keys_is_not_put_back():
    # What a second Apply stored as the "original" before 1.5.7.
    before = '[Preferences]\nGeneral\\CustomUIThemePath=/home/d/.local/share/liquid-glass/qbittorrent/config.json\n'
    now = '[Preferences]\nGeneral\\Locale=de\nGeneral\\CustomUIThemePath=/home/d/.local/share/liquid-glass/qbittorrent/config.json\n'
    out = unmerge.unmerge(now, before, ("ini", "Preferences", ("General\\CustomUIThemePath",)))
    assert "CustomUIThemePath" not in out and "Locale=de" in out
    assert unmerge.unmerge('color_theme = "fedora-glass"\n', 'color_theme = "fedora-glass"\n',
                           ("conf", ("color_theme",))) == ""
    out = unmerge.unmerge('{"enabledThemes": ["a.css", "fedora-glass.css"]}',
                          '{"enabledThemes": ["a.css", "fedora-glass.css"]}', ("json", ("enabledThemes",)))
    assert json.loads(out) == {"enabledThemes": ["a.css"]}
