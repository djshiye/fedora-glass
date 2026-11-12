"""Flatpak and Snap installs: Obsidian, VS Code, VSCodium, qBittorrent, Firefox (Snap) and Ptyxis
(Flatpak). Each is found when only that install exists, themed in its own folders, and
Restore original puts every file back exactly."""
from __future__ import annotations

import json

import pytest

from fedoraglass import palette
from fedoraglass.engine import Engine
from fedoraglass.render import apps as ra
from fedoraglass.settings import Settings
from fedoraglass.targets import apps as ta
from fedoraglass.targets import terminal as tt
from fedoraglass.targets.base import Command, Context, WriteFile


def ctx_for(env, dark=True, **kw):
    kw.setdefault("scheme", "dark" if dark else "light")
    s = Settings(**kw)
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d if dark else l, dark=d, light=l, env=env)


def snapshot(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()} | \
        {str(p.relative_to(folder)) + "/": b"" for p in folder.rglob("*") if p.is_dir()}


@pytest.fixture
def only_flatpak(fake_env, monkeypatch):
    """A PC where no program is on PATH and the machine's own installs don't count."""
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: None)
    monkeypatch.setattr(ta, "has_desktop_file", lambda env, d: False)
    monkeypatch.setattr(tt, "ptyxis_native", lambda env: False)
    monkeypatch.setattr(type(fake_env), "flatpak_installed", lambda self, a: (self.data / "flatpak/app" / a).is_dir())
    return fake_env


def install_flatpak(env, app_id):
    (env.data / "flatpak/app" / app_id).mkdir(parents=True)


# ---- Obsidian ---------------------------------------------------------------------------------
def test_obsidian_flatpak_only(only_flatpak, tmp_path):
    env = only_flatpak
    assert not ta.Obsidian().detect(env).available
    install_flatpak(env, ta.OBSIDIAN_FLATPAK)
    assert ta.Obsidian().detect(env).available
    vault = tmp_path / "vault"
    (vault / ".obsidian").mkdir(parents=True)
    cfg = env.home / ".var/app/md.obsidian.Obsidian/config/obsidian"
    cfg.mkdir(parents=True)
    (cfg / "obsidian.json").write_text(json.dumps({"vaults": {"a": {"path": str(vault)}}}))
    plan = ta.Obsidian().plan(ctx_for(env))
    assert {a.path.name for a in plan} == {"manifest.json", "theme.css", "appearance.json"}
    assert all(vault in a.path.parents for a in plan)


def test_obsidian_native_and_flatpak_vaults_are_both_themed_once(only_flatpak, tmp_path):
    env = only_flatpak
    v1, v2 = tmp_path / "v1", tmp_path / "v2"
    for v in (v1, v2):
        (v / ".obsidian").mkdir(parents=True)
    (env.config / "obsidian").mkdir(parents=True)
    (env.config / "obsidian/obsidian.json").write_text(json.dumps({"vaults": {"a": {"path": str(v1)}, "b": {"path": str(v2)}}}))
    cfg = env.home / ".var/app/md.obsidian.Obsidian/config/obsidian"
    cfg.mkdir(parents=True)
    (cfg / "obsidian.json").write_text(json.dumps({"vaults": {"c": {"path": str(v2)}}}))
    assert ta.Obsidian().vaults(env) == [v1, v2]


# ---- VS Code and VSCodium -----------------------------------------------------------------------
def test_vscode_flatpak_only_uses_its_own_folders_and_command(only_flatpak):
    env = only_flatpak
    assert not ta.VSCode().detect(env).available
    install_flatpak(env, ta.VSCODE_FLATPAK)
    assert ta.VSCode().detect(env).available
    fh = env.home / ".var/app/com.visualstudio.code"
    plan = ta.VSCode().plan(ctx_for(env, scheme="auto"))
    cmd = next(a for a in plan if isinstance(a, Command))
    assert cmd.argv[:4] == ("flatpak", "run", "com.visualstudio.code", "--install-extension")
    assert cmd.argv[4].startswith(str(fh / "data"))      # a path the sandbox reads
    assert cmd.undo[:3] == ("flatpak", "run", "com.visualstudio.code") and cmd.undo[3] == "--uninstall-extension"
    paths = [a.path for a in plan if isinstance(a, WriteFile)]
    assert fh / "config/Code/User/settings.json" in paths
    assert not any(str(p).startswith(str(env.config / "Code")) for p in paths)
    assert json.loads(next(a for a in plan if isinstance(a, WriteFile) and a.path.name == "settings.json").content)[
        "workbench.colorTheme"] == "Fedora Glass Dark"


def test_vscode_native_and_flatpak_are_both_themed(fake_env):
    install_flatpak(fake_env, ta.VSCODE_FLATPAK)
    plan = ta.VSCode().plan(ctx_for(fake_env))
    cmds = [a.argv[0] for a in plan if isinstance(a, Command)]
    assert cmds == ["code", "flatpak"]
    assert len([a for a in plan if isinstance(a, WriteFile) and a.path.name == "settings.json"]) == 2


def test_vscode_flatpak_restore_is_byte_identical(only_flatpak, monkeypatch):
    env = only_flatpak
    monkeypatch.setattr(type(env), "which", lambda self, n: "/usr/bin/flatpak" if n == "flatpak" else None)
    install_flatpak(env, ta.VSCODE_FLATPAK)
    fh = env.home / ".var/app/com.visualstudio.code"
    (fh / "config/Code/User").mkdir(parents=True)
    (fh / "config/Code/User/settings.json").write_bytes(b'{"editor.fontSize": 15}')
    before = snapshot(fh)
    eng = Engine(env, [ta.VSCode()])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    assert (fh / "data/liquid-glass/liquid-glass.vsix").is_file()
    assert "Fedora Glass" in (fh / "config/Code/User/settings.json").read_text()
    assert ["flatpak", "run", "com.visualstudio.code"] == next(c for c in env.commands if "--install-extension" in c)[:3]
    assert eng.revert() == []
    assert ["flatpak", "run", "com.visualstudio.code", "--uninstall-extension", ra.VSCODE_ID] in env.commands
    assert snapshot(fh) == before


def test_vscodium_native_and_flatpak(only_flatpak):
    env = only_flatpak
    t = ta.VSCodium()
    assert t.id == "vscodium" and t.name == "VSCodium" and t.group == "Apps"
    assert not t.detect(env).available
    install_flatpak(env, ta.VSCODIUM_FLATPAK)
    assert t.detect(env).available
    plan = t.plan(ctx_for(env))
    fh = env.home / ".var/app/com.vscodium.codium"
    assert fh / "config/VSCodium/User/settings.json" in [a.path for a in plan if isinstance(a, WriteFile)]
    assert next(a for a in plan if isinstance(a, Command)).argv[:3] == ("flatpak", "run", "com.vscodium.codium")
    # Native codium: its config folder alone is enough, and the paths are VSCodium's.
    (env.config / "VSCodium").mkdir(parents=True)
    paths = [a.path for a in t.plan(ctx_for(env)) if isinstance(a, WriteFile)]
    assert env.config / "VSCodium/User/settings.json" in paths
    # VS Code's own part does not see VSCodium.
    assert not ta.VSCode().detect(env).available


def test_vscodium_native_install_extension_is_codium(fake_env):
    (fake_env.config / "VSCodium/User").mkdir(parents=True)
    plan = ta.VSCodium().plan(ctx_for(fake_env))
    cmd = next(a for a in plan if isinstance(a, Command))
    assert cmd.argv[:2] == ("codium", "--install-extension")
    assert "liquid-glass/vscodium/" in cmd.argv[2]


def test_vscode_comment_note_covers_flatpak_settings(only_flatpak):
    env = only_flatpak
    install_flatpak(env, ta.VSCODE_FLATPAK)
    s = env.home / ".var/app/com.visualstudio.code/config/Code/User/settings.json"
    s.parent.mkdir(parents=True)
    s.write_text('{\n// hi\n"a": 1}')
    c = ctx_for(env)
    assert "comments" in ta.VSCode().live_notes(c)[0]
    assert "settings.json" not in {a.path.name for a in ta.VSCode().plan(c) if isinstance(a, WriteFile)}


# ---- qBittorrent -----------------------------------------------------------------------------------
def test_qbittorrent_flatpak_only(only_flatpak):
    env = only_flatpak
    assert not ta.QBittorrent().detect(env).available
    install_flatpak(env, ta.QBITTORRENT_FLATPAK)
    assert ta.QBittorrent().detect(env).available
    fh = env.home / ".var/app/org.qbittorrent.qBittorrent"
    conf = fh / "config/qBittorrent/qBittorrent.conf"
    conf.parent.mkdir(parents=True)
    conf.write_bytes(b"[Preferences]\r\nGeneral\\Locale=en\r\n")
    before = snapshot(fh)
    plan = ta.QBittorrent().plan(ctx_for(env))
    out = next(a for a in plan if a.path == conf).content
    assert f"General\\CustomUIThemePath={fh}/data/liquid-glass/qbittorrent/config.json" in out
    assert not any(str(a.path).startswith(str(env.config)) or str(a.path).startswith(str(env.data / "liquid-glass"))
                   for a in plan)
    eng = Engine(env, [ta.QBittorrent()])
    eng.apply(Settings())
    assert (fh / "data/liquid-glass/qbittorrent/stylesheet.qss").is_file()
    assert eng.revert() == []
    assert snapshot(fh) == before


def test_qbittorrent_native_and_flatpak_both(fake_env):
    install_flatpak(fake_env, ta.QBITTORRENT_FLATPAK)
    confs = [a.path for a in ta.QBittorrent().plan(ctx_for(fake_env)) if a.path.name == "qBittorrent.conf"]
    assert confs == [fake_env.config / "qBittorrent/qBittorrent.conf",
                     fake_env.home / ".var/app/org.qbittorrent.qBittorrent/config/qBittorrent/qBittorrent.conf"]


# ---- Firefox from Snap --------------------------------------------------------------------------------
def make_profile(root, name="abcd.default"):
    prof = root / name
    prof.mkdir(parents=True)
    (root / "profiles.ini").write_text(f"[Profile0]\nName={name}\nIsRelative=1\nPath={name}\nDefault=1\n")
    return prof


def test_snap_firefox_profile_is_found_and_restored(only_flatpak, monkeypatch):
    env = only_flatpak
    monkeypatch.setattr(type(env), "which", lambda self, n: "/snap/bin/firefox" if n == "firefox" else None)
    d = ta.Firefox().detect(env)
    assert not d.available and "start Firefox once" in d.detail
    root = env.home / "snap/firefox/common/.mozilla/firefox"
    prof = make_profile(root)
    assert ta.Firefox().detect(env).available
    assert ta.firefox_profiles(env) == [prof]
    (prof / "user.js").write_bytes(b'user_pref("a", 1);')
    before = snapshot(env.home / "snap")
    eng = Engine(env, [ta.Firefox()])
    assert [r.status for r in eng.apply(Settings(targets={"firefox-theme": True}))] == ["applied"]
    assert (prof / "chrome/fedora-glass.css").is_file()
    assert eng.revert() == []
    assert snapshot(env.home / "snap") == before


def test_snap_firefox_stays_opt_in_and_skips_linked_chrome(only_flatpak, tmp_path):
    env = only_flatpak
    prof = make_profile(env.home / "snap/firefox/common/.mozilla/firefox")
    assert "firefox-theme" not in Engine(env, [ta.Firefox()]).plan(Settings())
    dot = tmp_path / "dot"
    dot.mkdir()
    (prof / "chrome").symlink_to(dot)
    assert ta.Firefox().plan(ctx_for(env, targets={"firefox-theme": True})) == []
    assert list(dot.iterdir()) == []


# ---- Ptyxis from Flatpak -------------------------------------------------------------------------------
UUID = "0123456789abcdef0123456789abcdef"


def ptyxis_keyfile(env, text=None, app="app.devsuite.Ptyxis"):
    kf = env.home / ".var/app" / app / "config/glib-2.0/settings/keyfile"
    kf.parent.mkdir(parents=True)
    kf.write_bytes((text if text is not None else
                    f"[org/gnome/Ptyxis]\nprofile-uuids=['{UUID}']\ndefault-profile-uuid='{UUID}'\n\n"
                    f"[org/gnome/Ptyxis/Profiles/{UUID}]\nlabel='Mine'\npalette='Gruvbox'\nopacity=1.0\n").encode())
    return kf


def test_ptyxis_flatpak_only_is_detected_and_written_to_its_own_file(only_flatpak):
    env = only_flatpak
    assert not tt.Ptyxis().detect(env).available
    install_flatpak(env, "app.devsuite.Ptyxis")
    assert tt.Ptyxis().detect(env).available
    kf = ptyxis_keyfile(env)
    fh = env.home / ".var/app/app.devsuite.Ptyxis"
    before = snapshot(fh)
    eng = Engine(env, [tt.Ptyxis()])
    assert [r.status for r in eng.apply(Settings(terminal_colors=True))] == ["applied"]
    out = kf.read_text()
    assert "palette='Fedora Glass'" in out and "opacity=1.0" not in out and "label='Mine'" in out
    assert (fh / "data/org.gnome.Ptyxis/palettes/Fedora Glass.palette").is_file()
    # Nothing for the host: its desktop settings and palette folder are not touched.
    assert not (env.data / "org.gnome.Ptyxis").exists() and not env.gs.get(("org.gnome.Ptyxis", None))
    before_second = kf.read_bytes()
    eng.apply(Settings(terminal_colors=True))
    assert kf.read_bytes() == before_second
    assert eng.revert() == []
    assert snapshot(fh) == before


def test_ptyxis_flatpak_colours_off_gives_the_profile_its_palette_back(only_flatpak):
    env = only_flatpak
    install_flatpak(env, "app.devsuite.Ptyxis")
    kf = ptyxis_keyfile(env)
    eng = Engine(env, [tt.Ptyxis()])
    eng.apply(Settings(terminal_colors=True))
    eng.apply(Settings(terminal_colors=False))
    out = kf.read_text()
    assert "palette" not in out.split("[org/gnome/Ptyxis/Profiles/")[1]
    assert "opacity=" in out


def test_ptyxis_flatpak_restore_keeps_what_the_app_wrote_since(only_flatpak):
    env = only_flatpak
    install_flatpak(env, "app.devsuite.Ptyxis")
    kf = ptyxis_keyfile(env)
    eng = Engine(env, [tt.Ptyxis()])
    eng.apply(Settings(terminal_colors=True))
    kf.write_text(kf.read_text() + "\n[org/gnome/Ptyxis]\nfont-name='Mono 11'\n")
    assert eng.revert() == []
    out = kf.read_text()
    assert "font-name='Mono 11'" in out and "palette='Gruvbox'" in out and "opacity=1.0" in out
    assert "Fedora Glass" not in out


def test_ptyxis_flatpak_without_profile_or_with_link_says_so(only_flatpak, tmp_path):
    env = only_flatpak
    install_flatpak(env, "app.devsuite.Ptyxis")
    c = ctx_for(env)
    plan = tt.Ptyxis().plan(c)
    assert [a.path.name for a in plan] == ["Fedora Glass.palette"]       # no profile yet: nothing else
    assert any("Flatpak" in n for n in tt.Ptyxis().live_notes(c))
    real = tmp_path / "dotfiles-keyfile"
    real.write_text(f"[org/gnome/Ptyxis]\nprofile-uuids=['{UUID}']\n")
    kf = env.home / ".var/app/app.devsuite.Ptyxis/config/glib-2.0/settings/keyfile"
    kf.parent.mkdir(parents=True)
    kf.symlink_to(real)
    assert [a.path.name for a in tt.Ptyxis().plan(c)] == ["Fedora Glass.palette"]
    assert "can't be read" in tt.Ptyxis().live_notes(c)[0]
    Engine(env, [tt.Ptyxis()]).apply(Settings())
    assert kf.is_symlink() and "Fedora" not in real.read_text()


def test_ptyxis_native_and_flatpak_both(fake_env):
    install_flatpak(fake_env, "app.devsuite.Ptyxis")
    ptyxis_keyfile(fake_env)
    names = [a.path for a in tt.Ptyxis().plan(ctx_for(fake_env)) if isinstance(a, WriteFile)]
    assert fake_env.data / "org.gnome.Ptyxis/palettes/Fedora Glass.palette" in names
    assert any(".var/app" in str(p) for p in names)
