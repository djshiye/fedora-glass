"""Review round after 1.7.4, engine side: Alacritty files with general keys but no [general]
header stay valid TOML, a deleted glass file never costs the user's stored original, an update
installed while logged out still reaches the other apps, AppImage folders are listed once per
Apply, leftovers are tidied, Restore never leaves the user's file missing, and a newer
version's per-app glass choices survive an older save."""
from __future__ import annotations

import json
import os
import time
import tomllib
from pathlib import Path

import pytest

from fedoraglass import __main__ as cli, engine
from fedoraglass.engine import Engine
from fedoraglass.render import terminal as rt
from fedoraglass.settings import Settings
from fedoraglass.targets import terminal as tt


# ---- E1. alacritty.toml with general keys but no [general] header ------------------------
ALA_CASES = {
    "none": "[font]\nsize = 12\n",
    "header": "[font]\nsize = 12\n\n[general]\nlive_config_reload = true\n",
    "extra": "[general.extra]\nx = 1\n[font]\nsize = 12\n",
    "dotted": "general.live_config_reload = true\n[font]\nsize = 12\n",
    "dotted_crlf": "general.live_config_reload = true\r\n[font]\r\nsize = 12\r\n",
    "empty": "",
}


@pytest.mark.parametrize("name", sorted(ALA_CASES))
def test_alacritty_edit_stays_valid_toml_and_restores_bytes(fake_env, name):
    text = ALA_CASES[name]
    main = fake_env.config / "alacritty/alacritty.toml"
    main.parent.mkdir(parents=True)
    main.write_bytes(text.encode())
    new = rt.alacritty_with_import(text, "/x/fedora-glass.toml")
    data = tomllib.loads(new)
    assert data["general"]["import"] == ["/x/fedora-glass.toml"]
    assert rt.alacritty_with_import(new, "/x/fedora-glass.toml") == new     # again: same
    eng = Engine(fake_env, targets=[tt.Alacritty()])
    eng.apply(Settings())
    tomllib.loads(main.read_text())
    assert "fedora-glass.toml" in main.read_text()
    eng.revert()
    assert main.read_bytes() == text.encode()


def test_alacritty_inline_general_table_is_left_to_the_manual_step():
    text = "general = { live_config_reload = true }\n[font]\nsize = 12\n"
    assert rt.alacritty_with_import(text, "/x/fedora-glass.toml") is None


# ---- helpers: a target that writes one file of ours -----------------------------------------
from dataclasses import dataclass, field          # noqa: E402

from fedoraglass.targets.base import Target, WriteFile      # noqa: E402


@dataclass
class OneFile(Target):
    path: Path = field(default=Path("/nonexistent"))
    body: str = "/* ours */\n"

    def plan(self, ctx):
        return [WriteFile(self.path, self.body)]


def one_file_engine(env, path, tid="t"):
    return Engine(env, [OneFile(id=tid, name="Test", path=path)])


# ---- E2. a deleted glass file never costs the stored original ---------------------------
def test_deleting_our_file_then_applying_keeps_the_users_original(fake_env):
    css = fake_env.config / "gtk-4.0/gtk.css"
    css.parent.mkdir(parents=True)
    css.write_text("/* 2024 */\n")
    eng = one_file_engine(fake_env, css)
    eng.apply(Settings())
    assert css.read_text() == "/* ours */\n"
    css.unlink()
    eng.apply(Settings())
    eng.apply(Settings())
    assert css.read_text() == "/* ours */\n"
    eng.revert()
    assert css.read_text() == "/* 2024 */\n"


# ---- E3. an update with no stamp (the only full Apply had a failing part) ---------------
def test_update_applies_the_other_parts_when_the_look_was_never_stamped(fake_env):
    from fedoraglass.engine import applied_version_path, failed_parts_path
    from test_wait_for_glass import desktop
    from fedoraglass import settings as settings_mod
    from fedoraglass.settings import config_dir
    eng = desktop(fake_env)
    s = Settings()
    settings_mod.save(s)
    (config_dir() / "tokens.json").mkdir(parents=True, exist_ok=True)       # fails every time
    assert any(r.status == "failed" for r in eng.apply(s))
    assert failed_parts_path(fake_env).exists() and not applied_version_path(fake_env).exists()
    # the glass files are this version's already (before-login did that): only the stamp is missing
    calls = []
    real = Engine.apply
    Engine.apply = lambda self, *a, **k: calls.append(1) or real(self, *a, **k)
    try:
        assert cli.update_after_upgrade(eng) is True, "the other parts get the update"
        n = len(calls)
        for _ in range(3):          # a part that keeps failing must not apply everything at every login
            cli.update_after_upgrade(eng)
    finally:
        Engine.apply = real
    assert len(calls) <= n + 1, "at most one more try, then it is left alone"
    assert cli.update_after_upgrade(eng) is False
    assert applied_version_path(fake_env).exists()


# ---- E4. AppImage folders are listed once per Apply ---------------------------------------
def test_appimage_folders_are_listed_once_per_apply(fake_env, monkeypatch):
    from fedoraglass.targets import apps
    dl = fake_env.home / "Downloads"
    dl.mkdir()
    for i in range(50):
        (dl / f"file{i}.txt").write_text("x")
    (dl / "Obsidian-1.5.AppImage").write_text("x")
    scans = []
    real = os.scandir
    monkeypatch.setattr(os, "scandir", lambda p=".": scans.append(str(p)) or real(p))
    eng = Engine(fake_env, targets=[])
    with eng._locked():
        assert apps.has_appimage(fake_env, "obsidian")
        assert not apps.has_appimage(fake_env, "qbittorrent")
        assert apps.has_appimage(fake_env, "obsidian")
        assert not apps.has_appimage(fake_env, "firefox")
    assert scans.count(str(dl)) == 1
    (dl / "qBittorrent-4.AppImage").write_text("x")
    with eng._locked():             # the next Apply sees what was added
        assert apps.has_appimage(fake_env, "qbittorrent")
    assert apps.has_appimage(fake_env, "qbittorrent") and apps.has_appimage(fake_env, "obsidian")
    (dl / "qBittorrent-4.AppImage").unlink()
    assert not apps.has_appimage(fake_env, "qbittorrent"), "outside an Apply it looks afresh"


# ---- E5a. temp files left by a killed write ---------------------------------------------
def _aged(p, seconds=300):
    t = time.time() - seconds
    os.utime(p, (t, t))


def test_stale_temp_files_are_swept_by_apply_and_restore(fake_env):
    d = fake_env.config / "newapp"
    path = d / "glass.css"
    eng = one_file_engine(fake_env, path)
    eng.apply(Settings())
    stale = d / ".glass.css.ab12_xYz.lg-tmp"
    other = d / ".notours.css.ab12_xYz.lg-tmp"          # another file's name: not ours to touch
    plain = d / ".glass.css.backup"
    link = d / ".glass.css.zz99zz99.lg-tmp"
    for p in (stale, other, plain):
        p.write_text("half")
        _aged(p)
    link.symlink_to(other)
    fresh = d / ".glass.css.n0wn0wn0.lg-tmp"            # a write that is under way right now
    fresh.write_text("half")
    eng.apply(Settings())
    assert not stale.exists()
    assert fresh.exists(), "a temp file younger than a minute may belong to a running write"
    assert other.exists() and plain.exists() and link.is_symlink()
    _aged(fresh)
    stale.write_text("half")
    _aged(stale)
    eng.revert()
    assert not fresh.exists()
    assert not stale.exists() and other.exists() and plain.exists() and link.is_symlink()
    assert sorted(x.name for x in d.iterdir()) == sorted([other.name, plain.name, link.name])


def test_a_killed_write_does_not_keep_the_folder_after_restore(fake_env, monkeypatch):
    d = fake_env.config / "newapp"
    path = d / "glass.css"
    eng = one_file_engine(fake_env, path)
    eng.apply(Settings())
    (d / ".glass.css.q1w2e3r4.lg-tmp").write_text("half")      # the process was killed here
    _aged(d / ".glass.css.q1w2e3r4.lg-tmp")
    eng.revert()
    assert not d.exists()


# ---- E5b. the Flatpak override file Apply made is taken away again -----------------------
def _flatpak_engine(env):
    from fedoraglass.targets.base import FlatpakOverride

    @dataclass
    class Grant(Target):
        def plan(self, ctx):
            return [FlatpakOverride(filesystems=("xdg-config/gtk-3.0:ro",))]
    return Engine(env, [Grant(id="g", name="Grant")])


def test_the_override_file_made_by_apply_is_removed_by_restore(fake_env):
    f = fake_env.data / "flatpak/overrides/global"
    assert not f.exists()
    eng = _flatpak_engine(fake_env)
    eng.apply(Settings())
    assert f.is_file() and "xdg-config/gtk-3.0:ro" in f.read_text()
    eng.revert()
    assert not f.exists()
    assert not (fake_env.data / "flatpak").exists(), "the folders Apply made go too"


def test_an_override_file_the_user_had_stays_after_restore(fake_env):
    f = fake_env.data / "flatpak/overrides/global"
    f.parent.mkdir(parents=True)
    f.write_text("")
    eng = _flatpak_engine(fake_env)
    eng.apply(Settings())
    eng.revert()
    assert f.is_file() and f.read_text() == ""


def test_an_old_record_without_the_fact_keeps_todays_behaviour(fake_env):
    f = fake_env.data / "flatpak/overrides/global"
    eng = _flatpak_engine(fake_env)
    eng.apply(Settings())
    m = engine.Backup(fake_env).manifest_path
    data = json.loads(m.read_text())
    for rec in data["flatpak"].values():
        rec.pop("absent", None)
        rec.pop("new_dirs", None)
    m.write_text(json.dumps(data))
    eng.revert()
    assert f.is_file() and f.read_text() == ""


# ---- E6. Restore never leaves the user's file missing -------------------------------------
def test_restore_keeps_the_file_in_place_until_the_original_is_written(fake_env, monkeypatch):
    css = fake_env.config / "gtk-4.0/gtk.css"
    css.parent.mkdir(parents=True)
    css.write_text("/* 2024 */\n")
    eng = one_file_engine(fake_env, css)
    eng.apply(Settings())
    real = engine.atomic_write
    calls = []

    def kill_once(path, data, *a, **k):
        if not calls and path == css:
            calls.append(1)
            raise OSError(5, "killed here")
        return real(path, data, *a, **k)
    monkeypatch.setattr(engine, "atomic_write", kill_once)
    problems = eng.revert()
    assert problems and css.read_text() == "/* ours */\n", "the file is still there, with the glass look"
    assert eng.revert() == []
    assert css.read_text() == "/* 2024 */\n"


def test_restore_still_swaps_a_link_for_the_original_file(fake_env):
    css = fake_env.config / "gtk-4.0/gtk.css"
    css.parent.mkdir(parents=True)
    css.write_text("/* 2024 */\n")
    eng = one_file_engine(fake_env, css)
    eng.apply(Settings())
    css.unlink()
    elsewhere = fake_env.home / "other.css"
    elsewhere.write_text("/* ours */\n")      # a link to a file with our bytes still counts as ours
    css.symlink_to(elsewhere)
    eng.revert()
    assert not css.is_symlink() and css.read_text() == "/* 2024 */\n"
    assert elsewhere.read_text() == "/* ours */\n"


# ---- E7. a newer version's per-app glass choices survive an older save --------------------
def test_an_unknown_app_glass_value_is_kept_when_this_version_saves(tmp_path):
    from fedoraglass import settings as S
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"app_glass": {"org.gnome.Nautilus": "dim", "kitty": "solid", "gimp": "dim"}}))
    s = S.load(p)
    assert s.app_glass == {"kitty": "solid"}, "this version does not know 'dim'"
    s.app_glass["gimp"] = "clearer"          # the user sets this one here
    S.save(s, p)
    saved = json.loads(p.read_text())["app_glass"]
    assert saved == {"org.gnome.Nautilus": "dim", "kitty": "solid", "gimp": "clearer"}
