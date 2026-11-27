"""A Flatpak app (or a Snap, or whatever arrives in an Obsidian vault) can change its own
folder at any moment. Fedora Glass writes theme files there with all of the person's
rights, so a folder swapped for a link must never lead Apply or Restore out of it: not into
~/.bashrc.d with the app's own bytes, not over the person's VS Code settings, and no secret
of theirs may be copied in."""
from __future__ import annotations

import json
import os
import shutil
import stat
import threading

import pytest

from fedoraglass import engine as eng
from fedoraglass.engine import Backup, Engine
from fedoraglass.safefs import Box
from fedoraglass.settings import Settings
from fedoraglass.targets import apps as ta
from fedoraglass.targets import terminal as tt
from tests.test_flatpak_snap_apps import install_flatpak, make_profile, only_flatpak  # noqa: F401

EVIL = b"echo ESCAPED > \"$HOME/escaped\"  # planted by the sandboxed app\n"
NOT_FOLLOWED = "links inside an app's own folder are not followed"
FIREFOX_ON = Settings(targets={"firefox-theme": True})


def vencord(home):
    v = home / ".var/app/com.discordapp.Discord/config/Vencord"
    (v / "themes").mkdir(parents=True)
    return v


def files_in(folder):
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


def statuses(results, target):
    return [(r.status, r.message) for r in results if r.target == target]


def swap_after_recording(monkeypatch, folder, to):
    """The app swaps `folder` for a link the moment the originals are on record, so the
    link shows up only when the files are written (after every check of the plan)."""
    real = Engine._record_originals

    def record_then_swap(self, tid, actions, backup):
        real(self, tid, actions, backup)
        if not folder.is_symlink():
            shutil.rmtree(folder)
            folder.symlink_to(to)
    monkeypatch.setattr(Engine, "_record_originals", record_then_swap)


# ---- Flatpak: Discord (Vencord) -------------------------------------------------------------
def test_restore_writes_nothing_outside_when_the_app_swapped_its_folder_for_a_link(fake_env):
    home = fake_env.home
    v = vencord(home)
    planted = v / "themes/liquid-glass.theme.css"
    planted.write_bytes(EVIL)           # the app's own file, before Apply
    os.chmod(planted, 0o755)
    victim = home / ".bashrc.d"         # Fedora's ~/.bashrc runs every file in here
    victim.mkdir()
    e = Engine(fake_env, [ta.Discord()])
    assert [s for s, _m in statuses(e.apply(Settings()), "discord")] == ["applied"]
    shutil.rmtree(v / "themes")
    (v / "themes").symlink_to(victim)
    problems = e.revert()
    assert files_in(victim) == []
    assert len(problems) == 1 and NOT_FOLLOWED in problems[0]
    assert "~/.var/app/com.discordapp.Discord/config/Vencord/themes" in problems[0]
    # The record and the stored original stay: once the link is gone, Restore finishes.
    assert e.is_applied()
    (v / "themes").unlink()
    (v / "themes").mkdir()
    assert e.revert() == []
    assert planted.read_bytes() == EVIL and stat.S_IMODE(planted.stat().st_mode) == 0o755
    assert files_in(victim) == [] and not e.is_applied()


def test_apply_leaves_the_app_alone_when_its_folder_is_a_link(fake_env, monkeypatch):
    """The app saw the plan read its settings (inotify) and swapped the folder right after."""
    home = fake_env.home
    v = vencord(home)
    (v / "settings").mkdir()
    (v / "settings/settings.json").write_text('{"evil": "attacker data", "enabledThemes": []}')
    victim = home / ".config/Code/User"
    victim.mkdir(parents=True)
    (victim / "settings.json").write_text('{"mine": 1}')
    real_plan = ta.Discord.plan

    def plan_then_swap(self, ctx):
        acts = real_plan(self, ctx)
        shutil.rmtree(v / "settings")
        (v / "settings").symlink_to(victim)
        return acts
    monkeypatch.setattr(ta.Discord, "plan", plan_then_swap)
    res = statuses(Engine(fake_env, [ta.Discord()]).apply(Settings()), "discord")
    assert (victim / "settings.json").read_text() == '{"mine": 1}'
    assert files_in(victim) == ["settings.json"]
    assert len(res) == 1 and res[0][0] == "skipped" and NOT_FOLLOWED in res[0][1]
    assert "~/.var/app/com.discordapp.Discord/config/Vencord/settings" in res[0][1]


def test_apply_writes_nothing_outside_when_the_link_shows_up_at_the_write(fake_env, monkeypatch):
    home = fake_env.home
    v = vencord(home)
    (v / "settings").mkdir()
    (v / "settings/settings.json").write_text('{"evil": "attacker data", "enabledThemes": []}')
    victim = home / ".config/Code/User"
    victim.mkdir(parents=True)
    (victim / "settings.json").write_text('{"mine": 1}')
    swap_after_recording(monkeypatch, v / "settings", victim)
    res = statuses(Engine(fake_env, [ta.Discord()]).apply(Settings()), "discord")
    assert (victim / "settings.json").read_text() == '{"mine": 1}'
    assert files_in(victim) == ["settings.json"]
    assert len(res) == 1 and res[0][0] == "failed" and NOT_FOLLOWED in res[0][1]


# ---- Snap: Firefox ------------------------------------------------------------------------
def snap_firefox(env, monkeypatch):
    monkeypatch.setattr(type(env), "which", lambda self, n: "/snap/bin/firefox" if n == "firefox" else None)
    prof = make_profile(env.home / "snap/firefox/common/.mozilla/firefox")
    (prof / "user.js").write_bytes(b'user_pref("a", 1);')
    return prof


def test_snap_restore_writes_nothing_outside_through_a_linked_chrome_folder(only_flatpak, monkeypatch):
    env = only_flatpak
    prof = snap_firefox(env, monkeypatch)
    e = Engine(env, [ta.Firefox()])
    assert [s for s, _m in statuses(e.apply(FIREFOX_ON), "firefox-theme")] == ["applied"]
    victim = env.home / ".config/autostart"
    victim.mkdir(parents=True)
    shutil.rmtree(prof / "chrome")
    (prof / "chrome").symlink_to(victim)
    problems = e.revert()
    assert files_in(victim) == []
    assert problems and all(NOT_FOLLOWED in p and "/chrome" in p for p in problems)
    assert e.is_applied()
    (prof / "chrome").unlink()
    assert e.revert() == []
    assert not e.is_applied() and (prof / "user.js").read_bytes() == b'user_pref("a", 1);'


def test_snap_apply_writes_nothing_outside_when_chrome_becomes_a_link(only_flatpak, monkeypatch):
    env = only_flatpak
    prof = snap_firefox(env, monkeypatch)
    (prof / "chrome").mkdir()
    victim = env.home / ".config/autostart"
    victim.mkdir(parents=True)
    swap_after_recording(monkeypatch, prof / "chrome", victim)
    res = statuses(Engine(env, [ta.Firefox()]).apply(FIREFOX_ON), "firefox-theme")
    assert files_in(victim) == []
    assert res[0][0] == "failed" and NOT_FOLLOWED in res[0][1]


def test_a_sandboxed_firefox_list_never_points_us_outside_its_folder(only_flatpak, monkeypatch):
    env = only_flatpak
    monkeypatch.setattr(type(env), "which", lambda self, n: "/snap/bin/firefox" if n == "firefox" else None)
    mine = env.home / ".mozilla/firefox/mine.default"
    mine.mkdir(parents=True)
    root = env.home / "snap/firefox/common/.mozilla/firefox"
    inside = root / "x.default"
    inside.mkdir(parents=True)
    (root / "profiles.ini").write_text(
        f"[Profile0]\nPath={mine}\nIsRelative=0\n\n[Profile1]\nPath=../../../../../.mozilla/firefox/mine.default\n"
        f"IsRelative=1\n\n[Profile2]\nPath={mine}\nIsRelative=1\n\n[Profile3]\nPath=x.default\nIsRelative=1\n")
    assert ta.firefox_profiles(env) == [inside]


# ---- Obsidian vault -------------------------------------------------------------------------
def obsidian_vault(env, tmp_path):
    vault = tmp_path / "notes"
    (vault / ".obsidian").mkdir(parents=True)
    (vault / ".obsidian/appearance.json").write_text('{"baseFontSize": 16}')
    (env.config / "obsidian").mkdir(parents=True)
    (env.config / "obsidian/obsidian.json").write_text(json.dumps({"vaults": {"a": {"path": str(vault)}}}))
    return vault


def test_vault_restore_writes_nothing_outside_through_a_linked_folder(fake_env, tmp_path):
    vault = obsidian_vault(fake_env, tmp_path)
    e = Engine(fake_env, [ta.Obsidian()])
    assert [s for s, _m in statuses(e.apply(Settings()), "obsidian")] == ["applied"]
    victim = fake_env.home / ".bashrc.d"
    victim.mkdir()
    shutil.rmtree(vault / ".obsidian/themes")
    (vault / ".obsidian/themes").symlink_to(victim)
    problems = e.revert()
    assert files_in(victim) == []
    assert problems and all(NOT_FOLLOWED in p for p in problems)
    assert e.is_applied()
    (vault / ".obsidian/themes").unlink()
    assert e.revert() == []
    assert files_in(vault) == [".obsidian", ".obsidian/appearance.json"]
    assert (vault / ".obsidian/appearance.json").read_text() == '{"baseFontSize": 16}'


def test_vault_apply_writes_nothing_outside_when_a_folder_becomes_a_link(fake_env, tmp_path, monkeypatch):
    vault = obsidian_vault(fake_env, tmp_path)
    (vault / ".obsidian/themes").mkdir()
    victim = fake_env.home / ".bashrc.d"
    victim.mkdir()
    swap_after_recording(monkeypatch, vault / ".obsidian/themes", victim)
    res = statuses(Engine(fake_env, [ta.Obsidian()]).apply(Settings()), "obsidian")
    assert files_in(victim) == []
    assert res[0][0] == "failed" and NOT_FOLLOWED in res[0][1]


def test_a_flatpak_obsidian_list_needs_a_folder_obsidian_made(only_flatpak, tmp_path):
    env = only_flatpak
    install_flatpak(env, ta.OBSIDIAN_FLATPAK)
    real, other = tmp_path / "real", env.home / ".config/autostart"
    (real / ".obsidian").mkdir(parents=True)
    other.mkdir(parents=True)
    cfg = env.home / ".var/app/md.obsidian.Obsidian/config/obsidian"
    cfg.mkdir(parents=True)
    (cfg / "obsidian.json").write_text(json.dumps({"vaults": {"a": {"path": str(real)}, "b": {"path": str(other)}}}))
    assert ta.Obsidian().vaults(env) == [real]


def other_spelling(env, tmp_path, how):
    """The way into the app's own folder by another name than ~ itself: /proc/self/root in
    front, or a second name for home (as /home is for /var/home on Silverblue)."""
    if how == "proc":
        return lambda p: f"/proc/self/root{p}"
    alias = tmp_path / "alias"
    alias.symlink_to(env.home)
    return lambda p: str(alias / p.relative_to(env.home))


def vault_by_other_spelling(env, tmp_path, how):
    install_flatpak(env, ta.OBSIDIAN_FLATPAK)
    app = env.home / ".var/app/md.obsidian.Obsidian"
    (app / "realv/.obsidian").mkdir(parents=True)
    (app / "realv/.obsidian/appearance.json").write_text('{"cssTheme": "x", "planted": "by the app"}')
    v = app / "v"
    v.symlink_to(app / "realv")
    (app / "config/obsidian").mkdir(parents=True)
    spelled = other_spelling(env, tmp_path, how)(v)
    (app / "config/obsidian/obsidian.json").write_text(json.dumps({"vaults": {"a": {"path": spelled}}}))
    victim = env.home / ".config/autostart"
    victim.mkdir(parents=True)
    return v, victim


@pytest.mark.parametrize("how", ["proc", "alias"])
def test_a_flatpak_obsidian_vault_named_another_way_never_leads_apply_outside(only_flatpak, tmp_path,
                                                                              monkeypatch, how):
    env = only_flatpak
    v, victim = vault_by_other_spelling(env, tmp_path, how)
    real_plan = ta.Obsidian.plan

    def plan_then_swap(self, ctx):
        acts = real_plan(self, ctx)
        v.unlink()
        v.symlink_to(victim)            # the app points its link at a folder of the person's
        return acts
    monkeypatch.setattr(ta.Obsidian, "plan", plan_then_swap)
    Engine(env, [ta.Obsidian()]).apply(Settings())
    assert files_in(victim) == []


@pytest.mark.parametrize("how", ["proc", "alias"])
def test_a_flatpak_obsidian_vault_named_another_way_never_leads_restore_outside(only_flatpak, tmp_path, how):
    env = only_flatpak
    v, victim = vault_by_other_spelling(env, tmp_path, how)
    e = Engine(env, [ta.Obsidian()])
    e.apply(Settings())
    v.unlink()
    v.symlink_to(victim)
    e.revert()
    assert files_in(victim) == []


# ---- a link at the file itself --------------------------------------------------------------
def secret(env):
    s = env.home / ".ssh/id_ed25519"
    s.parent.mkdir()
    s.write_bytes(b"-----BEGIN OPENSSH PRIVATE KEY----- the person's own\n")
    return s


def backup_holds(env, data: bytes) -> bool:
    store = env.state / "liquid-glass/backup"
    return any(data in p.read_bytes() for p in store.rglob("*") if p.is_file() and not p.is_symlink())


def test_a_link_at_the_file_never_has_a_secret_copied_or_handed_back(fake_env):
    key = secret(fake_env)
    v = vencord(fake_env.home)
    theme = v / "themes/liquid-glass.theme.css"
    theme.symlink_to(key)
    e = Engine(fake_env, [ta.Discord()])
    e.apply(Settings())
    assert not backup_holds(fake_env, key.read_bytes())
    assert e.revert() == []
    assert theme.is_symlink() and os.readlink(theme) == str(key)        # the app's own link back
    assert key.read_bytes().startswith(b"-----BEGIN")


def test_a_file_swapped_for_a_link_while_it_is_backed_up_is_not_copied(fake_env, monkeypatch):
    key = secret(fake_env)
    v = vencord(fake_env.home)
    (v / "settings").mkdir()
    sp = v / "settings/settings.json"
    sp.write_text('{"enabledThemes": []}')
    real, asked = Backup._copy_path, []

    def swap_then_copy(self, k, path):
        if path == sp:
            asked.append(path)
            if len(asked) == 2:         # the copy itself, right after the check that it is a file
                sp.unlink()
                sp.symlink_to(key)
        return real(self, k, path)
    monkeypatch.setattr(Backup, "_copy_path", swap_then_copy)
    e = Engine(fake_env, [ta.Discord()])
    res = statuses(e.apply(Settings()), "discord")
    assert res[0][0] == "failed"
    assert not backup_holds(fake_env, key.read_bytes())
    monkeypatch.undo()
    e.revert()
    assert sp.is_symlink() or not sp.exists() or key.read_bytes() not in sp.read_bytes()
    assert key.read_bytes().startswith(b"-----BEGIN")


# ---- a FIFO in place of a settings file -------------------------------------------------------
def test_a_fifo_in_place_of_an_apps_settings_file_does_not_hang_apply(only_flatpak):
    env = only_flatpak
    install_flatpak(env, ta.QBITTORRENT_FLATPAK)
    conf = env.home / ".var/app/org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf"
    conf.parent.mkdir(parents=True)
    os.mkfifo(conf)
    out = []
    t = threading.Thread(target=lambda: out.append(Engine(env, [ta.QBittorrent()]).apply(Settings())),
                         daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "Apply hung on a FIFO"
    assert out and statuses(out[0], "qbittorrent")


# ---- a normal Flatpak folder: exactly as before ----------------------------------------------
FH = ".var/app"


def flatpak_scene(env):
    home = env.home
    for app in (ta.VSCODE_FLATPAK, ta.DISCORD_FLATPAK, ta.QBITTORRENT_FLATPAK, ta.PRISM_FLATPAK,
                "app.devsuite.Ptyxis", ta.OBSIDIAN_FLATPAK):
        install_flatpak(env, app)

    def put(rel, text, mode=0o644):
        p = home / FH / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        os.chmod(p, mode)
    put("com.visualstudio.code/config/Code/User/settings.json", '{"editor.fontSize": 14}\n', 0o600)
    put("com.discordapp.Discord/config/Vencord/settings/settings.json", '{"enabledThemes": []}')
    put("org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf",
        "[Preferences]\r\nGeneral\\Locale=en\r\n", 0o600)
    put("org.prismlauncher.PrismLauncher/data/PrismLauncher/prismlauncher.cfg", "[General]\nLanguage=en\n")
    put("app.devsuite.Ptyxis/config/glib-2.0/settings/keyfile",
        "[org/gnome/Ptyxis]\nprofile-uuids=['0123456789abcdef']\ndefault-profile-uuid='0123456789abcdef'\n")
    vault = home / FH / "md.obsidian.Obsidian/Documents/notes"
    put("md.obsidian.Obsidian/Documents/notes/.obsidian/appearance.json", '{"baseFontSize": 16}')
    put("md.obsidian.Obsidian/config/obsidian/obsidian.json", json.dumps({"vaults": {"a": {"path": str(vault)}}}))
    return [ta.VSCode(), ta.Discord(), ta.QBittorrent(), ta.Prism(), tt.Ptyxis(), ta.Obsidian()]


def everything(home):
    """Every name below `home` with its type, mode and bytes (or link), never followed."""
    out = {}
    for top, dirs, files in os.walk(home):
        for n in dirs + files:
            p = os.path.join(top, n)
            st = os.lstat(p)
            what = os.readlink(p) if stat.S_ISLNK(st.st_mode) else \
                open(p, "rb").read() if stat.S_ISREG(st.st_mode) else None
            out[os.path.relpath(p, home)] = (stat.S_IFMT(st.st_mode), stat.S_IMODE(st.st_mode), what)
    return out


def test_a_normal_flatpak_folder_gets_the_same_files_and_records_as_before(only_flatpak, monkeypatch):
    env = only_flatpak
    home = env.home

    def run():
        e = Engine(env, flatpak_scene(env))
        e.apply(Settings())
        # The apps change their own files afterwards (Restore then takes only our keys out).
        vs = home / FH / "com.visualstudio.code/config/Code/User/settings.json"
        vs.write_text(vs.read_text().replace("{", '{\n  "files.autoSave": "on",', 1))
        with open(home / FH / "org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf", "a") as f:
            f.write("[LegalNotice]\r\nAccepted=true\r\n")
        res = [(r.target, r.status, r.message) for r in e.apply(Settings(scheme="light"))]
        applied = everything(home)
        manifest = json.loads(Backup(env).manifest_path.read_text())
        problems = e.revert()
        return res, applied, manifest, problems, everything(home)

    assert isinstance(Backup(env).files(home / FH / "x/y"), Box)
    walked = run()
    assert ("vscode", "applied", "") in walked[0] and ("ptyxis", "applied", "") in walked[0]
    assert len(walked[2]["files"]) >= 10 and walked[3] == []
    assert walked[2]["files"][str(home / FH / "com.visualstudio.code/config/Code/User/settings.json")]["changed"]
    assert '"files.autoSave": "on"' in walked[4][".var/app/com.visualstudio.code/config/Code/User/settings.json"][2].decode()
    shutil.rmtree(home)
    home.mkdir()
    # Today's calls, links followed: what every earlier version did in these folders.
    for module in (eng, ta, ta.ra):
        monkeypatch.setattr(module, "box_root", lambda path, home: None)
    assert Backup(env).files(home / FH / "x/y") is eng.PLAIN
    plain = run()
    assert walked == plain
