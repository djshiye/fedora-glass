"""Removing the app: `fedora-glass on-remove` (run by dnf remove as each person) and the
script that runs it. Nothing on the machine is touched."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.base import Context, Target, WriteFile

ROOT = Path(__file__).resolve().parent.parent


class FileTarget(Target):
    def plan(self, ctx: Context):
        return [WriteFile(ctx.env.config / "gtk-4.0/gtk.css", "/* Fedora Glass */")]


@pytest.fixture
def applied(fake_env, monkeypatch):
    eng = Engine(fake_env, [FileTarget(id="t", name="Test")])
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    eng.apply(Settings())
    assert eng.is_applied()
    return eng


def test_undo_on_remove_is_on_by_default_and_saved(fake_env):
    assert Settings().undo_on_remove is True
    s = settings_mod.load()
    s.undo_on_remove = False
    settings_mod.save(s)
    assert settings_mod.load().undo_on_remove is False


def test_on_remove_restores_the_original_look(applied, fake_env, capsys):
    assert cli.main(["on-remove"]) == 0
    assert not applied.is_applied()
    assert not (fake_env.config / "gtk-4.0/gtk.css").exists()
    assert "original look is back" in capsys.readouterr().out


def test_on_remove_keeps_the_look_when_turned_off(applied, fake_env, capsys):
    s = settings_mod.load()
    s.undo_on_remove = False
    settings_mod.save(s)
    assert cli.main(["on-remove"]) == 0
    assert applied.is_applied()
    assert (fake_env.config / "gtk-4.0/gtk.css").exists()
    assert "stays as it is" in capsys.readouterr().out


def test_on_remove_does_nothing_when_nothing_is_applied(fake_env, monkeypatch, capsys):
    eng = Engine(fake_env, [FileTarget(id="t", name="Test")])
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    assert cli.main(["on-remove"]) == 0
    assert capsys.readouterr().out == ""


def test_undo_for_users_runs_on_remove_as_each_person_with_a_backup(tmp_path):
    """The dnf script picks people (not system users) with a Fedora Glass backup and runs
    the app as them; stand-ins for getent, runuser and the app record what it does."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    homes = {"dino": (1000, True), "sam": (1001, False), "daemon": (2, True), "nobody": (65534, True)}
    lines = []
    for name, (uid, has_backup) in homes.items():
        h = tmp_path / "home" / name
        if has_backup:
            (h / ".local/state/liquid-glass/backup").mkdir(parents=True)
            (h / ".local/state/liquid-glass/backup/manifest.json").write_text("{}")
        lines.append(f"{name}:x:{uid}:{uid}::{h}:/bin/bash")
    log = tmp_path / "log"
    (bin_ / "getent").write_text("#!/bin/sh\ncat <<'X'\n" + "\n".join(lines) + "\nX\n")
    (bin_ / "runuser").write_text(f"#!/bin/sh\necho \"runuser $*\" >> {log}\n")
    (bin_ / "dbus-run-session").write_text("#!/bin/sh\nexit 0\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    script = (ROOT / "packaging/undo-for-users.sh").read_text()
    # Point the script at the stand-ins: its own PATH and the app's fixed path.
    script = script.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={bin_}:/usr/bin:/bin") \
                   .replace("app=/usr/bin/fedora-glass", f"app={bin_}/getent")
    run = tmp_path / "undo.sh"
    run.write_text(script)
    out = subprocess.run(["sh", str(run)], capture_output=True, text=True, timeout=30,
                         env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    assert out.returncode == 0
    calls = log.read_text().splitlines()
    assert len(calls) == 1 and calls[0].startswith("runuser -u dino -- env -i HOME=")
    assert "dbus-run-session" in calls[0] and calls[0].endswith("on-remove")
    assert "checking the look for dino" in out.stdout


def test_spec_runs_it_only_on_removal():
    spec = (ROOT / "packaging/fedora-glass.spec").read_text()
    preun = spec.split("%preun\n", 1)[1].split("\n%", 1)[0]
    assert "if [ $1 -eq 0 ]; then\n    %{_libexecdir}/fedora-glass-undo-for-users || :" in preun
    bridge = spec.split("%preun -n liquid-glass\n", 1)[1].split("\n%", 1)[0]
    assert "undo-for-users" not in bridge     # replacing the old package must not undo the look
