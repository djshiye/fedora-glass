"""The backup of the user's original look survives an Apply stopped half way, a damaged
manifest, and a stored copy that went missing."""
from __future__ import annotations

import json
import os

import pytest

from fedoraglass import engine as engine_mod
from fedoraglass.engine import Backup, Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.base import GSet, ListEdit, Target, WriteFile

IFACE = "org.gnome.desktop.interface"
SHELL = "org.gnome.shell"


class Killed(BaseException):
    """Stands in for the process being killed: nothing after it runs, not even a save."""


class GtkTarget(Target):
    def plan(self, ctx):
        return [WriteFile(ctx.env.config / "gtk-4.0/gtk.css", "/* Fedora Glass */\nwindow {}\n"),
                WriteFile(ctx.env.config / "gtk-3.0/gtk.css", "/* Fedora Glass */\nwindow {}\n"),
                GSet(IFACE, "gtk-theme", "'adw-gtk3-dark'"),
                GSet(IFACE, "accent-color", "'slate'")]


def gtk_engine(env):
    return Engine(env, [GtkTarget(id="t", name="Test")])


def user_files(env):
    g4, g3 = env.config / "gtk-4.0/gtk.css", env.config / "gtk-3.0/gtk.css"
    for p, text in ((g4, "/* my own gtk4 */\n"), (g3, "/* my own gtk3 */\n")):
        p.parent.mkdir(parents=True)
        p.write_text(text)
    return g4, g3


def kill_on_first_gsettings_set(monkeypatch, env):
    """The first setting is changed, then the process dies: files are already written."""
    real = env.gsettings_set
    calls = []

    def dying(schema, key, value, path=None):
        r = real(schema, key, value, path)
        if not calls:
            calls.append(key)
            raise Killed
        return r
    monkeypatch.setattr(env, "gsettings_set", dying)


def test_killed_apply_keeps_the_originals(fake_env, monkeypatch):
    g4, g3 = user_files(fake_env)
    eng = gtk_engine(fake_env)
    kill_on_first_gsettings_set(monkeypatch, fake_env)
    with pytest.raises(Killed):
        eng.apply(Settings())
    # The kill left the glass behind with no save after it.
    assert "Fedora Glass" in g4.read_text()
    assert fake_env.gs[(IFACE, None)]["gtk-theme"] == "'adw-gtk3-dark'"
    monkeypatch.undo()
    # The next Apply must not take that glass for the user's own look.
    assert all(r.status == "applied" for r in eng.apply(Settings()))
    assert eng.revert() == []
    assert g4.read_text() == "/* my own gtk4 */\n"
    assert g3.read_text() == "/* my own gtk3 */\n"
    assert fake_env.gs[(IFACE, None)]["gtk-theme"] == "'Adwaita'"
    assert fake_env.gs[(IFACE, None)]["accent-color"] == "'blue'"


def test_killed_list_edit_still_takes_its_item_away(fake_env, monkeypatch):
    class Ext(Target):
        def plan(self, ctx):
            return [ListEdit(SHELL, "enabled-extensions", add=("glass@test",))]

    fake_env.gs[(SHELL, None)] = {"enabled-extensions": "['mine@user']"}
    eng = Engine(fake_env, [Ext(id="e", name="Ext")])
    kill_on_first_gsettings_set(monkeypatch, fake_env)
    with pytest.raises(Killed):
        eng.apply(Settings())
    monkeypatch.undo()
    eng.apply(Settings())
    assert eng.revert() == []
    assert fake_env.gs[(SHELL, None)]["enabled-extensions"] == "['mine@user']"


def test_stored_copy_without_a_record_is_the_original(fake_env):
    """An older version stored the copy, wrote the glass, and was killed before saving."""
    g4, _ = user_files(fake_env)
    b = Backup(fake_env)
    b.record_file("t", g4, generated=True)       # the copy is stored, the record never saved
    g4.write_text("/* Fedora Glass */\nwindow {}\n")
    eng = gtk_engine(fake_env)
    eng.apply(Settings())
    assert eng.revert() == []
    assert g4.read_text() == "/* my own gtk4 */\n"


def test_damaged_manifest_falls_back_to_the_last_good_copy(fake_env):
    g4, g3 = user_files(fake_env)
    eng = gtk_engine(fake_env)
    eng.apply(Settings())
    b = Backup(fake_env)
    assert b.last_good_path.is_file()
    b.manifest_path.write_text('{"files": {"half-writ')
    assert eng.revert() == []
    assert g4.read_text() == "/* my own gtk4 */\n"
    assert g3.read_text() == "/* my own gtk3 */\n"
    assert fake_env.gs[(IFACE, None)]["gtk-theme"] == "'Adwaita'"
    # The manifest is good again after that save.
    json.loads(b.manifest_path.read_text())


@pytest.mark.parametrize("junk", ['{"files": {"half-writ', "[]", '{"files": []}', "\xff\xfe"])
def test_unreadable_manifest_stops_apply_and_restore(fake_env, junk):
    g4, _ = user_files(fake_env)
    eng = gtk_engine(fake_env)
    eng.apply(Settings())
    b = Backup(fake_env)
    b.last_good_path.unlink()
    b.manifest_path.write_bytes(junk.encode("latin-1"))
    before = b.manifest_path.read_bytes()

    results = eng.apply(Settings())
    assert [r.status for r in results] == ["failed"]
    assert "can't read its backup of your original look" in results[0].message
    problems = eng.revert()
    assert len(problems) == 1 and "can't read its backup" in problems[0]
    # Nothing was changed, and the damaged backup was never written over.
    assert b.manifest_path.read_bytes() == before
    assert not b.last_good_path.exists()
    assert "Fedora Glass" in g4.read_text()
    assert fake_env.gs[(IFACE, None)]["gtk-theme"] == "'adw-gtk3-dark'"
    # Still "applied" (so removing the app tries Restore and says why), but the watcher waits.
    assert eng.is_applied() and not eng.look_on()


def test_missing_manifest_is_a_first_run(fake_env):
    b = Backup(fake_env)
    assert not b.manifest_path.exists()
    assert b.data["files"] == {}


def test_lost_copy_does_not_block_restore(fake_env):
    g4, g3 = user_files(fake_env)
    eng = gtk_engine(fake_env)
    eng.apply(Settings())
    os.unlink(Backup(fake_env).data["files"][str(g4)]["copy"])
    problems = eng.revert()
    assert len(problems) == 1
    assert str(g4) in problems[0] and "saved copy of your original was lost" in problems[0]
    # The rest came back, and the file without a copy is left as it is.
    assert g3.read_text() == "/* my own gtk3 */\n"
    assert fake_env.gs[(IFACE, None)]["gtk-theme"] == "'Adwaita'"
    assert "Fedora Glass" in g4.read_text()
    # The next Restore finishes.
    assert eng.revert() == []
    assert not eng.is_applied()


def test_manifest_is_flushed_to_disk_theme_files_are_not(fake_env, monkeypatch):
    synced = []
    real = os.fsync
    monkeypatch.setattr(engine_mod.os, "fsync", lambda fd: (synced.append(fd), real(fd)))
    engine_mod.write_if_changed(fake_env.config / "some.css", b"x")
    assert synced == []
    b = Backup(fake_env)
    b.data["gsettings"]["a|b|c"] = {"target": "t", "value": "1"}
    b.save()
    assert len(synced) == 2         # the file, then its folder


def test_an_apply_with_nothing_new_writes_no_manifest(fake_env):
    user_files(fake_env)
    eng = gtk_engine(fake_env)
    eng.apply(Settings())
    m = Backup(fake_env).manifest_path
    st = m.stat().st_mtime_ns
    os.utime(m, ns=(st - 10**9, st - 10**9))
    eng.apply(Settings())
    assert m.stat().st_mtime_ns == st - 10**9


def test_last_good_copy_alone_is_not_followed(fake_env):
    """The manifest moved away by hand (what the message suggests): a first run again, and
    the old last-good copy never comes back as if it were this backup's."""
    user_files(fake_env)
    eng = gtk_engine(fake_env)
    eng.apply(Settings())
    b = Backup(fake_env)
    b.last_good_path.write_bytes(b.manifest_path.read_bytes())
    b.manifest_path.unlink()
    fresh = Backup(fake_env)
    assert fresh.data["files"] == {}
    fresh.data["gsettings"]["x|/|y"] = {"target": "t", "value": "1"}
    fresh.save()
    assert not fresh.last_good_path.exists()
