"""Repository indexes for the Ubuntu (apt) and Arch (pacman) packages, standard library only.

fedora-glass-sign carries a copy of this file (between its REPO_INDEX markers) and runs it
with python3 -I on Dino's PC, so signing needs nothing beyond gpg and Python. Keep the two
the same: tests/test_repo_index.py checks that they are.

  repo_index.py deb-info FILE.deb        prints "name version"
  repo_index.py pkg-info FILE.pkg.tar.xz prints "name version"
  repo_index.py apt DIR                  writes DIR/Packages, Packages.gz and Release
  repo_index.py arch DIR NAME            writes DIR/NAME.db (and NAME.db.tar.gz); every
                                         package needs its detached .sig next to it already
"""
import base64
import gzip
import hashlib
import io
import lzma
import os
import re
import sys
import tarfile
import time

NAME = re.compile(r"[a-z0-9][a-z0-9.+_-]*")
VERSION = re.compile(r"[0-9A-Za-z.:~+_-]+")
MAX = 64 << 20


def _read(path):
    if os.path.getsize(path) > MAX:
        raise SystemExit(f"{path} is too big")
    with open(path, "rb") as f:
        return f.read()


def _members(blob):
    """The members of an ar archive (a .deb), as (name, data)."""
    if not blob.startswith(b"!<arch>\n"):
        raise SystemExit("not a .deb (ar) file")
    pos, out = 8, []
    while pos + 60 <= len(blob):
        head = blob[pos:pos + 60]
        name = head[:16].decode().strip().rstrip("/")
        size = int(head[48:58].decode().strip())
        out.append((name, blob[pos + 60:pos + 60 + size]))
        pos += 60 + size + (size & 1)
    return out


def deb_control(path):
    """The control file of a .deb, as (text, fields)."""
    for name, data in _members(_read(path)):
        if name == "control.tar.xz":
            raw = lzma.decompress(data)
        elif name == "control.tar.gz":
            raw = gzip.decompress(data)
        elif name.startswith("control.tar"):
            raise SystemExit(f"{path}: unsupported {name} (build with dpkg-deb -Zxz)")
        else:
            continue
        with tarfile.open(fileobj=io.BytesIO(raw)) as t:
            for m in t.getmembers():
                if m.isfile() and m.name.lstrip("./") == "control":
                    text = t.extractfile(m).read().decode()
                    fields = {}
                    for line in text.splitlines():
                        if line[:1] not in (" ", "\t") and ":" in line:
                            k, _, v = line.partition(":")
                            fields[k.strip()] = v.strip()
                    return text.strip() + "\n", fields
    raise SystemExit(f"{path} has no control file")


def pkginfo(path):
    """.PKGINFO of an Arch package (xz), as a dict of lists."""
    raw = _read(path)
    with tarfile.open(fileobj=io.BytesIO(lzma.decompress(raw))) as t:
        m = t.getmember(".PKGINFO")
        text = t.extractfile(m).read().decode()
    info = {}
    for line in text.splitlines():
        if line.startswith("#") or " = " not in line:
            continue
        k, _, v = line.partition(" = ")
        info.setdefault(k.strip(), []).append(v.strip())
    return info


def _checked(name, version):
    if not NAME.fullmatch(name) or not VERSION.fullmatch(version):
        raise SystemExit(f"bad package name or version: {name!r} {version!r}")
    return name, version


def deb_info(path):
    _, f = deb_control(path)
    return _checked(f.get("Package", ""), f.get("Version", ""))


def pkg_info(path):
    i = pkginfo(path)
    return _checked(i.get("pkgname", [""])[0], i.get("pkgver", [""])[0])


def apt_index(d):
    debs = sorted(n for n in os.listdir(d) if n.endswith(".deb"))
    if not debs:
        raise SystemExit("no .deb files")
    stanzas = []
    for n in debs:
        p = os.path.join(d, n)
        text, _ = deb_control(p)
        blob = _read(p)
        stanzas.append(text + f"Filename: ./{n}\nSize: {len(blob)}\n"
                       f"MD5sum: {hashlib.md5(blob).hexdigest()}\n"
                       f"SHA256: {hashlib.sha256(blob).hexdigest()}\n")
    packages = "\n".join(stanzas).encode()
    files = {"Packages": packages, "Packages.gz": gzip.compress(packages, mtime=0)}
    for name, data in files.items():
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    date = time.strftime("%a, %d %b %Y %H:%M:%S UTC", time.gmtime(int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))))
    rel = ["Origin: Fedora Glass", "Label: Fedora Glass", "Architectures: all", f"Date: {date}",
           "Acquire-By-Hash: no", "SHA256:"]
    rel += [f" {hashlib.sha256(v).hexdigest()} {len(v)} {k}" for k, v in files.items()]
    with open(os.path.join(d, "Release"), "w") as f:
        f.write("\n".join(rel) + "\n")


DESC = [("FILENAME", None), ("NAME", "pkgname"), ("BASE", "pkgbase"), ("VERSION", "pkgver"),
        ("DESC", "pkgdesc"), ("GROUPS", "group"), ("CSIZE", None), ("ISIZE", "size"),
        ("SHA256SUM", None), ("PGPSIG", None), ("URL", "url"), ("LICENSE", "license"),
        ("ARCH", "arch"), ("BUILDDATE", "builddate"), ("PACKAGER", "packager"),
        ("REPLACES", "replaces"), ("CONFLICTS", "conflict"), ("PROVIDES", "provides"),
        ("DEPENDS", "depend"), ("OPTDEPENDS", "optdepend"), ("MAKEDEPENDS", "makedepend"),
        ("CHECKDEPENDS", "checkdepend")]


def _vkey(ver):
    """Sort key for our own versions (1.5.16-1): numbers compare as numbers."""
    return [int(x) if x.isdigit() else -1 for x in re.split(r"[.:-]", ver)]


def arch_db(d, repo):
    pkgs = sorted(n for n in os.listdir(d) if n.endswith(".pkg.tar.xz"))
    if not pkgs:
        raise SystemExit("no .pkg.tar.xz files")
    # A pacman database holds one version of each package: the newest. The older files
    # stay on the site, for `pacman -U <url>` to go back by hand.
    newest = {}
    for n in pkgs:
        name, ver = pkg_info(os.path.join(d, n))
        if name not in newest or _vkey(ver) > _vkey(newest[name][1]):
            newest[name] = (n, ver)
    pkgs = sorted(n for n, _ in newest.values())
    buf = io.BytesIO()
    mtime = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
    with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as t:
        for n in pkgs:
            p = os.path.join(d, n)
            blob = _read(p)
            sig = _read(p + ".sig")
            info = pkginfo(p)
            name, ver = _checked(info["pkgname"][0], info["pkgver"][0])
            own = {"FILENAME": [n], "CSIZE": [str(len(blob))],
                   "SHA256SUM": [hashlib.sha256(blob).hexdigest()],
                   "PGPSIG": [base64.b64encode(sig).decode()]}
            out = []
            for key, src in DESC:
                vals = own.get(key) if src is None else info.get(src, [])
                if key == "BASE" and not vals:
                    vals = [name]
                if vals:
                    out.append(f"%{key}%\n" + "\n".join(vals) + "\n")
            data = ("\n".join(out) + "\n").encode()
            top = f"{name}-{ver}"
            di = tarfile.TarInfo(top)
            di.type, di.mode, di.mtime = tarfile.DIRTYPE, 0o755, mtime
            t.addfile(di)
            fi = tarfile.TarInfo(f"{top}/desc")
            fi.size, fi.mode, fi.mtime = len(data), 0o644, mtime
            t.addfile(fi, io.BytesIO(data))
    for name in (f"{repo}.db", f"{repo}.db.tar.gz"):
        with open(os.path.join(d, name), "wb") as f:
            f.write(buf.getvalue())


def main(argv):
    if len(argv) >= 2 and argv[0] == "deb-info":
        print(*deb_info(argv[1]))
    elif len(argv) >= 2 and argv[0] == "pkg-info":
        print(*pkg_info(argv[1]))
    elif len(argv) >= 2 and argv[0] == "apt":
        apt_index(argv[1])
    elif len(argv) >= 3 and argv[0] == "arch":
        arch_db(argv[1], argv[2])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
