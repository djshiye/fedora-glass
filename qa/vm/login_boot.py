#!/usr/bin/env python3
"""The real-boot lane for the glass login screen: boots a real Fedora, Ubuntu or Arch in a
virtual machine with a real GDM, turns the glass on with the real package, logs in for real
through the login screen, and breaks the glass on purpose to show nobody is ever locked out.

    python3 -I qa/vm/login_boot.py --distro fedora-45 --out /tmp/login-boot

Runs on a Linux PC with KVM (GitHub's ubuntu-latest runners have it). Standard library only;
it needs qemu-system-x86_64, qemu-img, genisoimage (or xorriso), ssh, ssh-keygen and gpg.
The guest is driven over SSH (qa/vm/guest/probe.py answers its questions) and its screen over
QEMU's QMP socket: `screendump` for pictures, `send-key` to type on the login screen.
See qa/vm/README.md for what each step proves.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
UUID = "fedora-glass-login@djshiye.github.io"
HELPER = "/usr/libexec/fedora-glass-login"
USER = "tester"
# Lower-case letters and digits only: every one is a plain key press, whatever the layout.
PASSWORD = "glasstest1"
SSH_PORT = 2222
GUEST_DIR = f"/home/{USER}/lgv"
ADDON_DIR = f"/usr/share/gdm/greeter/gnome-shell/extensions/{UUID}"
GUARD = "fedora-glass-login-guard.service"

# How different two screen pictures are (mean difference per colour channel, 0..255, of the
# pictures shrunk to 160 px wide). The glass login screen over the bright test picture must be
# far from GNOME's plain grey one; two plain ones differ only by the clock. TO CONFIRM ON
# FIRST RUN: the numbers are printed every time, so these can be tuned from a real log.
CLEARLY_DIFFERENT = 12.0
ABOUT_THE_SAME = 6.0

T0 = time.monotonic()


def log(msg: str = "") -> None:
    s = int(time.monotonic() - T0)
    for line in str(msg).splitlines() or [""]:
        print(f"[{s // 60:02d}:{s % 60:02d}] {line}", flush=True)


class StepFailed(Exception):
    pass


def check(ok, msg: str) -> None:
    """One check of a step: prints what it saw, and fails the step if it was not so."""
    log(f"  {'ok  ' if ok else 'FAIL'} {msg}")
    if not ok:
        raise StepFailed(msg)


# ===== Distributions and their cloud images =====================================================

DISTROS = {
    "fedora-45": {"family": "fedora", "release": "45"},
    "fedora-44": {"family": "fedora", "release": "44"},
    "ubuntu-26.04": {"family": "ubuntu", "release": "26.04", "codename": "resolute"},
    "ubuntu-26.10": {"family": "ubuntu", "release": "26.10", "codename": "stonking"},
    "arch": {"family": "arch", "release": "rolling"},
}

# Ubuntu's cloud images are signed with this key ("UEC Image Automatic Signing Key
# <cdimage@ubuntu.com>"), which the runner's ubuntu-keyring package has in
# /usr/share/keyrings/ubuntu-cloudimage-keyring.gpg. Seen on the SHA256SUMS.gpg of both
# releases on 2026-11-13.
UBUNTU_KEYRING = "/usr/share/keyrings/ubuntu-cloudimage-keyring.gpg"
UBUNTU_KEY = "D2EB44626FDDC30B513D5BB71A5D6C4C7DB87C81"
# The arch-boxes release key, as published in the "Releases" part of the arch-boxes README
# (https://gitlab.archlinux.org/archlinux/arch-boxes/-/blob/master/README.md); a copy is in
# qa/vm/keys/arch-boxes.asc. Primary key fingerprint (uid arch-boxes <arch-boxes@archlinux.org>):
ARCH_BOXES_KEY = "1B9A16984A4E8CB448712D2AE0B78BF4326C6F8F"
# Fedora's published keyring (all current release keys). The key that signed a CHECKSUM file
# must carry the uid "Fedora (<release>)": its fingerprint is printed, not pinned (TO CONFIRM).
FEDORA_KEYRING_URL = "https://fedoraproject.org/fedora.gpg"
ARCH_IMAGES = "https://geo.mirror.pkgbuild.com/images/latest/"


def fedora_index_urls(release: str) -> list[str]:
    """Where Fedora keeps its cloud images: a released Fedora, then one still in development."""
    base = "https://dl.fedoraproject.org/pub/fedora/linux"
    return [f"{base}/releases/{release}/Cloud/x86_64/images/",
            f"{base}/development/{release}/Cloud/x86_64/images/"]


def ubuntu_base_url(codename: str) -> str:
    return f"https://cloud-images.ubuntu.com/releases/{codename}/release/"


def links(html: str) -> list[str]:
    """The file names an index page links to (Apache and nginx listings)."""
    names = []
    for href in re.findall(r'href="([^"?#]+)"', html):
        name = href.rsplit("/", 1)[-1] if not href.endswith("/") else ""
        if name and name not in names:
            names.append(urllib.parse.unquote(name))
    return names


def _version_key(v: str) -> list:
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.\-]", v)]


def pick_fedora(names: list[str], release: str) -> tuple[str, str]:
    """The newest Generic cloud image of a Fedora release and the CHECKSUM file of its compose."""
    img = re.compile(rf"Fedora-Cloud-Base-Generic-{release}-([0-9][0-9A-Za-z.]*)\.x86_64\.qcow2")
    found = {m.group(1): n for n in names if (m := img.fullmatch(n))}
    if not found:
        raise LookupError(f"no Fedora-Cloud-Base-Generic-{release}-*.x86_64.qcow2 on the index page")
    compose = max(found, key=_version_key)
    checksum = f"Fedora-Cloud-{release}-{compose}-x86_64-CHECKSUM"
    if checksum not in names:
        raise LookupError(f"{found[compose]} is there but {checksum} is not")
    return found[compose], checksum


def pick_arch(names: list[str]) -> str:
    """The dated Arch cloud image (it does not change under us, as "latest" can), else the plain one."""
    dated = {m.group(1): n for n in names if (m := re.fullmatch(r"Arch-Linux-x86_64-cloudimg-([0-9.]+)\.qcow2", n))}
    if dated:
        return dated[max(dated, key=_version_key)]
    if "Arch-Linux-x86_64-cloudimg.qcow2" in names:
        return "Arch-Linux-x86_64-cloudimg.qcow2"
    raise LookupError("no Arch-Linux-x86_64-cloudimg*.qcow2 on the index page")


def parse_checksums(text: str) -> dict[str, str]:
    """SHA-256 sums by file name, from GNU lines ("<hex> *name", Ubuntu) or BSD lines
    ("SHA256 (name) = <hex>", Fedora). Other lines (comments, other hashes) are ignored."""
    sums = {}
    for line in text.splitlines():
        line = line.strip()
        m = re.fullmatch(r"SHA256 \((.+)\) = ([0-9a-fA-F]{64})", line)
        if m:
            sums[m.group(1)] = m.group(2).lower()
            continue
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if m:
            sums[m.group(2)] = m.group(1).lower()
    return sums


def parse_gpg_status(text: str) -> dict:
    """What `gpg --status-fd` said about a signature: good or not, and by which key."""
    good = bad = False
    fpr = primary = ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "[GNUPG:]":
            continue
        if parts[1] == "GOODSIG":
            good = True
        elif parts[1] in ("BADSIG", "ERRSIG", "EXPKEYSIG", "REVKEYSIG", "NO_PUBKEY"):
            bad = True
        elif parts[1] == "VALIDSIG" and len(parts) >= 3:
            fpr = parts[2]
            primary = parts[11] if len(parts) >= 12 else parts[2]
    return {"good": good and not bad and bool(fpr), "fpr": fpr, "primary": primary}


# ===== Downloads and signatures ==================================================================

def fetch(url: str, dest: Path | None = None, tries: int = 3) -> bytes | str:
    """Downloads `url` (into `dest` when given, returning its SHA-256), with a few tries."""
    for n in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "login-boot-test"})
            with urllib.request.urlopen(req, timeout=60) as r:
                if dest is None:
                    return r.read()
                h, done, shown = hashlib.sha256(), 0, 0
                with open(dest, "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                        h.update(chunk)
                        done += len(chunk)
                        if done - shown >= 200 << 20:
                            shown = done
                            log(f"  ... {done >> 20} MiB")
                log(f"  got {dest.name}: {done >> 20} MiB")
                return h.hexdigest()
        except urllib.error.HTTPError as e:
            if e.code == 404 or n == tries:
                raise
            log(f"  {url}: HTTP {e.code}, trying again")
        except (urllib.error.URLError, OSError) as e:
            if n == tries:
                raise
            log(f"  {url}: {e}, trying again")
        time.sleep(5 * n)
    raise AssertionError("unreachable")


def dearmor(data: bytes) -> bytes:
    """The binary keys in an ASCII-armored key file (several blocks allowed); binary input as is."""
    if b"-----BEGIN PGP PUBLIC KEY BLOCK-----" not in data:
        return data
    out, body, state = b"", [], "out"
    for line in data.decode("ascii", "replace").splitlines():
        line = line.strip()
        if line == "-----BEGIN PGP PUBLIC KEY BLOCK-----":
            state, body = "head", []
        elif state == "head":
            if not line:
                state = "body"
            elif ":" not in line:              # no header lines at all: this is data already
                state = "body"
                body.append(line)
        elif state == "body":
            if line.startswith("-----END PGP PUBLIC KEY BLOCK"):
                out += base64.b64decode("".join(body))
                state = "out"
            elif not line.startswith("="):     # "=XXXX" is the checksum line
                body.append(line)
    return out


def key_uids(colons: str) -> dict[str, list[str]]:
    """Primary key fingerprint -> its user ids, from `gpg --show-keys --with-colons`."""
    keys, current, want_fpr = {}, None, False
    for line in colons.splitlines():
        f = line.split(":")
        if f[0] == "pub":
            want_fpr = True
        elif f[0] == "fpr" and want_fpr:
            current, want_fpr = f[9], False
            keys[current] = []
        elif f[0] == "uid" and current:
            keys[current].append(f[9])
    return keys


class Gpg:
    """Signature checks with gpgv against a keyring of only the keys a check trusts. gpgv
    needs no GnuPG home and starts no agent."""

    def __init__(self, work: Path):
        self.work = work

    def keyring(self, sources: list[Path], name: str) -> Path:
        ring = self.work / f"{name}.keyring"
        ring.write_bytes(b"".join(dearmor(p.read_bytes()) for p in sources))
        return ring

    def verify(self, ring: Path, signed: Path, sig: Path | None = None, plain_out: Path | None = None) -> dict:
        argv = ["gpgv", "--status-fd", "1", "--keyring", str(ring.resolve())]
        if sig is not None:
            argv += [str(sig), str(signed)]
        else:
            # A clear-signed file: what counts is only the signed text gpgv hands back, never
            # anything put around it.
            argv += ["--output", str(plain_out), str(signed)]
        r = subprocess.run(argv, capture_output=True, text=True)
        st = parse_gpg_status(r.stdout)
        if r.returncode != 0 or not st["good"]:
            raise RuntimeError(f"signature check of {signed.name} failed:\n{r.stdout}\n{r.stderr}")
        return st

    def uids(self, ring: Path) -> dict[str, list[str]]:
        home = self.work / "gnupg"
        home.mkdir(mode=0o700, exist_ok=True)
        r = subprocess.run(["gpg", "--homedir", str(home), "--batch", "--no-tty", "--no-autostart", "--show-keys",
                            "--with-colons", str(ring)], capture_output=True, text=True)
        return key_uids(r.stdout)


def find_image(distro: str, work: Path) -> dict:
    """Finds the distribution's official cloud image and its checked SHA-256 (nothing big is
    downloaded yet). Every name, URL and key it settles on is printed."""
    d = DISTROS[distro]
    keys = work / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    gpg = Gpg(keys)
    if d["family"] == "fedora":
        last = None
        for index in fedora_index_urls(d["release"]):
            try:
                names = links(fetch(index).decode("utf-8", "replace"))
                image, checksum = pick_fedora(names, d["release"])
                break
            except (urllib.error.HTTPError, LookupError) as e:
                log(f"  {index}: {e}")
                last = e
        else:
            raise RuntimeError(f"no Fedora {d['release']} cloud image found: {last}")
        log(f"  image {index}{image}")
        log(f"  checksum file {index}{checksum}")
        signed = work / checksum
        signed.write_bytes(fetch(index + checksum))
        published = keys / "fedora.gpg"
        published.write_bytes(fetch(FEDORA_KEYRING_URL))
        ring = gpg.keyring([published], "fedora")
        st = gpg.verify(ring, signed, plain_out=work / (checksum + ".signed"))
        uids = gpg.uids(ring).get(st["primary"], [])
        log(f"  CHECKSUM signed by {st['primary']} ({'; '.join(uids)})  [TO CONFIRM ON FIRST RUN]")
        if not any(f"Fedora ({d['release']})" in u for u in uids):
            raise RuntimeError(f"CHECKSUM was signed by a key that is not Fedora {d['release']}'s: {uids}")
        sums = parse_checksums((work / (checksum + ".signed")).read_text())
        url = index + image
    elif d["family"] == "ubuntu":
        base = ubuntu_base_url(d["codename"])
        image = f"ubuntu-{d['release']}-server-cloudimg-amd64.img"
        (work / "SHA256SUMS").write_bytes(fetch(base + "SHA256SUMS"))
        (work / "SHA256SUMS.gpg").write_bytes(fetch(base + "SHA256SUMS.gpg"))
        ring = gpg.keyring([Path(UBUNTU_KEYRING)], "ubuntu")
        st = gpg.verify(ring, work / "SHA256SUMS", sig=work / "SHA256SUMS.gpg")
        log(f"  SHA256SUMS signed by {st['primary']} (expected {UBUNTU_KEY})")
        if st["primary"] != UBUNTU_KEY:
            raise RuntimeError(f"SHA256SUMS signed by {st['primary']}, not Ubuntu's cloud image key")
        sums = parse_checksums((work / "SHA256SUMS").read_text())
        url = base + image
    else:
        names = links(fetch(ARCH_IMAGES).decode("utf-8", "replace"))
        image = pick_arch(names)
        url = ARCH_IMAGES + image
        ring = gpg.keyring([HERE / "keys" / "arch-boxes.asc"], "arch-boxes")
        sig = work / (image + ".sig")
        sig.write_bytes(fetch(url + ".sig"))
        log(f"  image {url}")
        # The signature is checked once the image is here; its SHA-256 is printed for the log.
        return {"url": url, "name": image, "sha256": None, "gpg": gpg, "ring": ring, "sig": sig}
    if image not in sums:
        raise RuntimeError(f"{image} is not in the signed checksum list")
    log(f"  sha256 {sums[image]} (from the signed list)")
    return {"url": url, "name": image, "sha256": sums[image]}


def get_image(distro: str, work: Path) -> Path:
    log(f"Finding the official {distro} cloud image")
    info = find_image(distro, work)
    dest = work / info["name"]
    log(f"Downloading {info['url']}")
    got = fetch(info["url"], dest)
    log(f"  sha256 of the download: {got}")
    if info["sha256"] is not None:
        if got != info["sha256"]:
            raise RuntimeError(f"{dest.name}: sha256 {got}, the signed list says {info['sha256']}")
        log("  matches the signed list")
    else:
        st = info["gpg"].verify(info["ring"], dest, sig=info["sig"])
        log(f"  signed by {st['fpr']} (primary {st['primary']}, expected {ARCH_BOXES_KEY})")
        if st["primary"] != ARCH_BOXES_KEY:
            raise RuntimeError(f"{dest.name} was signed by {st['primary']}, not the arch-boxes key")
    return dest


# ===== Screen pictures (PPM from QEMU, PNG out), pure Python ======================================

class Picture:
    def __init__(self, width: int, height: int, rgb: bytes):
        assert len(rgb) == width * height * 3, (width, height, len(rgb))
        self.width, self.height, self.rgb = width, height, rgb


def read_ppm(data: bytes) -> Picture:
    """A binary PPM (P6, 8 bits), as QEMU's screendump writes it."""
    fields, pos = [], 0
    while len(fields) < 4:
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[pos:end])
        pos = end
    if fields[0] != b"P6" or int(fields[3]) != 255:
        raise ValueError(f"not an 8-bit P6 picture: {fields}")
    w, h = int(fields[1]), int(fields[2])
    pos += 1                                   # the single white space after the maximum value
    return Picture(w, h, data[pos:pos + w * h * 3])


def png_bytes(pic: Picture) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    stride = pic.width * 3
    raw = b"".join(b"\x00" + pic.rgb[y * stride:(y + 1) * stride] for y in range(pic.height))
    ihdr = struct.pack(">IIBBBBB", pic.width, pic.height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def shrink(pic: Picture, width: int) -> Picture:
    """Box-averaged copy `width` pixels wide (never wider than the picture)."""
    width = max(1, min(width, pic.width))
    height = max(1, round(pic.height * width / pic.width))
    out = bytearray(width * height * 3)
    stride = pic.width * 3
    xs = [(x * pic.width // width, max(x * pic.width // width + 1, (x + 1) * pic.width // width)) for x in range(width)]
    for y in range(height):
        y0 = y * pic.height // height
        y1 = max(y0 + 1, (y + 1) * pic.height // height)
        for x, (x0, x1) in enumerate(xs):
            n = (y1 - y0) * (x1 - x0)
            for c in range(3):
                s = 0
                for yy in range(y0, y1):
                    row = yy * stride
                    s += sum(pic.rgb[row + x0 * 3 + c:row + x1 * 3:3])
                out[(y * width + x) * 3 + c] = s // n
    return Picture(width, height, bytes(out))


def mean_colour(pic: Picture) -> tuple[int, int, int]:
    n = pic.width * pic.height
    return tuple(sum(pic.rgb[c::3]) // n for c in range(3))


def difference(a: Picture, b: Picture, width: int = 160) -> float:
    """Mean difference per colour channel (0..255) of the two pictures shrunk to the same size."""
    a, b = shrink(a, width), shrink(b, width)
    if (a.width, a.height) != (b.width, b.height):
        b = _resize_to(b, a.width, a.height)
    return sum(abs(x - y) for x, y in zip(a.rgb, b.rgb)) / len(a.rgb)


def _resize_to(p: Picture, w: int, h: int) -> Picture:
    """Nearest-pixel copy at w x h (for two screens of different shape, which should not happen)."""
    out = bytearray()
    for y in range(h):
        sy = y * p.height // h
        for x in range(w):
            sx = x * p.width // w
            i = (sy * p.width + sx) * 3
            out += p.rgb[i:i + 3]
    return Picture(w, h, bytes(out))


def thumbnail_block(pic: Picture, name: str, width: int = 240) -> str:
    """A small PNG as base64 between marker lines, for the job log: copy the lines between the
    markers into a file and run `base64 -d file > picture.png` to see the screen."""
    small = shrink(pic, width)
    data = base64.b64encode(png_bytes(small)).decode()
    lines = [f"----- BEGIN PNG {name} ({small.width}x{small.height}) -----"]
    lines += [data[i:i + 76] for i in range(0, len(data), 76)]
    lines.append(f"----- END PNG {name} -----")
    return "\n".join(lines)


# ===== Keys for QMP send-key ======================================================================

# QEMU's QKeyCode names (qapi/ui.json) for what the test types.
_QCODES = {**{c: c for c in "abcdefghijklmnopqrstuvwxyz0123456789"},
           " ": "spc", "-": "minus", ".": "dot", "\n": "ret"}


def keys_for_text(text: str) -> list[str]:
    """One QKeyCode per character; only plain unshifted keys, so no layout or Shift can change them."""
    out = []
    for ch in text:
        if ch not in _QCODES:
            raise ValueError(f"cannot type {ch!r} with a plain key")
        out.append(_QCODES[ch])
    return out


def qmp_message(command: str, **arguments) -> bytes:
    msg = {"execute": command}
    if arguments:
        msg["arguments"] = arguments
    return (json.dumps(msg) + "\r\n").encode()


def send_key_message(keys: list[str], hold_ms: int = 60) -> bytes:
    return qmp_message("send-key", keys=[{"type": "qcode", "data": k} for k in keys], **{"hold-time": hold_ms})


class Qmp:
    @classmethod
    def connect(cls, path: Path, timeout: float = 30) -> "Qmp":
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(str(path))
        return cls(sock)

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.buf = b""
        greeting = self._read()
        if "QMP" not in greeting:
            raise RuntimeError(f"not a QMP greeting: {greeting}")
        self.execute("qmp_capabilities")

    def _read(self) -> dict:
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("QMP socket closed")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def _send(self, raw: bytes) -> dict:
        self.sock.sendall(raw)
        while True:
            msg = self._read()
            if "event" in msg:
                log(f"  (QEMU event {msg['event']})")
                continue
            if "error" in msg:
                raise RuntimeError(f"QMP error: {msg['error']}")
            if "return" in msg:
                return msg["return"]

    def execute(self, command: str, **arguments):
        return self._send(qmp_message(command, **arguments))

    def send_keys(self, keys: list[str], hold_ms: int = 60):
        return self._send(send_key_message(keys, hold_ms))

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


# ===== The step planner ==========================================================================

# Each step and the steps it builds on. A step whose groundwork failed is skipped (and the run
# fails anyway); the steps that break the glass on purpose start from a clean state of their
# own, so they still run when an earlier step failed. "removal" takes the package away: last.
STEPS: list[tuple[str, tuple[str, ...]]] = [
    ("baseline", ()),
    ("on", ("baseline",)),
    ("glass", ("on",)),
    ("login", ("glass",)),
    ("update", ("login",)),
    ("restart", ("update",)),
    ("off", ("on",)),
    ("crash", ("baseline",)),
    ("broken-addon", ("baseline",)),
    ("no-login", ("baseline",)),
    ("removal", ("baseline",)),
]
NEEDS = dict(STEPS)
ORDER = [name for name, _ in STEPS]


def plan(selected: list[str] | None = None) -> list[str]:
    """The steps to run, in order, with everything they build on."""
    if not selected:
        return list(ORDER)
    unknown = [s for s in selected if s not in NEEDS]
    if unknown:
        raise ValueError(f"unknown steps: {', '.join(unknown)} (known: {', '.join(ORDER)})")
    want = set()

    def add(s):
        if s not in want:
            want.add(s)
            for n in NEEDS[s]:
                add(n)
    for s in selected:
        add(s)
    return [s for s in ORDER if s in want]


def blocked_by(step: str, results: dict[str, str]) -> str:
    """The step this one builds on that did not pass, or ''."""
    for n in NEEDS[step]:
        if results.get(n) != "PASS":
            return n
    return ""


# ===== Comparisons of guest state =================================================================

def listing_differences(before: list[dict], after: list[dict]) -> list[str]:
    """What changed under /etc/dconf. A compiled database is compared by being there (and its
    mode and owner), not by its bytes: `dconf update` may write the same settings differently."""
    a = {e["path"]: e for e in before}
    b = {e["path"]: e for e in after}
    out = []
    for p in sorted(set(a) | set(b)):
        if p not in b:
            out.append(f"gone: {p}")
        elif p not in a:
            out.append(f"new: {p}")
        else:
            x, y = dict(a[p]), dict(b[p])
            if x.get("compiled") and y.get("compiled"):
                x.pop("sha256", None)
                y.pop("sha256", None)
            for k in sorted(set(x) | set(y)):
                if x.get(k) != y.get(k):
                    out.append(f"changed {k}: {p} ({x.get(k)} -> {y.get(k)})")
    return out


def greeters(state: dict) -> list[dict]:
    return [s for s in state["sessions"] if s["class"] == "greeter"]


def user_sessions(state: dict, user: str = USER) -> list[dict]:
    """The user's sessions on the screen. Its SSH sessions (type tty), the ones this driver
    talks through, don't count."""
    return [s for s in state["sessions"] if s["user"] == user and s["class"] == "user" and s["type"] in ("wayland", "x11")]


def cloud_init_seed(pubkey: str, instance: str) -> tuple[str, str]:
    """NoCloud user-data and meta-data: the one test user, its key and its password."""
    user_data = "\n".join([
        "#cloud-config",
        "users:",
        f"  - name: {USER}",
        "    gecos: Glass Tester",
        "    shell: /bin/bash",
        "    lock_passwd: false",
        f"    plain_text_passwd: {PASSWORD}",
        "    sudo: \"ALL=(ALL) NOPASSWD:ALL\"",
        "    ssh_authorized_keys:",
        f"      - {pubkey.strip()}",
        "ssh_pwauth: false",
        "chpasswd:",
        "  expire: false",
        "package_update: false",
        "package_upgrade: false",
        "",
    ])
    meta_data = f"instance-id: {instance}\nlocal-hostname: glass-test\n"
    return user_data, meta_data


# ===== The virtual machine ========================================================================

class VM:
    def __init__(self, distro: str, out: Path, work: Path):
        self.distro, self.out, self.work = distro, out, work
        self.family = DISTROS[distro]["family"]
        self.proc: subprocess.Popen | None = None
        self.qmp: Qmp | None = None
        self.key = work / "id_ed25519"
        self.serial = out / "serial.log"
        self.journals = 0
        self.gdm_unit = "gdm.service"

    # --- set-up ---
    def prepare(self, image: Path, disk_gb: int = 20) -> None:
        log("Making the disk (a qcow2 overlay on the image) and the cloud-init seed")
        fmt = json.loads(subprocess.run(["qemu-img", "info", "--output=json", str(image)], check=True,
                                        capture_output=True, text=True).stdout)["format"]
        self.disk = self.work / "disk.qcow2"
        subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", "-F", fmt, "-b", str(image), str(self.disk),
                        f"{disk_gb}G"], check=True)
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "login-boot", "-f", str(self.key)], check=True)
        seed = self.work / "seed"
        seed.mkdir(exist_ok=True)
        ud, md = cloud_init_seed(self.key.with_suffix(".pub").read_text(), f"lgv-{self.distro}-{int(time.time())}")
        (seed / "user-data").write_text(ud)
        (seed / "meta-data").write_text(md)
        self.seed = self.work / "seed.iso"
        tool = shutil.which("genisoimage") or shutil.which("mkisofs")
        if tool:
            argv = [tool]
        elif shutil.which("xorriso"):
            argv = ["xorriso", "-as", "mkisofs"]
        else:
            raise RuntimeError("needs genisoimage, mkisofs or xorriso for the cloud-init seed")
        subprocess.run(argv + ["-quiet", "-output", str(self.seed), "-volid", "cidata", "-joliet", "-rock",
                               str(seed / "user-data"), str(seed / "meta-data")], check=True)

    def start(self) -> None:
        self.qmp_path = self.work / "qmp.sock"
        argv = ["qemu-system-x86_64", "-name", f"lgv-{self.distro}", "-machine", "q35", "-enable-kvm",
                "-cpu", "host", "-smp", "4", "-m", "6G",
                "-drive", f"file={self.disk},if=virtio,format=qcow2",
                "-drive", f"file={self.seed},if=virtio,format=raw,readonly=on",
                "-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{SSH_PORT}-:22",
                "-device", "virtio-net-pci,netdev=n0",
                "-device", "virtio-vga", "-display", "none",
                "-device", "virtio-rng-pci",
                "-qmp", f"unix:{self.qmp_path},server=on,wait=off",
                "-serial", f"file:{self.serial}"]
        log("Starting the VM: " + " ".join(argv))
        self.proc = subprocess.Popen(argv, stdout=open(self.out / "qemu.log", "wb"), stderr=subprocess.STDOUT)
        for _ in range(100):
            if self.qmp_path.exists():
                break
            if self.proc.poll() is not None:
                raise RuntimeError(f"QEMU stopped at once:\n{(self.out / 'qemu.log').read_text()}")
            time.sleep(0.1)
        self.qmp = Qmp.connect(self.qmp_path)
        log(f"  QEMU {self.qmp.execute('query-version')['qemu']} is up, QMP connected")

    def stop(self) -> None:
        if self.qmp:
            try:
                self.qmp.execute("quit")
            except Exception:
                pass
            self.qmp.close()
        if self.proc:
            try:
                self.proc.wait(20)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    # --- talking to the guest ---
    def ssh_argv(self) -> list[str]:
        # A throwaway VM on this machine's loopback, with a key made for this run: its host key
        # can't be known ahead, so it is not checked (and never stored).
        return ["ssh", "-q", "-p", str(SSH_PORT), "-i", str(self.key), "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=6",
                f"{USER}@127.0.0.1"]

    def sh(self, cmd: str, check: bool = True, input: bytes | None = None, timeout: int = 300,
           quiet: bool = False) -> subprocess.CompletedProcess:
        if not quiet:
            log(f"  $ {cmd}")
        try:
            r = subprocess.run(self.ssh_argv() + [cmd], capture_output=True, timeout=timeout,
                               **({"input": input} if input is not None else {"stdin": subprocess.DEVNULL}))
        except subprocess.TimeoutExpired:
            if check:
                raise StepFailed(f"`{cmd}` took more than {timeout} s")
            r = subprocess.CompletedProcess(cmd, 124, b"", f"timed out after {timeout} s".encode())
        r.out = r.stdout.decode("utf-8", "replace").strip()
        r.err = r.stderr.decode("utf-8", "replace").strip()
        if not quiet:
            text = "\n".join(x for x in (r.out, r.err) if x)
            lines = text.splitlines()
            for line in lines[:40]:
                log(f"    {line}")
            if len(lines) > 40:
                log(f"    ... ({len(lines) - 40} more lines)")
        if check and r.returncode != 0:
            raise StepFailed(f"`{cmd}` exited {r.returncode}")
        return r

    def probe(self, *args) -> dict:
        r = self.sh(f"sudo python3 -I {GUEST_DIR}/probe.py {' '.join(args)}", quiet=True, timeout=120)
        if r.returncode != 0:
            raise StepFailed(f"probe {' '.join(args)} failed: {r.err or r.out}")
        return json.loads(r.out)

    def stream(self, cmd: str, logfile: Path) -> int:
        """Runs a long command, printing its output as it comes and keeping all of it in `logfile`."""
        log(f"  $ {cmd}")
        with open(logfile, "w") as keep:
            p = subprocess.Popen(self.ssh_argv() + [cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
            for raw in p.stdout:
                line = raw.decode("utf-8", "replace").rstrip()
                keep.write(line + "\n")
                log(f"  | {line}")
            return p.wait()

    def put(self, local: Path, remote: str) -> None:
        r = subprocess.run(self.ssh_argv() + [f"cat > {remote}"], stdin=open(local, "rb"), capture_output=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"copying {local.name} in failed: {r.stderr.decode()}")

    def serial_tail(self, n: int = 1) -> str:
        try:
            lines = self.serial.read_bytes().decode("utf-8", "replace").splitlines()
        except OSError:
            return ""
        return "\n".join(l.rstrip() for l in lines[-n:])

    def boot_id(self) -> str:
        r = self.sh("cat /proc/sys/kernel/random/boot_id", check=False, quiet=True, timeout=20)
        return r.out if r.returncode == 0 else ""

    def wait_ssh(self, timeout: int = 420, not_boot: str = "") -> str:
        log("Waiting for SSH")
        start = last = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.proc and self.proc.poll() is not None:
                raise RuntimeError("QEMU stopped")
            b = self.boot_id()
            if b and b != not_boot:
                log(f"  SSH answers after {int(time.monotonic() - start)} s (boot {b})")
                return b
            if time.monotonic() - last > 30:
                last = time.monotonic()
                log(f"  still waiting ({int(last - start)} s); serial: {self.serial_tail()[-150:]}")
            time.sleep(3)
        raise RuntimeError(f"no SSH after {timeout} s")

    def save_journal(self, label: str) -> None:
        self.journals += 1
        path = self.out / f"journal-{self.journals:02d}-{label}.txt"
        r = self.sh("sudo journalctl -b --no-pager -o short-precise", check=False, quiet=True, timeout=120)
        path.write_text(r.out)
        log(f"  saved this boot's journal as {path.name} ({len(r.out) >> 10} KiB)")

    def reboot(self, label: str) -> None:
        log(f"Rebooting ({label})")
        self.save_journal(f"before-{label}")
        old = self.boot_id()
        # Started a moment later by systemd, so this SSH call returns before the network goes.
        self.sh("sudo systemd-run --quiet --on-active=2 /usr/bin/systemctl reboot", check=False, timeout=30)
        self.wait_ssh(not_boot=old)

    # --- the screen ---
    def picture(self, name: str) -> Picture:
        ppm = self.work / f"{name}.ppm"
        self.qmp.execute("screendump", filename=str(ppm))
        for _ in range(50):                     # QEMU writes it as the command returns, but be sure
            if ppm.exists() and ppm.stat().st_size > 0:
                break
            time.sleep(0.1)
        pic = read_ppm(ppm.read_bytes())
        ppm.unlink()
        (self.out / f"{name}.png").write_bytes(png_bytes(pic))
        log(f"  picture {name}.png: {pic.width}x{pic.height}, mean colour {mean_colour(pic)}")
        return pic

    def wake_screen(self) -> None:
        # A blanked login screen comes back with any key; Shift types nothing.
        self.qmp.send_keys(["shift"])
        time.sleep(1.5)

    def type_text(self, text: str) -> None:
        for k in keys_for_text(text):
            self.qmp.send_keys([k])
            time.sleep(0.15)


# ===== The lane ===================================================================================

class Lane:
    def __init__(self, vm: VM, out: Path):
        self.vm, self.out = vm, out
        self.results: dict[str, str] = {}
        self.notes: dict[str, str] = {}
        self.baseline: dict = {}
        self.plain: Picture | None = None
        self.first_failure_shown = False

    # --- what the guest says ---
    def status(self) -> dict:
        r = self.vm.sh(f"{HELPER} status", check=False)
        if r.returncode != 0:
            raise StepFailed(f"status exited {r.returncode}")
        return json.loads(r.out)

    def look_token(self) -> str:
        r = self.vm.sh("sudo cat /etc/fedora-glass/login/look.json", check=False, quiet=True)
        try:
            return json.loads(r.out)["token"]
        except (ValueError, KeyError):
            return ""

    def turn_on(self, values: dict, picture: bool) -> subprocess.CompletedProcess:
        data = (HERE / "test-picture.jpg").read_bytes() if picture else None
        arg = json.dumps(values).replace("'", "")
        return self.vm.sh(f"sudo {HELPER} on '{arg}'", check=False, input=data)

    # --- the login screen ---
    def wait_greeter(self, timeout: int = 180) -> dict:
        log("  waiting for the login screen (a greeter session with its gnome-shell)")
        start, seen = time.monotonic(), None
        while time.monotonic() - start < timeout:
            state = self.vm.probe("sessions")
            g = [s for s in greeters(state) if s["gnome_shell"] and s["state"] != "closing"]
            summary = [(s["id"], s["user"], s["class"], s["type"], s["state"], s["gnome_shell"]) for s in state["sessions"]]
            if summary != seen:
                seen = summary
                log(f"    sessions: {summary}")
            if g:
                log(f"  login screen up after {int(time.monotonic() - start)} s: session {g[0]['id']} "
                    f"of {g[0]['user']} ({g[0]['type']})")
                time.sleep(8)                  # let the Shell finish drawing before a picture
                return g[0]
            time.sleep(3)
        raise StepFailed(f"no login screen within {timeout} s")

    def restart_gdm(self) -> dict:
        self.vm.sh(f"sudo systemctl restart {self.vm.gdm_unit}")
        return self.wait_greeter()

    def end_sessions(self) -> None:
        """Logs the tester out, so that the next real login goes through the login screen. This
        also ends the SSH session that asks for it, so its exit status means nothing."""
        self.vm.sh(f"sudo loginctl terminate-user {USER}", check=False)
        for _ in range(20):
            if not user_sessions(self.vm.probe("sessions")):
                break
            time.sleep(2)

    def login(self) -> dict:
        """Logs in for real: Enter picks the user in GDM's list, then the password and Enter."""
        for attempt in (1, 2):
            log(f"  logging in through the login screen (try {attempt})")
            wait = 2 if attempt == 1 else 5
            self.vm.wake_screen()
            self.vm.qmp.send_keys(["ret"])
            time.sleep(wait + 1)
            self.vm.picture(f"login-prompt-{attempt}")
            self.vm.type_text(PASSWORD)
            time.sleep(0.5)
            self.vm.qmp.send_keys(["ret"])
            start = time.monotonic()
            while time.monotonic() - start < 60:
                mine = [s for s in user_sessions(self.vm.probe("sessions")) if s["type"] == "wayland"]
                if mine:
                    log(f"  logged in: session {mine[0]['id']} of {USER}, class user, type wayland, "
                        f"after {int(time.monotonic() - start)} s")
                    return mine[0]
                time.sleep(2)
            self.vm.picture(f"login-failed-{attempt}")
            if attempt == 1:
                log("  no session yet; Escape twice and try once more")
                self.vm.qmp.send_keys(["esc"])
                time.sleep(2)
                self.vm.qmp.send_keys(["esc"])
                time.sleep(3)
        state = self.vm.probe("sessions")
        raise StepFailed(f"the real login did not start a wayland session for {USER}: {state['sessions']}")

    def fresh_greeter(self) -> None:
        self.end_sessions()
        self.restart_gdm()

    def reset(self) -> None:
        """A clean start for a step that breaks the glass: switch off, nobody logged in."""
        log("  starting clean: switch off, tester logged out, login screen restarted")
        self.vm.sh(f"sudo {HELPER} off", check=False)
        self.fresh_greeter()

    def show(self, pic: Picture, name: str) -> None:
        print(thumbnail_block(pic, name), flush=True)

    def plain_again(self, name: str) -> Picture:
        self.vm.wake_screen()
        pic = self.vm.picture(name)
        d = difference(self.plain, pic)
        check(d <= ABOUT_THE_SAME, f"{name} looks like the plain login screen (difference {d:.1f}, at most {ABOUT_THE_SAME})")
        return pic

    def wait_phase(self, phases: tuple[str, ...], token: str, timeout: int = 45, boot: str = "") -> dict:
        start = time.monotonic()
        note = None
        while time.monotonic() - start < timeout:
            note = self.vm.probe("health").get("note")
            if note and note.get("phase") in phases and note.get("token") == token and (not boot or note.get("boot") == boot):
                break
            time.sleep(3)
        log(f"  health note: {json.dumps(note)}")
        return note or {}

    def denials(self) -> dict:
        d = self.vm.probe("denials")
        log(f"  SELinux: {d['selinux'] or '-'}; AppArmor: {d['apparmor'] or '-'}; {len(d['lines'])} denial lines since boot")
        return d

    # --- the steps ---
    def step_baseline(self):
        g = self.wait_greeter()
        check(g["class"] == "greeter", f"a greeter session {g['id']} runs gnome-shell")
        st = self.status()
        log(f"  status: {json.dumps(st)}")
        check(st.get("state") == "off" and st.get("available") is True,
              f"the switch is off and available (state {st.get('state')}, why {st.get('why')!r})")
        self.vm.wake_screen()
        self.plain = self.vm.picture("01-plain")
        self.show(self.plain, "01-plain")
        self.baseline = self.vm.probe("dconf-state")
        log(f"  gdm profile: {json.dumps(self.baseline['gsettings'])}")
        log(f"  /etc/dconf: {len(self.baseline['etc'])} entries")
        self.baseline_denials = set(self.denials()["lines"])
        (self.out / "baseline-dconf.json").write_text(json.dumps(self.baseline, indent=1))

    def step_on(self):
        r = self.turn_on({"picture": "wallpaper"}, picture=True)
        check(r.returncode == 0, f"`on` with the test picture exited {r.returncode}")
        st = self.status()
        check(st.get("state") == "trial", f"status says trial (it says {st.get('state')})")
        self.token = self.look_token()
        check(re.fullmatch(r"[0-9a-f]{32}", self.token or ""), f"look.json has a token ({self.token})")

    def step_glass(self):
        self.restart_gdm()
        note = self.wait_phase(("ok",), self.token)
        check(note.get("phase") == "ok", f"the add-on's health note says ok (it says {note.get('phase')})")
        self.vm.wake_screen()
        pic = self.vm.picture("02-glass")
        self.show(pic, "02-glass")
        d = difference(self.plain, pic)
        log(f"  mean colour plain {mean_colour(self.plain)}, glass {mean_colour(pic)}")
        check(d >= CLEARLY_DIFFERENT, f"the glass screen differs clearly from the plain one (difference {d:.1f}, at least {CLEARLY_DIFFERENT})")
        den = self.denials()
        new = [l for l in den["lines"] if l not in self.baseline_denials]
        for l in new[:20]:
            log(f"    new denial: {l}")
        ours = [l for l in new if re.search(r"gnome-shell|dconf|fedora-glass|fedora_glass|" + re.escape(UUID), l)]
        if self.vm.family == "fedora":
            check(den["selinux"] == "Enforcing", f"SELinux is enforcing (it is {den['selinux'] or 'missing'})")
        check(not ours, f"no SELinux or AppArmor denial for gnome-shell, dconf or fedora-glass ({len(ours)} new)")

    def step_login(self):
        self.login()
        start = time.monotonic()
        st = {}
        while time.monotonic() - start < 20:
            st = self.status()
            if st.get("state") == "on":
                break
            time.sleep(2)
        log(f"  status: {json.dumps(st)}")
        check(st.get("state") == "on", f"within 20 s of the login the trial was confirmed (state {st.get('state')})")

    def step_update(self):
        r = self.turn_on({"picture": "glow", "clock": "thin"}, picture=False)
        check(r.returncode == 0, f"`on` with new values exited {r.returncode}")
        st = self.status()
        check(st.get("state") == "on", f"still on (state {st.get('state')})")
        values = st.get("values") or {}
        check(values.get("picture") == "glow" and values.get("clock") == "thin",
              f"the new values are in (picture {values.get('picture')}, clock {values.get('clock')})")
        token = self.look_token()
        check(token == self.token, f"the same token in look.json ({token})")

    def _still_on_after_reboot(self, label: str) -> None:
        """A plain reboot with the glass on: the boot guard runs in its real systemd sandbox and
        must leave the feature on (the only place that is proven on each Linux)."""
        self.vm.reboot(label)
        self.wait_greeter()
        boot = self.vm.boot_id()
        st = self.status()
        log(f"  status: {json.dumps(st)}")
        check(st.get("state") == "on" and st.get("stopped") == "",
              f"still on with nothing stopped (state {st.get('state')}, stopped {st.get('stopped')!r})")
        note = self.wait_phase(("ok",), self.token, boot=boot)
        check(note.get("phase") == "ok" and note.get("boot") == boot,
              f"the health note says ok for this boot {boot} (phase {note.get('phase')}, boot {note.get('boot')})")
        token = self.look_token()
        check(token == self.token, f"the same token in look.json ({token})")
        r = self.vm.sh(f"systemctl show -p Result,ExecMainStatus {GUARD}", check=False)
        props = dict(l.split("=", 1) for l in r.out.splitlines() if "=" in l)
        self.vm.sh(f"sudo journalctl -b -u {GUARD} --no-pager", check=False)
        check(props.get("Result") == "success" and props.get("ExecMainStatus") == "0",
              f"the boot guard ran and succeeded (Result {props.get('Result')}, ExecMainStatus {props.get('ExecMainStatus')})")
        r = self.vm.sh("sudo cat /var/lib/fedora-glass/login/state.json", check=False)
        try:
            silent = json.loads(r.out).get("silent_boots")
        except ValueError:
            silent = None
        log(f"  silent_boots: {silent}")
        check(silent == 0, f"the guard's silent counter stays at zero (it is {silent})")

    def step_restart(self):
        self._still_on_after_reboot("stays-on-1")
        self._still_on_after_reboot("stays-on-2")

    def step_off(self):
        self.vm.sh(f"sudo fedora-glass login-screen off")
        st = self.status()
        check(st.get("state") == "off", f"status says off (it says {st.get('state')})")
        now = self.vm.probe("dconf-state")
        diffs = listing_differences(self.baseline["etc"], now["etc"])
        for d in diffs:
            log(f"    {d}")
        check(not diffs, "/etc/dconf is as it was before the first `on`")
        for k, v in self.baseline["gsettings"].items():
            if now["gsettings"].get(k) != v:
                log(f"    {k}: {v} -> {now['gsettings'].get(k)}")
        check(now["gsettings"] == self.baseline["gsettings"] and now["dump"] == self.baseline["dump"],
              "the login screen's dconf settings are as they were")
        o = self.vm.probe("ours")
        check(not o["etc_login"], "/etc/fedora-glass/login is gone")
        self.fresh_greeter()
        self.plain_again("06-plain-again")
        self.login()

    def _on_trial(self) -> str:
        r = self.turn_on({"picture": "wallpaper"}, picture=True)
        check(r.returncode == 0, f"`on` exited {r.returncode}")
        st = self.status()
        check(st.get("state") == "trial", f"a new trial (state {st.get('state')})")
        token = self.look_token()
        check(bool(token), f"token {token}")
        return token

    def _after_reboot_off(self, why: str) -> None:
        st = self.status()
        log(f"  status: {json.dumps(st)}")
        check(st.get("state") == "off" and st.get("stopped") == why,
              f"after the reboot the switch is off with stopped = {why} (state {st.get('state')}, stopped {st.get('stopped')!r})")

    def step_crash(self):
        self.reset()
        token = self._on_trial()
        # A greeter that crashed leaves its `starting` note behind. The login screen is stopped
        # first (a clean stop would write `ok`), then the note is put back as a crash leaves it.
        self.vm.sh(f"sudo systemctl stop {self.vm.gdm_unit}")
        time.sleep(3)
        w = self.vm.probe("write-health", "starting")
        log(f"  wrote {w['path']} as {w['owner']}: {json.dumps(w['note'])}")
        self.vm.sh(f"sudo systemctl start {self.vm.gdm_unit}")
        self.wait_greeter()
        note = self.wait_phase(("safe",), token)
        check(note.get("phase") == "safe", f"the add-on found the crash and stayed out (phase {note.get('phase')})")
        self.plain_again("07-crash-plain")
        self.login()
        self.vm.reboot("after-crash")
        self.wait_greeter()
        self._after_reboot_off("crash")

    def step_broken_addon(self):
        self.reset()
        token = self._on_trial()
        js = f"{ADDON_DIR}/login.js"
        self.vm.sh(f"sudo ls -l {ADDON_DIR}/")
        check(self.vm.sh(f"sudo test -f {js}", check=False).returncode == 0, f"{js} is installed")
        self.vm.sh(f"sudo cp -a {js} /root/lgv-login.js.saved")
        try:
            self.vm.sh(f"sudo sh -c 'printf \"throw new Error(\\\"boot test\\\");\\n\" | cat - /root/lgv-login.js.saved > {js}'")
            self.vm.sh(f"sudo head -n 2 {js}")
            self.restart_gdm()
            note = self.wait_phase(("error",), token)
            check(note.get("phase") == "error", f"the add-on noted its error (phase {note.get('phase')})")
            self.plain_again("08-broken-plain")
            self.login()
            self.vm.reboot("after-broken-addon")
            self.wait_greeter()
            self._after_reboot_off("crash")
        finally:
            self.vm.sh(f"sudo cp -a /root/lgv-login.js.saved {js} && sudo rm -f /root/lgv-login.js.saved", check=False)

    def step_no_login(self):
        self.reset()
        self._on_trial()
        self.vm.reboot("no-login-1")
        self.wait_greeter()
        log(f"  status after the first reboot: {json.dumps(self.status())}")
        self.vm.reboot("no-login-2")
        self.wait_greeter()
        self._after_reboot_off("no-login")
        self.plain_again("09-no-login-plain")
        self.login()

    def step_removal(self):
        self.reset()
        self._on_trial()
        remove = {"fedora": "sudo dnf -y -q remove fedora-glass",
                  "ubuntu": "sudo DEBIAN_FRONTEND=noninteractive apt-get -y -qq remove fedora-glass",
                  "arch": "sudo pacman -R --noconfirm fedora-glass"}[self.vm.family]
        self.vm.sh(remove, timeout=600)
        o = self.vm.probe("ours")
        log(f"  left on the disk: {json.dumps(o)}")
        check(not o["dconf_files"], f"no file under /etc/dconf has our switch ({o['dconf_files']})")
        check(not o["etc_login"], "/etc/fedora-glass/login is gone")
        now = self.vm.probe("dconf-state")
        check(UUID not in now["gsettings"]["org.gnome.shell enabled-extensions"],
              f"the login screen's extension list is {now['gsettings']['org.gnome.shell enabled-extensions']}")
        self.fresh_greeter()
        self.plain_again("10-removed-plain")
        self.login()

    # --- running them ---
    def on_failure(self, step: str) -> None:
        log(f"--- what the VM looked like when {step} failed ---")
        try:
            pic = self.vm.picture(f"fail-{step}")
            if not self.first_failure_shown:
                self.first_failure_shown = True
                self.show(pic, f"fail-{step}")
        except Exception as e:
            log(f"  no picture: {e}")
        log("  serial log, last 60 lines:")
        for line in self.vm.serial_tail(60).splitlines():
            log(f"    | {line}")
        extra = ()
        if step == "restart":
            # The guard in its sandbox is what this step proves: its journal and how tight the
            # sandbox is, to tell a sandbox that is too tight from a guard that misjudged.
            extra = (f"sudo journalctl -b -u {GUARD} --no-pager -n 200",
                     f"systemd-analyze security {GUARD} | tail -3")
        for cmd in extra + (f"sudo journalctl -b -u {self.vm.gdm_unit} --no-pager -n 120",
                    "sudo journalctl -b _COMM=gnome-shell --no-pager -n 120",
                    f"{HELPER} status",
                    f"sudo python3 -I {GUEST_DIR}/probe.py health",
                    f"sudo python3 -I {GUEST_DIR}/probe.py sessions"):
            try:
                self.vm.sh(cmd, check=False, timeout=60)
            except Exception as e:
                log(f"  {cmd}: {e}")

    def run(self, steps: list[str]) -> bool:
        for step in steps:
            num = ORDER.index(step) + 1
            blocker = blocked_by(step, self.results)
            if blocker:
                self.results[step] = "SKIP"
                self.notes[step] = f"needs {blocker}"
                log(f"SKIP step {num} {step}: it builds on {blocker}, which did not pass")
                continue
            print(f"::group::Step {num}: {step}", flush=True)
            log(f"=== step {num}: {step} ===")
            try:
                getattr(self, "step_" + step.replace("-", "_"))()
                self.results[step] = "PASS"
                print("::endgroup::", flush=True)
                log(f"PASS step {num} {step}")
            except Exception as e:                      # one step's trouble must not hide the others
                self.results[step] = "FAIL"
                self.notes[step] = str(e)
                try:
                    self.on_failure(step)
                finally:
                    print("::endgroup::", flush=True)
                log(f"FAIL step {num} {step}: {e}")
            (self.out / "results.json").write_text(json.dumps({"results": self.results, "notes": self.notes}, indent=1))
        return all(self.results.get(s) == "PASS" for s in steps)


def summary(distro: str, steps: list[str], results: dict, notes: dict) -> str:
    lines = [f"### Login screen, real boot: {distro}", "", "| Step | Result | Note |", "|---|---|---|"]
    for s in steps:
        lines.append(f"| {ORDER.index(s) + 1}. {s} | {results.get(s, 'not run')} | {notes.get(s, '').replace('|', '/')[:200]} |")
    return "\n".join(lines) + "\n"


def tools_missing() -> list[str]:
    need = ["qemu-system-x86_64", "qemu-img", "ssh", "ssh-keygen", "gpg", "git"]
    miss = [t for t in need if not shutil.which(t)]
    if not any(shutil.which(t) for t in ("genisoimage", "mkisofs", "xorriso")):
        miss.append("genisoimage")
    return miss


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--distro", required=True, choices=sorted(DISTROS))
    ap.add_argument("--out", required=True, type=Path, help="folder for pictures, logs and journals")
    ap.add_argument("--image", type=Path, help="a cloud image already here (not checked: for runs on your own PC)")
    ap.add_argument("--steps", help=f"comma-separated steps to run (default all): {','.join(ORDER)}")
    ap.add_argument("--find-image-only", action="store_true", help="find and check the image's signed checksum, then stop")
    args = ap.parse_args(argv)

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="lgv-", dir=os.environ.get("RUNNER_TEMP")))
    steps = plan(args.steps.split(",") if args.steps else None)
    log(f"Real boot of the glass login screen on {args.distro}; steps: {', '.join(steps)}")

    if args.find_image_only:
        try:
            info = find_image(args.distro, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        log(f"Image: {info['url']}")
        return 0
    missing = tools_missing()
    if missing:
        log(f"Missing tools: {', '.join(missing)}")
        return 1
    if not os.access("/dev/kvm", os.R_OK | os.W_OK):
        log("/dev/kvm is not usable by this user (see the udev step in .github/workflows/login-boot.yml)")
        return 1

    vm = VM(args.distro, out, work)
    lane = Lane(vm, out)
    ok = False
    try:
        image = args.image.resolve() if args.image else get_image(args.distro, work)
        vm.prepare(image)
        vm.start()
        vm.wait_ssh()
        ver = re.search(r"^Version:\s*(\S+)", (ROOT / "packaging/fedora-glass.spec").read_text(), re.M).group(1)
        tarball = work / f"fedora-glass-{ver}.tar.gz"
        log(f"Copying the source in (git archive HEAD, version {ver})")
        subprocess.run(["git", "-C", str(ROOT), "archive", "--format=tar.gz", f"--prefix=fedora-glass-{ver}/",
                        "-o", str(tarball), "HEAD"], check=True)
        vm.sh(f"mkdir -p {GUEST_DIR}", quiet=True)
        for local, name in ((tarball, tarball.name), (HERE / "guest/setup.sh", "setup.sh"),
                            (HERE / "guest/probe.py", "probe.py")):
            vm.put(local, f"{GUEST_DIR}/{name}")
        print("::group::Guest setup: login screen, GNOME Shell and the real package", flush=True)
        rc = vm.stream(f"sudo timeout 1800 bash {GUEST_DIR}/setup.sh {vm.family} {ver} 2>&1", out / "setup.log")
        print("::endgroup::", flush=True)
        if rc != 0:
            log(f"Guest setup failed (exit {rc}); its whole output is in setup.log")
            for line in (out / "setup.log").read_text(errors="replace").splitlines()[-40:]:
                log(f"  | {line}")
            return 1
        vm.gdm_unit = vm.sh(f"cat {GUEST_DIR}/gdm-unit", quiet=True).out or "gdm.service"
        vm.reboot("setup")
        ok = lane.run(steps)
    finally:
        try:
            if vm.proc and vm.proc.poll() is None:
                vm.save_journal("end")
        except Exception as e:
            log(f"(no final journal: {e})")
        vm.stop()
        text = summary(args.distro, steps, lane.results, lane.notes)
        print(text, flush=True)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
                f.write(text)
        shutil.rmtree(work, ignore_errors=True)
    log("ALL STEPS PASSED" if ok else "SOME STEPS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
