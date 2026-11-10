#!/usr/bin/env python3
"""Builds the cursor themes that ship with Fedora Glass, from pinned upstream sources.

    python3 packaging/cursors/build.py            # rebuild data/cursors/ and the previews
    python3 packaging/cursors/build.py --check    # rebuild in a temp folder, compare checksums

Not part of the app or the packages: the output is committed (data/cursors/*.tar.xz, with
SHA256SUMS, and the preview pictures in fedoraglass/data/cursors/), so building a package
needs no network and no browser. This script exists so anyone can see exactly where those
files come from and rebuild them.

Sources (both GPL-3.0-or-later, see THIRD-PARTY-NOTICES.md):
  * Bibata Cursor by Abdulkaiz Khatri: the shapes for Fedora Glass Light/Dark (recoloured)
    and Bibata Modern Ice/Classic (its own colours). Rendered from its SVGs with Chromium
    (as Bibata's own build does), packed into Xcursor files here, with its hotspots and
    alias names from configs/normal/x.build.toml.
  * WhiteSur cursors by Vince Liuice: its own prebuilt theme (dist/), copied as it is.

Each source is cloned at a pinned commit and the commit is checked before anything is read.
Needs: git, node with Playwright (Chromium), python3 with Pillow (previews only).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT_TARS = REPO / "data/cursors"
OUT_PREVIEWS = REPO / "fedoraglass/data/cursors"

SOURCES = {
    "bibata": ("https://github.com/ful1e5/Bibata_Cursor", "ddb09273cde49faeb6a32282660ff4293f52d6e0"),
    "whitesur": ("https://github.com/vinceliuice/WhiteSur-cursors", "e190baf618ed95ee217d2fd45589bd309b37672b"),
}

# Bibata's SVGs use three placeholder colours: #00FF00 the body, #0000FF the outline,
# #FF0000 the busy ring. Fedora Glass Light/Dark make the body see-through glass.
BIBATA_THEMES = {
    "fedora-glass-light": {
        "name": "Fedora Glass Light", "comment": "Frosted glass cursors, based on Bibata Modern",
        "colors": [("#00FF00", "#F2F6FC\" fill-opacity=\"0.9"), ("#0000FF", "#0E1420"),
                   ("#FF0000", "#7FA6D6")],
    },
    "fedora-glass-dark": {
        "name": "Fedora Glass Dark", "comment": "Smoked glass cursors, based on Bibata Modern",
        "colors": [("#00FF00", "#121722\" fill-opacity=\"0.86"), ("#0000FF", "#F4F7FB"),
                   ("#FF0000", "#7FA6D6")],
    },
    "fedora-glass-bibata-ice": {
        "name": "Bibata Modern Ice", "comment": "Bibata Modern Ice by Abdulkaiz Khatri",
        "colors": [("#00FF00", "#FFFFFF"), ("#0000FF", "#000000"), ("#FF0000", "#FFFFFF")],
    },
    "fedora-glass-bibata-classic": {
        "name": "Bibata Modern Classic", "comment": "Bibata Modern Classic by Abdulkaiz Khatri",
        "colors": [("#00FF00", "#000000"), ("#0000FF", "#FFFFFF"), ("#FF0000", "#000000")],
    },
}
WHITESUR_ID = "fedora-glass-whitesur"

# Pixel sizes in each cursor file: GNOME's sizes 24, 32 and 48 at 100 %, 125 %, 150 % and 200 %.
SIZES = (24, 30, 32, 36, 40, 48, 60, 64, 72, 96)
ANIM_SIZES = (24, 30, 32, 36, 48, 64)   # busy cursors have 54 frames each: fewer sizes
SVG_SIZE = 256                           # Bibata's hotspots are in its 256 px SVG space
# Shown in the app's picker: arrow, link hand, text beam, busy.
PREVIEW = ("left_ptr", "hand2", "xterm", "left_ptr_watch")
PREVIEW_SIZE = 48


def sh(*argv: str, cwd: Path | None = None) -> str:
    return subprocess.run(argv, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def fetch(work: Path, key: str) -> Path:
    url, commit = SOURCES[key]
    dest = work / key
    sh("git", "init", "-q", str(dest))
    sh("git", "fetch", "-q", "--depth", "1", url, commit, cwd=dest)
    sh("git", "checkout", "-q", "FETCH_HEAD", cwd=dest)
    got = sh("git", "rev-parse", "HEAD", cwd=dest)
    if got != commit:
        sys.exit(f"{key}: got commit {got}, expected {commit}")
    return dest


# ---- Xcursor ------------------------------------------------------------------------
def xcursor(frames: list[list[tuple[int, int, int, bytes, int]]]) -> bytes:
    """frames: per size, a list of (size, xhot, yhot, argb_premultiplied, delay)."""
    images = [img for per_size in frames for img in per_size]
    ntoc = len(images)
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, ntoc)
    pos = 16 + 12 * ntoc
    toc, chunks = b"", b""
    for size, xh, yh, px, delay in images:
        toc += struct.pack("<III", 0xFFFD0002, size, pos)
        chunk = struct.pack("<9I", 36, 0xFFFD0002, size, 1, size, size, xh, yh, delay) + px
        chunks += chunk
        pos += len(chunk)
    return header + toc + chunks


def argb(png: Path) -> bytes:
    from PIL import Image
    im = Image.open(png).convert("RGBA")
    out = bytearray()
    for r, g, b, a in im.getdata():
        out += struct.pack("<I", (a << 24) | (r * a // 255 << 16) | (g * a // 255 << 8) | (b * a // 255))
    return bytes(out)


def index_theme(name: str, comment: str) -> str:
    return f"[Icon Theme]\nName={name}\nComment={comment}\nInherits=Adwaita\n"


def build_bibata(src: Path, work: Path) -> dict[str, Path]:
    cfg = tomllib.loads((src / "configs/normal/x.build.toml").read_text())["cursors"]
    fallback = cfg.pop("fallback_settings")
    svgdir = src / "svg/modern"
    jobs, plan = [], {}
    for tid, theme in BIBATA_THEMES.items():
        pngs = work / "png" / tid
        pngs.mkdir(parents=True)
        for cname, c in cfg.items():
            pattern = c["png"].removesuffix(".png")
            if pattern.endswith("-*"):
                base = pattern[:-2]
                svgs = sorted((svgdir / base).glob(f"{base}-*.svg"))
                sizes = ANIM_SIZES
            else:
                svgs = [svgdir / f"{pattern}.svg"]
                sizes = SIZES
            frames = []
            for i, svg in enumerate(svgs):
                out = {s: str(pngs / f"{cname}.{i:02d}.{s}.png") for s in sizes}
                jobs.append({"svg": str(svg), "colors": theme["colors"], "out": out})
                frames.append(out)
            plan[(tid, cname)] = (c, frames)
    jobfile = work / "jobs.json"
    jobfile.write_text(json.dumps(jobs))
    subprocess.run(["node", str(HERE / "render.mjs"), str(jobfile)], check=True)

    themes = {}
    for tid, theme in BIBATA_THEMES.items():
        root = work / "themes" / tid
        (root / "cursors").mkdir(parents=True)
        (root / "index.theme").write_text(index_theme(theme["name"], theme["comment"]))
        for cname, c in cfg.items():
            c_, frames = plan[(tid, cname)]
            xh0 = c.get("x_hotspot", fallback["x_hotspot"])
            yh0 = c.get("y_hotspot", fallback["y_hotspot"])
            delay = c.get("x11_delay", fallback["x11_delay"])
            per_size = []
            for s in frames[0]:
                xh = min(s - 1, round(xh0 * int(s) / SVG_SIZE))
                yh = min(s - 1, round(yh0 * int(s) / SVG_SIZE))
                per_size.append([(int(s), xh, yh, argb(Path(f[s])), delay) for f in frames])
            name = c.get("x11_name", cname)
            (root / "cursors" / name).write_bytes(xcursor(per_size))
            for alias in c.get("x11_symlinks", []):
                link = root / "cursors" / alias
                if not link.exists():
                    link.symlink_to(name)
        themes[tid] = root
    return themes


def build_whitesur(src: Path, work: Path) -> Path:
    root = work / "themes" / WHITESUR_ID
    shutil.copytree(src / "dist", root, symlinks=True,
                    ignore=shutil.ignore_patterns("cursors_scalable"))
    (root / "index.theme").write_text(index_theme("WhiteSur", "WhiteSur cursors by Vince Liuice"))
    return root


def tar_theme(root: Path, dest: Path) -> None:
    """A reproducible .tar.xz: sorted names, fixed owner and times, no extra headers."""
    def clean(ti: tarfile.TarInfo) -> tarfile.TarInfo:
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = "root"
        ti.mtime = 0
        ti.mode = 0o755 if ti.isdir() else (0o777 if ti.issym() else 0o644)
        return ti
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        paths = sorted(p for p in root.rglob("*"))
        tf.add(root, arcname=root.name, recursive=False, filter=clean)
        for p in paths:
            tf.add(p, arcname=f"{root.name}/{p.relative_to(root)}", recursive=False, filter=clean)
    import lzma
    dest.write_bytes(lzma.compress(buf.getvalue(), preset=9 | lzma.PRESET_EXTREME))


def read_xcursor(path: Path, want: int):
    """The image nearest `want` px (first frame) from an Xcursor file, as a Pillow image."""
    from PIL import Image
    b = path.read_bytes()
    if b[:4] != b"Xcur":
        raise ValueError(f"{path} is not an Xcursor file")
    _, _, n = struct.unpack_from("<III", b, 4)
    toc = [struct.unpack_from("<III", b, 16 + 12 * i) for i in range(n)]
    imgs = [(sub, pos) for t, sub, pos in toc if t == 0xFFFD0002]
    best = min({s for s, _ in imgs}, key=lambda s: (abs(s - want), -s))
    pos = next(p for s, p in imgs if s == best)
    w, h = struct.unpack_from("<II", b, pos + 16)
    px = b[pos + 36:pos + 36 + w * h * 4]
    im = Image.frombuffer("RGBa", (w, h), px, "raw", "BGRa", 0, 1).convert("RGBA")
    return im if best == want else im.resize((want, want), Image.LANCZOS)


def previews(root: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    alt = {"left_ptr_watch": "progress", "hand2": "pointer", "xterm": "text"}
    for name in PREVIEW:
        path = root / "cursors" / name
        if not path.exists():
            path = root / "cursors" / alt[name]
        read_xcursor(path.resolve(), PREVIEW_SIZE).save(dest / f"{name}.png", optimize=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="rebuild and compare with SHA256SUMS")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        themes = build_bibata(fetch(work, "bibata"), work)
        themes[WHITESUR_ID] = build_whitesur(fetch(work, "whitesur"), work)
        outdir = work / "out" if args.check else OUT_TARS
        outdir.mkdir(parents=True, exist_ok=True)
        sums = []
        for tid in sorted(themes):
            tar = outdir / f"{tid}.tar.xz"
            tar_theme(themes[tid], tar)
            sums.append(f"{hashlib.sha256(tar.read_bytes()).hexdigest()}  {tar.name}\n")
            if not args.check:
                previews(themes[tid], OUT_PREVIEWS / tid)
        if args.check:
            want = (OUT_TARS / "SHA256SUMS").read_text()
            if "".join(sums) != want:
                print("Rebuilt cursors differ from data/cursors/SHA256SUMS", file=sys.stderr)
                print("".join(sums), file=sys.stderr)
                return 1
            print("Rebuilt cursors match data/cursors/SHA256SUMS")
        else:
            (OUT_TARS / "SHA256SUMS").write_text("".join(sums))
    return 0


if __name__ == "__main__":
    sys.exit(main())
