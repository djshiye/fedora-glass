"""Theme installers (Orchis, for one) often link ~/.config/gtk-4.0 into their own theme
folder. Applying must never write through such a link into the theme, and Revert must
put the link back exactly as it was."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from liquidglass.engine import Backup, Engine
from liquidglass.settings import Settings
from liquidglass.targets import gtk as tg
from liquidglass.targets.base import Target, WriteFile


def gtk4():
    return next(t for t in tg.TARGETS if t.id == "gtk4")


class WriteTo(Target):
    """A target that writes one file, for folders no real target covers on this machine."""

    def __init__(self, path: Path):
        super().__init__(id="probe", name="Probe")
        self.path = path

    def plan(self, ctx):
        return [WriteFile(self.path, "/* ours */")]


def orchis(env, sub="gtk-4.0") -> Path:
    theme = env.home / ".themes/Orchis-Dark" / sub
    (theme / "assets").mkdir(parents=True)
    (theme / "assets/check.png").write_bytes(b"png")
    (theme / "gtk.css").write_text("/* orchis */")
    (theme / "gtk-dark.css").write_text("/* orchis dark */")
    return theme


def link_config(env, sub: str, to: Path, relative: bool = False) -> Path:
    d = env.config / sub
    d.parent.mkdir(parents=True, exist_ok=True)
    d.symlink_to(os.path.relpath(to, d.parent) if relative else to)
    return d


@pytest.mark.parametrize("relative", (False, True))
def test_gtk4_never_writes_into_a_linked_theme_folder(fake_env, relative):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme, relative)
    link = os.readlink(d)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    # The theme is untouched; the config folder is a real folder holding our sheet.
    assert (theme / "gtk.css").read_text() == "/* orchis */"
    assert (theme / "gtk-dark.css").read_text() == "/* orchis dark */"
    assert not d.is_symlink() and d.is_dir()
    assert "Liquid Glass" in (d / "gtk.css").read_text()
    # What else the theme provided still resolves (assets for relative url()s).
    assert (d / "assets/check.png").read_bytes() == b"png"
    # Revert puts the very same link back.
    assert Engine(fake_env, targets=[gtk4()]).revert("gtk4") == []
    assert d.is_symlink() and os.readlink(d) == link
    assert (d / "gtk.css").read_text() == "/* orchis */"
    assert not [p for p in d.parent.iterdir() if p.name.endswith(".lg-tmp")]   # no temp folders left


@pytest.mark.parametrize("sub", ("gtk-3.0", "gtk-4.0", "Kvantum"))
def test_any_linked_config_folder_is_handled(fake_env, sub):
    theme = orchis(fake_env, sub)
    d = link_config(fake_env, sub, theme)
    probe = WriteTo(d / "gtk.css")
    Engine(fake_env, targets=[probe]).apply(Settings())
    assert (theme / "gtk.css").read_text() == "/* orchis */"
    assert (d / "gtk.css").read_text() == "/* ours */"
    assert Engine(fake_env, targets=[probe]).revert("probe") == []
    assert d.is_symlink() and (d / "gtk.css").read_text() == "/* orchis */"


def test_a_new_file_in_a_linked_folder_stays_out_of_the_theme(fake_env):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    probe = WriteTo(d / "extra/new.css")
    Engine(fake_env, targets=[probe]).apply(Settings())
    assert not (theme / "extra").exists()
    assert Engine(fake_env, targets=[probe]).revert("probe") == []
    assert d.is_symlink() and not (theme / "extra").exists()


def test_earlier_write_through_the_link_is_repaired(fake_env, monkeypatch):
    """Versions up to 1.2.1 wrote straight into the theme folder. The backup kept the
    theme's original file, so the next Apply puts it back before unlinking."""
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    monkeypatch.setattr(Backup, "linked_folder", lambda self, path: None)   # the old behaviour
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert "Liquid Glass" in (theme / "gtk.css").read_text()               # the damage
    monkeypatch.undo()
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert (theme / "gtk.css").read_text() == "/* orchis */"               # repaired
    assert (theme / "gtk-dark.css").read_text() == "/* orchis dark */"
    assert "Liquid Glass" in (d / "gtk.css").read_text()
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert d.is_symlink() and (theme / "gtk.css").read_text() == "/* orchis */"


def test_revert_on_the_old_version_alone_still_repairs_the_theme(fake_env, monkeypatch):
    theme = orchis(fake_env)
    link_config(fake_env, "gtk-4.0", theme)
    monkeypatch.setattr(Backup, "linked_folder", lambda self, path: None)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    monkeypatch.undo()
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert (theme / "gtk.css").read_text() == "/* orchis */"


def test_users_own_files_keep_the_folder(fake_env):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    (d / "mine.css").write_text("/* the user's */")
    problems = Engine(fake_env, targets=[gtk4()]).revert("gtk4")
    assert problems == ["Kept your gtk-4.0 folder because it has files you added. "
                        "Your link to Orchis-Dark was not restored."]
    assert (d / "mine.css").read_text() == "/* the user's */"
    assert (theme / "gtk.css").read_text() == "/* orchis */"


def test_linked_config_root_is_left_alone(fake_env, tmp_path):
    """~/.config itself may be a link on purpose (dotfiles); only folders below it count."""
    real = tmp_path / "dotfiles-config"
    real.mkdir()
    fake_env.config.parent.mkdir(parents=True, exist_ok=True)
    fake_env.config.symlink_to(real)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert fake_env.config.is_symlink()
    assert "Liquid Glass" in (real / "gtk-4.0/gtk.css").read_text()


def test_dry_run_changes_nothing(fake_env):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    fake_env.dry_run = True
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert d.is_symlink() and (theme / "gtk.css").read_text() == "/* orchis */"


def test_repair_leaves_a_theme_file_someone_else_changed(fake_env, monkeypatch):
    """An Orchis update reinstalls the theme after the old version wrote into it: the
    old backup must never go over the fresh file."""
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    monkeypatch.setattr(Backup, "linked_folder", lambda self, path: None)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    monkeypatch.undo()
    (theme / "gtk.css").write_text("/* orchis, updated */")          # the theme's update
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert (theme / "gtk.css").read_text() == "/* orchis, updated */"
    assert "Liquid Glass" in (d / "gtk.css").read_text()
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert d.is_symlink() and (theme / "gtk.css").read_text() == "/* orchis, updated */"


def test_folder_links_follow_the_theme(fake_env):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    (theme / "new.css").write_text("/* new */")
    (theme / "assets/check.png").unlink()
    (theme / "assets").rmdir()
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert (d / "new.css").read_text() == "/* new */"
    assert not (d / "assets").is_symlink() and not (d / "assets").exists()
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert d.is_symlink()


@pytest.mark.parametrize("swapped", (False, True))
def test_an_interrupted_swap_is_cleaned_up(fake_env, swapped):
    theme = orchis(fake_env)
    d = link_config(fake_env, "gtk-4.0", theme)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    stray = d.parent / ".gtk-4.0.x1y2z3.lg-tmp"
    if swapped:
        d.rename(stray)                # stopped after the link went, before the rename
    else:
        stray.mkdir()
        (stray / "gtk.css").symlink_to(theme / "gtk.css")
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert not stray.exists() and d.is_dir() and not d.is_symlink()
    assert "Liquid Glass" in (d / "gtk.css").read_text()
    assert (theme / "gtk.css").read_text() == "/* orchis */"     # rmtree never followed a link


def test_a_relinked_style_sheet_is_noticed(fake_env):
    """orchis-update deletes and relinks ~/.config/gtk-4.0/gtk.css; the app then offers Re-apply."""
    theme = orchis(fake_env)
    d = fake_env.config / "gtk-4.0"
    d.mkdir(parents=True)
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert Backup(fake_env).overwritten() == []
    (d / "gtk.css").unlink()
    (d / "gtk.css").symlink_to(theme / "gtk.css")
    assert Backup(fake_env).overwritten() == ["gtk4"]
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    assert Backup(fake_env).overwritten() == []


def test_revert_after_a_theme_relink_and_reapply_keeps_the_theme_link(fake_env):
    """Apply, then orchis-update relinks gtk.css, then Re-apply, then Revert: Orchis's link stays."""
    theme = orchis(fake_env)
    d = fake_env.config / "gtk-4.0"
    d.mkdir(parents=True)
    (d / "gtk.css").write_text("/* the user's own, before Liquid Glass */")
    Engine(fake_env, targets=[gtk4()]).apply(Settings())
    (d / "gtk.css").unlink()
    (d / "gtk.css").symlink_to(theme / "gtk.css")               # orchis-update
    Engine(fake_env, targets=[gtk4()]).apply(Settings())         # Re-apply
    assert "Liquid Glass" in (d / "gtk.css").read_text() and not (d / "gtk.css").is_symlink()
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert (d / "gtk.css").is_symlink() and os.readlink(d / "gtk.css") == str(theme / "gtk.css")
    assert (theme / "gtk.css").read_text() == "/* orchis */"


def test_an_unchanged_file_keeps_its_first_backup(fake_env):
    d = fake_env.config / "gtk-4.0"
    d.mkdir(parents=True)
    (d / "gtk.css").write_text("/* the user's own */")
    for _ in range(2):
        Engine(fake_env, targets=[gtk4()]).apply(Settings(frost=0.2 if _ else 0.8))
    assert Engine(fake_env, targets=[gtk4()]).revert() == []
    assert (d / "gtk.css").read_text() == "/* the user's own */"
