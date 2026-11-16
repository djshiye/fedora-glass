"""Review round on the engine: nothing is written as root, a Flatpak override file comes
back as it was, a removed app's settings are not brought back, a damaged manifest is
unreadable (not a crash), CRLF files keep their endings, and odd files are left alone."""
from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

import pytest

from fedoraglass import __main__ as cli, engine, login_screen
from fedoraglass.engine import Backup, BackupUnreadable, Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.base import FlatpakOverride
from fedoraglass.targets.qt import QtKvantum
from fedoraglass.targets.terminal import Btop, Kitty

ROOT = Path(__file__).resolve().parent.parent


# ---- 1. as root ---------------------------------------------------------------------
@pytest.mark.parametrize("argv", [["apply"], ["revert"], ["watch"], ["before-login"], ["gui"],
                                  ["gui", "--screenshot", "x"], []])
def test_commands_that_write_the_look_are_refused_as_root(monkeypatch, capsys, argv):
    monkeypatch.setattr(cli, "_is_root", lambda: True)
    called = []
    for name in ("cmd_apply", "cmd_revert", "cmd_watch", "cmd_before_login", "cmd_gui"):
        monkeypatch.setattr(cli, name, lambda *a, **k: called.append(1) or 0)
    assert cli.main(argv) == 1
    assert not called
    err = capsys.readouterr().err
    assert "without sudo" in err and err.count("\n") == 1


@pytest.mark.parametrize("argv", [["plan"], ["status"], ["on-remove"], ["login-screen", "status"],
                                  ["login-screen", "off"]])
def test_commands_meant_for_root_still_run(monkeypatch, argv):
    monkeypatch.setattr(cli, "_is_root", lambda: True)
    ran = []
    for name in ("cmd_plan", "cmd_status", "cmd_on_remove", "cmd_login_screen"):
        monkeypatch.setattr(cli, name, lambda *a, **k: ran.append(1) or 0)
    # argparse binds func at parse time, so rebuild through main
    assert cli.main(argv) == 0
    assert ran


def test_packaging_never_runs_a_user_command_as_root():
    """The scripts run as root call only on-remove (as each person, through runuser)."""
    text = (ROOT / "packaging/undo-for-users.sh").read_text()
    assert '"$app" on-remove' in text
    for cmd in ("apply", "revert", "watch", "before-login"):
        assert f'"$app" {cmd}' not in text


def test_an_unusable_lock_is_a_failed_result_not_a_traceback(fake_env):
    d = fake_env.state / "liquid-glass"
    d.mkdir(parents=True)
    (d / "lock").write_text("")
    os.chmod(d / "lock", 0)
    os.chmod(d, 0o500)
    try:
        if os.access(d / "lock", os.W_OK):
            pytest.skip("this user can write anything (root)")
        eng = Engine(fake_env, targets=[])
        r = eng.apply(Settings())
        assert [x.status for x in r] == ["failed"] and str(d) in r[0].message
        assert len(eng.revert()) == 1
    finally:
        os.chmod(d, 0o700)
        os.chmod(d / "lock", 0o600)


def test_an_unusable_lock_folder_is_reported(fake_env, monkeypatch):
    real_open = open

    def deny(path, *a, **k):
        if str(path).endswith("liquid-glass/lock"):
            raise PermissionError(13, "Permission denied")
        return real_open(path, *a, **k)
    monkeypatch.setattr("builtins.open", deny)
    eng = Engine(fake_env, targets=[])
    assert eng.apply(Settings())[0].status == "failed"
    assert "Permission denied" in eng.revert()[0]


# ---- 2. Flatpak override file --------------------------------------------------------
ORIGINAL = ("# my notes: keep wayland only\n[Context]\nsockets=wayland;!x11;\nfilesystems=~/Music:ro;\n\n"
            "[Session Bus Policy]\n# allow tray\norg.kde.StatusNotifierWatcher=talk\n")


@pytest.mark.parametrize("original", [
    ORIGINAL,
    "# only a note\n[Context]\nsockets=wayland;\n",
    "[Session Bus Policy]\norg.x.Y=talk\n",
    "# nothing but a note\n",
    "[Context]\r\nsockets=wayland;\r\n",
])
def test_flatpak_override_comes_back_byte_for_byte_with_its_mode(fake_env, original):
    p = engine._flatpak_file(fake_env)
    p.parent.mkdir(parents=True)
    p.write_bytes(original.encode())
    os.chmod(p, 0o600)
    b = Backup(fake_env)
    engine._flatpak_apply(fake_env, "x", FlatpakOverride(filesystems=("xdg-config/gtk-4.0:ro",),
                                                         env=(("QT_STYLE_OVERRIDE", "kvantum"),)), b)
    mid = p.read_bytes().decode()
    assert "xdg-config/gtk-4.0:ro" in mid and "QT_STYLE_OVERRIDE=kvantum" in mid
    assert mid.startswith(original.split("\n")[0])          # comments are still there
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    engine._flatpak_undo(fake_env, b.data["flatpak"]["x"])
    assert p.read_bytes() == original.encode()
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_flatpak_override_made_by_us_is_gone_on_restore(fake_env):
    p = engine._flatpak_file(fake_env)
    b = Backup(fake_env)
    engine._flatpak_apply(fake_env, "x", FlatpakOverride(filesystems=("a:ro",)), b)
    assert stat.S_IMODE(p.stat().st_mode) == 0o644
    engine._flatpak_undo(fake_env, b.data["flatpak"]["x"])
    assert not p.exists()       # up to 1.7.4 an empty file was left behind


def test_flatpak_user_added_lines_survive_restore(fake_env):
    p = engine._flatpak_file(fake_env)
    p.parent.mkdir(parents=True)
    p.write_text("[Context]\nsockets=wayland;\n")
    b = Backup(fake_env)
    engine._flatpak_apply(fake_env, "x", FlatpakOverride(filesystems=("a:ro",)), b)
    p.write_text(p.read_text() + "[Environment]\nFOO=1\n")
    engine._flatpak_undo(fake_env, b.data["flatpak"]["x"])
    assert p.read_text() == "[Context]\nsockets=wayland;\n[Environment]\nFOO=1\n"


# ---- 3. a removed app is not brought back --------------------------------------------
def _seed(env, rel, text):
    p = env.home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_restore_does_not_recreate_settings_of_a_removed_app(fake_env):
    btop = _seed(fake_env, ".config/btop/btop.conf", '#? Config file for btop\ncolor_theme = "Default"\n')
    kitty = _seed(fake_env, ".config/kitty/kitty.conf", "font_size 12\n")
    eng = Engine(fake_env, [Btop(), Kitty()])
    eng.apply(Settings())
    assert btop.read_text() != '#? Config file for btop\ncolor_theme = "Default"\n'
    shutil.rmtree(btop.parent)
    shutil.rmtree(kitty.parent)
    assert eng.revert() == []
    assert not btop.parent.exists() and not kitty.parent.exists()
    assert not Backup(fake_env).data["files"]
    assert not list((fake_env.state / "liquid-glass/backup/files").glob("*"))   # stored copies are used up


def test_restore_does_not_recreate_a_merged_file_whose_folder_stays(fake_env):
    btop = _seed(fake_env, ".config/btop/btop.conf", "color_theme = \"Default\"\n")
    eng = Engine(fake_env, [Btop()])
    eng.apply(Settings())
    btop.unlink()
    assert eng.revert() == []
    assert not btop.exists()


def test_restore_still_puts_back_the_original_of_a_file_only_we_removed(fake_env):
    """A whole file of ours over the user's own, its folder still there: the original returns."""
    css = _seed(fake_env, ".config/gtk-3.0/gtk.css", "/* mine */\n")
    from fedoraglass.engine import Backup as B
    b = B(fake_env)
    b.record_file("t", css)
    css.write_text("/* Fedora Glass */\n")      # what Apply wrote
    b.data["files"][str(css)]["wrote"] = "x"
    b.save()
    css.unlink()
    assert B(fake_env).restore() == []
    assert css.read_text() == "/* mine */\n"


# ---- 4. a damaged manifest -----------------------------------------------------------
@pytest.mark.parametrize("content", [
    {"files": {"/x": {"kind": "file"}}},
    {"files": {"/x": "y"}},
    {"files": {"/x": {"target": "t"}}},
    {"files": {"/x": {"target": "t", "kind": "file"}}},
    {"files": {"/x": {"target": "t", "kind": "weird"}}},
    {"gsettings": {"a|b": {"target": "t", "value": "1"}}},
    {"gsettings": {"a||b": {"target": "t"}}},
    {"lists": {"a||b": {"target": "t", "added": 1, "removed": []}}},
    {"commands": {"x": {"target": "t", "undo": []}}},
    {"dirlinks": {"/d": {"target": "t"}}},
    {"flatpak": {"x": []}},
])
def test_damaged_manifest_entries_are_unreadable_not_a_crash(fake_env, content):
    m = fake_env.state / "liquid-glass/backup/manifest.json"
    m.parent.mkdir(parents=True)
    m.write_text(json.dumps(content))
    with pytest.raises(BackupUnreadable):
        Backup(fake_env)
    eng = Engine(fake_env, targets=[])
    assert eng.is_applied() in (True, False)
    assert eng.look_on() in (True, False)
    assert len(eng.revert()) == 1
    assert eng.apply(Settings())[0].status == "failed"


def test_a_damaged_manifest_falls_back_to_the_last_good_copy(fake_env):
    good = {"files": {"/x": {"target": "t", "kind": "missing", "new_dirs": []}}}
    m = fake_env.state / "liquid-glass/backup/manifest.json"
    m.parent.mkdir(parents=True)
    m.write_text(json.dumps({"files": {"/x": {"kind": "file"}}}))
    (m.parent / "manifest.json.bak").write_text(json.dumps(good))
    assert Backup(fake_env).data["files"] == good["files"]


def test_the_manifest_the_engine_writes_is_valid(fake_env):
    """What Apply records passes the check, for every kind of entry."""
    _seed(fake_env, ".config/btop/btop.conf", "color_theme = \"Default\"\n")
    fake_env.gs[("org.gnome.shell", None)] = {"enabled-extensions": "@as []", "disabled-extensions": "@as []"}
    eng = Engine(fake_env)
    eng.apply(Settings())
    assert Backup(fake_env).data["files"]
    Backup._parse((fake_env.state / "liquid-glass/backup/manifest.json").read_bytes())


# ---- 5. CRLF -------------------------------------------------------------------------
def test_crlf_app_configs_keep_their_line_endings(fake_env):
    from fedoraglass.render import apps as ra
    q = fake_env.config / "qBittorrent/qBittorrent.conf"
    q.parent.mkdir(parents=True)
    q.write_bytes(b"[Preferences]\r\nGeneral\\Locale=de\r\n")
    assert ra.read_text(q) == "[Preferences]\r\nGeneral\\Locale=de\r\n"
    out = ra.ini_set(ra.read_text(q), "Preferences", {"Cat": "1"})
    assert out == "[Preferences]\r\nGeneral\\Locale=de\r\nCat=1\r\n"
    assert ra.ini_set(ra.read_text(q), "Other", {"a": "1"}).endswith("\r\n[Other]\r\na=1\r\n")
    assert "\r\n" in ra.conf_set("a = 1\r\n", {"b": "2"}) and ra.conf_set("a = 1\r\n", {"b": "2"}) == "a = 1\r\nb = 2\r\n"


def test_qbittorrent_crlf_through_apply_and_restore(fake_env):
    from fedoraglass.targets.apps import QBittorrent
    q = _seed(fake_env, ".config/qBittorrent/qBittorrent.conf", "")
    q.write_bytes(b"[Preferences]\r\nGeneral\\Locale=de\r\n")
    eng = Engine(fake_env, [QBittorrent()])
    eng.apply(Settings())
    mid = q.read_bytes()
    assert b"\r\n" in mid and b"\n" not in mid.replace(b"\r\n", b"")
    # the app rewrites its file (so Restore unmerges rather than copies back)
    q.write_bytes(mid + b"[LegalNotice]\r\nAccepted=true\r\n")
    assert eng.revert() == []
    assert q.read_bytes() == b"[Preferences]\r\nGeneral\\Locale=de\r\n[LegalNotice]\r\nAccepted=true\r\n"


# ---- 6a. kvantum.kvconfig that can't be merged ---------------------------------------
def _qt_ctx(env):
    eng = Engine(env, [QtKvantum()])
    return eng, eng.context(Settings())


def test_kvantum_main_config_as_a_link_is_left_alone(fake_env):
    kv = fake_env.config / "Kvantum"
    kv.mkdir(parents=True)
    other = fake_env.home / "dotfiles/kvantum.kvconfig"
    other.parent.mkdir(parents=True)
    other.write_text("[General]\ntheme=Mine\n")
    (kv / "kvantum.kvconfig").symlink_to(other)
    eng, ctx = _qt_ctx(fake_env)
    t = QtKvantum()
    paths = [getattr(a, "path", None) for a in t.plan(ctx)]
    assert kv / "kvantum.kvconfig" not in paths
    assert kv / "FedoraGlass/FedoraGlass.kvconfig" in paths
    assert any("kvantum.kvconfig" in n for n in t.live_notes(ctx))
    assert other.read_text() == "[General]\ntheme=Mine\n"


def test_kvantum_main_config_not_utf8_is_left_alone(fake_env):
    kv = fake_env.config / "Kvantum"
    kv.mkdir(parents=True)
    (kv / "kvantum.kvconfig").write_bytes(b"[General]\ntheme=M\xe9\n")
    eng, ctx = _qt_ctx(fake_env)
    t = QtKvantum()
    assert kv / "kvantum.kvconfig" not in [getattr(a, "path", None) for a in t.plan(ctx)]
    assert t.live_notes(ctx)[0] != t.notes[0]


def test_kvantum_main_config_in_text_is_still_merged(fake_env):
    kv = fake_env.config / "Kvantum"
    kv.mkdir(parents=True)
    (kv / "kvantum.kvconfig").write_text("[General]\ntheme=Mine\n[Other]\nx=1\n")
    eng, ctx = _qt_ctx(fake_env)
    assert kv / "kvantum.kvconfig" in [getattr(a, "path", None) for a in QtKvantum().plan(ctx)]


# ---- 6b. login screen sheet that isn't text ------------------------------------------
def test_a_non_utf8_login_sheet_is_a_clean_error(monkeypatch, tmp_path):
    monkeypatch.setattr(login_screen, "_check_file", lambda p: None)
    monkeypatch.setattr(login_screen, "list_files", lambda p: ["/org/gnome/shell/theme/gdm.css"])
    monkeypatch.setattr(login_screen, "sheets", lambda names: list(names))
    monkeypatch.setattr(login_screen, "extract", lambda p, n: b"body { content: '\xff\xfe'; }")
    with pytest.raises(login_screen.LoginScreenError):
        login_screen.build("x", str(tmp_path / "out"), "#3584e4", "#3584e4", 0.5)


# ---- 6c. the CLI says a damaged settings file ----------------------------------------
def test_apply_says_when_the_settings_file_was_damaged(fake_env, monkeypatch, capsys):
    from fedoraglass import settings as S
    path = S.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")
    monkeypatch.setattr(cli, "_engine", lambda: Engine(fake_env, targets=[]))
    assert cli.main(["apply"]) == 0
    err = capsys.readouterr().err
    assert "could not be read" in err and "settings.json.damaged" in err and "defaults" in err
    assert Path(str(path) + ".damaged").read_text() == "{ not json"      # kept aside, not overwritten


def test_apply_with_good_settings_prints_nothing_on_stderr(fake_env, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_engine", lambda: Engine(fake_env, targets=[]))
    assert cli.main(["apply"]) == 0
    assert capsys.readouterr().err == ""


# ---- 6d. user units are not for system users -----------------------------------------
@pytest.mark.parametrize("name", ["liquid-glass-watch.service", "fedora-glass-before-login.service"])
@pytest.mark.parametrize("script", ["packaging/fedora-glass.spec", "packaging/install-tree.sh"])
def test_user_units_skip_system_users(script, name):
    text = (ROOT / script).read_text()
    unit = text.split(f"{name} <<'UNIT'\n", 1)[1].split("\nUNIT\n", 1)[0] if f"{name} <<'UNIT'" in text \
        else text.split(f"/{name}\" <<'UNIT'\n", 1)[1].split("\nUNIT\n", 1)[0]
    assert "\nConditionUser=!@system\n" in unit.split("[Service]")[0]
