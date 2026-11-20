"""Logic-break pass on the engine, the settings and saved looks: sequences and damaged or
hostile files that used to stop Apply or Restore with a Python error, empty a file of the
user's, or leave something behind."""
from __future__ import annotations

import json

import pytest

from fedoraglass import engine as engine_mod, looks, palette
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Backup, Engine, pending_path
from fedoraglass.render import apps as ra
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from fedoraglass.targets.base import Context, FlatpakOverride, GReset, GSet, ListEdit, Target, WriteFile

IFACE = "org.gnome.desktop.interface"
SHELL = "org.gnome.shell"


def sparse(path, size=2 ** 40):
    """A file that says it holds `size` bytes (a terabyte), without using the disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "wb") as f:
            f.truncate(size)
    except OSError:
        pytest.skip("this file system has no sparse files that big")


# ---- the lock file ------------------------------------------------------------------
def test_a_lock_file_that_is_a_link_never_empties_the_file_it_leads_to(fake_env):
    victim = fake_env.home / "notes.txt"
    victim.write_text("precious\n")
    d = fake_env.state / "liquid-glass"
    d.mkdir(parents=True)
    (d / "lock").symlink_to(victim)
    eng = Engine(fake_env, targets=[])
    eng.apply(Settings())
    assert victim.read_text() == "precious\n"
    assert not (d / "lock").is_symlink()
    (d / "lock").unlink()
    (d / "lock").symlink_to(fake_env.home / "made-by-the-lock")
    assert eng.revert() == []
    assert not (fake_env.home / "made-by-the-lock").exists()


# ---- a manifest that is valid JSON with the wrong types in it -------------------------
class Full(Target):
    def plan(self, ctx):
        e = ctx.env
        return [WriteFile(e.config / "gtk-4.0/gtk.css", "/* Fedora Glass */\nwindow {}\n"),
                WriteFile(e.config / "new/sub/x.css", "/* Fedora Glass */\nx {}\n"),
                GSet(IFACE, "gtk-theme", "'adw-gtk3-dark'"),
                ListEdit(SHELL, "enabled-extensions", add=("glass@test",)),
                ListEdit(SHELL, "disabled-extensions", remove=("glass@test",)),
                FlatpakOverride(filesystems=("xdg-config/gtk-4.0:ro",), env=(("GTK_THEME", "x"),))]


def _applied(env):
    env.gs[(SHELL, None)] = {"enabled-extensions": "['a@b']", "disabled-extensions": "['glass@test']"}
    (env.config / "gtk-4.0").mkdir(parents=True)
    (env.config / "gtk-4.0/gtk.css").write_text("/* mine */\n")
    eng = Engine(env, targets=[Full(id="t", name="T")])
    assert all(r.status == "applied" for r in eng.apply(Settings()))
    return eng


def _entry(data, section, end):
    return next(e for k, e in data[section].items() if k.endswith(end))


@pytest.mark.parametrize("section,end,field,bad", [
    ("files", "gtk-4.0/gtk.css", "mode", "644"),
    ("files", "gtk-4.0/gtk.css", "mode", 1.5),
    ("files", "gtk-4.0/gtk.css", "mode", 10 ** 30),
    ("files", "sub/x.css", "new_dirs", 5),
    ("files", "sub/x.css", "new_dirs", [1]),
    ("files", "sub/x.css", "new_dirs", ["relative/folder"]),
    ("lists", "|enabled-extensions", "added", [1]),
    ("lists", "|disabled-extensions", "removed", [1]),
    ("gsettings", "|gtk-theme", "value", 5),
    ("flatpak", "t", "filesystems", 5),
    ("flatpak", "t", "env", ["x"]),
    ("flatpak", "t", "new_dirs", None),
])
def test_a_manifest_with_a_wrong_type_is_said_to_be_damaged_not_a_crash(fake_env, section, end, field, bad):
    eng = _applied(fake_env)
    root = fake_env.state / "liquid-glass/backup"
    data = json.loads((root / "manifest.json").read_text())
    _entry(data, section, end)[field] = bad
    (root / "manifest.json").write_text(json.dumps(data))
    (root / "manifest.json.bak").unlink(missing_ok=True)
    problems = eng.revert()         # used to stop with TypeError or AttributeError
    assert len(problems) == 1 and "can't read its backup" in problems[0]
    assert (root / "manifest.json").read_text() == json.dumps(data), "the backup stays as it is"
    assert eng.apply(Settings())[0].status == "failed"


def test_a_manifest_with_a_wrong_type_falls_back_to_the_last_good_copy(fake_env):
    eng = _applied(fake_env)
    root = fake_env.state / "liquid-glass/backup"
    good = (root / "manifest.json").read_text()
    (root / "manifest.json.bak").write_text(good)
    data = json.loads(good)
    _entry(data, "files", "gtk-4.0/gtk.css")["mode"] = "644"
    (root / "manifest.json").write_text(json.dumps(data))
    assert eng.revert() == []
    assert (fake_env.config / "gtk-4.0/gtk.css").read_text() == "/* mine */\n"
    assert fake_env.gs[(IFACE, None)]["gtk-theme"] == "'Adwaita'"


def test_records_every_version_writes_still_read(fake_env):
    """The checks take nothing a real backup holds for damaged."""
    _applied(fake_env)
    Backup(fake_env)        # no BackupUnreadable


# ---- a folder two parts share -------------------------------------------------------
class InShared(Target):
    def __init__(self, id, sub):
        super().__init__(id=id, name=id)
        self.sub = sub

    def plan(self, ctx):
        return [WriteFile(ctx.env.data / "liquid-glass" / self.sub / "x.txt", f"/* Fedora Glass */ {self.sub}\n")]


def test_a_new_folder_two_parts_share_goes_when_the_last_of_them_does(fake_env):
    eng = Engine(fake_env, targets=[InShared("a", "a"), InShared("b", "b")])
    eng.apply(Settings())
    shared = fake_env.data / "liquid-glass"
    assert sorted(p.name for p in shared.iterdir()) == ["a", "b"]
    assert [r.status for r in eng.apply(Settings(targets={"a": False}))] == ["reverted", "applied"]
    assert shared.is_dir(), "b's file is still in it"
    assert eng.revert() == []
    assert not shared.exists(), "left behind, empty, for good"
    assert not fake_env.data.exists()


def test_a_shared_folder_with_the_users_own_file_in_it_stays(fake_env):
    eng = Engine(fake_env, targets=[InShared("a", "a"), InShared("b", "b")])
    eng.apply(Settings())
    eng.revert("a")
    (fake_env.data / "liquid-glass/mine.txt").write_text("mine\n")
    assert eng.revert() == []
    assert (fake_env.data / "liquid-glass/mine.txt").read_text() == "mine\n"


# ---- files far bigger than any of ours ------------------------------------------------
def test_a_huge_pending_file_does_not_stop_apply_or_restore(fake_env):
    sparse(pending_path())
    eng = Engine(fake_env, targets=[InShared("a", "a")])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]     # was MemoryError
    assert eng.revert() == []
    assert engine_mod.read_pending() == set()


def test_a_huge_manifest_is_said_to_be_unreadable(fake_env):
    sparse(fake_env.state / "liquid-glass/backup/manifest.json")
    eng = Engine(fake_env, targets=[InShared("a", "a")])
    assert eng.apply(Settings())[0].status == "failed"                 # was MemoryError
    assert "can't read its backup" in eng.revert()[0]
    assert eng.is_applied() and not eng.look_on()


def test_a_huge_file_in_the_looks_folder_is_left_out(tmp_path):
    lib = looks.Library(tmp_path / "looks")
    look_id = lib.save("Evening", Settings(frost=0.8))
    sparse(tmp_path / "looks/huge.json")
    assert [d["id"] for d in lib.list()] == [look_id]                  # was MemoryError
    assert lib.get(look_id) is not None


# ---- other damaged files of ours ------------------------------------------------------
def test_a_previous_look_with_a_huge_time_still_reads(tmp_path):
    path = tmp_path / "settings.json"
    settings_mod.save_previous(Settings(frost=0.3), 1.0, path=path)
    p = settings_mod.previous_path(path)
    data = json.loads(p.read_text())
    data["applied_at"] = 10 ** 400              # a whole number no float holds
    p.write_text(json.dumps(data))
    prev = settings_mod.load_previous(path)     # was OverflowError
    assert prev is not None and prev.applied_at == 0.0 and prev.settings.frost == pytest.approx(0.3)


def test_a_deeply_nested_remove_choice_beside_a_damaged_file_is_ignored(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{damaged")
    settings_mod._on_remove_path(path).write_text("[" * 100_000 + "]" * 100_000)
    loaded = settings_mod.load_checked(path, fix=False)        # was RecursionError
    assert not loaded.usable and loaded.settings.undo_on_remove is True


# ---- settings typed by hand -------------------------------------------------------------
@pytest.mark.parametrize("raw,off", [("false", False), ("no", False), ("maybe", False), (0, False),
                                     (None, False), ("true", True), (True, True)])
def test_dash_to_panels_hover_switch_reads_words_as_meant(fake_env, raw, off):
    s = settings_mod._from_dict({"motion_dtp_hover_off": raw})
    assert s.motion_dtp_hover_off is off
    t = palette.build(s, dark=True)
    ctx = Context(settings=s, tokens=t, dark=t, light=palette.build(s, dark=False), env=fake_env)
    acts = [a for a in ts.DashToPanel().plan(ctx) if getattr(a, "key", "") == "animate-appicon-hover"]
    assert isinstance(acts[0], GSet if off else GReset), "\"false\" switched Dash to Panel's hover off"


# ---- an app's own settings file changed into something no parser can read ---------------
def test_restore_leaves_an_app_file_nested_too_deep_to_read(fake_env):
    p = fake_env.config / "Code/User/settings.json"
    p.parent.mkdir(parents=True)
    p.write_text('{"a": 1}\n')

    class Code(Target):
        def plan(self, ctx):
            # As the VS Code part does: a file it can't read as plain JSON is left alone.
            merged = ra.merge_json_text(ra.read_text(p), {"workbench.colorTheme": "Fedora Glass Dark"})
            return [] if merged is None else [WriteFile(p, merged, edits=("json", ("workbench.colorTheme",)))]
    eng = Engine(fake_env, targets=[Code(id="code", name="Code")])
    eng.apply(Settings())
    deep = '{"a": ' + "[" * 200_000 + "]" * 200_000 + "}"
    p.write_text(deep)
    problems = eng.revert()             # was RecursionError, with nothing restored
    assert len(problems) == 1 and "can't be read" in problems[0]
    assert p.read_text() == deep
    assert not eng.is_applied()
    # And the next Apply leaves it alone too, instead of failing the part.
    assert eng.apply(Settings())[0].status in ("applied", "info")
    assert p.read_text() == deep


# ---- the Restore mark replaced by a folder ------------------------------------------------
def test_a_folder_where_the_restore_mark_goes_never_stops_apply(fake_env):
    p = fake_env.config / "x/file.conf"

    class One(Target):
        def plan(self, ctx):
            return [WriteFile(p, "ours\n")]
    eng = Engine(fake_env, targets=[One(id="one", name="One")])
    mark = engine_mod.restored_path(fake_env)
    mark.mkdir(parents=True)
    assert eng.apply(Settings())[0].status == "applied"     # was IsADirectoryError
    assert p.read_text() == "ours\n"
    assert not mark.exists(), "the look would have read as restored for good"
