"""Removing the app: `fedora-glass on-remove` (run by dnf remove as each person) and the
script that runs it. Nothing on the machine is touched."""

from __future__ import annotations

import os
import re
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
    (bin_ / "runuser").write_text("#!/bin/sh\n"
                                  # reading their environment.d files (as them): run, don't log
                                  "case $4 in cat|sh|test) shift 3; exec \"$@\" ;; esac\n"
                                  f"echo \"runuser $*\" >> {log}\n"
                                  # its session and input, to see it is apart from root's terminal
                                  f"cut -d' ' -f6 /proc/$$/stat > {tmp_path}/sid\n"
                                  f"readlink /proc/$$/fd/0 > {tmp_path}/stdin\n")
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
    # Its own session, with no terminal to type into, and nothing to read.
    assert int((tmp_path / "sid").read_text()) != os.getsid(0)
    assert (tmp_path / "stdin").read_text().strip() == "/dev/null"


def _undo_with_env_d(tmp_path, conf, backup_at):
    """One person whose environment.d holds `conf` (with @HOME@ for their home) and whose
    backup is at `backup_at` (under their home); returns the runuser calls."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    home = tmp_path / "home" / "dino"
    (home / ".config/environment.d").mkdir(parents=True)
    for name, text in conf.items():
        (home / ".config/environment.d" / name).write_text(text.replace("@HOME@", str(home)))
    (home / backup_at / "liquid-glass/backup").mkdir(parents=True)
    (home / backup_at / "liquid-glass/backup/manifest.json").write_text("{}")
    log = tmp_path / "log"
    (bin_ / "getent").write_text(f"#!/bin/sh\necho 'dino:x:1000:1000::{home}:/bin/bash'\n")
    (bin_ / "runuser").write_text("#!/bin/sh\n"
                                  "case $4 in cat|sh|test) shift 3; exec \"$@\" ;; esac\n"
                                  f"echo \"runuser $*\" >> {log}\n")
    (bin_ / "dbus-run-session").write_text("#!/bin/sh\nexit 0\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    script = (ROOT / "packaging/undo-for-users.sh").read_text()
    script = script.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={bin_}:/usr/bin:/bin") \
                   .replace("app=/usr/bin/fedora-glass", f"app={bin_}/getent")
    run = tmp_path / "undo.sh"
    run.write_text(script)
    out = subprocess.run(["sh", str(run)], capture_output=True, text=True, timeout=30,
                         env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    assert out.returncode == 0
    return home, (log.read_text().splitlines() if log.exists() else [])


def test_undo_for_users_follows_xdg_folders_set_in_environment_d(tmp_path):
    """Someone who moved XDG_STATE_HOME in ~/.config/environment.d keeps the backup there:
    the app is run for them with that folder (and the other three when set), and only
    $HOME is expanded."""
    home, calls = _undo_with_env_d(tmp_path, {
        "10-xdg.conf": "# mine\nXDG_STATE_HOME=@HOME@/old\nXDG_STATE_HOME=$HOME/st ate\n"
                       "XDG_CONFIG_HOME=${HOME}/cfg\nXDG_CACHE_HOME=/var/tmp/cache\n",
        "20-more.conf": "XDG_DATA_HOME=$HOME/data\nOTHER=/x\n",
        "readme.txt": "XDG_DATA_HOME=/not/a/conf/file\n",
    }, "st ate")
    assert len(calls) == 1
    c = calls[0]
    assert f"XDG_STATE_HOME={home}/st ate " in c and f"XDG_CONFIG_HOME={home}/cfg " in c
    assert "XDG_CACHE_HOME=/var/tmp/cache " in c and f"XDG_DATA_HOME={home}/data " in c
    assert c.endswith("on-remove")


def test_undo_for_users_ignores_what_it_cannot_trust_in_environment_d(tmp_path):
    """Other variables, a $ that is not $HOME, backticks, a relative path: ignored, and
    nothing in the files is ever run."""
    marker = tmp_path / "ran"
    home, calls = _undo_with_env_d(tmp_path, {
        "10-bad.conf": f"XDG_STATE_HOME=$(touch {marker})\nXDG_CONFIG_HOME=$HOMEDIR/x\n"
                       f"XDG_CACHE_HOME=`touch {marker}`\nXDG_DATA_HOME=relative/dir\n"
                       "XDG_STATE_HOME=$OTHER/state\nexport XDG_CONFIG_HOME=/ignored\n",
    }, ".local/state")
    assert not marker.exists()
    assert len(calls) == 1 and "XDG_" not in calls[0].split("--", 1)[1].replace("XDG_RUNTIME_DIR", "")


def test_undo_for_users_still_uses_the_default_folder_when_the_backup_is_there(tmp_path):
    """XDG_STATE_HOME points somewhere with no backup, the backup is in the default place:
    the app is run without the moved folders, as it would look in the default place."""
    _, calls = _undo_with_env_d(tmp_path, {"10.conf": "XDG_STATE_HOME=/nowhere/state\n"}, ".local/state")
    assert len(calls) == 1 and "XDG_STATE_HOME" not in calls[0]


def test_undo_for_users_skips_people_with_no_backup_where_the_app_looks(tmp_path):
    _, calls = _undo_with_env_d(tmp_path, {"10.conf": "XDG_STATE_HOME=@HOME@/moved\n"}, "elsewhere")
    assert calls == []


def test_undo_for_users_is_detached_from_roots_terminal():
    """Every run as a person goes through setsid, with input from /dev/null: a process of
    theirs could otherwise push keystrokes into root's terminal (TIOCSTI)."""
    script = (ROOT / "packaging/undo-for-users.sh").read_text()
    runs = [l for l in script.splitlines() if "runuser -u" in l and '-- "$@"' not in l]
    assert len(runs) == 2
    assert all(l.strip().startswith("setsid -w timeout 120 runuser -u") for l in runs)
    # Reading their environment.d files is as them too, never as root.
    assert 'setsid -w timeout 10 runuser -u "$name" -- "$@"' in script
    assert script.count('on-remove </dev/null') == 2
    assert "for tool in runuser setsid" in script


def _stop_watchers(tmp_path, units, systemd=True):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "log"
    (bin_ / "systemctl").write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = list-units ]; then printf '%s\\n' {' '.join(repr(u) for u in units)}; exit 0; fi\n"
        f"echo \"systemctl $* sid=$(cut -d' ' -f6 /proc/$$/stat) in=$(readlink /proc/$$/fd/0)\" >> {log}\n")
    (bin_ / "systemctl").chmod(0o755)
    if systemd:
        (tmp_path / "systemd").mkdir()
    script = (ROOT / "packaging/stop-watchers.sh").read_text()
    script = script.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={bin_}:/usr/bin:/bin") \
                   .replace("[ -d /run/systemd/system ]", f"[ -d {tmp_path}/systemd ]")
    run = tmp_path / "stop.sh"
    run.write_text(script)
    out = subprocess.run(["sh", str(run)], capture_output=True, text=True, timeout=30,
                         env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    return out, (log.read_text().splitlines() if log.exists() else [])


def test_removal_stops_the_watcher_in_running_sessions(tmp_path):
    """Ubuntu and Arch: the watcher is stopped in each logged-in person's session, through
    their own service manager (as the rpm's %systemd_user_preun does), detached from
    root's terminal; anything that isn't a user@UID unit is skipped."""
    out, calls = _stop_watchers(tmp_path, ["user@1000.service loaded active running User Manager for UID 1000",
                                           "  user@1001.service loaded active running User Manager for UID 1001",
                                           "user@x;rm.service loaded active running nope"])
    assert out.returncode == 0
    assert [c.split(" sid=")[0] for c in calls] == [
        "systemctl --user -M 1000@ stop liquid-glass-watch.service",
        "systemctl --user -M 1001@ stop liquid-glass-watch.service"]
    for c in calls:
        assert int(c.split(" sid=")[1].split()[0]) != os.getsid(0) and c.endswith("in=/dev/null")


def test_stopping_watchers_is_skipped_without_systemd(tmp_path):
    """A container or chroot with no systemd running: nothing to stop, and no error."""
    out, calls = _stop_watchers(tmp_path, ["user@1000.service loaded active running x"], systemd=False)
    assert out.returncode == 0 and calls == []


def test_deb_and_arch_stop_the_watcher_before_undoing():
    """The watcher must be off before the look is put back, or it could re-apply it."""
    tree = (ROOT / "packaging/install-tree.sh").read_text()
    assert '"$src/packaging/stop-watchers.sh" "$dest/usr/libexec/fedora-glass-stop-watchers"' in tree
    for script in (ROOT / "packaging/deb/prerm", ROOT / "packaging/arch/fedora-glass.install"):
        s = script.read_text()
        steps = [s.index(x) for x in ("systemctl --global disable liquid-glass-watch.service",
                                      "/usr/libexec/fedora-glass-stop-watchers || :",
                                      "/usr/libexec/fedora-glass-undo-for-users || :")]
        assert steps == sorted(steps), script
    # Only on removal, never on an upgrade.
    assert (ROOT / "packaging/deb/prerm").read_text().count('if [ "$1" = remove ]; then') == 1
    assert "pre_upgrade" not in (ROOT / "packaging/arch/fedora-glass.install").read_text()


def test_spec_runs_it_only_on_removal():
    spec = (ROOT / "packaging/fedora-glass.spec").read_text()
    # The removal steps are one macro, written out where it is used.
    m = re.search(r"^%define fg_remove_steps \\\n(.*?)^%\{nil\}\n", spec, re.M | re.S)
    steps = "\n".join(re.sub(r" \\$", "", x) for x in m.group(1).splitlines())
    spec = spec.replace("%{fg_remove_steps}", steps)
    preun = spec.split("%preun\n", 1)[1].split("\n%postun\n", 1)[0]
    assert "if [ $1 -eq 0 ]; then\n%{_libexecdir}/fedora-glass-undo-for-users || :" in preun
    bridge = spec.split("%preun -n liquid-glass\n", 1)[1].split("\n%postun -n liquid-glass\n", 1)[0]
    # replacing the old package must not undo the look: only a removal with no fedora-glass file there does
    assert ("if [ $1 -eq 0 ] && [ ! -e %{_prefix}/lib/fedora-glass/main-package ]; then\n"
            "%{_libexecdir}/fedora-glass-undo-for-users || :") in bridge
    # The rpm's macro disables the watcher and stops it in running sessions, before the undo.
    assert preun.index("%systemd_user_preun liquid-glass-watch.service") < preun.index("undo-for-users")
    # undo-for-users needs setsid (both packages).
    assert spec.count("Requires:       /usr/bin/setsid\n") == 2


def test_undo_for_users_reads_quoted_values_in_environment_d(tmp_path):
    """environment.d allows quotes around a value. Up to 1.7.8 a quoted XDG_STATE_HOME read as
    nothing, the backup was looked for in the default place only, and that person's look
    stayed behind after the package was removed."""
    home, calls = _undo_with_env_d(tmp_path, {
        "10.conf": "XDG_STATE_HOME=\"$HOME/st\"\nXDG_CONFIG_HOME='@HOME@/cfg'\n"}, "st")
    assert len(calls) == 1
    assert f"XDG_STATE_HOME={home}/st " in calls[0] and f"XDG_CONFIG_HOME={home}/cfg " in calls[0]
    # A quote on one side only is not a quoted value: not trusted, the default place is used.
    other = tmp_path / "b"
    other.mkdir()
    _, calls = _undo_with_env_d(other, {"10.conf": "XDG_STATE_HOME=\"@HOME@/st\n"}, ".local/state")
    assert len(calls) == 1 and "XDG_STATE_HOME" not in calls[0]


def test_undo_for_users_covers_systemd_homed_people():
    """systemd-homed gives its people the ids 60001 to 60513; up to 1.7.8 everyone from 60000 up
    was passed over as a system user."""
    script = (ROOT / "packaging/undo-for-users.sh").read_text()
    assert '[ "$uid" -ge 60001 ] && [ "$uid" -le 60513 ]' in script
