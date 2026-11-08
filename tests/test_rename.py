"""Liquid Glass became Fedora Glass in 1.5.0. Files an older version wrote under the old
name must not linger beside the new ones after the next Apply (two "Liquid Glass" themes
in a picker, say), and Restore original must still put everything back."""

from __future__ import annotations

import json
from pathlib import Path

from fedoraglass.engine import Backup, Engine, is_legacy
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from fedoraglass.targets.base import Target, WriteFile

from test_shell import seeded_env


class Writes(Target):
    def __init__(self, *paths: Path, content: str = "/* Fedora Glass */"):
        super().__init__(id="probe", name="Probe")
        self.paths, self.content = paths, content

    def plan(self, ctx):
        return [WriteFile(p, self.content) for p in self.paths]


def old_and_new(env):
    old = env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css"
    new = env.data / "themes/FedoraGlass/gnome-shell/gnome-shell.css"
    return old, new


def test_old_name_files_go_once_the_new_ones_are_written(fake_env):
    old, new = old_and_new(fake_env)
    Engine(fake_env, [Writes(old, content="/* Liquid Glass */")]).apply(Settings())
    assert old.is_file()
    Engine(fake_env, [Writes(new)]).apply(Settings())
    assert new.is_file()
    assert not old.exists() and not (fake_env.data / "themes/LiquidGlass").exists()
    assert str(old) not in Backup(fake_env).data["files"]
    # Restore original still takes everything away.
    assert Engine(fake_env, [Writes(new)]).revert() == []
    assert not new.exists() and not (fake_env.data / "themes").exists()


def test_a_file_the_user_had_before_comes_back(fake_env):
    conf = fake_env.config / "btop/themes/liquid-glass.theme"
    conf.parent.mkdir(parents=True)
    conf.write_text("their own theme\n")
    Engine(fake_env, [Writes(conf, content="# Liquid Glass for btop\n")]).apply(Settings())
    Engine(fake_env, [Writes(fake_env.config / "btop/themes/fedora-glass.theme")]).apply(Settings())
    assert conf.read_text() == "their own theme\n"


def test_an_old_file_the_user_changed_since_stays(fake_env):
    old, new = old_and_new(fake_env)
    Engine(fake_env, [Writes(old, content="/* Liquid Glass */")]).apply(Settings())
    old.write_text("/* edited by hand */")
    Engine(fake_env, [Writes(new)]).apply(Settings())
    assert old.read_text() == "/* edited by hand */"
    assert str(old) not in Backup(fake_env).data["files"]
    Engine(fake_env, [Writes(new)]).revert()
    assert old.read_text() == "/* edited by hand */"


def test_a_target_that_fails_keeps_its_old_files(fake_env):
    old, new = old_and_new(fake_env)
    Engine(fake_env, [Writes(old, content="/* Liquid Glass */")]).apply(Settings())
    new.parent.mkdir(parents=True)
    new.mkdir()                       # a folder where the file should go: the write fails
    [r] = Engine(fake_env, [Writes(new)]).apply(Settings())
    assert r.status == "failed" and old.is_file()


def test_files_from_before_the_rename_are_still_ours(fake_env, tmp_path):
    f = tmp_path / "gtk.css"
    f.write_text("/* Liquid Glass for GTK 4 and libadwaita. Generated, edits are overwritten. */\n")
    assert Backup.is_ours(f, {})
    f.write_text("/* Fedora Glass for GTK 4 and libadwaita. Generated, edits are overwritten. */\n")
    assert Backup.is_ours(f, {})
    f.write_text("/* someone else */\n")
    assert not Backup.is_ours(f, {})


def test_only_old_theme_names_count_as_old(fake_env):
    d, c = fake_env.data, fake_env.config
    assert is_legacy(d / "themes/LiquidGlass/gnome-shell/gnome-shell.css")
    assert is_legacy(c / "Kvantum/LiquidGlass/LiquidGlass.svg")
    assert is_legacy(d / "org.gnome.Ptyxis/palettes/Liquid Glass.palette")
    assert is_legacy(fake_env.home / "Notes/.obsidian/themes/Liquid Glass/theme.css")
    assert is_legacy(c / "micro/colorschemes/liquid-glass.micro")
    # Names that did not change: config, state, the extension, Discord's theme file.
    for kept in (c / "liquid-glass/settings.json", d / "liquid-glass/vscode/liquid-glass.vsix",
                 d / "gnome-shell/extensions/liquid-glass@djshiye.github.io/extension.js",
                 c / "vesktop/themes/liquid-glass.theme.css", c / "btop/btop.conf"):
        assert not is_legacy(kept)


def test_shell_theme_moves_to_the_new_name(fake_env, monkeypatch):
    seeded_env(fake_env)
    before = {k: dict(v) for k, v in fake_env.gs.items()}
    monkeypatch.setattr(ts, "THEME_NAME", "LiquidGlass")       # what 1.4.4 did
    Engine(fake_env, ts.TARGETS).apply(Settings())
    old = fake_env.data / "themes/LiquidGlass/gnome-shell/gnome-shell.css"
    assert old.is_file()
    monkeypatch.undo()
    seeded_schema = ("org.gnome.shell.extensions.user-theme", None)
    Engine(fake_env, ts.TARGETS).apply(Settings())
    assert fake_env.gs[seeded_schema]["name"] == "'FedoraGlass'"
    assert (fake_env.data / "themes/FedoraGlass/gnome-shell/gnome-shell.css").is_file()
    assert not old.exists()
    assert Engine(fake_env, ts.TARGETS).revert() == []
    assert {k: dict(v) for k, v in fake_env.gs.items()} == before
    assert not (fake_env.data / "themes").exists() or not any((fake_env.data / "themes").rglob("*.css"))


def test_package_moves_old_installs_over():
    spec = (Path(__file__).resolve().parents[1] / "packaging/fedora-glass.spec").read_text()
    assert "Name:           fedora-glass" in spec
    assert "%global fg_evr  %{version}-%{release}" in spec
    assert "Obsoletes:      liquid-glass < %{fg_evr}" in spec
    assert "Provides:       liquid-glass = %{fg_evr}" in spec
    assert "%triggerpostun -- liquid-glass < %{fg_evr}" in spec
    # The bridge package sorts after every older liquid-glass and before fedora-glass.
    assert "%package -n liquid-glass" in spec and "Release:        0%{?dist}" in spec
    repo = (Path(__file__).resolve().parents[1] / "packaging/fedora-glass.repo").read_text()
    assert "includepkgs=fedora-glass\n" in repo and "gpgcheck=0" in repo


def test_extension_shows_the_new_name():
    root = Path(__file__).resolve().parents[1]
    meta = json.loads((root / "fedoraglass/data/extension/liquid-glass@djshiye.github.io/metadata.json").read_text())
    assert meta["name"] == "Fedora Glass" and "Liquid Glass" not in meta["description"]
