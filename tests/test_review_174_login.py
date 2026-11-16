"""Fixes after the 1.7.4 review: the login screen helper and its packaging (L2 to L6)."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from fedoraglass import login_glass as lg
from fedoraglass import login_screen as ls

ROOT = Path(__file__).resolve().parent.parent
UNIT = lg.GUARD_UNIT


def _tree(tmp_path, wants_target=f"../{UNIT}", unit_file=True):
    r = tmp_path / "root"
    (r / "usr/lib/systemd/system/graphical.target.wants").mkdir(parents=True)
    (r / "etc/systemd/system").mkdir(parents=True)
    (r / "run/systemd/system").mkdir(parents=True)
    if unit_file:
        (r / "usr/lib/systemd/system" / UNIT).write_text("[Unit]\n")
    os.symlink(wants_target, r / "usr/lib/systemd/system/graphical.target.wants" / UNIT)
    return r


# ---- L2: the boot guard counts only when it can start -------------------------------------

def test_guard_enabled_when_the_package_link_leads_to_the_unit(tmp_path):
    assert lg.guard_enabled(lg.Paths(str(_tree(tmp_path)))) is True


@pytest.mark.parametrize("where", ["etc", "run"])
def test_guard_not_enabled_when_the_unit_is_masked(tmp_path, where):
    r = _tree(tmp_path)
    os.symlink("/dev/null", r / where / "systemd/system" / UNIT)
    assert lg.guard_enabled(lg.Paths(str(r))) is False


def test_guard_not_enabled_when_an_empty_unit_file_masks_it(tmp_path):
    r = _tree(tmp_path)
    (r / "etc/systemd/system" / UNIT).write_text("")
    assert lg.guard_enabled(lg.Paths(str(r))) is False
    (r / "etc/systemd/system" / UNIT).write_text("[Unit]\n")     # an override with something in it is not a mask
    assert lg.guard_enabled(lg.Paths(str(r))) is True


def test_guard_not_enabled_when_the_link_leads_nowhere(tmp_path):
    r = _tree(tmp_path, unit_file=False)
    assert lg.guard_enabled(lg.Paths(str(r))) is False
    r2 = _tree(tmp_path / "abs", wants_target=f"/usr/lib/systemd/system/{UNIT}", unit_file=False)
    assert lg.guard_enabled(lg.Paths(str(r2))) is False


def test_guard_enabled_with_an_absolute_link_read_inside_the_same_tree(tmp_path):
    r = _tree(tmp_path, wants_target=f"/usr/lib/systemd/system/{UNIT}")
    assert lg.guard_enabled(lg.Paths(str(r))) is True


def test_turn_on_refuses_when_the_guard_is_masked(tmp_path, monkeypatch):
    """The 'no guard' outcome (exit 4) is what turn_on gives; the rest of the system is
    taken as fine so only the guard decides."""
    r = _tree(tmp_path)
    os.symlink("/dev/null", r / "etc/systemd/system" / UNIT)
    (r / "var/lib").mkdir(parents=True)
    p = lg.Paths(str(r))
    monkeypatch.setattr(lg, "assess", lambda *a: type("A", (), {"ok": True, "why": ""})())
    code, msg = lg.turn_on(p, dict(lg.DEFAULTS), None)
    assert code == 4 and "boot guard" in msg


# ---- L4: refresh leaves no empty state folder ---------------------------------------------

def test_refresh_on_a_missing_state_folder_is_off_and_creates_nothing(tmp_path):
    state = tmp_path / "var-lib" / "liquid-glass"
    assert ls.refresh(str(tmp_path / "shell"), str(state)) == "off"
    assert not state.exists() and not state.parent.exists()


# ---- L5: a huge whole number is bad input, not a crash ------------------------------------

@pytest.mark.parametrize("key", ["frost", "dim", "tint_amount"])
def test_a_huge_integer_is_bad_input(key):
    with pytest.raises(lg.BadInput):
        lg.parse_values('{"%s": 1%s}' % (key, "0" * 400))
    with pytest.raises(lg.BadInput):
        lg.parse_values('{"%s": -1%s}' % (key, "0" * 400))


# ---- L3: undo-for-users looks into homes only as the person -------------------------------

def _run_undo(tmp_path, home_for_script, translate=None):
    """Runs the script for one person; runuser is a stand-in that logs every call and, for
    a look at a path, maps `home_for_script` to the real folder (so root itself cannot
    see that home, as with an NFS home under root_squash)."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    log = tmp_path / "log"
    (bin_ / "getent").write_text(f"#!/bin/sh\necho 'dino:x:1000:1000::{home_for_script}:/bin/bash'\n")
    fix = ""
    if translate:
        fix = f"for a; do set -- \"$@\" \"$(printf %s \"$a\" | sed 's|{translate[0]}|{translate[1]}|g')\"; shift; done\n"
    (bin_ / "runuser").write_text("#!/bin/sh\n"
                                  f"echo \"runuser $*\" >> {log}\n"
                                  f"case $4 in cat|sh|test)\n shift 3\n{fix} exec \"$@\" ;; esac\n")
    (bin_ / "timeout").write_text(f"#!/bin/sh\necho \"timeout $1\" >> {log}\nshift\nexec \"$@\"\n")
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
    return out, log.read_text().splitlines()


def test_undo_for_users_never_tests_a_path_under_a_home_as_root(tmp_path):
    script = (ROOT / "packaging/undo-for-users.sh").read_text()
    code = "\n".join(l for l in script.splitlines() if not l.lstrip().startswith("#"))
    assert not re.search(r"\[ -[a-z] [^\]]*\$(\{)?(home|xs|xc|xk|xd)", code), "a test of a user's path runs as root"
    assert "ls " not in code and 'for f in "$home' not in code


def test_undo_for_users_looks_into_a_home_root_cannot_see(tmp_path):
    """Root cannot see /virtual/dino at all; the person (the stand-in maps it) can: the
    environment.d files and the backup are still found, and every look is a runuser run
    under a time limit."""
    home = tmp_path / "real" / "dino"
    (home / ".config/environment.d").mkdir(parents=True)
    (home / ".config/environment.d/10.conf").write_text("XDG_STATE_HOME=$HOME/moved\n")
    (home / "moved/liquid-glass/backup").mkdir(parents=True)
    (home / "moved/liquid-glass/backup/manifest.json").write_text("{}")
    assert not os.path.exists("/virtual/dino")
    out, calls = _run_undo(tmp_path, "/virtual/dino", ("/virtual", str(tmp_path / "real")))
    looks = [c for c in calls if c.startswith("runuser -u dino -- ") and (" test -f " in c or " sh -c " in c)]
    assert len(looks) == 2 and looks[1].endswith("/virtual/dino/moved/liquid-glass/backup/manifest.json")
    assert "checking the look for dino" in out.stdout
    assert any("on-remove" in c for c in calls)
    assert calls.count("timeout 10") >= 2          # each look has a time limit


def test_undo_for_users_skips_a_person_whose_home_cannot_be_looked_into(tmp_path):
    """The look fails or finds nothing (a hung or empty home): nobody is touched, no error."""
    out, calls = _run_undo(tmp_path, "/virtual/dino")
    assert not any("on-remove" in c for c in calls) and "checking" not in out.stdout


# ---- L6: SECURITY.md names every part that runs as root ----------------------------------

def test_security_md_names_all_the_parts_that_run_as_root():
    text = (ROOT / "SECURITY.md").read_text()
    for part in ("login_screen.py", "login_glass.py", "fedora-glass-login", "boot guard",
                 "undo-for-users.sh", "package scripts"):
        assert part in text
