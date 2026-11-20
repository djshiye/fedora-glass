"""Logic breaks of the glass login screen, found on purpose and kept as regression tests.

A power cut or a signal can stop the root helpers between any two steps. These tests stop
them at every step that changes a file (or at a chosen one), then boot, turn off and turn
on again, and check that the login screen goes back to stock GNOME and that nothing of
ours is left behind in /etc/dconf, /etc/fedora-glass, /usr/share/gnome-shell or root's
state folders.

The systems are the ones tests/test_login_glass.py builds. Where the real dconf is not
installed, a small stand-in does its `compile` and `read` (keyfiles in name order, later
files win; a lock in a lower db hides the dbs above it; hidden files are skipped), so these
run everywhere; in CI the real dconf is used.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from fedoraglass import login_glass as lg
from fedoraglass import login_screen as ls
from tests import test_login_glass as tl
from tests.test_login_glass import BOOT_A, BOOT_B, JPEG, PROFILES, UUID, effective, make_system, on, snapshot

BOOT_C = "3c3c3c3c-1111-4222-8333-444455556666"

FAKE_DCONF = r'''
import json, os, re, sys

MAGIC = b"FAKEDCONF\n"


def value(text):
    t = text.strip()
    if t.startswith("@as "):
        t = t[4:].strip()
        if not t.startswith("["):
            raise ValueError(t)
    if t in ("true", "false") or re.fullmatch(r"-?\d+(\.\d+)?", t):
        return t
    if t[:1] in ("'", '"'):
        q, i, out = t[0], 1, ""
        while i < len(t):
            if t[i] == "\\":
                out += t[i + 1]
                i += 2
                continue
            if t[i] == q:
                if t[i + 1:].strip():
                    raise ValueError(t)
                return "'" + out.replace("\\", "\\\\").replace("'", "\\'") + "'"
            out += t[i]
            i += 1
        raise ValueError(t)
    if t.startswith("[") and t.endswith("]"):
        inner = t[1:-1].strip()
        if not inner:
            return "@as []"
        parts, cur, q = [], "", None
        for c in inner:
            if q:
                cur += c
                q = None if c == q else q
            elif c in "'\"":
                q, cur = c, cur + c
            elif c == ",":
                parts, cur = parts + [cur], ""
            else:
                cur += c
        return "[" + ", ".join(value(p) for p in parts + [cur]) + "]"
    raise ValueError(t)


def files(folder):
    return sorted(n for n in os.listdir(folder) if not n.startswith(".") and os.path.isfile(os.path.join(folder, n)))


def compile_db(out, src):
    values, locks = {}, []
    for n in files(src):
        group = None
        for raw in open(os.path.join(src, n), encoding="utf-8"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                group = line[1:-1].strip("/")
                continue
            k, sep, v = line.partition("=")
            if not sep or group is None:
                sys.exit(f"{n}: cannot parse")
            try:
                values["/" + group + "/" + k.strip()] = value(v)
            except (ValueError, IndexError):
                sys.exit(f"{n}: bad value")
    ld = os.path.join(src, "locks")
    for n in files(ld) if os.path.isdir(ld) else []:
        locks += [x.strip() for x in open(os.path.join(ld, n), encoding="utf-8") if x.strip() and x[0] != "#"]
    with open(out, "wb") as f:
        f.write(MAGIC + json.dumps({"values": values, "locks": locks}).encode())


def load(path):
    try:
        data = open(path, "rb").read()
        return json.loads(data[len(MAGIC):]) if data.startswith(MAGIC) else {"values": {}, "locks": []}
    except (OSError, ValueError):
        return {"values": {}, "locks": []}


def read(key):
    sources = []
    for raw in open(os.environ["DCONF_PROFILE"], encoding="utf-8"):
        kind, _, v = raw.strip().partition(":")
        if kind == "file-db":
            sources.append(load(v))
        elif kind == "user-db":
            home = os.environ.get("XDG_CONFIG_HOME")
            sources.append(load(os.path.join(home, "dconf", v)) if home else {"values": {}, "locks": []})
    level = next((i for i in range(len(sources) - 1, 0, -1) if key in sources[i]["locks"]), 0)
    print(next((s["values"][key] for s in sources[level:] if key in s["values"]), ""))


a = sys.argv[1:]
if len(a) == 3 and a[0] == "compile":
    compile_db(a[1], a[2])
elif len(a) == 2 and a[0] == "read":
    read(a[1])
else:
    sys.exit("usage")
'''


@pytest.fixture(autouse=True)
def dconf(tmp_path_factory, monkeypatch):
    """The real dconf where it is installed, else the stand-in."""
    if not os.access(tl.DCONF, os.X_OK):
        fake = tmp_path_factory.mktemp("dconf") / "dconf"
        fake.write_text(f"#!{sys.executable} -I\n" + FAKE_DCONF)
        fake.chmod(0o755)
        monkeypatch.setattr(tl, "DCONF", str(fake))


def stock(root: Path) -> dict:
    """What must be as it was once everything is off: everything but GDM's own folders
    (the greeter's notes), the boot id and the add-on (a test may change it)."""
    return {k: v for k, v in snapshot(root).items()
            if not k.startswith(("var/lib/gdm", "proc/")) and "/extensions/" not in k}


def state_left(paths: lg.Paths) -> list[str]:
    return sorted(os.listdir(paths.state_dir)) if os.path.isdir(paths.state_dir) else []


# ---- a power cut ------------------------------------------------------------------------

class PowerCut(BaseException):
    """The machine is gone: nothing runs after it, not even a roll back."""


CHANGES = ("replace", "unlink", "rmdir", "mkdir", "symlink", "chmod", "fchmod", "write", "rename")


def cut_after(monkeypatch, n: int, fn) -> bool:
    """Run fn with the power cut before its (n+1)th change of a file; True when it finished."""
    count = {"n": 0}
    real = {name: getattr(os, name) for name in CHANGES}

    def gone(name):
        def f(*a, **kw):
            count["n"] += 1
            if count["n"] > n:
                raise PowerCut()
            return real[name](*a, **kw)
        return f
    for name in CHANGES:
        monkeypatch.setattr(os, name, gone(name))
    try:
        fn()
        return True
    except PowerCut:
        return False
    finally:
        for name in CHANGES:
            monkeypatch.setattr(os, name, real[name])


def test_off_finishes_after_a_power_cut_left_a_temporary_file_in_our_own_db(tmp_path):
    """Ubuntu (our own db): a power cut while a keyfile was being written left its temporary
    file in /etc/dconf/db/fedora-glass-login.d. It counted as someone else's file, so off
    kept that db and said "still there" for ever: the package removal said it could not
    switch the glass off, and `on` refused with "an earlier off is not finished"."""
    paths = make_system(tmp_path / "root", "ubuntu")
    root = Path(paths.root)
    before = stock(root)
    assert on(paths)[0] == 0
    own = root / "etc/dconf/db" / (lg.OWN_DB + ".d")
    (own / ".fedora-glass-k3x9q2a1").write_bytes(b"# Fedora Glass: the glass log")       # cut short
    (own / "locks/.fedora-glass-0m4b7c2d").write_bytes(b"")
    assert lg.turn_off(paths) == []
    assert lg.switch_gone(paths) == [] and UUID not in effective(paths)
    assert stock(root) == before
    assert on(paths)[0] == 0 and lg.turn_off(paths) == []


def test_off_takes_away_every_temporary_file_a_power_cut_left(tmp_path):
    """Fedora: temporary files of ours in GDM's db folder, its locks, /etc/dconf/db (a cut
    compile) and root's state folder all go with off; an admin's files and a link with our
    prefix stay as they are."""
    paths = make_system(tmp_path / "root", "fedora")
    root = Path(paths.root)
    admin = root / "etc/dconf/db/gdm.d/00-admin"
    admin.write_text("[org/gnome/login-screen]\ndisable-user-list=true\n")
    subprocess.run([tl.DCONF, "compile", str(root / "etc/dconf/db/gdm"), str(admin.parent)], check=True)
    link = root / "etc/dconf/db/gdm.d/.fedora-glass-link"
    link.symlink_to("/etc/passwd")
    before = stock(root)
    assert on(paths)[0] == 0
    for f in ("etc/dconf/db/gdm.d/.fedora-glass-aaaa1111", "etc/dconf/db/gdm.d/locks/.fedora-glass-bbbb2222",
              "etc/dconf/db/.fedora-glass-cccc3333"):
        (root / f).write_bytes(b"GVariant\0\0")
    Path(paths.state_dir, ".fedora-glass-dddd4444").write_bytes(b"{")
    assert lg.turn_off(paths) == []
    assert stock(root) == before
    assert os.path.islink(link) and admin.exists()
    assert state_left(paths) == [".lock"]


def test_work_folders_a_power_cut_left_are_taken_away(tmp_path, monkeypatch):
    """A power cut while `on` or the guard was reading dconf left its work folder in root's
    state folder. The next run under the lock and every off take it away, or the package
    removal could not remove that folder."""
    paths = make_system(tmp_path / "root", "fedora")
    if os.geteuid() != 0:
        # The helper only ever changes things as root, and only then works in root's state
        # folder: said to be root here, as the other tests of root's folders do.
        monkeypatch.setattr(os, "geteuid", lambda: 0)
    assert on(paths)[0] == 0
    (Path(paths.state_dir) / ".work-cutshort/run").mkdir(parents=True)
    assert on(paths, picture="glow")[0] == 0
    assert ".work-cutshort" not in state_left(paths)
    (Path(paths.state_dir) / ".work-again/run").mkdir(parents=True)
    assert lg.turn_off(paths) == []
    assert state_left(paths) == [".lock"]


@pytest.mark.parametrize("kind", ["fedora", "ubuntu"])
def test_a_power_cut_at_any_step_of_on_then_a_boot_and_off_leave_stock_gnome(tmp_path, monkeypatch, kind):
    """`on`, cut at each step in turn; boot (the guard runs if a record is there); while
    the add-on is switched on, it is on record; off then puts back every file exactly and
    leaves nothing in root's state folder; and the glass can be turned on again."""
    for n in range(300):
        root = tmp_path / f"cut{n}"
        paths = make_system(root, kind, base_exts="['a@b.c']")
        tl.reboot(paths, BOOT_B)
        before = stock(root)
        tl.reboot(paths, BOOT_A)
        done = cut_after(monkeypatch, n, lambda: on(paths))
        tl.reboot(paths, BOOT_B)
        if os.path.exists(paths.state) or os.path.exists(paths.leaving):
            lg.guard_boot(paths)
        if UUID in effective(paths):
            assert lg.read_state(paths) is not None, n
        assert lg.turn_off(paths) == [], n
        assert stock(root) == before, n
        assert state_left(paths) in ([], [".lock"]), (n, state_left(paths))
        assert on(paths)[0] == 0 and lg.turn_off(paths) == [], n
        if done:
            break
    else:
        pytest.fail("on never finished")


# ---- a signal (systemd's timeout, a closed terminal) -----------------------------------------

def stopped_at(monkeypatch, n: int, fn, after: bool = False):
    """Run fn with a signal at its (n+1)th change of a file (before it, or right after it)."""
    count = {"n": 0}
    real = {name: getattr(os, name) for name in CHANGES}

    def signalled(name):
        def f(*a, **kw):
            count["n"] += 1
            if count["n"] == n + 1:
                if after:
                    real[name](*a, **kw)
                raise lg.Interrupted("stopped by signal 15")
            return real[name](*a, **kw)
        return f
    for name in CHANGES:
        monkeypatch.setattr(os, name, signalled(name))
    try:
        return fn()
    except lg.Interrupted:
        return None
    finally:
        for name in CHANGES:
            monkeypatch.setattr(os, name, real[name])


def test_a_signal_between_making_a_folder_and_setting_its_mode_leaves_no_folder(tmp_path, monkeypatch):
    """The folder was made, the signal came before its mode was set, and nothing knew it had
    been made: /etc/fedora-glass (and /etc/fedora-glass/login) stayed behind after a failed
    `on`, which then also said "could not undo"."""
    paths = make_system(tmp_path / "root", "fedora")
    root = Path(paths.root)
    before = snapshot(root)
    real = os.chmod

    def chmod(path, *a, **kw):
        if os.path.abspath(str(path)) == paths.conf_dir:
            raise lg.Interrupted("stopped by signal 15")
        return real(path, *a, **kw)
    monkeypatch.setattr(os, "chmod", chmod)
    code, msg = on(paths)
    monkeypatch.setattr(os, "chmod", real)
    assert code == 4 and "could not undo" not in msg
    assert snapshot(root) == before


def test_a_signal_right_after_a_folder_is_taken_away_still_rolls_back(tmp_path, monkeypatch):
    """A route move (our own db to GDM's) takes our own db's folders away. A signal right
    after one went, before its undo was noted, left the roll back unable to put our files
    back ("could not undo"), with half of the old switch left."""
    paths = make_system(tmp_path / "root", "ubuntu")
    root = Path(paths.root)
    assert on(paths)[0] == 0
    (root / "usr/share/dconf/profile/gdm").write_text(PROFILES["fedora"].replace("/usr/share/gdm", "/var/lib/gdm3"))
    (root / "etc/dconf/db/gdm.d/locks").mkdir(parents=True)
    before, st = snapshot(root), Path(paths.state).read_bytes()
    real = os.rmdir
    own = os.path.join(paths.db_dir, lg.OWN_DB + ".d")

    def rmdir(path, *a, **kw):
        real(path, *a, **kw)
        if os.path.abspath(str(path)) == own:
            monkeypatch.setattr(os, "rmdir", real)
            raise lg.Interrupted("stopped by signal 15")
    monkeypatch.setattr(os, "rmdir", rmdir)
    code, msg = on(paths, picture="glow")
    monkeypatch.setattr(os, "rmdir", real)
    assert code == 4 and "could not undo" not in msg
    assert snapshot(root) == before and Path(paths.state).read_bytes() == st


def test_a_signal_while_only_tidying_up_says_what_was_done(tmp_path, monkeypatch):
    """Everything was in and checked; the signal came while the work folder was being
    deleted. `on` said it failed (exit 4) while the glass was on, and the watching for the
    first login was never started."""
    paths = make_system(tmp_path / "root", "fedora")
    real = shutil.rmtree

    def rmtree(path, *a, **kw):
        if os.path.basename(str(path)).startswith(".work-"):
            monkeypatch.setattr(shutil, "rmtree", real)
            raise lg.Interrupted("stopped by signal 15")
        return real(path, *a, **kw)
    monkeypatch.setattr(shutil, "rmtree", rmtree)
    armed = []
    monkeypatch.setattr(lg, "_arm_check", lambda p: armed.append(p))
    assert on(paths) == (0, "trial")
    assert armed and UUID in effective(paths)


@pytest.mark.parametrize("kind", ["fedora", "no-gdm-db", "route-move"])
def test_a_signal_at_any_step_of_on_puts_back_exactly_what_was_there(tmp_path, monkeypatch, kind):
    for after in (False, True):
        for n in range(300):
            root = tmp_path / f"s{int(after)}-{n}"
            if kind == "no-gdm-db":
                paths = make_system(root, "fedora", gdm_db=False)
            else:
                paths = make_system(root, "ubuntu" if kind == "route-move" else "fedora", base_exts="['a@b.c']")
            if kind == "route-move":
                assert on(paths)[0] == 0
                (root / "usr/share/dconf/profile/gdm").write_text(
                    PROFILES["fedora"].replace("/usr/share/gdm", "/var/lib/gdm3"))
                (root / "etc/dconf/db/gdm.d/locks").mkdir(parents=True)
            before = snapshot(root)
            st = Path(paths.state).read_bytes() if os.path.exists(paths.state) else None
            r = stopped_at(monkeypatch, n, lambda: on(paths, picture="glow", accent="#00ff00"), after)
            if r is not None and r[0] == 0:
                break
            assert r is None or "could not undo" not in r[1], (after, n, r)
            assert snapshot(root) == before, (after, n, r)
            assert (Path(paths.state).read_bytes() if os.path.exists(paths.state) else None) == st, (after, n)
        else:
            pytest.fail("on never finished")


# ---- the painted glass of earlier versions (login_screen.py) --------------------------------

needs_glib = pytest.mark.skipif(not (shutil.which("gresource") and shutil.which("glib-compile-resources")),
                                reason="needs gresource and glib-compile-resources")


@pytest.fixture
def theme(tmp_path):
    from tests.test_login_screen import make_theme
    shell, state = tmp_path / "gnome-shell", tmp_path / "state"
    shell.mkdir()
    make_theme(shell / "gnome-shell-theme.gresource")
    return shell, state


def _gnome_files(shell: Path) -> list[str]:
    return sorted(n for n in os.listdir(shell) if n not in ("gnome-shell-theme.gresource", "src", "t.xml"))


@needs_glib
def test_undo_takes_away_a_theme_copy_a_power_cut_left_in_gnomes_folder(theme):
    """A power cut while Apply copied the new theme file in left a hidden theme-sized copy
    in /usr/share/gnome-shell, which no package ever takes away; undo (and the package
    removal) left it there for good."""
    shell, state = theme
    orig = (shell / "gnome-shell-theme.gresource").read_bytes()
    ls.apply("#3584e4", "#203050", 0.5, str(shell), str(state))
    (shell / ".liquid-glass-cut0001").write_bytes(orig[:100])
    (shell / ".liquid-glass-link").symlink_to("/etc/passwd")
    assert ls.undo(str(shell), str(state)) == "the normal login screen is back"
    assert _gnome_files(shell) == [".liquid-glass-link"]          # a link is never ours to delete
    assert (shell / "gnome-shell-theme.gresource").read_bytes() == orig


@needs_glib
@pytest.mark.parametrize("n", range(40))
def test_a_power_cut_in_apply_then_undo_leaves_gnomes_file_and_no_copy_behind(theme, monkeypatch, n):
    shell, state = theme
    orig = (shell / "gnome-shell-theme.gresource").read_bytes()
    cut_after(monkeypatch, n, lambda: ls.apply("#ff0000", "#203050", 0.2, str(shell), str(state)))
    ls.undo(str(shell), str(state))
    assert (shell / "gnome-shell-theme.gresource").read_bytes() == orig
    assert ls.status(str(shell), str(state)) == "off"
    assert _gnome_files(shell) == []
    assert (os.listdir(state) if state.exists() else []) == []


@needs_glib
def test_undo_keeps_a_saved_original_that_is_not_the_file_in_place(theme):
    """No record, and a saved original that differs from GNOME's file in place: it may be the
    only original of a glass whose record was lost, so it stays."""
    shell, state = theme
    ls.apply("#3584e4", "#203050", 0.5, str(shell), str(state))
    (state / ls.STATE).unlink()
    assert ls.undo(str(shell), str(state)) == "it was already off"
    assert (state / ls.BACKUP).exists()
