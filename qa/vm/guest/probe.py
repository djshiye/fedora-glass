#!/usr/bin/python3
"""What the real-boot lane asks the test VM, run inside it as root (qa/vm/login_boot.py copies it in).

Each command prints one JSON object, so the driver on the runner reads facts, not guesses:

  sessions          every logind session, with its class and type and whether its gnome-shell runs
  health            the login screen add-on's health note, read from the greeter's state folder
  write-health P    writes a note with phase P and the current token, as the greeter would have
                    left it (owned by the greeter's user), to fake a crash
  dconf-state       what the login screen's dconf profile says, and a listing of /etc/dconf
  denials           SELinux and AppArmor denials since this boot
  ours              anything of the login screen switch that is still on the disk

Standard library only: the cloud images have Python because cloud-init is written in it.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

UUID = "fedora-glass-login@djshiye.github.io"
LOOK = "/etc/fedora-glass/login/look.json"
# GDM 49 and later keep a state folder per seat in their working folder (gdm-launch-environment.c,
# setup_seat_persist_dirs): /var/lib/gdm on Fedora and Arch, /var/lib/gdm3 on Ubuntu.
WORKING_DIRS = ("/var/lib/gdm", "/var/lib/gdm3")
NOTE_DIR = "fedora-glass-login"
NOTE = "health.json"


def _run(argv, env=None) -> tuple[int, str]:
    """Exit status and output. Warnings on stderr (with times and process ids in them) are
    left out when the command worked, so two runs that saw the same thing print the same."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, f"{argv[0]}: {e}"
    return r.returncode, (r.stdout if r.returncode == 0 else r.stdout + r.stderr).strip()


# ---- sessions -------------------------------------------------------------------------------

def _shell_uids() -> set[int]:
    """The users that have a gnome-shell process running (from /proc, no pgrep needed)."""
    uids = set()
    for d in glob.glob("/proc/[0-9]*"):
        try:
            with open(f"{d}/comm") as f:
                if f.read().strip() != "gnome-shell":
                    continue
            with open(f"{d}/status") as f:
                for line in f:
                    if line.startswith("Uid:"):
                        uids.add(int(line.split()[1]))
        except OSError:
            continue
    return uids


def sessions() -> dict:
    rc, out = _run(["loginctl", "list-sessions", "--no-legend", "--no-pager"])
    ids = [line.split()[0] for line in out.splitlines() if line.strip()] if rc == 0 else []
    problem = "" if rc == 0 else out
    shells = _shell_uids()
    found = []
    for sid in ids:
        rc, props = _run(["loginctl", "show-session", sid, "--no-pager",
                          "-p", "Name", "-p", "User", "-p", "Class", "-p", "Type", "-p", "State",
                          "-p", "Active", "-p", "Seat", "-p", "Remote", "-p", "Service"])
        if rc != 0:
            continue
        p = dict(line.split("=", 1) for line in props.splitlines() if "=" in line)
        uid = int(p.get("User", "-1") or -1)
        found.append({"id": sid, "user": p.get("Name", ""), "uid": uid, "class": p.get("Class", ""),
                      "type": p.get("Type", ""), "state": p.get("State", ""), "active": p.get("Active") == "yes",
                      "seat": p.get("Seat", ""), "remote": p.get("Remote") == "yes", "service": p.get("Service", ""),
                      "gnome_shell": uid in shells})
    return {"sessions": found, "shell_uids": sorted(shells), "loginctl_error": problem}


# ---- the health note ------------------------------------------------------------------------

def _state_dirs() -> list[str]:
    """The greeter's state folders, seat0 first."""
    dirs = []
    for wd in WORKING_DIRS:
        dirs += sorted(glob.glob(f"{wd}/seat*/state"), key=lambda p: (not p.endswith("/seat0/state"), p))
    return dirs


def health() -> dict:
    dirs = _state_dirs()
    for d in dirs:
        path = os.path.join(d, NOTE_DIR, NOTE)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    raw = f.read(4096)
                note = json.loads(raw)
            except (OSError, ValueError) as e:
                return {"path": path, "note": None, "error": str(e), "state_dirs": dirs}
            st = os.stat(path)
            return {"path": path, "note": note, "owner": st.st_uid, "mode": oct(st.st_mode & 0o7777),
                    "state_dirs": dirs}
    return {"path": "", "note": None, "error": "no health note", "state_dirs": dirs}


def make_note(token: str, boot: str, phase: str, verified: str = "") -> dict:
    """A note in the form the add-on writes (see the shared contract)."""
    if phase not in ("starting", "ok", "safe", "error"):
        raise ValueError(f"bad phase: {phase}")
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError(f"bad token: {token!r}")
    return {"v": 1, "token": token, "boot": boot, "phase": phase, "verified": verified}


def write_health(phase: str) -> dict:
    with open(LOOK) as f:
        token = json.load(f)["token"]
    with open("/proc/sys/kernel/random/boot_id") as f:
        boot = f.read().strip()
    dirs = [d for d in _state_dirs() if d.endswith("/seat0/state")] or _state_dirs()
    if not dirs:
        raise SystemExit("no greeter state folder (has the greeter run on this PC yet?)")
    state = dirs[0]
    # The folder belongs to the greeter's throwaway user (GDM makes it 0700 for that user), and
    # the note must look exactly as the greeter left it, so ours gets the same owner.
    st = os.stat(state)
    folder = os.path.join(state, NOTE_DIR)
    os.makedirs(folder, mode=0o700, exist_ok=True)
    os.chown(folder, st.st_uid, st.st_gid)
    note = make_note(token, boot, phase)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".health-")
    with os.fdopen(fd, "w") as f:
        json.dump(note, f)
    os.chown(tmp, st.st_uid, st.st_gid)
    os.chmod(tmp, 0o600)
    path = os.path.join(folder, NOTE)
    os.replace(tmp, path)
    return {"path": path, "note": note, "owner": f"{st.st_uid}:{st.st_gid}"}


# ---- dconf ----------------------------------------------------------------------------------

def etc_listing(top: str = "/etc/dconf") -> list[dict]:
    entries = []
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames.sort()
        for name in [""] + sorted(filenames):
            path = os.path.join(dirpath, name) if name else dirpath
            try:
                st = os.lstat(path)
            except OSError:
                continue
            kind = "d" if os.path.isdir(path) and not os.path.islink(path) else "l" if os.path.islink(path) else "f"
            e = {"path": os.path.relpath(path, top), "kind": kind, "mode": oct(st.st_mode & 0o7777),
                 "owner": f"{st.st_uid}:{st.st_gid}"}
            if kind == "f":
                with open(path, "rb") as f:
                    e["sha256"] = hashlib.sha256(f.read()).hexdigest()
                # A compiled database (/etc/dconf/db/<name>) is rebuilt by `dconf update`; its bytes
                # may change while what it says does not, which dconf-state compares instead.
                e["compiled"] = os.path.dirname(path) == os.path.join(top, "db")
            elif kind == "l":
                e["target"] = os.readlink(path)
            entries.append(e)
    return entries


def dconf_state() -> dict:
    home = tempfile.mkdtemp(prefix="lgv-dconf-")
    # The gdm profile as the greeter reads it, without anyone's own settings: an empty home.
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "DCONF_PROFILE": "gdm", "HOME": home,
           "XDG_CONFIG_HOME": home, "XDG_RUNTIME_DIR": home}
    keys = {}
    for schema, key in (("org.gnome.shell", "enabled-extensions"), ("org.gnome.shell", "disable-user-extensions"),
                        ("org.gnome.desktop.background", "picture-uri"),
                        ("org.gnome.desktop.background", "picture-uri-dark"),
                        ("org.gnome.desktop.screensaver", "picture-uri")):
        rc, out = _run(["gsettings", "get", schema, key], env=env)
        keys[f"{schema} {key}"] = out if rc == 0 else f"(error {rc}) {out}"
    rc, dump = _run(["dconf", "dump", "/"], env=env)
    shutil.rmtree(home, ignore_errors=True)
    return {"gsettings": keys, "dump": dump if rc == 0 else f"(error {rc}) {dump}", "etc": etc_listing()}


# ---- denials --------------------------------------------------------------------------------

DENIAL = re.compile(r"avc:\s+denied|apparmor=\"DENIED\"")


def denials() -> dict:
    lines = []
    rc, out = _run(["journalctl", "-b", "--no-pager", "-o", "cat"])
    lines += [l for l in out.splitlines() if DENIAL.search(l)]
    if shutil.which("ausearch"):
        rc, out = _run(["ausearch", "-m", "AVC,USER_AVC", "-ts", "boot"])
        lines += [l for l in out.splitlines() if DENIAL.search(l)]
    selinux = _run(["getenforce"])[1] if shutil.which("getenforce") else ""
    apparmor = ""
    if os.path.exists("/sys/module/apparmor/parameters/enabled"):
        with open("/sys/module/apparmor/parameters/enabled") as f:
            apparmor = f.read().strip()
    seen, unique = set(), []
    for l in lines:
        key = re.sub(r"audit\([0-9.:]+\)|msg=audit\([0-9.:]+\)", "", l).strip()
        if key not in seen:
            seen.add(key)
            unique.append(l)
    return {"selinux": selinux, "apparmor": apparmor, "lines": unique}


# ---- what is left of the switch -------------------------------------------------------------

def ours() -> dict:
    hits = []
    for dirpath, _dirs, files in os.walk("/etc/dconf"):
        for name in files:
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                continue
            # The compiled database counts too: one still holding our UUID keeps the add-on on.
            if UUID.encode() in data or b"fedora-glass" in name.encode():
                hits.append(path)
    return {"dconf_files": sorted(hits),
            "etc_login": os.path.exists("/etc/fedora-glass/login"),
            "var_login": os.path.exists("/var/lib/fedora-glass/login"),
            "addon": os.path.isdir(f"/usr/share/gdm/greeter/gnome-shell/extensions/{UUID}"),
            "helper": os.path.exists("/usr/libexec/fedora-glass-login")}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "sessions":
        out = sessions()
    elif cmd == "health":
        out = health()
    elif cmd == "write-health" and len(args) == 1:
        out = write_health(args[0])
    elif cmd == "dconf-state":
        out = dconf_state()
    elif cmd == "denials":
        out = denials()
    elif cmd == "ours":
        out = ours()
    else:
        print(f"unknown command: {' '.join(argv)}", file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
