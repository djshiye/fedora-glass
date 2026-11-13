#!/usr/bin/python3 -IS
"""The glass login screen: the root helper, installed as /usr/libexec/fedora-glass-login.

The login screen (GDM's greeter) is a second GNOME Shell that reads its settings through
the dconf profile "gdm". This helper turns the Fedora Glass login add-on on there with one
locked dconf keyfile (the add-on's UUID in org.gnome.shell enabled-extensions, for that
profile only) and writes the look the add-on reads (/etc/fedora-glass/login). Root never
writes CSS or code: only checked colours, numbers, a few words and a picture whose bytes
are never decoded.

  status          what is on, and whether it can be (no root needed); one JSON object
  on 'JSON'       turn it on, or change its look (root, through pkexec); picture bytes on stdin
  off             take it all away again (root), whatever state the system is in
  guard boot      run by systemd before the display manager on every boot while it is on:
                  turns it off by itself when the last login screen crashed, when nobody
                  managed to log in through it during the trial, or when the kernel command
                  line says fedora-glass-login=off; otherwise heals and re-checks the switch
  guard check     run by systemd when a login session appears during the trial

Nobody may ever be left unable to log in, so every change is checked after it is made by
reading the setting back the way the login screen will, and undone when it does not hold.
The notes the login screen leaves behind (health.json) are written by GDM's throwaway user
and are read here as hostile data.

Runs with python3 -I -S: standard library only, one file, nothing from the environment.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

UUID = "fedora-glass-login@djshiye.github.io"
OWN_DB = "fedora-glass-login"                 # our own dconf db, when the profile has no system db
OUR_FILE = "90-fedora-glass-login"            # our keyfile and our locks file, by this name
PROFILE_LINE = "system-db:" + OWN_DB
GUARD_UNIT = "fedora-glass-login-guard.service"
CHECK_PATH_UNIT = "fedora-glass-login-guard-check.path"
KERNEL_OFF = "fedora-glass-login=off"
PICTURE_DIR_SEEN_BY_GREETER = "/etc/fedora-glass/login"
MAX_PICTURE = 16 << 20
MAX_ARG = 8192
MAX_NOTE = 4096
MAX_SMALL = 64 << 10                          # profiles, metadata, state, keyfiles
MAX_DB = 64 << 20                             # a compiled dconf db, kept for undo
MAX_ADDON = 64 << 20
GUARD_LOCK_WAIT = 10.0                        # seconds the boot guard waits for a change still running

WHY = ("", "no-gdm", "not-gdm", "no-addon", "no-dconf", "gnome-version", "policy")
STOPPED = ("", "no-login", "crash", "silent", "kernel-arg", "gnome-version", "error")

HEX6 = re.compile(r"#[0-9a-fA-F]{6}")
HEX32 = re.compile(r"[0-9a-f]{32}")
HEX64 = re.compile(r"[0-9a-f]{64}")
BOOT = re.compile(r"[0-9a-f-]{36}")
NAME = re.compile(r"[A-Za-z0-9._-]+")
EXT_UUID = re.compile(r"[A-Za-z0-9._@-]+")
FILE_DB = re.compile(r"/[A-Za-z0-9._+/-]+")
SEAT = re.compile(r"seat[A-Za-z0-9_-]{0,60}")
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]+")
_SURROGATE = re.compile("[\ud800-\udfff]")
MESSAGE_MAX = 120

DEFAULTS = {"accent": "#3584e4", "tint": "#1e1e2a", "tint_amount": 0.2, "frost": 0.35, "blur": 60,
            "dim": 0.28, "card": True, "clock": "bold", "picture": "wallpaper", "fit": "zoom", "battery": True,
            "message": ""}
NUMBERS = {"tint_amount": (0.0, 1.0), "frost": (0.0, 1.0), "dim": (0.0, 0.65)}
# fit: how "My wallpaper" is placed, by GNOME's own picture-options names (so a picture
# spanned over two screens is spanned on the login screen too).
CHOICES = {"clock": ("gnome", "bold", "thin"), "picture": ("wallpaper", "system", "glow"),
           "fit": ("zoom", "spanned", "scaled", "stretched", "centered", "wallpaper")}
BOOLS = ("card", "battery")

SAFE_ENV_PATH = "/usr/bin:/usr/sbin:/bin:/sbin"


class BadInput(Exception):
    """The values or the picture are not acceptable (exit 2)."""


class Unavailable(Exception):
    """The glass login screen cannot be on here; .why is one of WHY (exit 3)."""

    def __init__(self, why: str, detail: str = ""):
        super().__init__(detail or why)
        self.why = why


class Failed(Exception):
    """Something went wrong while changing things (exit 4 after the roll back)."""


class Interrupted(Failed):
    """A signal (systemd's start timeout, a closed terminal) while changing things: the
    change is rolled back like any other failure."""


class Garbled(Exception):
    """state.json is there but is not what this helper writes."""


# ---- where everything is -------------------------------------------------------------

class Paths:
    """Every file the helper looks at, under `root`. The real program always uses "/";
    the tests point it at a temporary folder. Nothing in the environment changes these."""

    def __init__(self, root: str = "/"):
        self.root = os.path.abspath(root)

    def p(self, path: str) -> str:
        return os.path.join(self.root, path.lstrip("/")) if self.root != "/" else path

    @property
    def real(self) -> bool:
        return self.root == "/"

    def __getattr__(self, name: str) -> str:
        try:
            return self.p(_PATHS[name])
        except KeyError:
            raise AttributeError(name) from None

    @property
    def profile_candidates(self) -> list[str]:
        # dconf's own search order for a profile by name: /etc first, then each folder of the
        # greeter's XDG_DATA_DIRS (GDM puts /usr/share/gdm/greeter in front of the defaults).
        return [self.p(x) for x in ("/etc/dconf/profile/gdm", "/usr/share/gdm/greeter/dconf/profile/gdm",
                                    "/usr/local/share/dconf/profile/gdm", "/usr/share/dconf/profile/gdm")]

    @property
    def gdm_dirs(self) -> list[str]:
        return [self.p("/var/lib/gdm"), self.p("/var/lib/gdm3")]

    @property
    def gdm_confs(self) -> list[str]:
        return [self.p(x) for x in ("/etc/gdm/custom.conf", "/etc/gdm3/custom.conf", "/etc/gdm3/daemon.conf")]

    @property
    def guard_wants(self) -> list[str]:
        return [self.p(f"{d}/graphical.target.wants/{GUARD_UNIT}")
                for d in ("/etc/systemd/system", "/usr/lib/systemd/system", "/lib/systemd/system")]


_PATHS = {
    "etc_profile": "/etc/dconf/profile/gdm",
    "etc_dconf": "/etc/dconf",
    "profile_dir": "/etc/dconf/profile",
    "db_dir": "/etc/dconf/db",
    "greeter": "/usr/share/gdm/greeter",
    "display_manager": "/etc/systemd/system/display-manager.service",
    "addon": "/usr/share/gdm/greeter/gnome-shell/extensions/" + UUID,
    "conf_parent": "/etc/fedora-glass",
    "conf_dir": "/etc/fedora-glass/login",
    "state_parent": "/var/lib/fedora-glass",
    "state_dir": "/var/lib/fedora-glass/login",
    "state": "/var/lib/fedora-glass/login/state.json",
    "stopped": "/var/lib/fedora-glass/login/stopped.json",
    "trial": "/var/lib/fedora-glass/login/trial",
    # There from the first step of an off until nothing of the switch is left: while it is,
    # the guard and `on` only finish that off, so a half-done off never comes back on.
    "leaving": "/var/lib/fedora-glass/login/leaving",
    "lock": "/var/lib/fedora-glass/login/.lock",
    "old_state": "/var/lib/liquid-glass/login-screen.json",
    "old_helper": "/usr/libexec/liquid-glass-login-screen",
    "dconf": "/usr/bin/dconf",
    "gnome_shell": "/usr/bin/gnome-shell",
    "systemctl": "/usr/bin/systemctl",
    "cmdline": "/proc/cmdline",
    "boot_id": "/proc/sys/kernel/random/boot_id",
    "run_systemd": "/run/systemd/system",
}


# ---- small, careful file helpers -------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: str, limit: int = MAX_SMALL) -> bytes | None:
    """A file's bytes, or None when it is not there. Larger than `limit`: an error."""
    try:
        with open(path, "rb") as f:
            data = f.read(limit + 1)
    except FileNotFoundError:
        return None
    if len(data) > limit:
        raise Failed(f"{path} is unexpectedly large")
    return data


def _read_regular(path: str, limit: int = MAX_SMALL) -> bytes | None:
    """Like _read, but only a plain file (never through a link); None for anything else."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        data = os.read(fd, limit + 1)
        while len(data) <= limit:
            more = os.read(fd, limit + 1 - len(data))
            if not more:
                break
            data += more
    finally:
        os.close(fd)
    if len(data) > limit:
        raise Failed(f"{path} is unexpectedly large")
    return data


def _is_real_dir(path: str) -> bool:
    try:
        return stat.S_ISDIR(os.lstat(path).st_mode)
    except OSError:
        return False


def _fsync_dir(folder: str) -> None:
    fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_atomic(path: str, data: bytes, mode: int = 0o644) -> None:
    """Write a file whole or not at all: a temporary file in the same root-owned folder,
    flushed to disk, then renamed over the old one. A link in its place is replaced, never
    written through."""
    folder = os.path.dirname(path)
    if not _is_real_dir(folder):
        raise Failed(f"{folder} is not a folder")
    fd, tmp = tempfile.mkstemp(prefix=".fedora-glass-", dir=folder)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fchmod(fd, mode)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(folder)


def _unlink(path: str) -> bool:
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


def _rmdir_if_empty(path: str) -> None:
    try:
        if _is_real_dir(path) and not os.listdir(path):
            os.rmdir(path)
    except OSError:
        pass


def _mkdir(path: str) -> bool:
    """Make one folder (0755) unless it is there; True when this made it. A link or a file
    in its place is an error: nothing of ours is ever written through a link."""
    try:
        os.mkdir(path, 0o755)
    except FileExistsError:
        if not _is_real_dir(path):
            raise Failed(f"{path} is not a plain folder") from None
        return False
    os.chmod(path, 0o755)                         # whatever the umask was
    return True


class Txn:
    """Every change of `on` (and of the guard's re-sync) goes through here, which first keeps
    what was there, so a failure at any step puts each file back exactly as it was."""

    def __init__(self):
        self.undo: list = []

    def _keep(self, path: str):
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(st.st_mode):
            return ("link", os.readlink(path))
        if not stat.S_ISREG(st.st_mode):
            raise Failed(f"{path} is not a plain file")
        data = _read(path, MAX_DB)
        return ("file", data, stat.S_IMODE(st.st_mode))

    def _put_back(self, path: str, kept) -> None:
        if kept is None:
            _unlink(path)
        elif kept[0] == "link":
            _unlink(path)
            os.symlink(kept[1], path)
        else:
            write_atomic(path, kept[1], kept[2])

    def write(self, path: str, data: bytes, mode: int = 0o644) -> None:
        kept = self._keep(path)
        self.undo.append(lambda: self._put_back(path, kept))
        write_atomic(path, data, mode)

    def remove(self, path: str) -> None:
        kept = self._keep(path)
        if kept is None:
            return
        self.undo.append(lambda: self._put_back(path, kept))
        os.unlink(path)
        _fsync_dir(os.path.dirname(path))

    def replace_from(self, path: str, tmp: str) -> None:
        """Rename `tmp` (a compiled db) over `path`, like `dconf update` does: the old file
        is then marked out of date, so a login screen that has it open reads the new one."""
        kept = self._keep(path)
        self.undo.append(lambda: self._put_back(path, kept))
        old = -1
        if kept is not None and kept[0] == "file":
            try:
                old = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            except OSError:
                old = -1
        try:
            os.replace(tmp, path)
            _fsync_dir(os.path.dirname(path))
            if old >= 0:
                os.write(old, b"\0" * 8)
        finally:
            if old >= 0:
                os.close(old)

    def mkdir(self, path: str) -> bool:
        made = _mkdir(path)
        if made:
            self.undo.append(lambda: os.rmdir(path))
        return made

    def rmdir(self, path: str) -> None:
        if _is_real_dir(path) and not os.listdir(path):
            os.rmdir(path)
            self.undo.append(lambda: _mkdir(path))

    def rollback(self) -> list[str]:
        problems = []
        for fn in reversed(self.undo):
            try:
                fn()
            except Exception as e:  # noqa: BLE001 - put back as much as possible
                problems.append(str(e))
        self.undo.clear()
        return problems


def _run(args: list[str], timeout: float, home: str = "/", extra: dict | None = None) -> subprocess.CompletedProcess:
    """A program by its absolute path, as a list, with a tiny clean environment."""
    if not os.path.isabs(args[0]):
        raise Failed(f"not an absolute path: {args[0]}")
    env = {"PATH": SAFE_ENV_PATH, "LC_ALL": "C", "HOME": home}
    env.update(extra or {})
    return subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout,
                          env=env, cwd="/", close_fds=True)


class Scratch:
    """A private folder for the dconf probes: in root's own state folder when root, else /tmp."""

    def __init__(self, paths: Paths):
        self.paths = paths
        self.dir = ""

    def __enter__(self) -> str:
        if os.geteuid() == 0:
            _make_state_dirs(self.paths)
            self.dir = tempfile.mkdtemp(prefix=".work-", dir=self.paths.state_dir)
        else:
            self.dir = tempfile.mkdtemp(prefix="fedora-glass-login-", dir="/tmp")
        os.mkdir(os.path.join(self.dir, "run"), 0o700)
        return self.dir

    def __exit__(self, *exc) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def _make_state_dirs(paths: Paths) -> None:
    for d in (paths.state_parent, paths.state_dir):
        _mkdir(d)


class Lock:
    """One of on, off and the guard at a time: an flock on a file in root's state folder."""

    def __init__(self, paths: Paths, wait: float = 60.0):
        self.paths = paths
        self.wait = wait
        self.fd = -1

    def __enter__(self) -> "Lock":
        _make_state_dirs(self.paths)
        self.fd = os.open(self.paths.lock, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        end = time.monotonic() + self.wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= end:
                    os.close(self.fd)
                    raise Failed("another change of the login screen is still running") from None
                time.sleep(0.1)

    def __exit__(self, *exc) -> None:
        os.close(self.fd)


# ---- the values ------------------------------------------------------------------------

def clean_message(raw: str) -> str:
    """One paragraph of plain text, at most MESSAGE_MAX characters (as fedoraglass.settings
    does for the lock screen; the helper cannot import the app)."""
    text = " ".join(_CONTROL.sub(" ", _SURROGATE.sub("", raw)).split())
    return text[:MESSAGE_MAX].strip()


def _strict_json(text: str):
    def no_constant(name):
        raise BadInput(f"{name} is not a number")

    def pairs(items):
        keys = [k for k, _ in items]
        if len(set(keys)) != len(keys):
            raise BadInput("a key is given twice")
        return dict(items)
    try:
        return json.loads(text, parse_constant=no_constant, object_pairs_hook=pairs)
    except BadInput:
        raise
    except (ValueError, RecursionError) as e:
        raise BadInput(f"not JSON: {e}") from None


def check_values(raw: object) -> dict:
    """The eleven values, checked and normalised; missing ones take their defaults."""
    if not isinstance(raw, dict):
        raise BadInput("the values must be a JSON object")
    unknown = sorted(set(raw) - set(DEFAULTS))
    if unknown:
        raise BadInput(f"unknown value: {str(unknown[0])[:40]}")
    v = {**DEFAULTS, **raw}
    out = {}
    for key in ("accent", "tint"):
        if not (isinstance(v[key], str) and HEX6.fullmatch(v[key])):
            raise BadInput(f"{key} must look like #3584e4")
        out[key] = v[key].lower()
    for key, (lo, hi) in NUMBERS.items():
        x = v[key]
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or not lo <= x <= hi:
            raise BadInput(f"{key} must be a number from {lo:g} to {hi:g}")
        out[key] = round(float(x), 3)
    b = v["blur"]
    if isinstance(b, bool) or not isinstance(b, int) or not 10 <= b <= 100:
        raise BadInput("blur must be a whole number from 10 to 100")
    out["blur"] = b
    for key in BOOLS:
        if not isinstance(v[key], bool):
            raise BadInput(f"{key} must be true or false")
        out[key] = v[key]
    for key, allowed in CHOICES.items():
        if v[key] not in allowed or not isinstance(v[key], str):
            raise BadInput(f"{key} must be one of {', '.join(allowed)}")
        out[key] = v[key]
    if not isinstance(v["message"], str):
        raise BadInput("message must be text")
    out["message"] = clean_message(v["message"])
    return {k: out[k] for k in DEFAULTS}


def parse_values(text: object) -> dict:
    if not isinstance(text, str) or len(text.encode("utf-8", "surrogatepass")) > MAX_ARG:
        raise BadInput("the values are missing or too long")
    return check_values(_strict_json(text))


def picture_kind(data: bytes) -> str:
    """"jpg" or "png" by the first bytes; the picture itself is never decoded here."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    raise BadInput("the picture must be a JPEG or PNG file")


def read_picture(stream) -> tuple[bytes, str]:
    data = b""
    while len(data) <= MAX_PICTURE:
        chunk = stream.read(MAX_PICTURE + 1 - len(data))
        if not chunk:
            break
        data += chunk
    if len(data) > MAX_PICTURE:
        raise BadInput("the picture is larger than 16 MiB")
    if not data:
        raise BadInput("no picture came on stdin")
    return data, picture_kind(data)


def look_json(token: str, values: dict) -> bytes:
    return (json.dumps({"version": 1, "token": token, **values}, sort_keys=True, indent=1) + "\n").encode()


# ---- what this system has --------------------------------------------------------------

def parse_profile(text: str) -> list[tuple[str, str]]:
    """A dconf profile's lines as (kind, value). Anything this does not understand fails."""
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, sep, value = line.partition(":")
        value = value.strip()
        if not sep:
            raise Unavailable("policy", "the dconf profile has a line this does not understand")
        if kind in ("user-db", "system-db"):
            if not NAME.fullmatch(value):
                raise Unavailable("policy", f"unexpected {kind} name in the dconf profile")
        elif kind == "file-db":
            if not FILE_DB.fullmatch(value) or "/../" in value + "/" or "/./" in value + "/":
                raise Unavailable("policy", "unexpected file-db path in the dconf profile")
        elif kind != "service-db":
            raise Unavailable("policy", f"unknown kind of line in the dconf profile: {kind[:30]}")
        out.append((kind, value))
    return out


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise Unavailable("policy", "the dconf profile is not text") from None


def _profile_text(path: str) -> str | None:
    """A profile file as dconf would open it (links followed: these folders are root's);
    None when it is not there."""
    try:
        data = _read(path)
    except IsADirectoryError:
        raise Unavailable("policy", f"{path} is a folder") from None
    except PermissionError:
        raise Unavailable("policy", f"{path} cannot be read") from None
    return None if data is None else _decode(data)


def distro_profile(paths: Paths) -> str | None:
    """The first profile after /etc in dconf's search order."""
    for p in paths.profile_candidates[1:]:
        text = _profile_text(p)
        if text is not None:
            return text
    return None


def active_profile(paths: Paths) -> str | None:
    for p in paths.profile_candidates:
        text = _profile_text(p)
        if text is not None:
            return text
    return None


def shared_dbs(paths: Paths) -> set[str] | None:
    """The system dbs that a dconf profile other than GDM's names, or None for "every db"
    (a profile that cannot be read or understood: fail closed). Our locks must never land
    in a db that desktop users read too, or their own settings would be locked to ours."""
    gdm = set(paths.profile_candidates)
    folders = [paths.p("/etc/dconf/profile"), paths.p("/usr/share/dconf/profile")]
    for c in paths.profile_candidates:
        if os.path.dirname(c) not in folders:
            folders.append(os.path.dirname(c))
    names: set[str] = set()
    for folder in folders:
        try:
            entries = sorted(os.listdir(folder))
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return None
        for name in entries:
            full = os.path.join(folder, name)
            if full in gdm:
                continue
            try:
                st = os.stat(full)
            except FileNotFoundError:
                continue                          # a dangling link: dconf cannot open it either
            except OSError:
                return None
            if stat.S_ISDIR(st.st_mode):
                continue
            if not stat.S_ISREG(st.st_mode):
                return None
            try:
                text = _profile_text(full)
                if text is None:
                    continue
                entries_of = parse_profile(text)
            except (Unavailable, Failed, OSError):
                return None
            names.update(v for k, v in entries_of if k == "system-db")
    return names


def without_our_line(text: str) -> str:
    return "".join(x for x in text.splitlines(keepends=True) if x.strip() != PROFILE_LINE)


def with_our_line(text: str) -> str:
    lines = without_our_line(text).splitlines(keepends=True)
    at = 0
    for i, x in enumerate(lines):
        if x.strip().startswith("user-db:"):
            at = i + 1
    if at and not lines[at - 1].endswith("\n"):
        lines[at - 1] += "\n"
    lines.insert(at, PROFILE_LINE + "\n")
    return "".join(lines)


GNOME_VERSION = re.compile(rb"GNOME Shell ((\d{1,4})(?:[.~+-][0-9A-Za-z.~+-]{0,19})?)\s*")
FULL_VERSION = re.compile(r"\d{1,4}(?:[.~+-][0-9A-Za-z.~+-]{0,19})?")


def gnome_version(paths: Paths) -> tuple[str, str]:
    """GNOME Shell's (major, full) version, e.g. ("51", "51.1"), or ("", ""). No file states
    it on every distro, so ask the program, with a clean environment and a short timeout.
    The major decides whether the add-on supports it; any change of the full version (51.1
    to 51.2 too) starts a new trial, since a point release can change the login screen."""
    try:
        r = _run([paths.gnome_shell, "--version"], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "", ""
    m = GNOME_VERSION.fullmatch(r.stdout)
    if r.returncode != 0 or not m:
        return "", ""
    return m.group(2).decode(), m.group(1).decode()


def addon_hash(paths: Paths) -> str:
    """sha256 over the names and bytes of the installed add-on's files."""
    base = paths.addon
    h = hashlib.sha256()
    total = 0
    for folder, dirs, files in os.walk(base):
        dirs.sort()
        rel = os.path.relpath(folder, base)
        h.update(b"D" + rel.encode("utf-8", "surrogateescape") + b"\0")
        for name in [d for d in dirs if os.path.islink(os.path.join(folder, d))]:
            dirs.remove(name)                     # never walked; it counts as a link
            files.append(name)
        for name in sorted(files):
            full = os.path.join(folder, name)
            relname = os.path.join(rel, name).encode("utf-8", "surrogateescape")
            if os.path.islink(full):
                h.update(b"L" + relname + b"\0" + os.readlink(full).encode("utf-8", "surrogateescape") + b"\0")
                continue
            data = _read_regular(full, MAX_ADDON) or b""
            total += len(data)
            if total > MAX_ADDON:
                raise Failed("the add-on is unexpectedly large")
            h.update(b"F" + relname + b"\0" + str(len(data)).encode() + b"\0" + data)
    return h.hexdigest()


def addon_versions(paths: Paths) -> list[str] | None:
    """The add-on's shell-version list, or None when it is not (properly) installed."""
    base = paths.addon
    if not _is_real_dir(base) or not os.path.isfile(os.path.join(base, "extension.js")):
        return None
    try:
        meta = json.loads((_read_regular(os.path.join(base, "metadata.json")) or b"").decode())
    except (ValueError, UnicodeDecodeError, Failed):
        return None
    if not isinstance(meta, dict) or meta.get("uuid") != UUID:
        return None
    versions = meta.get("shell-version")
    if not isinstance(versions, list) or not all(isinstance(x, str) for x in versions):
        return None
    return versions


def _display_manager_is_gdm(paths: Paths) -> bool:
    try:
        target = os.readlink(paths.display_manager)
    except OSError:
        return False
    return os.path.basename(target) in ("gdm.service", "gdm3.service")


def guard_enabled(paths: Paths) -> bool:
    return any(os.path.lexists(p) for p in paths.guard_wants)


# ---- reading dconf the way the login screen will --------------------------------------

def parse_strv(text: str) -> list[str]:
    """`dconf read` output of an array of strings, strictly; anything else fails closed."""
    t = text.strip()
    if t == "":
        return []                                 # unset: GNOME's default, no extensions
    if t.startswith("@as "):
        t = t[4:].strip()
    if not (t.startswith("[") and t.endswith("]")):
        raise Unavailable("policy", "enabled-extensions is not a list of names")
    inner = t[1:-1]
    if inner == "":
        return []
    out = []
    for part in inner.split(", "):
        m = re.fullmatch(r"'([A-Za-z0-9._@-]+)'", part)
        if not m:
            raise Unavailable("policy", "enabled-extensions holds a name this does not accept")
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def probe_read(paths: Paths, work: str, sources: list[str], keys: list[str]) -> dict[str, str]:
    """Read keys through a profile of only these db files (no user db: nothing is created,
    no D-Bus is needed), with HOME and XDG_RUNTIME_DIR in the private work folder."""
    profile = os.path.join(work, f"probe-{secrets.token_hex(4)}")
    with open(profile, "w", encoding="utf-8") as f:
        f.write("".join(f"file-db:{s}\n" for s in sources))
        if not sources:
            f.write("# nothing\n")
    out = {}
    for key in keys:
        r = _run([paths.dconf, "read", key], timeout=20, home=work,
                 extra={"DCONF_PROFILE": profile, "XDG_RUNTIME_DIR": os.path.join(work, "run")})
        if r.returncode != 0:
            raise Failed(f"dconf read failed: {r.stderr.decode(errors='replace')[:200]}")
        out[key] = r.stdout.decode("utf-8", "replace").strip()
    return out


def _compile(paths: Paths, out: str, source_dir: str) -> None:
    r = _run([paths.dconf, "compile", out, source_dir], timeout=30)
    if r.returncode != 0:
        raise Failed(f"dconf compile failed: {r.stderr.decode(errors='replace')[:300]}")


def _copy_without_ours(src: str, dest: str) -> None:
    """A copy of a db's .d folder (keyfiles and locks) without our two files."""
    os.mkdir(dest, 0o700)
    os.mkdir(os.path.join(dest, "locks"), 0o700)
    for sub in ("", "locks"):
        folder = os.path.join(src, sub)
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            full = os.path.join(folder, name)
            if name == OUR_FILE or not os.path.isfile(full):
                continue
            data = _read(full, MAX_SMALL * 16)
            with open(os.path.join(dest, sub, name), "wb") as f:
                f.write(data or b"")


EXT_KEY = "/org/gnome/shell/enabled-extensions"
DUE_KEY = "/org/gnome/shell/disable-user-extensions"
# GNOME's own disableExtension() writes this into the greeter's persistent user db, and it
# wins over enabled-extensions: ours is locked too, without our UUID.
DIS_KEY = "/org/gnome/shell/disabled-extensions"


def _sources(paths: Paths, entries: list[tuple[str, str]], work: str, strip: set[str],
             skip_own: bool) -> list[str]:
    """The db files of a profile, in its order, for a probe. `strip`: the dbs read as they
    will be compiled without our keyfile (the one it goes in, and any it moves out of)."""
    out = []
    for kind, value in entries:
        if kind == "system-db":
            if skip_own and value == OWN_DB:
                continue
            if value in strip and _is_real_dir(os.path.join(paths.db_dir, value + ".d")):
                copy = os.path.join(work, f"base-{value}.d")
                shutil.rmtree(copy, ignore_errors=True)
                _copy_without_ours(os.path.join(paths.db_dir, value + ".d"), copy)
                db = os.path.join(work, f"base-{value}")
                _compile(paths, db, copy)
                out.append(db)
                continue
            f = os.path.join(paths.db_dir, value)
        elif kind == "file-db":
            f = paths.p(value)
        else:
            continue
        if os.path.isfile(f):
            out.append(f)
    return out


# ---- the plan: which db, which profile -------------------------------------------------

class Plan:
    def __init__(self):
        self.route = ""           # "a": a system db of the profile, "b": our own db and a profile line
        self.db = ""
        self.entries: list[tuple[str, str]] = []
        self.profile_new: bytes | None = None
        self.profile_info: dict | None = None
        self.base_list: list[str] = []
        self.base_disabled: list[str] = []


def _our_profile_unchanged(paths: Paths, st: dict | None) -> tuple[bytes | None, bool]:
    etc = _read_regular(paths.etc_profile) if not os.path.islink(paths.etc_profile) else None
    info = (st or {}).get("profile")
    same = bool(info) and etc is not None and sha256_bytes(etc) == info.get("written")
    return etc, same


def make_plan(paths: Paths, st: dict | None) -> Plan:
    plan = Plan()
    etc_present = os.path.lexists(paths.etc_profile)
    etc_bytes, ours = _our_profile_unchanged(paths, st)
    info = (st or {}).get("profile") or {}
    if ours and info.get("created"):
        base = distro_profile(paths)               # our own copy: start again from the distro's
    elif ours:
        base = info.get("original")
    elif etc_present:
        text = _profile_text(paths.etc_profile)
        base = None if text is None else without_our_line(text)
    else:
        base = distro_profile(paths)
    if base is None:
        raise Unavailable("no-gdm", "GDM's dconf profile is not there")
    plan.entries = parse_profile(base)
    shared = shared_dbs(paths)
    for kind, value in plan.entries:
        if kind != "system-db" or value == OWN_DB:
            continue
        if shared is None or value in shared:
            continue                              # read by desktop users too: never ours to lock
        d = os.path.join(paths.db_dir, value + ".d")
        if _is_real_dir(d) or not os.path.lexists(os.path.join(paths.db_dir, value)):
            if os.path.lexists(d) and not _is_real_dir(d):
                continue
            plan.route, plan.db = "a", value
            return plan
    plan.route, plan.db = "b", OWN_DB
    if etc_present and (os.path.islink(paths.etc_profile) or etc_bytes is None):
        raise Unavailable("policy", f"{paths.etc_profile} is not a plain file")
    new = with_our_line(base).encode()
    plan.profile_new = new
    if ours:
        plan.profile_info = {"created": bool(info.get("created")), "written": sha256_bytes(new),
                             "original": info.get("original")}
    elif etc_bytes is None:
        plan.profile_info = {"created": True, "written": sha256_bytes(new), "original": None}
    else:
        plan.profile_info = {"created": False, "written": sha256_bytes(new), "original": base}
    return plan


class Assessment:
    def __init__(self):
        self.ok = False
        self.why = ""
        self.detail = ""
        self.plan: Plan | None = None
        self.addon = ""
        self.gnome = ""           # the major version: what the add-on must list
        self.gnome_full = ""      # the whole version: a change starts a new trial


def assess(paths: Paths, st: dict | None, work: str) -> Assessment:
    """Whether it can be on, and how: the checks in the order of the `why` codes."""
    a = Assessment()
    try:
        if active_profile(paths) is None or not os.path.isdir(paths.greeter):
            raise Unavailable("no-gdm")
        if not _display_manager_is_gdm(paths):
            raise Unavailable("not-gdm")
        versions = addon_versions(paths)
        if versions is None:
            raise Unavailable("no-addon")
        if not os.access(paths.dconf, os.X_OK):
            raise Unavailable("no-dconf")
        a.gnome, a.gnome_full = gnome_version(paths)
        if not a.gnome or a.gnome not in versions:
            raise Unavailable("gnome-version")
        a.addon = addon_hash(paths)
        plan = make_plan(paths, st)
        strip = {plan.db} | {n for n in _d_dirs(paths) if _ours_in(paths, n)}
        base = probe_read(paths, work, _sources(paths, plan.entries, work, strip, skip_own=True),
                          [EXT_KEY, DUE_KEY, DIS_KEY])
        if base[DUE_KEY] == "true":
            raise Unavailable("policy", "an administrator switched off extensions on the login screen")
        if base[DUE_KEY] not in ("", "false"):
            raise Unavailable("policy", "disable-user-extensions has an unexpected value")
        plan.base_list = [x for x in parse_strv(base[EXT_KEY]) if x != UUID]
        plan.base_disabled = [x for x in parse_strv(base[DIS_KEY]) if x != UUID]
        a.plan = plan
        a.ok = True
    except Unavailable as e:
        a.why, a.detail = e.why, str(e)
    except (Failed, OSError, subprocess.SubprocessError) as e:
        a.why, a.detail = "policy", str(e)
    return a


def available(paths: Paths) -> tuple[bool, str]:
    try:
        st = read_state(paths)
    except Garbled:
        st = None
    with Scratch(paths) as work:
        a = assess(paths, st, work)
    return a.ok, a.why


# ---- the switch ------------------------------------------------------------------------

def _strv(names: list[str]) -> str:
    for x in names:
        if not EXT_UUID.fullmatch(x):
            raise Unavailable("policy", "an extension name this does not accept")
    return "[" + ", ".join(f"'{x}'" for x in names) + "]" if names else "@as []"


def keyfile(base_list: list[str], values: dict, base_disabled: list[str] = ()) -> tuple[bytes, bytes]:
    """Our keyfile and our locks file. Every value is one this file built from checked parts."""
    names = [x for x in base_list if x != UUID] + [UUID]
    disabled = [x for x in base_disabled if x != UUID]
    lines = ["# Fedora Glass: the glass login screen. Written by /usr/libexec/fedora-glass-login;",
             "# `sudo fedora-glass login-screen off` takes it away again.",
             "[org/gnome/shell]",
             "enabled-extensions=" + _strv(names),
             "disabled-extensions=" + _strv(disabled),
             "disable-user-extensions=false"]
    locks = [EXT_KEY, DIS_KEY, DUE_KEY]
    pic = values["picture"]
    bg = "/org/gnome/desktop/background/"
    if pic == "wallpaper":
        kind = values.get("_kind", "jpg")
        uri = f"file://{PICTURE_DIR_SEEN_BY_GREETER}/picture.{kind}"
        lines += ["", "[org/gnome/desktop/background]", f"picture-uri='{uri}'", f"picture-uri-dark='{uri}'",
                  f"picture-options='{values['fit']}'"]
        locks += [bg + k for k in ("picture-uri", "picture-uri-dark", "picture-options")]
    elif pic == "glow":
        tint = values["tint"]
        lines += ["", "[org/gnome/desktop/background]", "picture-uri=''", "picture-uri-dark=''",
                  "picture-options='none'", f"primary-color='{tint}'", f"secondary-color='{tint}'",
                  "color-shading-type='solid'"]
        locks += [bg + k for k in ("picture-uri", "picture-uri-dark", "picture-options", "primary-color",
                                   "secondary-color", "color-shading-type")]
    return ("\n".join(lines) + "\n").encode(), ("\n".join(locks) + "\n").encode()


def _d_dirs(paths: Paths) -> list[str]:
    try:
        names = sorted(os.listdir(paths.db_dir))
    except OSError:
        return []
    return [n[:-2] for n in names if n.endswith(".d") and NAME.fullmatch(n[:-2])
            and _is_real_dir(os.path.join(paths.db_dir, n))]


def _ours_in(paths: Paths, name: str) -> list[str]:
    d = os.path.join(paths.db_dir, name + ".d")
    return [p for p in (os.path.join(d, OUR_FILE), os.path.join(d, "locks", OUR_FILE)) if os.path.lexists(p)]


def _has_other_files(d: str) -> bool:
    for sub in ("", "locks"):
        try:
            names = os.listdir(os.path.join(d, sub))
        except OSError:
            continue
        if any(n != OUR_FILE and n != "locks" for n in names):
            return True
    return False


def _compile_into(paths: Paths, txn: Txn | None, name: str) -> None:
    """Compile /etc/dconf/db/NAME.d into a temporary file next to the db, then rename it in.
    Never `dconf update`: that would compile every db, including ones that are not ours."""
    fd, tmp = tempfile.mkstemp(prefix=".fedora-glass-", dir=paths.db_dir)
    os.close(fd)
    try:
        _compile(paths, tmp, os.path.join(paths.db_dir, name + ".d"))
        os.chmod(tmp, 0o644)
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        target = os.path.join(paths.db_dir, name)
        if txn is None:
            Txn().replace_from(target, tmp)       # off: nothing to roll back to
        else:
            txn.replace_from(target, tmp)
    finally:
        _unlink(tmp)


def _made_paths(paths: Paths, plan: Plan) -> list[str]:
    """The folders and files the switch will create (so off can take them away again)."""
    chain = ["/etc/dconf", "/etc/dconf/db", f"/etc/dconf/db/{plan.db}.d", f"/etc/dconf/db/{plan.db}.d/locks",
             f"/etc/dconf/db/{plan.db}"]
    if plan.route == "b":
        chain += ["/etc/dconf/profile"]
    return [c for c in chain if not os.path.lexists(paths.p(c))]


ALLOWED_MADE = re.compile(r"/etc/dconf(?:/profile|/db(?:/[A-Za-z0-9._-]+(?:\.d(?:/locks)?)?)?)?")


def _profile_without_us(paths: Paths, info: dict | None) -> bytes | None | bool:
    """What /etc/dconf/profile/gdm becomes with our switch gone: bytes, None (delete it) or
    False (leave it as it is)."""
    if os.path.islink(paths.etc_profile) or not os.path.lexists(paths.etc_profile):
        return False
    etc = _read_regular(paths.etc_profile)
    if etc is None:
        return False
    if info and sha256_bytes(etc) == info.get("written"):
        if info.get("created"):
            return None
        if isinstance(info.get("original"), str):
            return info["original"].encode()
    try:
        text = etc.decode("utf-8")
    except UnicodeDecodeError:
        return False
    new = without_our_line(text).encode()
    if new == etc:
        return False
    try:
        distro = distro_profile(paths)
    except Unavailable:
        distro = None
    if distro is not None and new == distro.encode():
        # Our copy of the distro's profile (its record lost): without it dconf reads the same.
        return None
    return new


def write_switch(paths: Paths, txn: Txn, plan: Plan, values: dict, st_prev: dict | None) -> None:
    key, locks = keyfile(plan.base_list, values, plan.base_disabled)
    # A distro update can move us from one route to the other: our files elsewhere go.
    for name in _d_dirs(paths):
        if name == plan.db or not _ours_in(paths, name):
            continue
        for p in _ours_in(paths, name):
            txn.remove(p)
        d = os.path.join(paths.db_dir, name + ".d")
        if name == OWN_DB and not _has_other_files(d):
            txn.rmdir(os.path.join(d, "locks"))
            txn.rmdir(d)
            txn.remove(os.path.join(paths.db_dir, name))
        else:
            _compile_into(paths, txn, name)
    for d in (paths.etc_dconf, paths.db_dir, os.path.join(paths.db_dir, plan.db + ".d"),
              os.path.join(paths.db_dir, plan.db + ".d", "locks")):
        txn.mkdir(d)
    d = os.path.join(paths.db_dir, plan.db + ".d")
    changed = False
    for path, data in ((os.path.join(d, OUR_FILE), key), (os.path.join(d, "locks", OUR_FILE), locks)):
        if os.path.islink(path) or _read_regular(path) != data:
            txn.write(path, data)
            changed = True
    if changed or not os.path.isfile(os.path.join(paths.db_dir, plan.db)):
        _compile_into(paths, txn, plan.db)
    if plan.route == "b":
        if os.path.islink(paths.etc_profile) or _read_regular(paths.etc_profile) != plan.profile_new:
            txn.mkdir(paths.profile_dir)
            txn.write(paths.etc_profile, plan.profile_new)
    else:
        new = _profile_without_us(paths, (st_prev or {}).get("profile"))
        if new is None:
            txn.remove(paths.etc_profile)
            if "/etc/dconf/profile" in (st_prev or {}).get("made", []):
                txn.rmdir(paths.profile_dir)
        elif new is not False:
            txn.write(paths.etc_profile, new)


def post_check(paths: Paths, work: str) -> None:
    """Read the two keys back through the real profile's db files, as the login screen will."""
    text = active_profile(paths)
    if text is None:
        raise Unavailable("policy", "no dconf profile after the change")
    got = probe_read(paths, work, _sources(paths, parse_profile(text), work, set(), skip_own=False),
                     [EXT_KEY, DUE_KEY, DIS_KEY])
    if UUID not in parse_strv(got[EXT_KEY]) or got[DUE_KEY] != "false" or UUID in parse_strv(got[DIS_KEY]):
        raise Unavailable("policy", "another setting overrides ours, so the add-on would not start")


# ---- state -----------------------------------------------------------------------------

def _int(x, hi=10000) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= hi


def read_state(paths: Paths) -> dict | None:
    """state.json, checked; None when it is not there. Anything else than what this writes: Garbled."""
    try:
        data = _read_regular(paths.state)
    except Failed:
        raise Garbled("too large") from None
    if data is None:
        if os.path.lexists(paths.state):
            raise Garbled("not a plain file")
        return None
    try:
        s = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise Garbled("not JSON") from None
    try:
        ok = (isinstance(s, dict) and s.get("version") == 1 and s.get("state") in ("trial", "on")
              and isinstance(s.get("token"), str) and HEX32.fullmatch(s["token"])
              and s.get("picture") in ("", "jpg", "png")
              and isinstance(s.get("picture_sha256"), str) and (s["picture_sha256"] == "" or HEX64.fullmatch(s["picture_sha256"]))
              and isinstance(s.get("addon_sha256"), str) and HEX64.fullmatch(s["addon_sha256"])
              and isinstance(s.get("gnome"), str) and re.fullmatch(r"\d{1,4}", s["gnome"])
              # Missing in a state file of an earlier build: it reads as a version change.
              and isinstance(s.get("gnome_full", ""), str)
              and (s.get("gnome_full", "") == "" or FULL_VERSION.fullmatch(s["gnome_full"]))
              and _int(s.get("trial_boots")) and _int(s.get("silent_boots"))
              and isinstance(s.get("last_boot"), str) and (s["last_boot"] == "" or BOOT.fullmatch(s["last_boot"]))
              and s.get("route") in ("a", "b") and isinstance(s.get("db"), str) and NAME.fullmatch(s["db"])
              and _made_ok(s.get("made")) and _profile_ok(s.get("profile"))
              and isinstance(s.get("started"), str) and len(s["started"]) < 40)
        if ok:
            if isinstance(s.get("values"), dict) and "fit" not in s["values"]:
                s["values"] = {**s["values"], "fit": "zoom"}      # written before fit existed
            ok = check_values(s.get("values")) == s["values"]
            ok = ok and (s["picture"] != "") == (s["values"]["picture"] == "wallpaper")
    except BadInput:
        ok = False
    if not ok:
        raise Garbled("unexpected contents")
    return s


def _made_ok(m) -> bool:
    return isinstance(m, list) and len(m) <= 20 and all(isinstance(x, str) and ALLOWED_MADE.fullmatch(x) for x in m)


def _profile_ok(p) -> bool:
    if p is None:
        return True
    return (isinstance(p, dict) and set(p) == {"created", "written", "original"} and isinstance(p["created"], bool)
            and isinstance(p["written"], str) and bool(HEX64.fullmatch(p["written"]))
            and (p["original"] is None or (isinstance(p["original"], str) and len(p["original"]) <= MAX_SMALL)))


def _lenient_state(paths: Paths) -> dict:
    """For off: whatever pieces of state.json can still be trusted (each checked alone)."""
    try:
        s = json.loads((_read_regular(paths.state) or b"{}").decode("utf-8"))
    except (ValueError, UnicodeDecodeError, Failed, OSError):
        return {}
    if not isinstance(s, dict):
        return {}
    out = {}
    if _made_ok(s.get("made")):
        out["made"] = s["made"]
    if s.get("profile") is not None and _profile_ok(s.get("profile")):
        out["profile"] = s["profile"]
    if isinstance(s.get("db"), str) and NAME.fullmatch(s["db"]):
        out["db"] = s["db"]
    return out


def save_state(paths: Paths, txn: Txn, st: dict) -> None:
    txn.write(paths.state, (json.dumps(st, sort_keys=True, indent=1) + "\n").encode())


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ---- the notes the login screen leaves -------------------------------------------------

def _open_dir(name: str, dir_fd: int | None) -> int:
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)


def _note_from(fd_dir: int) -> dict | None:
    try:
        fd = os.open("health.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=fd_dir)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_NOTE:
            return None
        data = b""
        while len(data) <= MAX_NOTE:
            more = os.read(fd, MAX_NOTE + 1 - len(data))
            if not more:
                break
            data += more
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(data) > MAX_NOTE:
        return None
    try:
        n = _strict_json(data.decode("utf-8"))
    except (BadInput, UnicodeDecodeError):
        return None
    if not (isinstance(n, dict) and set(n) == {"v", "token", "boot", "phase", "verified"}):
        return None
    if not (n["v"] == 1 and not isinstance(n["v"], bool)):
        return None
    for key, pattern in (("token", HEX32), ("verified", HEX32), ("boot", BOOT)):
        if not (isinstance(n[key], str) and (n[key] == "" or pattern.fullmatch(n[key]))):
            return None
    if n["phase"] not in ("starting", "ok", "safe", "error") or not isinstance(n["phase"], str):
        return None
    return n


def read_notes(paths: Paths) -> list[dict]:
    """Every health note under GDM's working folders, walked without following any link.
    GDM gives <seat>/state to each new throwaway greeter user at every greeter start (it
    re-owns it recursively), so who owns a note says nothing: no owner is ever checked."""
    notes = []
    for wd in paths.gdm_dirs:
        try:
            fd_wd = _open_dir(wd, None)
        except OSError:
            continue
        try:
            try:
                seats = sorted(n for n in os.listdir(fd_wd) if SEAT.fullmatch(n))[:16]
            except OSError:
                seats = []
            for seat in seats:
                fds = []
                try:
                    fds.append(_open_dir(seat, fd_wd))
                    fds.append(_open_dir("state", fds[-1]))
                    fds.append(_open_dir("fedora-glass-login", fds[-1]))
                    note = _note_from(fds[-1])
                    if note is not None:
                        notes.append(note)
                except OSError:
                    pass
                finally:
                    for fd in fds:
                        os.close(fd)
        finally:
            os.close(fd_wd)
    return notes


def boot_id(paths: Paths) -> str:
    try:
        text = (_read(paths.boot_id, 256) or b"").decode().strip()
    except (OSError, Failed, UnicodeDecodeError):
        return ""
    return text if BOOT.fullmatch(text) else ""


def kernel_says_off(paths: Paths) -> bool:
    try:
        return KERNEL_OFF in (_read(paths.cmdline, 1 << 16) or b"").decode("utf-8", "replace").split()
    except (OSError, Failed):
        return False


def automatic_login(paths: Paths) -> bool:
    """GDM logs someone in by itself (automatic or timed login): then no one types a
    password on the login screen, and no login is not a sign of trouble."""
    for path in paths.gdm_confs:
        try:
            text = (_read(path) or b"").decode("utf-8", "replace")
        except (OSError, Failed):
            continue
        section, keys = "", {}
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in "#;":
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip().lower()
                continue
            k, sep, v = line.partition("=")
            if sep and section == "daemon":
                keys[k.strip().lower()] = v.strip()
        for flag, who in (("automaticloginenable", "automaticlogin"), ("timedloginenable", "timedlogin")):
            if keys.get(flag, "").lower() in ("true", "1", "yes") and keys.get(who, ""):
                return True
    return False


# ---- on -------------------------------------------------------------------------------

def _paint_glass_on(paths: Paths) -> bool:
    """The painted login glass of earlier versions keeps its record here while it is on (or
    half on); its own undo settles either."""
    return os.path.lexists(paths.old_state)


def _install(paths: Paths, txn: Txn, st: dict, a: Assessment, picture: bytes | None, work: str,
             st_prev: dict | None) -> None:
    """Config files, state, switch, check, in that order, all through txn."""
    plan = a.plan
    values = st["values"]
    for d in (paths.conf_parent, paths.conf_dir):
        txn.mkdir(d)
    names = {"jpg": "picture.jpg", "png": "picture.png"}
    keep = names.get(st["picture"]) if values["picture"] == "wallpaper" else None
    if keep:
        conf_pic, kept_pic = os.path.join(paths.conf_dir, keep), os.path.join(paths.state_dir, keep)
        if picture is None:
            # The guard heals the picture from root's own copy.
            have = _read_regular(conf_pic, MAX_PICTURE)
            if have is None or sha256_bytes(have) != st["picture_sha256"]:
                picture = _read_regular(kept_pic, MAX_PICTURE)
                if picture is None or sha256_bytes(picture) != st["picture_sha256"]:
                    raise Failed("the login screen's picture is missing")
                txn.write(conf_pic, picture)
        else:
            txn.write(conf_pic, picture)
            txn.write(kept_pic, picture)
    for name in names.values():
        if name != keep:
            txn.remove(os.path.join(paths.conf_dir, name))
            txn.remove(os.path.join(paths.state_dir, name))
    look = look_json(st["token"], values)
    if _read_regular(os.path.join(paths.conf_dir, "look.json")) != look:
        txn.write(os.path.join(paths.conf_dir, "look.json"), look)
    # Recorded before the switch, with what it will create, so a stop half way is cleaned up.
    st["route"], st["db"] = plan.route, plan.db
    st["made"] = sorted(set((st_prev or {}).get("made", [])) | set(_made_paths(paths, plan)))[:20]
    st["profile"] = plan.profile_info
    save_state(paths, txn, st)
    if st["state"] == "trial":
        if not os.path.isfile(paths.trial):
            txn.write(paths.trial, b"")
    else:
        txn.remove(paths.trial)
    write_switch(paths, txn, plan, {**values, "_kind": st["picture"] or "jpg"}, st_prev)
    post_check(paths, work)


def _new_state(values: dict, a: Assessment, kind: str, pic_sha: str) -> dict:
    return {"version": 1, "state": "trial", "token": secrets.token_hex(16), "values": values,
            "picture": kind, "picture_sha256": pic_sha, "addon_sha256": a.addon, "gnome": a.gnome,
            "gnome_full": a.gnome_full,
            "trial_boots": 0, "silent_boots": 0, "last_boot": "", "route": "", "db": "", "made": [],
            "profile": None, "started": _now()}


def turn_on(paths: Paths, values: dict, picture: tuple[bytes, str] | None) -> tuple[int, str]:
    """Returns (exit code, message)."""
    with Lock(paths), Scratch(paths) as work:
        if os.path.lexists(paths.leaving):
            # An off that did not get all the way: it is finished first, and only a system
            # with nothing of the switch left starts again from scratch.
            problems = _off_locked(paths, None, keep_stopped=True)
            if os.path.lexists(paths.leaving):
                return 4, "an earlier off is not finished: " + "; ".join(problems)
        try:
            st_prev = read_state(paths)
        except Garbled:
            st_prev = None
        a = assess(paths, st_prev, work)
        if not a.ok:
            return 3, a.why
        if not guard_enabled(paths):
            # Without the boot guard nothing would turn it off by itself: never on without it.
            return 4, f"the boot guard ({GUARD_UNIT}) is not installed or not enabled"
        kind, pic_sha = ("", "")
        if values["picture"] == "wallpaper":
            kind, pic_sha = picture[1], sha256_bytes(picture[0])
        same = (st_prev is not None and st_prev["addon_sha256"] == a.addon and st_prev["gnome"] == a.gnome
                and st_prev.get("gnome_full", "") == a.gnome_full)
        if same:
            # A new look keeps "on" (no new trial), by choice: bounded values, crash notes still count.
            st = {**st_prev, "values": values, "picture": kind, "picture_sha256": pic_sha, "gnome_full": a.gnome_full}
        else:
            st = _new_state(values, a, kind, pic_sha)
        txn = Txn()
        try:
            _install(paths, txn, st, a, picture[0] if picture else None, work, st_prev)
            txn.remove(paths.stopped)
            # Last: the painted glass of earlier versions goes only once the new glass is in
            # and checked, so a failure of ours never leaves the person with neither.
            _take_off_painted_glass(paths)
        except Unavailable as e:
            problems = txn.rollback()
            return (4 if problems else 3), e.why if not problems else f"{e}; could not undo: {problems[0]}"
        except BaseException as e:
            problems = txn.rollback()
            if not isinstance(e, Exception):
                raise
            return 4, f"{e}" + (f"; could not undo: {problems[0]}" if problems else "")
    _arm_check(paths)
    return 0, st["state"]


def _take_off_painted_glass(paths: Paths) -> None:
    """Run the earlier version's own undo while its record is there; Failed when it fails or
    its record stays (then the caller rolls the new glass back too)."""
    if not _paint_glass_on(paths):
        return
    try:
        ok = _run([paths.old_helper, "undo"], timeout=120).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if not ok or _paint_glass_on(paths):
        raise Failed("the painted login glass of an earlier version could not be taken off")


def _watch(paths: Paths, verb: str) -> None:
    """Best effort: start or stop the path unit that watches for the first login. Only
    where systemd runs (not in a chroot, a container or an image being built)."""
    if not os.path.isdir(paths.run_systemd):
        return
    try:
        _run([paths.systemctl, "--no-block", verb, CHECK_PATH_UNIT], timeout=10)
    except (OSError, subprocess.SubprocessError, Failed):
        pass


def _arm_check(paths: Paths) -> None:
    """Start the watching now, for a trial that starts in this boot."""
    _watch(paths, "start")


def _disarm_check(paths: Paths) -> None:
    """No trial is left, so there is nothing to watch for. Left running, the path unit
    would go on starting a check that has nothing to do at every change of the session
    list, with a line in the journal each time."""
    if not os.path.lexists(paths.trial):
        _watch(paths, "stop")


# ---- off ------------------------------------------------------------------------------

def _step(problems: list[str], what: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception as e:  # noqa: BLE001 - every step on its own, as far as it gets
        problems.append(f"{what}: {e}")


def _remove_switch(paths: Paths, made: list[str], again: set[str] | frozenset[str] = frozenset()) -> None:
    """Our keyfile and locks out of every db folder, and those dbs compiled again. The dbs
    in `again` (the one on record, and those an unfinished off noted) are compiled again
    even with no file of ours left in them: an earlier off may have been stopped before
    its compile. Our own db goes whether or not a file of ours is left in it (a route move
    cut short by a power loss can leave it empty)."""
    problems = []
    for name in _d_dirs(paths):
        ours = _ours_in(paths, name)
        compiled = os.path.join(paths.db_dir, name)
        if not (ours or name == OWN_DB or (name in again and os.path.isfile(compiled))):
            continue
        for p in ours:
            _unlink(p)
        d = os.path.join(paths.db_dir, name + ".d")
        made_db = name == OWN_DB or f"/etc/dconf/db/{name}" in made
        if made_db and not _has_other_files(d):
            _unlink(compiled)
            if name == OWN_DB or f"/etc/dconf/db/{name}.d/locks" in made:
                _rmdir_if_empty(os.path.join(d, "locks"))
            if name == OWN_DB or f"/etc/dconf/db/{name}.d" in made:
                _rmdir_if_empty(d)
        else:
            _step(problems, f"compiling {name}", _compile_into, paths, None, name)
    # Our own db with no keyfile left (a stop half way).
    own = os.path.join(paths.db_dir, OWN_DB)
    if os.path.lexists(own) and not os.path.isdir(own + ".d"):
        _unlink(own)
    if problems:
        raise Failed("; ".join(problems))


def _fix_profile(paths: Paths, info: dict | None, made: list[str]) -> None:
    new = _profile_without_us(paths, info)
    if new is None:
        os.unlink(paths.etc_profile)
    elif new is not False:
        write_atomic(paths.etc_profile, new)
    if "/etc/dconf/profile" in made:
        _rmdir_if_empty(paths.profile_dir)


def _remove_conf(paths: Paths) -> None:
    if os.path.islink(paths.conf_dir):
        os.unlink(paths.conf_dir)
    elif os.path.lexists(paths.conf_dir):
        shutil.rmtree(paths.conf_dir)
    _rmdir_if_empty(paths.conf_parent)


def switch_gone(paths: Paths) -> list[str]:
    left = [f"/etc/dconf/db/{n}.d" for n in _d_dirs(paths) if _ours_in(paths, n)]
    if os.path.lexists(os.path.join(paths.db_dir, OWN_DB)):
        left.append(f"/etc/dconf/db/{OWN_DB}")
    try:
        text = (_read_regular(paths.etc_profile) or b"").decode("utf-8", "replace")
    except Failed:
        text = ""
    if any(x.strip() == PROFILE_LINE for x in text.splitlines()):
        left.append("/etc/dconf/profile/gdm")
    return left


def _leaving_dbs(paths: Paths) -> set[str]:
    """The dbs an unfinished off noted in its flag (any other contents: none)."""
    try:
        data = _read_regular(paths.leaving)
        x = json.loads(data.decode("utf-8")) if data else {}
    except (Failed, ValueError, UnicodeDecodeError):
        return set()
    dbs = x.get("dbs") if isinstance(x, dict) else None
    if not isinstance(dbs, list):
        return set()
    return {n for n in dbs[:64] if isinstance(n, str) and NAME.fullmatch(n)}


def _mark_leaving(paths: Paths, dbs: set[str]) -> None:
    _make_state_dirs(paths)
    write_atomic(paths.leaving, (json.dumps({"dbs": sorted(dbs)}) + "\n").encode())


def _off_locked(paths: Paths, reason: str | None, keep_stopped: bool = False) -> list[str]:
    """Every step on its own, as far as each gets, on a damaged system too. Returns the
    problems; "still there: ..." among them means the switch is not (verifiably) gone.
    reason: why the guard turned it off (None: a person did). keep_stopped: finishing an
    earlier off, whose stopped.json (its reason, or none) stays as it is."""
    problems: list[str] = []
    st = _lenient_state(paths)
    made = st.get("made", [])
    # First, before anything is taken away: an off that stops half way stays an off, and
    # the flag names every db that holds the switch now, so finishing it compiles each one
    # again even once our files are out of it and state.json is lost.
    again = _leaving_dbs(paths) | {n for n in _d_dirs(paths) if _ours_in(paths, n)}
    if st.get("db"):
        again.add(st["db"])
    _step(problems, "the leaving flag", _mark_leaving, paths, again)
    _step(problems, "the dconf switch", _remove_switch, paths, made, again)
    compiled = not problems                       # a db that could not be recompiled still holds our keys
    _step(problems, "the dconf profile", _fix_profile, paths, st.get("profile"), made)
    for d in ("/etc/dconf/db", "/etc/dconf"):
        if d in made:
            _rmdir_if_empty(paths.p(d))
    _step(problems, "the look", _remove_conf, paths)
    left = switch_gone(paths) + ([] if compiled else ["a dconf db that still holds the switch"])
    if left:
        problems.append("still there: " + ", ".join(left))
    for name in ("picture.jpg", "picture.png"):
        _step(problems, "root's copy of the picture", _unlink, os.path.join(paths.state_dir, name))
    if reason is None and not keep_stopped:
        _step(problems, "stopped.json", _unlink, paths.stopped)
    elif not keep_stopped:
        _step(problems, "stopped.json", write_atomic, paths.stopped,
              (json.dumps({"reason": reason, "when": _now()}) + "\n").encode())
    if not left:
        # Kept while any of the switch is left, so the guard tries again at the next boot.
        _step(problems, "state.json", _unlink, paths.state)
        _step(problems, "the trial flag", _unlink, paths.trial)
        # Last, and only once state.json is gone: without the flag a state.json left behind
        # would read as "on" again.
        if not os.path.lexists(paths.state):
            _step(problems, "the leaving flag", _unlink, paths.leaving)
    return problems


def turn_off(paths: Paths, reason: str | None = None) -> list[str]:
    with Lock(paths):
        problems = _off_locked(paths, reason)
    _disarm_check(paths)
    return problems


# ---- the guard ------------------------------------------------------------------------

def guard_boot(paths: Paths) -> str:
    """Every boot before the display manager, while state.json (or the leaving flag) is
    there. Returns what it did."""
    try:
        lock = Lock(paths, wait=GUARD_LOCK_WAIT)
        lock.__enter__()
    except Exception:  # noqa: BLE001 - never hold up the boot
        try:
            return _guard_boot_unlocked(paths)
        except Exception:  # noqa: BLE001
            return "busy"
    try:
        try:
            return _guard_boot(paths)
        except Exception:  # noqa: BLE001 - anything unexpected: take it away
            _off_locked(paths, "error")
            return "off: error"
    finally:
        lock.__exit__()


def _crashed(notes: list[dict], boot: str) -> bool:
    """A note (of the token on record) says the last start crashed or failed; a `starting`
    still there from an earlier boot never finished."""
    return any(n["phase"] in ("safe", "error") or (n["phase"] == "starting" and n["boot"] != boot) for n in notes)


def _guard_boot_unlocked(paths: Paths) -> str:
    """The lock could not be taken (a change hung, or root's state folder is damaged): the
    signs that must never wait still count, and turn it off without the lock."""
    if os.path.lexists(paths.leaving):
        _off_locked(paths, None, keep_stopped=True)
        return "off: leaving"
    if not os.path.lexists(paths.state):
        return "busy"
    if kernel_says_off(paths):
        _off_locked(paths, "kernel-arg")
        return "off: kernel-arg"
    try:
        st = read_state(paths)
    except Garbled:
        st = None
    if st is not None and _crashed([n for n in read_notes(paths) if n["token"] == st["token"]], boot_id(paths)):
        _off_locked(paths, "crash")
        return "off: crash"
    return "busy"


def _guard_boot(paths: Paths) -> str:
    if os.path.lexists(paths.leaving):
        # An off was asked for and did not finish: finish it, never put anything back.
        _off_locked(paths, None, keep_stopped=True)
        return "off: leaving"
    try:
        st = read_state(paths)
    except Garbled:
        _off_locked(paths, "error")
        return "off: error"
    if st is None:
        return "nothing"
    if kernel_says_off(paths):
        _off_locked(paths, "kernel-arg")
        return "off: kernel-arg"
    prev = json.loads(json.dumps(st))             # as it was, for what the switch has to take back
    with Scratch(paths) as work:
        a = assess(paths, st, work)
        if not a.ok:
            reason = "gnome-version" if a.why == "gnome-version" else "error"
            _off_locked(paths, reason)
            return f"off: {reason}"
        boot = boot_id(paths)
        notes = [n for n in read_notes(paths) if n["token"] == st["token"]]
        if _crashed(notes, boot):
            _off_locked(paths, "crash")
            return "off: crash"
        did = "kept"
        if a.addon != st["addon_sha256"] or a.gnome_full != st.get("gnome_full", ""):
            # A new add-on or any new GNOME Shell (a point release too): a fresh trial. This
            # boot already shows it, so it counts as the trial's one boot without a login (as
            # the first boot after `on` does): the next boot without one turns it off.
            st.update(token=secrets.token_hex(16), state="trial", trial_boots=1, silent_boots=0,
                      addon_sha256=a.addon, gnome=a.gnome, gnome_full=a.gnome_full)
            did = "new trial"
        elif st["state"] == "trial":
            if any(n["verified"] == st["token"] for n in notes):
                st.update(state="on", silent_boots=0)
                did = "on"
            elif automatic_login(paths):
                did = "trial (automatic login)"
            elif st["trial_boots"] >= 1:
                _off_locked(paths, "no-login")
                return "off: no-login"
            else:
                st["trial_boots"] += 1
                did = "trial"
        elif st["last_boot"]:
            # Was the login screen heard from in the boot before this one? (With no boot on
            # record there is nothing to compare with: the count starts at the next boot.)
            if any(n["boot"] == st["last_boot"] for n in notes):
                st["silent_boots"] = 0
            elif not automatic_login(paths):
                st["silent_boots"] += 1
                if st["silent_boots"] >= 3:
                    _off_locked(paths, "silent")
                    return "off: silent"
        txn = Txn()
        try:
            _install(paths, txn, st, a, None, work, prev)
        except Exception:
            txn.rollback()
            _off_locked(paths, "error")
            return "off: error"
    st["last_boot"] = boot
    write_atomic(paths.state, (json.dumps(st, sort_keys=True, indent=1) + "\n").encode())
    return did


def guard_check(paths: Paths) -> str:
    """While a trial runs, when a login session appears: a login through the glass ends the
    trial; a crash note turns it off. Once no trial is left, the watching stops."""
    did = _guard_check(paths)
    _disarm_check(paths)
    return did


def _guard_check(paths: Paths) -> str:
    try:
        with Lock(paths, wait=10):
            if os.path.lexists(paths.leaving):
                _off_locked(paths, None, keep_stopped=True)
                return "off: leaving"
            try:
                st = read_state(paths)
            except Garbled:
                return "nothing"
            if st is None or st["state"] != "trial":
                return "nothing"
            notes = [n for n in read_notes(paths) if n["token"] == st["token"]]
            if any(n["phase"] in ("safe", "error") for n in notes):
                _off_locked(paths, "crash")
                return "off: crash"
            if any(n["verified"] == st["token"] for n in notes):
                # This boot goes on record as the one the login screen was last heard from,
                # so the next boot's guard does not take it for a silent one.
                st.update(state="on", silent_boots=0, last_boot=boot_id(paths))
                write_atomic(paths.state, (json.dumps(st, sort_keys=True, indent=1) + "\n").encode())
                _unlink(paths.trial)
                return "on"
            return "nothing"
    except Exception:  # noqa: BLE001 - never fail the unit; the boot guard looks again
        return "error"


# ---- status ---------------------------------------------------------------------------

def status(paths: Paths) -> dict:
    out = {"version": 1, "available": False, "why": "", "state": "off", "stopped": "", "values": None,
           "picture_sha256": ""}
    try:
        st = read_state(paths)
    except Garbled:
        st = None
        out["state"] = "trial"          # something of it may be on; the guard sorts it out at boot
    if st is not None:
        out["state"], out["values"] = st["state"], st["values"]
    try:
        ok, why = available(paths)
    except Exception:  # noqa: BLE001 - status always answers
        ok, why = False, "policy"
    out["available"], out["why"] = ok, (why if why in WHY else "policy")
    try:
        s = json.loads((_read_regular(paths.stopped) or b"{}").decode("utf-8"))
        if isinstance(s, dict) and s.get("reason") in STOPPED:
            out["stopped"] = s["reason"]
    except (ValueError, UnicodeDecodeError, Failed, OSError):
        pass
    for name in ("picture.jpg", "picture.png"):
        try:
            data = _read_regular(os.path.join(paths.conf_dir, name), MAX_PICTURE)
        except Failed:
            data = None
        if data is not None:
            out["picture_sha256"] = sha256_bytes(data)
            break
    return out


# ---- command line ---------------------------------------------------------------------

USAGE = "Usage: fedora-glass-login status | on 'JSON' | off | guard boot | guard check"


def _on_signal(signum, frame) -> None:
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)        # once: let the roll back finish
    raise Interrupted(f"stopped by signal {signum}")


def main(argv: list[str] | None = None, stdin=None) -> int:
    os.umask(0o022)
    argv = list(sys.argv if argv is None else argv)[1:]
    paths = Paths("/")
    if argv == ["status"]:
        print(json.dumps(status(paths), sort_keys=True))
        return 0
    if not (argv in (["off"], ["guard", "boot"], ["guard", "check"]) or (len(argv) == 2 and argv[0] == "on")):
        print(USAGE, file=sys.stderr)
        return 2
    if os.geteuid() != 0:
        print("This needs root: run it through pkexec or sudo.", file=sys.stderr)
        return 77
    if argv[0] == "guard":
        try:
            signal.signal(signal.SIGTERM, _on_signal)
            did = guard_boot(paths) if argv[1] == "boot" else guard_check(paths)
        except BaseException as e:  # noqa: BLE001 - the guard never fails the boot
            did = f"error: {type(e).__name__}"
        print(f"fedora-glass-login guard {argv[1]}: {did}")
        return 0
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_signal)
    if argv == ["off"]:
        try:
            problems = turn_off(paths)
        except (Failed, OSError) as e:
            problems = [str(e)]
        for p in problems:
            print(f"fedora-glass-login off: {p}", file=sys.stderr)
        return 4 if any(p.startswith("still there") for p in problems) or switch_gone(paths) else 0
    try:
        values = parse_values(argv[1])
        picture = None
        if values["picture"] == "wallpaper":
            picture = read_picture(stdin if stdin is not None else sys.stdin.buffer)
    except BadInput as e:
        print(f"fedora-glass-login on: {e}", file=sys.stderr)
        return 2
    try:
        code, msg = turn_on(paths, values, picture)
    except (Failed, OSError) as e:
        code, msg = 4, str(e)
    print(msg, file=sys.stdout if code in (0, 3) else sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
