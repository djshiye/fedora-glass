"""Liquid Glass release checks. Runs inside the test desktop (see ../run.sh).

    python3 run_checks.py [--only looks,leftovers,...] [--update-references]

Writes /out/report/{report.md,report.html,results.json} and the pictures they show.
Exit code 0 = every check passed, 1 = at least one failed, 2 = the test desktop broke.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import statistics
import sys
import time
import tomllib
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import lgqa  # noqa: E402
from lgqa import LG, OUT, Shell, ShellError  # noqa: E402

HERE = Path(__file__).resolve().parent
REFS = HERE.parent / "references"
NEW_REFS = OUT / "new-references"
REPORT = OUT / "report"
LIMITS = tomllib.loads((HERE.parent / "limits.toml").read_text())

DINO_EXTENSIONS = [
    "extension-list@tu.berry", "arcmenu@arcmenu.com", "dash-to-panel@jderose9.github.com",
    "appindicatorsupport@rgcjonas.gmail.com", "blur-my-shell@aunetx", "just-perfection-desktop@just-perfection",
    "deja-window@mcast.gnomext.com", "user-theme@gnome-shell-extensions.gcampax.github.com", LG,
]
NAMES = {
    "extension-list@tu.berry": "Extension List", "arcmenu@arcmenu.com": "ArcMenu",
    "dash-to-panel@jderose9.github.com": "Dash to Panel", "appindicatorsupport@rgcjonas.gmail.com": "AppIndicator",
    "blur-my-shell@aunetx": "Blur my Shell", "just-perfection-desktop@just-perfection": "Just Perfection",
    "deja-window@mcast.gnomext.com": "Deja Window", "user-theme@gnome-shell-extensions.gcampax.github.com": "User Themes",
    LG: "Liquid Glass",
}


# ---------------------------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------------------------
@dataclass
class Step:
    ok: bool
    text: str                       # one plain sentence
    images: list[str] = field(default_factory=list)
    info: bool = False              # shown, never fails the check


@dataclass
class Check:
    key: str
    title: str
    why: str
    steps: list[Step] = field(default_factory=list)
    crashed: str = ""

    @property
    def ok(self) -> bool:
        return not self.crashed and all(s.ok for s in self.steps)

    def add(self, ok: bool, text: str, *images) -> bool:
        self.steps.append(Step(bool(ok), text, [str(i) for i in images if i]))
        print(("  PASS  " if ok else "  FAIL  ") + text, flush=True)
        return bool(ok)

    def info(self, text: str) -> None:
        self.steps.append(Step(True, text, info=True))
        print("  INFO  " + text, flush=True)


class Ctx:
    def __init__(self, sh: Shell, update: bool) -> None:
        self.sh, self.update = sh, update
        self.s = sh.scale
        self.log = OUT / "shell.log"

    def px(self, rect) -> list[float]:
        return [v * self.s for v in rect]

    def log_lines(self) -> int:
        return sum(1 for _ in self.log.open(errors="replace"))

    def new_errors(self, since: int) -> list[str]:
        lines = self.log.read_text(errors="replace").splitlines()[since:]
        pat = re.compile(r"JS ERROR|TypeError|ReferenceError|Gjs-CRITICAL|Liquid Glass:.*(fail|error)", re.I)
        return [l for l in lines if pat.search(l) and "Xwayland" not in l]


# ---------------------------------------------------------------------------------------------
# Picture comparison against the reference pictures
# ---------------------------------------------------------------------------------------------
def thumb(a: np.ndarray, width: int = 1000) -> Image.Image:
    im = Image.fromarray(a.astype(np.uint8))
    return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)


def triptych(name: str, ref: np.ndarray, now: np.ndarray, diff: np.ndarray) -> str:
    tiles = [thumb(ref, 640), thumb(now, 640), thumb(diff, 640)]
    out = Image.new("RGB", (sum(t.width for t in tiles) + 20, tiles[0].height), (24, 24, 28))
    x = 0
    for t in tiles:
        out.paste(t, (x, 0))
        x += t.width + 10
    p = REPORT / f"{name}-compare.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    out.save(p, quality=85)
    return p.name


def picture(name: str, a: np.ndarray, width: int = 1000) -> str:
    p = REPORT / f"{name}.jpg"
    p.parent.mkdir(parents=True, exist_ok=True)
    thumb(a, width).save(p, quality=85)
    return p.name


def against_reference(ctx: Ctx, chk: Check, name: str, label: str, now: np.ndarray,
                      ignore: np.ndarray | None = None, lim: dict | None = None) -> bool:
    lim = {**LIMITS["looks"], **(lim or {})}
    ref_p = REFS / f"{name}.png"
    if ctx.update:
        lgqa.save(now, NEW_REFS / f"{name}.png")
        return chk.add(True, f"{label}: saved as the new reference picture.", picture(name, now))
    if not ref_p.exists():
        return chk.add(False, f"{label}: there is no reference picture yet (run with --update-references once).",
                       picture(name, now))
    ref = lgqa.load(ref_p)
    d = lgqa.compare(now, ref, ignore, lim["pixel_threshold"])
    img = triptych(name, ref, now, d.image)
    problems = []
    if d.mean_l > lim["max_mean_brightness_change"]:
        darker = "darker" if d.brightness_now < d.brightness_ref else "brighter"
        problems.append(f"it is {darker} overall (by {d.mean_l:.1f} of 255, limit {lim['max_mean_brightness_change']})")
    if d.changed > lim["max_changed_share"]:
        problems.append(f"{d.changed * 100:.1f} % of it changed (limit {lim['max_changed_share'] * 100:.1f} %)")
    if d.blob > lim["max_changed_patch"]:
        x, y, w, h = d.box
        problems.append(f"a {w}x{h} px patch changed at {x},{y} (limit {lim['max_changed_patch']} px)")
    if problems:
        return chk.add(False, f"{label} looks different from the reference: " + "; ".join(problems) + ".", img)
    return chk.add(True, f"{label} matches the reference (brightness change {d.mean_l:.1f}, "
                         f"{d.changed * 100:.2f} % changed, biggest patch {d.blob} px).", img)


def actor_box_js(match: str) -> str:
    """JS returning [x, y, w, h] of the first mapped actor whose class/name matches, or null."""
    return ("let r = null; const re = new RegExp(%s); const walk = a => { if (r) return;"
            " if (a.mapped && re.test(a.constructor.name + ' ' + (a.name || '') + ' ' + (a.style_class || ''))) {"
            " const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size(); if (w > 0) { r = [x, y, w, h]; return; } }"
            " for (const c of a.get_children()) walk(c); }; walk(global.stage); return r;") % json.dumps(match)


def actor_boxes(ctx: Ctx, match: str) -> list:
    """Boxes [x, y, w, h] of every shown actor whose class, name or style class matches."""
    return ctx.sh.json("const r = [], re = new RegExp(%s); const walk = a => { if (!a.mapped) return;"
                       " if (re.test(a.constructor.name + ' ' + (a.name || '') + ' ' + (a.style_class || ''))) {"
                       " const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size();"
                       " if (w > 0) { r.push([x, y, w, h]); return; } } for (const c of a.get_children()) walk(c); };"
                       " walk(global.stage); return r;" % json.dumps(match))


def clock_mask(ctx: Ctx, shape) -> np.ndarray:
    """Clocks change every minute: leave them out of picture comparisons."""
    return lgqa.rect_mask(shape, [ctx.px(b) for b in actor_boxes(ctx, "DateMenuButton|clock-display")], grow=6)


def panel_mask(ctx: Ctx, shape) -> np.ndarray:
    """The panels' task bars change as apps open and close (the panel glass is checked in "looks")."""
    boxes = ctx.sh.json("return (global.dashToPanel?.panels ?? []).map(p => { const a = p.panelBox ?? p;"
                        " const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size(); return [x, y, w, h]; });")
    return lgqa.rect_mask(shape, [ctx.px(b) for b in boxes], grow=2)


def settle(sec: float = 1.0) -> None:
    time.sleep(sec)


# ---------------------------------------------------------------------------------------------
# 1. Looks
# ---------------------------------------------------------------------------------------------
ARC = "Main.extensionManager.lookup('arcmenu@arcmenu.com').stateObj.menuControllers[0]"


def check_looks(ctx: Ctx) -> Check:
    c = Check("looks", "The glass looks right",
              "Compares the desktop, panel, menus and windows with reference pictures, at 125 % scaling. "
              "Catches black glass (1.3.0) and stray dark boxes in menus (1.4.2).")
    sh = ctx.sh
    sh.close_all()
    lgqa.kill_apps()
    settle(2)

    now = lgqa.load(sh.shot("looks-desktop"))
    mask = clock_mask(ctx, now.shape)
    against_reference(ctx, c, "desktop", "Desktop and panel", now, mask)

    # ArcMenu
    sh.eval(f"{ARC}.menuButton.toggleMenu(); 1")
    if sh.wait_for(f"return {ARC}._menuButton.arcMenu.isOpen;", 5):
        settle(1.5)
        now = lgqa.load(sh.shot("looks-arcmenu"))
        against_reference(ctx, c, "arcmenu", "ArcMenu", now, mask)
        sh.eval(f"if ({ARC}._menuButton.arcMenu.isOpen) {ARC}.menuButton.toggleMenu(); 1")
    else:
        c.add(False, "ArcMenu did not open.")
    settle(1)

    # Quick Settings
    sh.eval("Main.panel.statusArea.quickSettings.menu.open(); 1")
    settle(1.5)
    now = lgqa.load(sh.shot("looks-quick-settings"))
    against_reference(ctx, c, "quick-settings", "Quick Settings", now, mask)
    sh.eval("Main.panel.statusArea.quickSettings.menu.close(); 1")
    settle(1)

    # Extension List's menu (where 1.4.2 showed a dark box at 125 %)
    opened = sh.eval("(() => { const b = Main.panel.statusArea['extension-list@tu.berry']; if (!b || !b.menu) return 0;"
                     " b.menu.open(); return 1; })()")
    if opened == "1":
        settle(1.5)
        now = lgqa.load(sh.shot("looks-extension-list"))
        against_reference(ctx, c, "extension-list-menu", "Extension List menu", now, mask)
        sh.eval("Main.panel.statusArea['extension-list@tu.berry'].menu.close(); 1")
    else:
        c.add(False, "The Extension List button is missing from the panel.")
    settle(1)

    # Windows: Files in front of a terminal
    lgqa.launch(["ptyxis", "--new-window"], log="ptyxis")
    term = sh.wait_window(r"ptyxis|terminal")
    sh.put(term["id"], 140, 110, 820, 520)
    lgqa.open_files()
    files = sh.wait_window(r"nautilus")
    settle(2)
    sh.put(files["id"], 640, 260, 860, 540, focus=True)
    settle(3)
    now = lgqa.load(sh.shot("looks-windows"))
    against_reference(ctx, c, "windows", "Terminal and Files windows", now, mask)

    # The glass alone: hide Files' own content, keep only what Liquid Glass draws under it.
    sh.win_js(files["id"], "a.get_children().filter(c => !c.name).forEach(c => c.opacity = 0); return 1;")
    settle(1.5)
    now = lgqa.load(sh.shot("looks-glass-only"))
    sh.win_js(files["id"], "a.get_children().forEach(c => c.opacity = 255); return 1;")
    against_reference(ctx, c, "window-glass-only", "Window glass with the window's content hidden", now, mask)
    fx, fy, fw, fh = ctx.px(sh.window(r"nautilus")["frame"])
    inner = (fx + fw * 0.15, fy + fh * 0.25, fw * 0.7, fh * 0.6)
    wall = lgqa.load(Path("/opt/lgqa/wallpaper.png"))      # drawn for one screen; Files is on the first
    glass_l = float(lgqa.lum(lgqa.crop(now, inner)).mean())
    wall_l = float(lgqa.lum(lgqa.crop(wall, inner)).mean())
    ratio = glass_l / max(wall_l, 1)
    c.add(ratio >= LIMITS["looks"]["min_glass_vs_wallpaper"],
          f"Window glass brightness is {glass_l:.0f} over wallpaper of {wall_l:.0f} "
          f"({ratio * 100:.0f} %, needs at least {LIMITS['looks']['min_glass_vs_wallpaper'] * 100:.0f} %)."
          + ("" if ratio >= LIMITS["looks"]["min_glass_vs_wallpaper"] else " The glass is too dark, like 1.3.0's black glass."))
    sh.close_all()
    lgqa.kill_apps()
    return c


# ---------------------------------------------------------------------------------------------
# 2. Leftover window pieces
# ---------------------------------------------------------------------------------------------
SHADOW = 70      # screen pixels around a window where its shadow may change the picture


def mark(now: np.ndarray, *boxes) -> np.ndarray:
    a = now.copy()
    for box in boxes:
        if not box:
            continue
        x, y, w, h = box
        g = 6
        x0, y0, x1, y1 = max(x - g, 0), max(y - g, 0), min(x + w + g, a.shape[1] - 1), min(y + h + g, a.shape[0] - 1)
        a[y0:y0 + 4, x0:x1] = a[y1 - 4:y1, x0:x1] = (255, 220, 0)
        a[y0:y1, x0:x0 + 4] = a[y0:y1, x1 - 4:x1] = (255, 220, 0)
    return a


class Leftovers:
    """Looks for two kinds of leftovers after each step:
    - pieces of the Electron window's colour anywhere outside where the window is now;
    - anything else that changed, compared with the desktop before the window opened,
      outside every window and its shadow (for example a strip of glass at the screen edge)."""

    def __init__(self, ctx: Ctx, c: Check, clean: np.ndarray, clean_mask: np.ndarray) -> None:
        self.ctx, self.c, self.clean, self.clean_mask = ctx, c, clean, clean_mask
        self.panels = panel_mask(ctx, clean.shape)

    def verdict(self, kind: str, step: str, name: str, pattern: str) -> None:
        ctx, lim = self.ctx, LIMITS["leftovers"]
        now = lgqa.load(ctx.sh.shot(name))
        wins = [w for w in ctx.sh.windows() if not w["minimized"]]
        me = [w["frame"] for w in wins if re.search(pattern, w["title"])]
        colour = lgqa.magenta(now) & ~lgqa.magenta(self.clean) & ~lgqa.rect_mask(now.shape, [ctx.px(r) for r in me], grow=4)
        n = int(colour.sum())
        cbox = lgqa.largest_blob(colour, cell=2, min_hits=1)[1] if n else None
        outside = lgqa.rect_mask(now.shape, [ctx.px(w["frame"]) for w in wins], grow=SHADOW) | self.clean_mask | self.panels
        d = lgqa.compare(now, self.clean, outside, LIMITS["looks"]["pixel_threshold"])
        problems = []
        if n > lim["max_stray_pixels"]:
            problems.append(f"{n} pixels of the window were left behind" + (f" near {cbox[0]},{cbox[1]}" if cbox else ""))
        if d.blob > lim["max_stale_patch"]:
            x, y, w, h = d.box
            problems.append(f"a {w}x{h} px piece appeared on the desktop at {x},{y}")
        ok = not problems
        self.c.add(ok, f"{kind}, {step}: " + ("no leftover pieces." if ok else "; ".join(problems) + "."),
                   None if ok else picture(name, mark(now, cbox, d.box if d.blob > lim["max_stale_patch"] else None), 1000))


def fresh_screen(ctx: Ctx, name: str) -> np.ndarray:
    """The same screen with all glass rebuilt from scratch (Liquid Glass switched off and on)."""
    sh = ctx.sh
    sh.eval(f"const m = Main.extensionManager; m._callExtensionDisable('{LG}').then(() => m._callExtensionEnable('{LG}'))"
            ".catch(e => log('LGQA fresh ' + e)); 1")
    time.sleep(1)
    sh.wait_for(f"return Main.extensionManager.lookup('{LG}').state === 1;", 15)
    settle(2.5)
    return lgqa.load(sh.shot(name))


def leftovers_for(ctx: Ctx, c: Check, x11: bool, lo: Leftovers, term: dict) -> None:
    sh, lim = ctx.sh, LIMITS["leftovers"]
    kind = "Electron (XWayland)" if x11 else "Electron (Wayland)"
    tag = "x11" if x11 else "wl"
    pat = r"^LGQA Electron X11$" if x11 else r"^LGQA Electron$"
    lgqa.open_electron(x11)
    el = sh.wait_window(pat)
    settle(2)
    W = int(float(sh.eval("global.display.get_monitor_geometry(0).width")))
    H = int(float(sh.eval("global.display.get_monitor_geometry(0).height")))
    sh.put(el["id"], 180, 140, 640, 400, focus=True)
    settle(1.5)
    step = lambda text, name: lo.verdict(kind, text, f"leftovers-{tag}-{name}", pat)  # noqa: E731

    for i in range(1, 13):                       # move in steps, the way a drag does
        sh.place(el["id"], 180 + i * 45, 140 + i * 18, 640, 400)
        time.sleep(0.05)
    settle(1.2)
    step("after moving", "moved")

    for i in range(1, 11):                       # resize bigger, then smaller
        sh.place(el["id"], 720, 356, 640 + i * 30, 400 + i * 15)
        time.sleep(0.05)
    for i in range(1, 11):
        sh.place(el["id"], 720, 356, 940 - i * 40, 550 - i * 20)
        time.sleep(0.05)
    settle(1.2)
    step("after resizing", "resized")

    # Across the edge between the two screens, onto the second screen and back.
    for x in range(W - 900, W + 200, 100):
        sh.place(el["id"], x, 200, 640, 400)
        time.sleep(0.06)
    settle(1.2)
    step("on the second screen after crossing the screen edge", "seam-over")
    sh.place(el["id"], W - 320, 200, 640, 400)
    settle(1.2)
    step("half on each screen", "seam-half")
    for x in range(W - 320, 100, -120):
        sh.place(el["id"], x, 200, 640, 400)
        time.sleep(0.06)
    settle(1.2)
    step("back on the first screen", "seam-back")

    # Screen corners (glass near the edges of a screen).
    sh.place(el["id"], W - 640, 0, 640, 400)
    settle(1.2)
    step("in the top-right corner", "corner-tr")
    sh.place(el["id"], 0, H - 44 - 400, 640, 400)
    settle(1.2)
    step("in the bottom-left corner, above the panel", "corner-bl")

    # Maximized on the second screen, its edge lies exactly on the seam: the strip of the
    # first screen next to the seam must stay plain desktop (1.4.3 drew glass there).
    seam_check(ctx, c, kind, tag, el["id"], W)

    sh.win_js(el["id"], "w.minimize(); return 1;")          # minimize and restore (animations on)
    settle(1.5)
    step("while minimized", "minimized")
    sh.win_js(el["id"], "w.unminimize(); w.activate(global.get_current_time()); return 1;")
    settle(1.5)
    step("after restoring", "restored")

    # Behind the glass: the terminal in front sees the Electron window through its glass.
    # Move Electron away behind it, then compare with a freshly drawn screen.
    sh.place(el["id"], 300, 200, 640, 400)
    sh.focus(term["id"])
    settle(1.5)
    for i in range(1, 9):
        sh.place(el["id"], 300 + i * 70, 200 + i * 20, 640, 400)
        time.sleep(0.06)
    settle(1.5)
    now = lgqa.load(sh.shot(f"leftovers-{tag}-behind"))
    fresh = fresh_screen(ctx, f"leftovers-{tag}-behind-fresh")
    region = ctx.px(sh.window(r"ptyxis|terminal")["frame"])
    d = lgqa.compare(lgqa.crop(now, region), lgqa.crop(fresh, region), threshold=LIMITS["looks"]["pixel_threshold"])
    ok = d.blob <= lim["max_stale_patch"] and d.changed <= lim["max_stale_share"]
    img = triptych(f"leftovers-{tag}-behind", lgqa.crop(fresh, region), lgqa.crop(now, region), d.image)
    c.add(ok, f"{kind}, glass of the window in front after the one behind moved: " +
          ("it shows the current picture." if ok else
           f"it still shows an old picture ({d.changed * 100:.1f} % stale, biggest patch {d.blob} px)."), img)

    sh.win_js(el["id"], "w.delete(global.get_current_time()); return 1;")   # close (animations on)
    end = time.monotonic() + 10
    while sh.window(pat) and time.monotonic() < end:
        time.sleep(0.2)
    settle(1.5)
    step("after closing", "closed")


def seam_check(ctx: Ctx, c: Check, kind: str, tag: str, wid: int, seam: int) -> None:
    sh, lim = ctx.sh, LIMITS["leftovers"]
    sh.place(wid, seam + 200, 150, 700, 450, focus=True)
    settle(0.8)
    sh.win_js(wid, "w.maximize(Meta.MaximizeFlags.BOTH); return 1;")
    settle(2)
    info = sh.window_by_id(wid)
    on_seam = info and abs(info["frame"][0] - seam) <= 1
    now = lgqa.load(sh.shot(f"leftovers-{tag}-seam"))
    sh.win_js(wid, "w.minimize(); return 1;")
    settle(1.5)
    bare = lgqa.load(sh.shot(f"leftovers-{tag}-seam-bare"))
    sh.win_js(wid, "w.unminimize(); w.unmaximize(Meta.MaximizeFlags.BOTH); w.activate(global.get_current_time()); return 1;")
    settle(1.5)
    strip = ctx.px([seam - 80, 0, 80, float(sh.eval("global.display.get_monitor_geometry(0).height"))])
    a, b = lgqa.crop(now, strip), lgqa.crop(bare, strip)
    ignore = (clock_mask(ctx, now.shape) | panel_mask(ctx, now.shape))
    # Glass over a dark wallpaper is close to the wallpaper, so this looks for small changes.
    d = lgqa.compare(a, b, lgqa.crop(ignore, strip), lim["seam_pixel_threshold"])
    ok = on_seam and d.changed <= lim["max_seam_changed_share"]
    wide = lambda x: np.repeat(np.repeat(x, 3, axis=1), 1, axis=0)  # noqa: E731  (a thin strip, shown wider)
    c.add(ok, f"{kind}, maximized on the second screen: " + (
        "the first screen next to the edge stays plain desktop." if ok else
        ("it did not line up with the screen edge, so this could not be tested." if not on_seam else
         f"a strip of glass shows on the first screen next to the edge ({d.changed * 100:.0f} % of the strip changed).")),
        None if ok else triptych(f"leftovers-{tag}-seam", wide(b), wide(a), wide(d.image)))


def check_leftovers(ctx: Ctx) -> Check:
    c = Check("leftovers", "No leftover pieces of windows",
              "Moves, resizes, minimizes and closes an Electron window (like Claude Desktop) on Wayland and on "
              "XWayland, next to a terminal, across the edge between two screens and into screen corners. "
              "Looks for pieces left behind on the desktop or inside the glass (1.4.3).")
    sh = ctx.sh
    sh.close_all()
    lgqa.kill_apps()
    settle(1.5)
    lgqa.launch(["ptyxis", "--new-window"], log="ptyxis")
    term = sh.wait_window(r"ptyxis|terminal")
    sh.put(term["id"], 40, 60, 700, 460)
    settle(2)
    clean = lgqa.load(sh.shot("leftovers-clean"))
    lo = Leftovers(ctx, c, clean, clock_mask(ctx, clean.shape))
    for x11 in (False, True):
        try:
            leftovers_for(ctx, c, x11, lo, term)
        except ShellError as e:
            c.add(False, f"Electron ({'XWayland' if x11 else 'Wayland'}) could not be tested: {e}.")
    sh.close_all()
    lgqa.kill_apps()
    return c


# ---------------------------------------------------------------------------------------------
# 3. Content stays in place while resizing
# ---------------------------------------------------------------------------------------------
def content_box(img: np.ndarray, colour, frame_px) -> tuple | None:
    reg = lgqa.crop(img, frame_px)
    m = colour(reg)
    if m.sum() < 200:
        return None
    rows, cols = np.nonzero(m.sum(axis=1) > 20)[0], np.nonzero(m.sum(axis=0) > 20)[0]
    if not len(rows) or not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])      # left, top, right, bottom inside the frame


class Placement:
    """Follows one window through a resize: where its picture is drawn compared with where
    GNOME says it is, and where its content starts inside it compared with before."""

    def __init__(self, ctx: Ctx, label: str, pat: str, colour) -> None:
        self.ctx, self.label, self.pat, self.colour = ctx, label, pat, colour
        self.worst_off, self.off_img, self.base, self.worst_drift, self.drift_img, self.samples = 0.0, None, None, 0, None, 0
        self.missing = 0

    def sample(self, name: str) -> None:
        ctx = self.ctx
        info = ctx.sh.window(self.pat)
        img = lgqa.load(ctx.sh.shot(name))
        self.samples += 1
        bx, by, _, _ = info["buffer"]
        off = max([max(abs(sx - bx), abs(sy - by)) * ctx.s for sx, sy, _, _ in info["surfaces"]] or [0])
        if abs(info["scale"][0] - 1) > 1e-3 or abs(info["scale"][1] - 1) > 1e-3 or \
                abs(info["translation"][0]) > 0.5 or abs(info["translation"][1]) > 0.5:
            off = max(off, 999)
        if off > self.worst_off:
            self.worst_off, self.off_img = off, (img, info["frame"])
        if self.colour is None:
            return
        box = content_box(img, self.colour, ctx.px(info["frame"]))
        if box is None:
            self.missing += 1
            return
        if self.base is None:
            self.base = box
            return
        drift = max(abs(box[0] - self.base[0]), abs(box[1] - self.base[1]))
        if drift > self.worst_drift:
            self.worst_drift, self.drift_img, self.drift_box = drift, (img, info["frame"]), box

    def report(self, c: Check, how: str) -> None:
        lim = LIMITS["resize"]
        ok = self.worst_off <= lim["max_surface_offset"]
        c.add(ok, f"{self.label}, {how}: the window's picture stays on the window"
              + (f" (off by at most {self.worst_off:.0f} px over {self.samples} samples)." if ok else
                 f", but it was drawn {self.worst_off:.0f} px away from where the window is."),
              None if ok else picture(f"resize-{slug(self.label)}-{slug(how)}-offset", self._around(*self.off_img), 800))
        if self.colour is None:
            return
        if self.base is None:
            c.add(False, f"{self.label}, {how}: its content could not be found on screen.")
            return
        okd = self.worst_drift <= lim["max_content_drift"] and self.missing == 0
        c.add(okd, f"{self.label}, {how}: its content stays in the top-left corner"
              + (f" (moved at most {self.worst_drift} px)." if okd else
                 (f", but it moved {self.worst_drift} px away from the corner (limit {lim['max_content_drift']} px)."
                  if self.worst_drift > lim["max_content_drift"] else f", but it vanished in {self.missing} samples.")),
              None if okd or not self.drift_img else picture(f"resize-{slug(self.label)}-{slug(how)}-drift",
                                                             self._around(*self.drift_img), 800))

    def _around(self, img, frame):
        x, y, w, h = frame
        return lgqa.crop(img, self.ctx.px([x - 30, y - 30, w + 60, h + 60]))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def check_resize(ctx: Ctx) -> Check:
    c = Check("resize", "Window content stays in place while resizing",
              "Resizes a terminal, Files and an Electron window by dragging their corner, by app request, and by "
              "maximizing and restoring, and checks that what the app draws stays lined up with the window "
              "(1.4.3 pushed the terminal's content to the middle).")
    sh = ctx.sh
    sh.close_all()
    lgqa.kill_apps()
    settle(1)
    lgqa.open_terminal()
    lgqa.open_files()
    lgqa.open_electron(False)
    apps = [("Terminal", r"ptyxis", lgqa.green), ("Files", r"nautilus", None), ("Electron", r"^LGQA Electron$", lgqa.magenta)]
    for label, pat, colour in apps:
        try:
            w = sh.wait_window(pat)
        except ShellError as e:
            c.add(False, f"{label}: {e}.")
            continue
        for how in ("dragging the corner", "app-requested sizes", "maximize and restore"):
            sh.put(w["id"], 100, 80, 640, 420, focus=True)
            settle(1.5)
            pl = Placement(ctx, label, pat, colour)
            pl.sample(f"resize-{slug(label)}-{slug(how)}-start")
            if how == "dragging the corner":
                if not sh.drag_begin(w["id"]):
                    c.add(False, f"{label}: could not start dragging its corner.")
                    continue
                for i in range(1, 15):
                    sh.drag_to(740 + i * 34, 500 + i * 20)
                    time.sleep(0.05)
                    if i % 4 == 0:
                        pl.sample(f"resize-{slug(label)}-drag-{i}")
                for i in range(1, 8):
                    sh.drag_to(1216 - i * 50, 780 - i * 30)
                    time.sleep(0.05)
                pl.sample(f"resize-{slug(label)}-drag-held")
                sh.drag_end()
            elif how == "app-requested sizes":
                sizes = [(640 + i * 50, 420 + i * 30) for i in range(1, 11)] + [(1140 - i * 60, 720 - i * 36) for i in range(1, 9)]
                for i, (ww, hh) in enumerate(sizes):
                    sh.place(w["id"], 100, 80, ww, hh)
                    time.sleep(0.06)
                    if i % 4 == 3:
                        pl.sample(f"resize-{slug(label)}-req-{i}")
            else:
                # GNOME animates these with a scaled copy of the window, so only the
                # settled window is measured.
                sh.win_js(w["id"], "w.maximize(Meta.MaximizeFlags.BOTH); return 1;")
                settle(1.5)
                pl.sample(f"resize-{slug(label)}-max")
                sh.win_js(w["id"], "w.unmaximize(Meta.MaximizeFlags.BOTH); return 1;")
            settle(1.2)
            pl.sample(f"resize-{slug(label)}-{slug(how)}-end")
            pl.report(c, how)
    sh.close_all()
    lgqa.kill_apps()
    return c


# ---------------------------------------------------------------------------------------------
# 4. Speed and processor use
# ---------------------------------------------------------------------------------------------
# The test desktop draws on the processor, so glass always costs far more here than on a
# graphics card and frame times say little about Dino's PC. What carries over is how much
# work the glass does: nothing while nothing moves, and no redraws of glass that a busy
# window does not touch. Processor use and frame rates are still shown, for information.
PROBE_JS = """(() => { const GLib = imports.gi.GLib; const S = global.stage; const p = globalThis._lgqaProbe = {frames: [], t: 0};
 p.b = S.connect('before-paint', () => { p.t = GLib.get_monotonic_time(); });
 p.a = S.connect('after-paint', () => { try { S.peek_stage_views()[0].get_framebuffer().finish(); } catch (e) {}
   if (p.t) p.frames.push((GLib.get_monotonic_time() - p.t) / 1000); p.t = 0; });
 return 1; })()"""
STOP_JS = ("(() => { const p = globalThis._lgqaProbe; global.stage.disconnect(p.a); global.stage.disconnect(p.b);"
           " return JSON.stringify(p.frames); })()")
PANES_JS = ("const r = []; const w = a => { for (const e of a.get_effects?.() ?? []) if (e.constructor.name === 'LiquidGlassEffect'"
            " && a.mapped) { const [x, y] = a.get_transformed_position(); const [W, H] = a.get_transformed_size();"
            " r.push({x, y, w: W, h: H, renders: e.renders ?? 0, name: a.name || a.constructor.name}); }"
            " for (const c of a.get_children()) w(c); }; w(global.stage); return r;")
MOVE_JS = """(() => { const GLib = imports.gi.GLib; const a = global.get_window_actors().find(a => a.meta_window.get_id() == %d);
 const w = a.meta_window; let i = 0; globalThis._lgqaMoving = 1;
 GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => { i++; const t = i / 150 * Math.PI * 2;
   w.move_frame(true, Math.round(420 + 260 * Math.cos(t)), Math.round(220 + 120 * Math.sin(t)));
   if (i >= 150) { globalThis._lgqaMoving = 0; return GLib.SOURCE_REMOVE; } return GLib.SOURCE_CONTINUE; });
 return 1; })()"""


def timed(ctx: Ctx, seconds: float) -> dict:
    sh = ctx.sh
    panes0 = sh.json(PANES_JS)
    cpu0, t0 = lgqa.shell_cpu_seconds(), time.monotonic()
    sh.eval(PROBE_JS)
    time.sleep(seconds)
    frames = json.loads(sh.eval(STOP_JS))
    wall = time.monotonic() - t0
    panes1 = sh.json(PANES_JS)
    for p in panes1:      # match panes by place; a pane that came or went counts from 0
        before = next((q for q in panes0 if abs(q["x"] - p["x"]) < 1 and abs(q["y"] - p["y"]) < 1 and q["name"] == p["name"]), None)
        p["rate"] = (p["renders"] - (before["renders"] if before else 0)) / wall
    return {"frames": len(frames), "fps": len(frames) / wall, "cpu": (lgqa.shell_cpu_seconds() - cpu0) / wall * 100,
            "seconds": wall, "panes": panes1}


def overlaps(p: dict, box, reach: float = 60) -> bool:
    x, y, w, h = box
    return p["x"] < x + w + reach and p["x"] + p["w"] > x - reach and p["y"] < y + h + reach and p["y"] + p["h"] > y - reach


def set_glass(ctx: Ctx, on: bool) -> bool:
    sh = ctx.sh
    lgqa.subprocess.run(["gnome-extensions", "enable" if on else "disable", LG], env=lgqa.ENV, check=False)
    return sh.wait_for(f"return Main.extensionManager.lookup('{LG}').state === {1 if on else 2};", 20) and \
        (not on or sh.wait_for("let n = 0; const w = a => { if (a.constructor.name === 'LiquidGlassPane') n++;"
                               " for (const c of a.get_children()) w(c); }; w(global.stage); return n > 0;", 15))


def check_speed(ctx: Ctx) -> Check:
    c = Check("speed", "Light on the processor",
              "With a terminal and Files open, checks that the glass does no work while nothing moves, and that an "
              "app streaming text (like Claude writing an answer) on the other screen does not make unrelated glass "
              "redraw (1.4.3 redrew it on every frame, which made it very slow).")
    sh, lim = ctx.sh, LIMITS["speed"]
    sh.close_all()
    lgqa.kill_apps()
    lgqa.launch(["ptyxis", "--new-window"], log="ptyxis")
    term = sh.wait_window(r"ptyxis|terminal")
    sh.put(term["id"], 60, 60, 700, 440)
    lgqa.open_files()
    files = sh.wait_window(r"nautilus")
    sh.put(files["id"], 520, 260, 760, 460, focus=True)
    W = int(float(sh.eval("global.display.get_monitor_geometry(0).width")))
    lgqa.open_electron(False, busy=True)
    el = sh.wait_window(r"^LGQA Electron$")
    busy_box = [W + 420, 160, 760, 480]           # on the second screen, away from its panel
    sh.put(el["id"], *busy_box)
    sh.focus(files["id"])
    results = {}
    for state in ("on", "off"):
        if not set_glass(ctx, state == "on"):
            c.add(False, f"Could not switch the glass {state} for the comparison.")
            return c
        sh.win_js(el["id"], "w.minimize(); return 1;")
        sh.focus(files["id"])
        settle(3)
        idle = timed(ctx, 10)
        sh.win_js(el["id"], "w.unminimize(); return 1;")
        sh.focus(files["id"])
        settle(2)
        stream = timed(ctx, 10)
        sh.win_js(el["id"], "w.minimize(); return 1;")
        sh.focus(files["id"])
        settle(2)
        sh.eval(PROBE_JS)
        cpu0, t0 = lgqa.shell_cpu_seconds(), time.monotonic()
        sh.eval(MOVE_JS % files["id"])
        sh.wait_for("return !globalThis._lgqaMoving;", 90, 0.2)
        wall = time.monotonic() - t0
        frames = json.loads(sh.eval(STOP_JS))
        results[state] = {"idle": idle, "busy": stream,
                          "move": {"fps": len(frames) / wall, "cpu": (lgqa.shell_cpu_seconds() - cpu0) / wall * 100}}
    set_glass(ctx, True)
    (OUT / "speed.json").write_text(json.dumps(results, indent=2))
    on, off = results["on"], results["off"]

    i = on["idle"]
    idle_frames = i["frames"] * 10 / i["seconds"]
    c.add(idle_frames <= lim["max_idle_frames"],
          f"While nothing moves, the screen redraws {idle_frames:.0f} times in 10 s (limit {lim['max_idle_frames']})."
          + ("" if idle_frames <= lim["max_idle_frames"] else " Something keeps redrawing all the time."))
    c.add(i["cpu"] <= lim["max_idle_cpu"],
          f"While nothing moves, GNOME Shell uses {i['cpu']:.1f} % of a processor core (limit {lim['max_idle_cpu']} %).")
    idle_glass = max((p["rate"] for p in i["panes"]), default=0)
    c.add(idle_glass <= lim["max_idle_glass_redraws"],
          f"While nothing moves, the busiest piece of glass redraws {idle_glass:.1f} times a second "
          f"(limit {lim['max_idle_glass_redraws']}).")

    b = on["busy"]
    unrelated = [p for p in b["panes"] if not overlaps(p, busy_box)]
    worst = max(unrelated, key=lambda p: p["rate"], default=None)
    rate = worst["rate"] if worst else 0
    c.add(rate <= lim["max_unrelated_glass_redraws"],
          f"While an app streams text on the other screen, glass it does not touch redraws at most {rate:.1f} times "
          f"a second (limit {lim['max_unrelated_glass_redraws']}; {len(unrelated)} pieces of glass checked)."
          + ("" if rate <= lim["max_unrelated_glass_redraws"] else
             f" The busiest is at {worst['x']:.0f},{worst['y']:.0f} ({worst['w']:.0f}x{worst['h']:.0f})."))
    c.info(f"For information (no graphics card here, so not a pass/fail): while the app streams, GNOME Shell uses "
           f"{b['cpu']:.0f} % of a core with glass and {off['busy']['cpu']:.0f} % without; while a window moves, "
           f"{on['move']['fps']:.0f} frames a second with glass and {off['move']['fps']:.0f} without.")
    sh.close_all()
    lgqa.kill_apps()
    return c


# ---------------------------------------------------------------------------------------------
# 5. Lock screen
# ---------------------------------------------------------------------------------------------
def lock_mask(ctx: Ctx, shape) -> np.ndarray:
    boxes = actor_boxes(ctx, "UnlockDialogClock|unlock-dialog-clock")
    return lgqa.rect_mask(shape, [ctx.px(b) for b in boxes], grow=8) | clock_mask(ctx, shape)


def check_lock(ctx: Ctx) -> Check:
    c = Check("lock", "Locking the screen works",
              "Locks the screen with windows open, compares the lock screen and the password screen with reference "
              "pictures, unlocks, and checks the desktop comes back as it was, three times in a row.")
    sh, lim = ctx.sh, {**LIMITS["looks"], **LIMITS["lock"]}
    sh.close_all()
    lgqa.kill_apps()
    lgqa.launch(["ptyxis", "--new-window"], log="ptyxis")
    term = sh.wait_window(r"ptyxis|terminal")
    sh.put(term["id"], 200, 120, 800, 500, focus=True)
    settle(2)
    before = lgqa.load(sh.shot("lock-before"))
    mask = clock_mask(ctx, before.shape) | panel_mask(ctx, before.shape)
    panes0 = sh.glass_panes()
    log0 = ctx.log_lines()
    for cycle in range(1, 4):
        sh.eval("Main.screenShield._lockScreenState = 0; Main.screenShield.lock(true); 1")
        if not sh.wait_for("return Main.screenShield.locked;", 10):
            c.add(False, f"Lock {cycle}: the screen did not lock.")
            return c
        settle(2.5)
        sh.eval("const S = Main.screenShield; S._shortLightbox?.lightOff(); S._longLightbox?.lightOff(); 1")
        settle(0.5)
        if cycle == 1:
            now = lgqa.load(sh.shot("lock-screen"))
            against_reference(ctx, c, "lock", "Lock screen", now, lock_mask(ctx, now.shape), LIMITS["lock"])
            bad = sh.json("const g = []; const w = a => { if (/LiquidGlass/.test(a.constructor.name) && (a.reactive || a.can_focus))"
                          " g.push(a.constructor.name); a.get_children().forEach(w); }; w(global.stage); return g;")
            c.add(not bad, "The lock screen glass never takes clicks or keyboard focus." if not bad else
                  f"{len(bad)} glass pieces on the lock screen can take clicks or focus.")
            sh.eval("Main.screenShield._dialog._showPrompt(); 1")
            settle(1.5)
            now = lgqa.load(sh.shot("lock-prompt"))
            against_reference(ctx, c, "lock-prompt", "Password screen", now, lock_mask(ctx, now.shape), LIMITS["lock"])
        sh.eval("Main.screenShield.deactivate(true); 1")
        if not sh.wait_for("return !Main.screenShield.locked && Main.sessionMode.currentMode === 'user';", 15):
            c.add(False, f"Lock {cycle}: the desktop did not come back after unlocking.")
            return c
        settle(3)
    after = lgqa.load(sh.shot("lock-after"))
    d = lgqa.compare(after, before, mask, lim["pixel_threshold"])
    ok = d.blob <= lim["max_changed_patch"] and d.changed <= lim["max_changed_share"]
    c.add(ok, "After three locks the desktop looks exactly as before." if ok else
          f"After unlocking the desktop looks different ({d.changed * 100:.1f} % changed, biggest patch {d.blob} px).",
          triptych("lock-after", before, after, d.image))
    panes = sh.glass_panes()
    c.add(panes >= 1 and panes <= panes0 + 6, f"Glass pieces before locking: {panes0}, after three locks: {panes}."
          + ("" if panes >= 1 and panes <= panes0 + 6 else " Glass is missing or piling up."))
    errs = [e for e in ctx.new_errors(log0) if "liquid-glass" in e.lower() or "Liquid Glass" in e]
    c.add(not errs, "No Liquid Glass errors while locking." if not errs else
          f"{len(errs)} Liquid Glass errors while locking, first: {errs[0][-160:]}")
    sh.close_all()
    lgqa.kill_apps()
    return c


# ---------------------------------------------------------------------------------------------
# 6. Extension restart order
# ---------------------------------------------------------------------------------------------
HEALTH_JS = """const m = Main.extensionManager, o = {};
 for (const u of %s) { const e = m.lookup(u); o[u] = e ? e.state : -1; }
 const arc = m.lookup('arcmenu@arcmenu.com')?.stateObj?.menuControllers;
 o.arcmenu_ok = !!(arc && arc.length && arc[0]._menuButton && arc[0]._menuButton.get_parent());
 o.panels = global.dashToPanel?.panels?.length ?? 0;
 let n = 0; const w = a => { if (a.constructor.name === 'LiquidGlassPane') n++; for (const c of a.get_children()) w(c); }; w(global.stage);
 o.panes = n; return o;"""


def health(ctx: Ctx, expected: list[str]) -> dict:
    return ctx.sh.json(HEALTH_JS % json.dumps(expected))


def healthy(h: dict, expected: list[str], glass: bool = True) -> list[str]:
    bad = [NAMES.get(u, u) + (" is in an error state" if h[u] == 3 else " is not running") for u in expected if h[u] != 1]
    if not h["arcmenu_ok"] and "arcmenu@arcmenu.com" not in [u for u in expected if h[u] != 1]:
        bad.append("ArcMenu has no menu button")
    if not h["panels"]:
        bad.append("Dash to Panel has no panel")
    if glass and not h["panes"]:
        bad.append("Liquid Glass draws no glass")
    return bad


def check_restart(ctx: Ctx) -> Check:
    c = Check("restart", "Extensions come back after restarts",
              "Switches each extension off and on in Dino's order, the way Extension List does. GNOME then restarts "
              "the extensions after it, in its own order. Everything must come back, including ArcMenu (1.4.2 turned "
              "it red).")
    sh = ctx.sh
    lim = LIMITS["restart"]
    states = sh.ext_states()
    expected = [u for u in DINO_EXTENSIONS if states.get(u) == 1]
    missing = [NAMES[u] for u in DINO_EXTENSIONS if states.get(u) != 1]
    c.add(not missing, "All of Dino's extensions are running at the start." if not missing else
          "Not running at the start: " + ", ".join(missing) + ".")
    for u in DINO_EXTENSIONS:
        if u not in expected:
            continue
        log0 = ctx.log_lines()
        sh.eval(f"Main.extensionManager.disableExtension('{u}'); 1")
        time.sleep(3)
        sh.eval(f"Main.extensionManager.enableExtension('{u}'); 1")
        t0 = time.monotonic()
        bad = ["not checked"]
        while time.monotonic() - t0 < lim["settle_seconds"]:
            time.sleep(1)
            bad = healthy(health(ctx, expected), expected)
            if not bad:
                break
        took = time.monotonic() - t0
        errs = [e for e in ctx.new_errors(log0) if "liquid-glass" in e.lower()]
        if bad:
            c.add(False, f"After switching {NAMES[u]} off and on: " + "; ".join(bad) + f" after {lim['settle_seconds']} s.")
        else:
            c.add(not errs, f"After switching {NAMES[u]} off and on, everything was back in {took:.0f} s"
                  + ("." if not errs else f", but Liquid Glass logged {len(errs)} errors: {errs[0][-140:]}"))
    return c


def wait_healthy(ctx: Ctx, expected: list[str], glass: bool, seconds: float) -> tuple[list[str], float]:
    t0, bad = time.monotonic(), ["not checked"]
    while time.monotonic() - t0 < seconds:
        time.sleep(1)
        bad = healthy(health(ctx, expected), expected, glass)
        if not bad:
            break
    return bad, time.monotonic() - t0


def run_lg(*args: str) -> tuple[int, str]:
    p = lgqa.subprocess.run(["python3", "-m", "liquidglass", *args], cwd=str(lgqa.HOME / "liquid-glass-src"),
                            env=lgqa.ENV, capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_restore(ctx: Ctx) -> Check:
    c = Check("restore", "Restore original and Apply keep the desktop working",
              "Runs Restore original (it switches Liquid Glass off, so GNOME restarts the extensions after it), "
              "then Apply again, and checks every extension comes back each time, ArcMenu included.")
    sh, lim = ctx.sh, LIMITS["restart"]
    others = [u for u in DINO_EXTENSIONS if u not in (LG, "user-theme@gnome-shell-extensions.gcampax.github.com")
              and sh.ext_states().get(u) == 1]
    # The order that broke 1.4.3: GNOME's start order ending with Liquid Glass, ArcMenu,
    # Dash to Panel (it gets there when those are switched off and on in this order).
    for u in ("arcmenu@arcmenu.com", LG, "arcmenu@arcmenu.com", "dash-to-panel@jderose9.github.com"):
        sh.eval(f"Main.extensionManager.disableExtension('{u}'); 1")
        time.sleep(2)
        sh.eval(f"Main.extensionManager.enableExtension('{u}'); 1")
        wait_healthy(ctx, others + [LG], True, lim["settle_seconds"])
    order = sh.json("return Main.extensionManager._extensionOrder.slice(-3);")
    want = [LG, "arcmenu@arcmenu.com", "dash-to-panel@jderose9.github.com"]
    c.add(order == want, "Set up GNOME's start order to end with Liquid Glass, ArcMenu, Dash to Panel." if order == want
          else f"Could not set up the start order (it ends with {', '.join(NAMES.get(u, u) for u in order)}).")
    log0 = ctx.log_lines()
    rc, out = run_lg("revert")
    c.add(rc == 0, "Restore original finished." if rc == 0 else f"Restore original failed: {out[-200:]}")
    bad, took = wait_healthy(ctx, others, False, lim["settle_seconds"])
    c.add(not bad, f"After Restore original, Dino's other extensions were all working in {took:.0f} s." if not bad else
          "After Restore original: " + "; ".join(bad) + f" after {lim['settle_seconds']} s.")
    rc, out = run_lg("apply")
    c.add(rc == 0, "Apply finished." if rc == 0 else f"Apply failed: {out[-200:]}")
    expected = others + [LG]
    bad, took = wait_healthy(ctx, expected, True, lim["settle_seconds"] + 15)
    c.add(not bad, f"After Apply, the glass and every extension were back in {took:.0f} s." if not bad else
          "After Apply: " + "; ".join(bad) + ".")
    errs = [e for e in ctx.new_errors(log0) if "liquid-glass" in e.lower()]
    c.add(not errs, "No Liquid Glass errors during Restore original and Apply." if not errs else
          f"{len(errs)} Liquid Glass errors, first: {errs[0][-160:]}")
    return c


# ---------------------------------------------------------------------------------------------
# 7. Log and Apply
# ---------------------------------------------------------------------------------------------
def check_log(ctx: Ctx) -> Check:
    c = Check("log", "No errors from Liquid Glass",
              "Reads GNOME Shell's log for the whole run and the output of Apply.")
    apply_txt = (OUT / "apply.txt").read_text(errors="replace")
    failed = [l for l in apply_txt.splitlines() if l.startswith("✗")]
    c.add("apply exit 0" in apply_txt and not failed,
          "Apply finished without problems." if not failed else f"Apply reported: {failed[0]}")
    errs = [e for e in ctx.new_errors(0) if "liquid-glass" in e.lower() or "Liquid Glass" in e]
    c.add(not errs, "GNOME Shell logged no Liquid Glass errors." if not errs else
          f"GNOME Shell logged {len(errs)} Liquid Glass errors. First: {errs[0][-200:]}")
    alive = lgqa.subprocess.run(["pgrep", "-u", "dino", "-x", "gnome-shell"], capture_output=True).returncode == 0
    c.add(alive, "GNOME Shell kept running for the whole test." if alive else "GNOME Shell crashed.")
    return c


ALL = {"looks": check_looks, "leftovers": check_leftovers, "resize": check_resize, "speed": check_speed,
       "restart": check_restart, "restore": check_restore, "lock": check_lock, "log": check_log}


# ---------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------
def write_report(checks: list[Check], meta: dict) -> bool:
    REPORT.mkdir(parents=True, exist_ok=True)
    passed = all(c.ok for c in checks)
    head = f"Liquid Glass {meta['version']}: " + ("all release checks passed" if passed else "release checks FAILED")
    md = [f"## {'✅' if passed else '❌'} {head}", "",
          f"Test desktop: {meta['desktop']}.", "", "| Check | Result | What we saw |", "|---|---|---|"]
    for c in checks:
        failed = [s for s in c.steps if not s.ok]
        n = sum(1 for s in c.steps if not s.info)
        what = c.crashed or (failed[0].text if failed else f"{n} of {n} steps passed.")
        md.append(f"| {c.title} | {'✅ passed' if c.ok else '❌ failed'} | {what.replace('|', '/')} |")
    md += ["", "The full report with pictures is in the run's `release-check-report` download."]
    (REPORT / "report.md").write_text("\n".join(md) + "\n")

    css = """:root{--bg:#f6f6f8;--card:#fff;--fg:#1d1d22;--muted:#6b6b76;--ok:#1f8a4c;--bad:#c62f3a;--line:#e4e4ea}
@media (prefers-color-scheme:dark){:root{--bg:#141418;--card:#1e1e24;--fg:#ececf1;--muted:#a0a0ad;--ok:#4cc27d;--bad:#ff6b73;--line:#2e2e36}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:28px 16px 64px}h1{font-size:26px;margin:0 0 4px}.sub{color:var(--muted);margin:0 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin:0 0 16px}
.card h2{font-size:18px;margin:0 0 4px;display:flex;gap:10px;align-items:center}.why{color:var(--muted);margin:0 0 12px}
.pill{font-size:12px;font-weight:600;padding:2px 10px;border-radius:99px;color:#fff}.pill.ok{background:var(--ok)}.pill.bad{background:var(--bad)}
ul{list-style:none;margin:0;padding:0}li{padding:8px 0;border-top:1px solid var(--line)}li:first-child{border-top:0}
.mark{font-weight:700;margin-right:6px}.mark.ok{color:var(--ok)}.mark.bad{color:var(--bad)}.mark.info{color:var(--muted)}
img{display:block;max-width:100%;border-radius:8px;margin:8px 0 2px;border:1px solid var(--line)}.cap{color:var(--muted);font-size:12px}
.banner{border-radius:14px;padding:16px 20px;margin:0 0 20px;color:#fff;font-weight:600;font-size:17px}.banner.ok{background:var(--ok)}.banner.bad{background:var(--bad)}"""
    h = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
         f"<title>Release checks {html.escape(meta['version'])}</title><style>{css}</style></head><body><main>",
         f"<h1>Liquid Glass {html.escape(meta['version'])}</h1><p class=sub>Release checks on {html.escape(meta['desktop'])}. "
         f"{html.escape(meta['when'])}</p>",
         f"<div class='banner {'ok' if passed else 'bad'}'>{'Every check passed. This version can be released.' if passed else 'Some checks failed. The release is blocked until they pass.'}</div>"]
    for c in checks:
        h.append(f"<section class=card><h2>{html.escape(c.title)} <span class='pill {'ok' if c.ok else 'bad'}'>"
                 f"{'passed' if c.ok else 'failed'}</span></h2><p class=why>{html.escape(c.why)}</p><ul>")
        if c.crashed:
            h.append(f"<li><span class='mark bad'>✗</span>The check itself broke: {html.escape(c.crashed)}</li>")
        for s in sorted(c.steps, key=lambda s: (s.ok, s.info)):
            sign = "i" if s.info else ("✓" if s.ok else "✗")
            h.append(f"<li><span class='mark {'info' if s.info else 'ok' if s.ok else 'bad'}'>{sign}</span>{html.escape(s.text)}")
            if s.images and not s.ok or (s.images and c.key == "looks" and s.ok and len(c.steps) < 3):
                for im in s.images:
                    h.append(f"<img src='{html.escape(im)}' alt=''>")
                    if im.endswith("-compare.jpg"):
                        h.append("<div class=cap>Left: reference. Middle: this version. Right: what changed (red).</div>")
            h.append("</li>")
        h.append("</ul></section>")
    h.append("</main></body></html>")
    (REPORT / "report.html").write_text("".join(h))
    (REPORT / "results.json").write_text(json.dumps(
        {"passed": passed, **meta, "checks": [{"key": c.key, "title": c.title, "passed": c.ok, "crashed": c.crashed,
                                               "steps": [s.__dict__ for s in c.steps]} for c in checks]}, indent=2))
    return passed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(ALL))
    ap.add_argument("--update-references", action="store_true")
    ap.add_argument("--version", default="")
    args = ap.parse_args()
    sh = Shell()
    try:
        sh.wait_for("return !Main.layoutManager._startingUp;", 60)
        sh.wait_for(f"return Main.extensionManager.lookup('{LG}')?.state === 1;", 60)
        sh.uninhibit_animations()
        sh.eval("Main.overview.hide(); 1")
        sh.measure_scale()
        lgqa.XENV.update(lgqa.xwayland_env(sh))
    except ShellError as e:
        print(f"The test desktop did not start: {e}", file=sys.stderr)
        return 2
    ctx = Ctx(sh, args.update_references)
    version = args.version or re.search(r"__version__\s*=\s*['\"]([^'\"]+)",
                                        Path("/src/liquidglass/__init__.py").read_text()).group(1)
    meta = {"version": version, "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "desktop": f"GNOME 50 on Wayland, {sh.scale * 100:.0f} % scaling, Orchis Dark, Dino's extensions, overview off"}
    checks = []
    for key in args.only.split(","):
        print(f"== {key}", flush=True)
        try:
            checks.append(ALL[key](ctx))
        except Exception as e:  # a broken step must fail the check, never pass it
            traceback.print_exc()
            ch = Check(key, ALL[key].__name__.replace("check_", "").title(), "")
            ch.crashed = f"{type(e).__name__}: {str(e)[:300]}"
            checks.append(ch)
    ok = write_report(checks, meta)
    print((REPORT / "report.md").read_text())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
