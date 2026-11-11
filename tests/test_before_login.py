"""An update installed while logged out (GNOME Software's "Restart & Update") must not need
a second restart: before GNOME Shell starts, the glass extension in the home folder is
brought up to the new version, and the watcher still updates the other parts after login."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from fedoraglass import __main__ as cli
from fedoraglass import __version__
from fedoraglass import settings as settings_mod
from fedoraglass.engine import applied_version_path
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from test_update_after_upgrade import _age, _meta
from test_wait_for_glass import desktop

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
UNIT = "fedora-glass-before-login.service"


def _applied_old(fake_env, settings=None):
    engine = desktop(fake_env)
    mine = settings or Settings(frost=0.7, overview_off=True)
    settings_mod.save(mine)
    engine.apply(mine)
    _age(fake_env, "1.5.23")
    fake_env.glass_loaded = False          # before login: no GNOME Shell to ask
    return engine


def test_the_glass_is_updated_before_the_shell_starts(fake_env):
    engine = _applied_old(fake_env)
    gtk_before = {p: p.read_bytes() for p in (fake_env.config / "gtk-4.0").glob("*.css")}
    assert cli.update_glass_before_login(engine) is True
    assert cli.installed_glass_version(engine) == __version__
    assert (_meta(fake_env).parent / "extension.js").read_text() != "// old\n"
    cfg = json.loads(ts.GlassEffects().config_path(fake_env).read_text())
    assert cfg, "the glass config is written by this version too"
    # Only the glass: the rest waits for the watcher, with the Shell running.
    assert {p: p.read_bytes() for p in (fake_env.config / "gtk-4.0").glob("*.css")} == gtk_before
    assert applied_version_path(fake_env).read_text().strip() == "1.5.23", "no stamp: the other parts still need it"


def test_after_it_the_watcher_still_updates_the_other_parts(fake_env):
    engine = _applied_old(fake_env)
    assert cli.update_glass_before_login(engine) is True
    fake_env.glass_loaded = True           # logged in: the Shell runs the new glass
    assert cli.update_after_upgrade(engine) is True
    assert applied_version_path(fake_env).read_text().strip() == __version__
    assert cli.update_after_upgrade(engine) is False, "and only once"


def test_nothing_happens_when_up_to_date_restored_or_glass_off(fake_env):
    engine = desktop(fake_env)
    assert cli.update_glass_before_login(engine) is False          # never applied
    settings_mod.save(Settings())
    engine.apply(Settings())
    assert cli.update_glass_before_login(engine) is False          # same version
    _age(fake_env, "1.5.23")
    engine.revert()
    assert cli.update_glass_before_login(engine) is False          # Restore original


def test_the_glass_part_turned_off_is_left_alone(fake_env):
    engine = _applied_old(fake_env)
    settings_mod.save(Settings(targets={"glass": False}))
    assert cli.update_glass_before_login(engine) is False
    assert cli.installed_glass_version(engine) == "1.5.23"


def test_a_damaged_settings_file_changes_nothing(fake_env):
    engine = _applied_old(fake_env)
    settings_mod.settings_path().write_text('{"frost": 0.')
    assert cli.update_glass_before_login(engine) is False
    assert cli.installed_glass_version(engine) == "1.5.23"


def test_the_command_never_fails_the_login(monkeypatch):
    def broken():
        raise OSError("disk full")
    monkeypatch.setattr(cli, "_engine", broken)
    assert cli.main(["before-login"]) == 0


def _unit(text: str) -> str:
    m = re.search(r"fedora-glass-before-login\.service\"? <<'UNIT'\n(.*?)\nUNIT\n", text, re.S)
    assert m, "the unit is written"
    return m.group(1)


def test_the_packages_ship_the_same_unit_before_gnomes_session():
    spec, tree = (PKG / "fedora-glass.spec").read_text(), (PKG / "install-tree.sh").read_text()
    unit = _unit(tree)
    assert _unit(spec) == unit, "rpm, deb and Arch run the same step"
    assert "Before=gnome-session-pre.target" in unit and "Type=oneshot" in unit
    assert "ExecStart=/usr/bin/fedora-glass before-login" in unit
    assert "TimeoutStartSec=" in unit, "a stuck step can't hold the login for long"
    assert "[Install]" not in unit, "pulled in by the shipped link, so upgrades get it without enabling"
    link = "gnome-session-pre.target.wants/fedora-glass-before-login.service"
    assert f"%{{_userunitdir}}/{link}" in spec and f"usr/lib/systemd/user/{link}" in tree
    for files in spec.split("%files")[1:]:
        assert f"%{{_userunitdir}}/{UNIT}" in files and f"%{{_userunitdir}}/{link}" in files


def test_the_package_tree_has_the_link(tmp_path):
    subprocess.run(["sh", str(PKG / "install-tree.sh"), str(ROOT), str(tmp_path)], check=True,
                   capture_output=True)
    units = tmp_path / "usr/lib/systemd/user"
    link = units / "gnome-session-pre.target.wants" / UNIT
    assert link.is_symlink() and link.resolve() == (units / UNIT).resolve()
    assert (units / UNIT).read_text().startswith("[Unit]\n")
