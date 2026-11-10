#!/usr/bin/env python3
"""Builds the cursor themes that ship with Fedora Glass, from pinned upstream sources.

    python3 packaging/cursors/build.py            # rebuild data/cursors/ and the previews
    python3 packaging/cursors/build.py --check    # rebuild in a temp folder, compare checksums

Not part of the app or the packages: the output is committed (data/cursors/*.tar.xz, with
SHA256SUMS, and the preview pictures in fedoraglass/data/cursors/), so building a package
needs no network and no browser. This script exists so anyone can see exactly where those
files come from and rebuild them.

Sources (free licences, see THIRD-PARTY-NOTICES.md):
  * Bibata Cursor by Abdulkaiz Khatri (GPL-3.0-or-later): the shapes for Fedora Glass
    Light/Dark (recoloured), Bibata Modern Ice/Classic and Original Ice/Classic (its own colours) and
    Amber (its orange with a dark rim, so it reads on white too). Rendered from its SVGs with
    Chromium (as Bibata's own build does), packed into Xcursor files here, with its hotspots
    and alias names from configs/normal/x.build.toml.
  * Banana Cursor by Abdulkaiz Khatri (GPL-3.0-or-later): built the same way.
  * Phinger Cursors by Philipp Schaffrath (CC-BY-SA-4.0): light and dark, from its 24 and
    32 px SVGs; hotspots from each SVG's hotspot marker; the busy spinner turned per frame.
  * Catppuccin Cursors (GPL-2.0): Mocha Mauve and Mocha Sky, coloured as its own build does.
  * Oreo Cursors by Alexey Varfolomeev (GPL-2.0): Pink and Teal, coloured as its own generator does,
    with the hotspots from its config files.
  * WhiteSur cursors by Vince Liuice (GPL-3.0-or-later): its prebuilt theme, copied as it is.

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
    "banana": ("https://github.com/ful1e5/banana-cursor", "6d1f8ba67e1547bf1bf5ab6acb43eb3abb5bca9f"),
    "phinger": ("https://github.com/phisch/phinger-cursors", "d8196cd133e5c168adbc84838da673ca0b8593b5"),
    "catppuccin": ("https://github.com/catppuccin/cursors", "a7eb08527dcce01010fa0ec46fa2bc4c3154f0d4"),
    "oreo": ("https://github.com/varlesh/oreo-cursors", "7483f2dec06ae0fce182f9e9fe96c7db23b312b5"),
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
    "fedora-glass-bibata-original": {
        "name": "Bibata Original Ice", "comment": "Bibata Original Ice by Abdulkaiz Khatri",
        "colors": [("#00FF00", "#FFFFFF"), ("#0000FF", "#000000"), ("#FF0000", "#FFFFFF")],
        "dir": "original",
    },
    "fedora-glass-bibata-original-classic": {
        "name": "Bibata Original Classic", "comment": "Bibata Original Classic by Abdulkaiz Khatri",
        "colors": [("#00FF00", "#000000"), ("#0000FF", "#FFFFFF"), ("#FF0000", "#000000")],
        "dir": "original",
    },
    # Bibata's own Amber has a white rim, which vanishes on white pages: a dark rim instead.
    "fedora-glass-amber": {
        "name": "Fedora Glass Amber", "comment": "Amber cursors, based on Bibata Modern Amber",
        "colors": [("#00FF00", "#FF8300"), ("#0000FF", "#001524"), ("#FF0000", "#001524")],
    },
}
BANANA_THEMES = {
    "fedora-glass-banana": {"name": "Banana", "comment": "The Banana Cursor by Abdulkaiz Khatri",
                            "colors": []},
}
PHINGER_THEMES = {"fedora-glass-phinger-light": "light", "fedora-glass-phinger-dark": "dark"}
PHINGER_SKIP = {"middle_finger", "rock_and_roll"}   # rude or pointless; no app asks for them
# Catppuccin's build: FF0000 is the inside, 00FF00 the rim, 0000FF a few special parts
# (the rim colour, for the accent themes). Mocha palette.
CATPPUCCIN_THEMES = {
    "fedora-glass-catppuccin-mauve": ("Catppuccin Mocha Mauve", "#CBA6F7", "#1E1E2E"),
    "fedora-glass-catppuccin-sky": ("Catppuccin Mocha Sky", "#89DCEB", "#1E1E2E"),
}
# Oreo's generator: background, label, shadow, shadow opacity (its defaults: #fff, #000, 0.3).
OREO_THEMES = {
    "fedora-glass-oreo-pink": ("Oreo Spark Pink", "#FF50A6"),
    "fedora-glass-oreo-teal": ("Oreo Teal", "#009789"),
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
def xcursor(frames: list[list[tuple]]) -> bytes:
    """frames: per size, a list of (size, xhot, yhot, argb_premultiplied, delay), or
    (size, xhot, yhot, argb_premultiplied, delay, width) for a picture bigger than its
    nominal size (square, as all of these are)."""
    images = [img for per_size in frames for img in per_size]
    ntoc = len(images)
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, ntoc)
    pos = 16 + 12 * ntoc
    toc, chunks = b"", b""
    for size, xh, yh, px, delay, *w in images:
        w = w[0] if w else size
        toc += struct.pack("<III", 0xFFFD0002, size, pos)
        chunk = struct.pack("<9I", 36, 0xFFFD0002, size, 1, w, w, xh, yh, delay) + px
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


def render(work: Path, jobs: list[dict]) -> dict:
    """Runs the Chromium renderer over jobs; returns the probes (hotspot markers) it read."""
    work.mkdir(parents=True, exist_ok=True)
    jobfile, probefile = work / "jobs.json", work / "probes.json"
    jobfile.write_text(json.dumps(jobs))
    subprocess.run(["node", str(HERE / "render.mjs"), str(jobfile), str(probefile)], check=True)
    return {int(k): v for k, v in json.loads(probefile.read_text()).items()}


def build_ful1e5(src: Path, work: Path, themes: dict, svgroot: Path) -> dict[str, Path]:
    """Bibata and Banana: one SVG set in a 256 px space, hotspots and aliases in a toml."""
    cfg = tomllib.loads((src / "configs/normal/x.build.toml" if (src / "configs/normal").is_dir()
                         else src / "configs/x.build.toml").read_text())["cursors"]
    fallback = cfg.pop("fallback_settings")
    jobs, plan = [], {}
    for tid, theme in themes.items():
        sub = svgroot / theme.get("dir", "modern")
        svgdir = sub if sub.is_dir() else svgroot    # Banana keeps its SVGs at the top
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
    render(work / "jobs" / src.name, jobs)

    out_themes = {}
    for tid, theme in themes.items():
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
        out_themes[tid] = root
    return out_themes


def build_bibata(src: Path, work: Path) -> dict[str, Path]:
    return build_ful1e5(src, work, BIBATA_THEMES, src / "svg")


def build_banana(src: Path, work: Path) -> dict[str, Path]:
    return build_ful1e5(src, work, BANANA_THEMES, src / "svg")


# ---- themes drawn at a small size, with a hotspot marker or file -----------------------
def alias_groups(bibata: Path) -> list[list[str]]:
    """Names that mean the same shape, from Bibata's full list: used to give the other
    themes every name apps ask for (CSS names, X11 names, the hash names old toolkits use)."""
    cfg = tomllib.loads((bibata / "configs/normal/x.build.toml").read_text())["cursors"]
    cfg.pop("fallback_settings")
    return [[c.get("x11_name", k), *c.get("x11_symlinks", [])] for k, c in cfg.items()]


def link_aliases(root: Path, pairs: list[tuple[str, str]], groups: list[list[str]]) -> None:
    """The theme's own aliases first, then any missing name from a group it has a shape for."""
    cur = root / "cursors"
    def has(n: str) -> bool:
        return (cur / n).exists() or (cur / n).is_symlink()
    def real(n: str) -> str:
        p = cur / n
        return os.readlink(p) if p.is_symlink() else n
    for alias, target in pairs:
        if not has(alias) and has(target) and "/" not in alias:
            (cur / alias).symlink_to(real(target))
    for group in groups:
        have = [n for n in group if (cur / n).is_file() and not (cur / n).is_symlink()]
        have = have or [n for n in group if has(n)]
        if not have:
            continue
        for n in group:
            if not has(n):
                (cur / n).symlink_to(real(have[0]))


def pack(root: Path, name: str, shots: list[dict], hot: tuple[float, float], units: float,
         nominal_units: float, delay: int) -> None:
    """One Xcursor file from rendered frames. shots: per frame, {nominal size: (png, px)}.
    hot: hotspot in the SVG's units; units: the SVG's width; nominal_units: how many of
    those units the nominal size stands for (a 32 unit drawing can be a 24 px pointer)."""
    per_size = []
    for s in shots[0]:
        px = shots[0][s][1]
        k = px / units
        xh = min(px - 1, int(hot[0] * k + 0.01))
        yh = min(px - 1, int(hot[1] * k + 0.01))
        per_size.append([(int(s), xh, yh, argb(Path(f[s][0])), delay, px) for f in shots])
    (root / "cursors" / name).write_bytes(xcursor(per_size))


def build_phinger(src: Path, work: Path, groups: list[list[str]]) -> dict[str, Path]:
    spec = json.loads((src / "theme/cursor-theme.json").read_text())
    jobs, plan = [], []
    for tid, variant in PHINGER_THEMES.items():
        v = next(x for x in spec["variants"] if x["name"] == variant)
        pngs = work / "png" / tid
        pngs.mkdir(parents=True)
        for c in v["cursors"]:
            if c["name"] in PHINGER_SKIP:
                continue
            files = {int(Path(sp["file"]).stem.rsplit("_", 1)[1]): src / "theme" / sp["file"]
                     for sp in c["sprites"]}
            busy = c["name"] in ("progress", "wait")
            sizes = ANIM_SIZES if busy else SIZES
            # The 24 unit drawing for sizes a multiple of 6 (24, 30, 36, 48, 60, 72, 96),
            # the 32 unit one for 32, 40 and 64: each scaled by as round a factor as it gets.
            pick = {s: (24 if s % 6 == 0 or 32 not in files else 32) for s in sizes}
            probes = {}
            for u in sorted(set(pick.values())):
                probes[u] = len(jobs)
                jobs.append({"svg": str(files[u]), "probe": "#hotspot"})
            frames = []
            for i, deg in enumerate(range(0, 360, 10) if busy else [None]):
                out = {}
                for s in sizes:
                    png = str(pngs / f"{c['name']}.{i:02d}.{s}.png")
                    job = {"svg": str(files[pick[s]]), "hide": ["#hotspot"], "out": {s: png}}
                    if deg is not None:
                        job["rotate"] = {"sel": "#spinner", "deg": deg}
                    jobs.append(job)
                    out[s] = (png, s)
                frames.append(out)
            plan.append((tid, v, c, pick, probes, frames, busy))
    got = render(work / "jobs/phinger", jobs)

    themes = {}
    for tid, v, c, pick, probes, frames, busy in plan:
        root = work / "themes" / tid
        if tid not in themes:
            (root / "cursors").mkdir(parents=True)
            title = f"Phinger Cursors {v['name'].capitalize()}"
            (root / "index.theme").write_text(index_theme(title, f"{title} by Philipp Schaffrath"))
            themes[tid] = root
        # One hotspot per drawing; frames of a size all come from the same drawing.
        for u in set(pick.values()):
            if got.get(probes[u]) is None:
                sys.exit(f"phinger {c['name']}: no hotspot marker in the {u} px drawing")
        by_unit: dict[int, list[int]] = {}
        for s, u in pick.items():
            by_unit.setdefault(u, []).append(s)
        per_size = []
        for u, sizes in sorted(by_unit.items()):
            hx, hy = got[probes[u]]
            for s in sizes:
                k = s / u
                xh, yh = min(s - 1, int(hx * k + 0.01)), min(s - 1, int(hy * k + 0.01))
                per_size.append([(s, xh, yh, argb(Path(f[s][0])), 30 if busy else 0) for f in frames])
        per_size.sort(key=lambda fs: fs[0][0])
        (root / "cursors" / c["name"]).write_bytes(xcursor(per_size))
    for tid, variant in PHINGER_THEMES.items():
        v = next(x for x in spec["variants"] if x["name"] == variant)
        pairs = [(a, c["name"]) for c in v["cursors"] if c["name"] not in PHINGER_SKIP
                 for a in c.get("aliases", [])]
        link_aliases(themes[tid], pairs, groups)
    return themes


def _cursor_list(path: Path) -> list[tuple[str, str]]:
    pairs = []
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            pairs.append((parts[0], parts[1]))
    return pairs


def build_catppuccin(src: Path, work: Path, groups: list[list[str]]) -> dict[str, Path]:
    svgdir = src / "src/svgs"
    names: dict[str, list[Path]] = {}
    for svg in sorted(svgdir.glob("*.svg")):
        base = svg.stem.rsplit("-", 1)[0] if svg.stem[-3:-2] == "-" and svg.stem[-2:].isdigit() else svg.stem
        names.setdefault(base, []).append(svg)
    jobs, plan = [], []
    for tid, (title, inner, rim) in CATPPUCCIN_THEMES.items():
        pngs = work / "png" / tid
        pngs.mkdir(parents=True)
        colors = [("FF0000", inner.lstrip("#")), ("00FF00", rim.lstrip("#")), ("0000FF", rim.lstrip("#"))]
        for name, svgs in names.items():
            probe = len(jobs)
            jobs.append({"svg": str(svgs[0]), "probe": "#hotspot"})
            sizes = ANIM_SIZES if len(svgs) > 1 else SIZES
            frames = []
            for i, svg in enumerate(svgs):
                out = {}
                for s in sizes:
                    px = s * 32 // 24
                    png = str(pngs / f"{name}.{i:02d}.{s}.png")
                    jobs.append({"svg": str(svg), "colors": colors, "hide": ["#hotspot"], "out": {px: png}})
                    out[s] = (png, px)
                frames.append(out)
            plan.append((tid, name, probe, frames))
    got = render(work / "jobs/catppuccin", jobs)
    themes = {}
    for tid, name, probe, frames in plan:
        root = work / "themes" / tid
        if tid not in themes:
            (root / "cursors").mkdir(parents=True)
            title = CATPPUCCIN_THEMES[tid][0]
            (root / "index.theme").write_text(index_theme(title, f"{title} cursors by Catppuccin"))
            themes[tid] = root
        if got.get(probe) is None:
            sys.exit(f"catppuccin {name}: no hotspot marker")
        pack(root, name, frames, tuple(got[probe]), 32, 24, 30 if len(frames) > 1 else 0)
    for tid in themes:
        link_aliases(themes[tid], _cursor_list(src / "src/cursorList"), groups)
    return themes


def build_oreo(src: Path, work: Path, groups: list[list[str]]) -> dict[str, Path]:
    base = src / "generator/oreo_base_cursors"
    shapes = []
    for cfg in sorted((src / "src/config").glob("*.cursor")):
        # The lines for the 32 px pictures (draft.cursor says size 30 for its 32 px picture).
        lines = [ln.split() for ln in cfg.read_text().splitlines()
                 if len(ln.split()) >= 4 and ln.split()[3].endswith("_32.png")]
        frames = [base / (ln[3].rsplit("_", 1)[0] + ".svg.oreo") for ln in lines]
        hot = (float(lines[0][1]), float(lines[0][2]))
        delay = int(lines[0][4]) if len(lines[0]) > 4 else 0
        shapes.append((cfg.stem, frames, hot, delay))
    jobs, plan = [], []
    for tid, (title, colour) in OREO_THEMES.items():
        pngs = work / "png" / tid
        pngs.mkdir(parents=True)
        colors = [(r"\{\{ background \}\}", colour), (r"\{\{ label \}\}", "#ffffff"),
                  (r"\{\{ shadow \}\}", "#000000"), (r"\{\{ shadow\s*opacity \}\}", "0.3"),
                  # Not filled in by Oreo's generator either; an unreadable value means 1.
                  (r"\{\{ opacity \}\}", "1")]
        for name, svgs, hot, delay in shapes:
            sizes = ANIM_SIZES if len(svgs) > 1 else SIZES
            frames = []
            for i, svg in enumerate(svgs):
                out = {}
                for s in sizes:
                    png = str(pngs / f"{name}.{i:02d}.{s}.png")
                    jobs.append({"svg": str(svg), "colors": colors, "out": {s: png}})
                    out[s] = (png, s)
                frames.append(out)
            plan.append((tid, name, frames, hot, delay))
    render(work / "jobs/oreo", jobs)
    themes = {}
    for tid, name, frames, hot, delay in plan:
        root = work / "themes" / tid
        if tid not in themes:
            (root / "cursors").mkdir(parents=True)
            title = OREO_THEMES[tid][0]
            (root / "index.theme").write_text(index_theme(title, f"{title} cursors by Alexey Varfolomeev"))
            themes[tid] = root
        pack(root, name, frames, hot, 32, 32, delay)
    for tid in themes:
        link_aliases(themes[tid], _cursor_list(src / "src/cursorList"), groups)
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
        bibata = fetch(work, "bibata")
        groups = alias_groups(bibata)
        themes = build_bibata(bibata, work)
        themes.update(build_banana(fetch(work, "banana"), work))
        themes.update(build_phinger(fetch(work, "phinger"), work, groups))
        themes.update(build_catppuccin(fetch(work, "catppuccin"), work, groups))
        themes.update(build_oreo(fetch(work, "oreo"), work, groups))
        for tid in ("fedora-glass-banana",):
            link_aliases(themes[tid], [], groups)
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
