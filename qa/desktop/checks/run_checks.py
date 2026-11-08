"""Fedora Glass release checks. Runs inside the test desktop (see ../run.sh).

    python3 run_checks.py [--only looks,leftovers,...] [--update-references]

Writes /out/report/{report.md,report.html,results.json} and the pictures they show.
Exit code 0 = every check passed, 1 = at least one failed, 2 = the test desktop broke.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
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
# Reference pictures are for the default 2000x1125 screens; other sizes keep their own set.
SCREEN = os.environ.get("LGQA_SCREEN", "2000x1125").split("@")[0]   # WxH@R: R is the refresh rate
REFS = HERE.parent / "references" / ("" if SCREEN == "2000x1125" else SCREEN)
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
    LG: "Fedora Glass", "spawn@djshiye.github.io": "Spawn",
}
SPAWN = "spawn@djshiye.github.io"
ARCMENU_UUID = "arcmenu@arcmenu.com"


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
        pat = re.compile(r"JS ERROR|TypeError|ReferenceError|Gjs-CRITICAL|(Liquid|Fedora) Glass:.*(fail|error)", re.I)
        return [l for l in lines if pat.search(l) and "Xwayland" not in l]


def ours(line: str) -> bool:
    """A log line from this project, under its old name or its new one (Fedora Glass)."""
    low = line.lower()
    return "liquid-glass" in low or "liquid glass" in low or "fedora glass" in low or "fedora-glass" in low


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
    if not ref_p.exists() and SCREEN != "2000x1125":
        chk.info(f"{label}: not compared, there are no reference pictures for {SCREEN} screens.")
        picture(name, now)
        return True
    if not ref_p.exists():
        return chk.add(False, f"{label}: there is no reference picture yet (run with --update-references once).",
                       picture(name, now))
    # GNOME lays some menus out a pixel or two differently from one session to the next
    # (Quick Settings at 125 %). Such a menu keeps one checked-in picture per layout
    # (name.alt.png); the closest one counts, and each is a picture of correct glass.
    best = None
    for p in (ref_p, REFS / f"{name}.alt.png"):
        if p.exists():
            r = lgqa.load(p)
            dd = lgqa.compare(now, r, ignore, lim["pixel_threshold"])
            if best is None or dd.blob < best[1].blob:
                best = (r, dd)
    ref, d = best
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


def steady_shot(sh, name: str, ignore: np.ndarray, limit: float = 6.0) -> np.ndarray:
    """A picture once the screen has stopped changing: a menu that is still growing open
    or drawing its first frame on a slow test machine would otherwise count as a look change."""
    end = time.monotonic() + limit
    now = lgqa.load(sh.shot(name))
    while time.monotonic() < end:
        time.sleep(0.5)
        nxt = lgqa.load(sh.shot(name))
        if nxt.shape == now.shape and not (np.abs(nxt.astype(int) - now.astype(int)).max(axis=-1)[~ignore] > 0).any():
            return nxt
        now = nxt
    return now


def settle(sec: float = 1.0) -> None:
    time.sleep(sec)


# ---------------------------------------------------------------------------------------------
# 1. Looks
# ---------------------------------------------------------------------------------------------
ARC = "Main.extensionManager.lookup('arcmenu@arcmenu.com').stateObj.menuControllers[0]"


QS_GRID = "Main.panel.statusArea.quickSettings.menu._grid"
QS_TOGGLES = ("NMWiredToggle", "NMWirelessToggle", "BluetoothToggle")
QS_PLACE_JS = """const m = Main.panel.statusArea.quickSettings.menu, g = m._grid;
 const t = g.get_children().find(c => c.constructor.name === 'NMWiredToggle');
 const box = a => { const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size(); return [x, y, w, h]; };
 const c = m._overlay?.get_children().find(k => k.visible && k.has_style_class_name?.('quick-toggle-menu-container'));
 return {grid: box(g), toggle: box(t), menu: c ? box(c) : null};"""


def quick_settings_toggle_menu(ctx: Ctx, c: Check) -> None:
    """A toggle's own menu (Wired, Wi-Fi) opens in place, under its toggle (1.5.1 put it low and off to
    the side, over the panel, when the menu had grown open)."""
    sh = ctx.sh
    find = f"{QS_GRID}.get_children().find(c => c.constructor.name === %s)"
    shown = [n for n in QS_TOGGLES if sh.eval(
        f"(() => {{ const t = {find % json.dumps(n)}; if (!t || t.visible) return 0; t.visible = true;"
        f" if (!t.title) t.title = {json.dumps(n[2:].replace('Toggle', ''))}; return 1; }})()") == "1"]
    wired = find % json.dumps("NMWiredToggle")
    try:
        # The test desktop has no network cards, so these toggles are hidden: showing them
        # moves the grid, and the menu measures again while it grows open, as on a real PC.
        sh.eval("Main.panel.statusArea.quickSettings.menu.open(); 1")
        settle(1.5)
        sh.eval(f"{wired}.menu.open(); 1")
        settle(1.5)
        g = sh.json(QS_PLACE_JS)
        now = lgqa.load(sh.shot("looks-quick-settings-wired"))
        if not g["menu"]:
            c.add(False, "Quick Settings: the Wired menu did not open.", picture("quick-settings-wired", now))
            return
        gx, menu, tog = g["grid"][0], g["menu"], g["toggle"]
        off_x, off_y = menu[0] - gx, menu[1] - (tog[1] + tog[3])
        c.add(abs(off_x) <= 2 and abs(off_y) <= 4,
              f"Quick Settings: the Wired menu opens right under its toggle (off by {off_x:.0f}, {off_y:.0f} px; "
              "limit 2, 4).", picture("quick-settings-wired", now))
    finally:
        sh.eval(f"(() => {{ const t = {wired}; t?.menu.close(); return 1; }})()")
        settle(0.5)
        sh.eval("Main.panel.statusArea.quickSettings.menu.close(); 1")
        for n in shown:
            sh.eval(f"(() => {{ const t = {find % json.dumps(n)}; if (t) t.visible = false; return 1; }})()")
        settle(1)


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
        now = steady_shot(sh, "looks-arcmenu", mask)
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
    quick_settings_toggle_menu(ctx, c)

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

    # Pictures only compare at full quality; lighter levels leave out the windows behind glass.
    level = sh.json(f"return Main.extensionManager.lookup('{LG}')?.stateObj?._speed?.level ?? 0;")
    c.add(level == 0, "The glass drew at full quality." if level == 0 else
          f"The glass had stepped itself down to level {level} (glass_quality was not full), "
          "so it shows only the wallpaper behind windows.")
    # The glass alone: hide Files' own content, keep only what Fedora Glass draws under it.
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
    """The same screen with all glass rebuilt from scratch (Fedora Glass switched off and on)."""
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


def maximized_while_opening(ctx: Ctx, c: Check) -> None:
    """A window maximized while it is still opening ends up fully shown (1.5.1 left Claude Desktop at
    opacity 1 of 255, see-through, until it was minimized and restored)."""
    sh = ctx.sh
    for ms in (150, 300):
        title = f"LGQA Claude {ms}"
        lgqa.open_electron(title=title, maximize_after_ms=ms)
        try:
            w = sh.wait_window(re.escape(title))
        except ShellError:
            c.add(False, f"Electron maximized {ms} ms after it shows: the window did not open.")
            continue
        settle(3)
        st = sh.json(f"const a = global.get_window_actors().find(a => a.meta_window.get_id() === {w['id']});"
                     " return a ? {op: a.opacity, sx: a.scale_x, sy: a.scale_y, tx: a.translation_x, ty: a.translation_y,"
                     " max: a.meta_window.maximized_horizontally && a.meta_window.maximized_vertically} : null;")
        ok = bool(st) and st["op"] == 255 and abs(st["sx"] - 1) < 1e-3 and abs(st["sy"] - 1) < 1e-3 and \
            abs(st["tx"]) < 0.5 and abs(st["ty"]) < 0.5
        img = lgqa.load(sh.shot(f"leftovers-maximized-{ms}"))
        c.add(ok, f"Electron maximized {ms} ms after it shows (like Claude Desktop): "
              + ("it is fully shown." if ok else f"it is left at opacity {st and st['op']} of 255, scale "
                 f"{st and round(st['sx'], 3)}, moved {st and round(st['tx'])} px."),
              picture(f"leftovers-maximized-{ms}", img))
    sh.close_all()
    lgqa.kill_apps()
    settle(1.5)


def check_leftovers(ctx: Ctx) -> Check:
    c = Check("leftovers", "No leftover pieces of windows",
              "Moves, resizes, minimizes and closes an Electron window (like Claude Desktop) on Wayland and on "
              "XWayland, next to a terminal, across the edge between two screens and into screen corners. "
              "Looks for pieces left behind on the desktop or inside the glass (1.4.3).")
    sh = ctx.sh
    sh.close_all()
    lgqa.kill_apps()
    settle(1.5)
    maximized_while_opening(ctx, c)
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
PANES_JS = ("const r = []; const w = a => { for (const e of a.get_effects?.() ?? []) if (e.constructor.name === 'FedoraGlassEffect'"
            " && a.mapped) { const [x, y] = a.get_transformed_position(); const [W, H] = a.get_transformed_size();"
            " r.push({x, y, w: W, h: H, renders: e.renders ?? 0, name: a.name || a.constructor.name}); }"
            " for (const c of a.get_children()) w(c); }; w(global.stage); return r;")
MOVE_JS = """(() => { const GLib = imports.gi.GLib; const a = global.get_window_actors().find(a => a.meta_window.get_id() == %d);
 const w = a.meta_window; let i = 0; globalThis._lgqaMoving = 1;
 GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => { i++; const t = i / 150 * Math.PI * 2;
   w.move_frame(true, Math.round(420 + 260 * Math.cos(t)), Math.round(220 + 120 * Math.sin(t)));
   if (i >= 150) { globalThis._lgqaMoving = 0; return GLib.SOURCE_REMOVE; } return GLib.SOURCE_CONTINUE; });
 return 1; })()"""


POINTER_NEAR_JS = """(() => { const {Clutter, GLib} = imports.gi; const be = global.stage.context.get_backend();
 const v = globalThis._lgqaVp || (globalThis._lgqaVp = be.get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE));
 let i = 0; globalThis._lgqaMoving = 1;
 GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => { i++; const t = i / 120 * Math.PI * 2;
   v.notify_absolute_motion(GLib.get_monotonic_time(), %f + 300 * Math.cos(t), %f + 40 * Math.sin(t));
   if (i >= 120) { globalThis._lgqaMoving = 0; return GLib.SOURCE_REMOVE; } return GLib.SOURCE_CONTINUE; });
 return 1; })()"""


def pointer_near_panel(ctx: Ctx, x: float, y: float) -> dict:
    """Glass redraws while the pointer moves just above a panel, near enough to light its rim."""
    sh = ctx.sh
    panes0 = sh.json(PANES_JS)
    t0 = time.monotonic()
    sh.eval(POINTER_NEAR_JS % (x, y))
    sh.wait_for("return !globalThis._lgqaMoving;", 60, 0.2)
    wall = time.monotonic() - t0
    worst = 0.0
    for p in sh.json(PANES_JS):
        before = next((q for q in panes0 if abs(q["x"] - p["x"]) < 1 and abs(q["y"] - p["y"]) < 1 and q["name"] == p["name"]), None)
        if p["name"] != "fedora-glass-reflections":    # the panel's own content may light up under the pointer
            worst = max(worst, (p["renders"] - (before["renders"] if before else 0)) / wall)
    return {"rate": worst, "seconds": wall}


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


def quiet(ctx: Ctx, limit: float = 30) -> None:
    """Wait until the desktop stops painting (a fresh desktop is still settling: apps
    loading, icons, the first frames after the glass comes on), up to `limit` seconds."""
    end = time.monotonic() + limit
    while time.monotonic() < end and timed(ctx, 2)["frames"] > 0:
        pass


def overlaps(p: dict, box, reach: float = 60) -> bool:
    x, y, w, h = box
    return p["x"] < x + w + reach and p["x"] + p["w"] > x - reach and p["y"] < y + h + reach and p["y"] + p["h"] > y - reach


def set_glass(ctx: Ctx, on: bool) -> bool:
    sh = ctx.sh
    lgqa.subprocess.run(["gnome-extensions", "enable" if on else "disable", LG], env=lgqa.ENV, check=False)
    return sh.wait_for(f"return Main.extensionManager.lookup('{LG}').state === {1 if on else 2};", 20) and \
        (not on or sh.wait_for("let n = 0; const w = a => { if (a.constructor.name === 'FedoraGlassPane') n++;"
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
    stream_boxes = []
    for state in ("on", "off"):
        if not set_glass(ctx, state == "on"):
            c.add(False, f"Could not switch the glass {state} for the comparison.")
            return c
        sh.win_js(el["id"], "w.minimize(); return 1;")
        sh.focus(files["id"])
        settle(3)
        quiet(ctx)
        idle = timed(ctx, 10)
        # The pointer just above the second screen's panel, where it lights the rim.
        H = float(sh.eval("global.display.get_monitor_geometry(1).y + global.display.get_monitor_geometry(1).height"))
        pointer = pointer_near_panel(ctx, W + 700, H - 260) if state == "on" else None
        settle(1)
        sh.win_js(el["id"], "w.unminimize(); return 1;")
        settle(1)
        # Deja Window can put the window back where it was saved when it comes back from
        # minimize, so place it again and measure against where it really is.
        sh.put(el["id"], *busy_box)
        sh.focus(files["id"])
        settle(2)
        stream = timed(ctx, 10)
        stream_boxes.append((sh.window_by_id(el["id"]) or {}).get("frame") or busy_box)
        sh.win_js(el["id"], "w.minimize(); return 1;")
        sh.focus(files["id"])
        settle(2)
        sh.eval(PROBE_JS)
        cpu0, t0 = lgqa.shell_cpu_seconds(), time.monotonic()
        sh.eval(MOVE_JS % files["id"])
        sh.wait_for("return !globalThis._lgqaMoving;", 90, 0.2)
        wall = time.monotonic() - t0
        frames = json.loads(sh.eval(STOP_JS))
        results[state] = {"idle": idle, "busy": stream, "pointer": pointer,
                          "move": {"fps": len(frames) / wall, "cpu": (lgqa.shell_cpu_seconds() - cpu0) / wall * 100}}
    set_glass(ctx, True)
    (OUT / "speed.json").write_text(json.dumps(results, indent=2))
    on, off = results["on"], results["off"]

    i = on["idle"]
    idle_frames = i["frames"] * 10 / i["seconds"]
    c.add(idle_frames <= lim["max_idle_frames"],
          f"While nothing moves, the screen redraws {idle_frames:.0f} times in 10 s (limit {lim['max_idle_frames']})."
          + ("" if idle_frames <= lim["max_idle_frames"] else " Something keeps redrawing all the time."))
    # Without a graphics card every painted frame costs the processor a lot, so idle
    # processor use only repeats the frame count above; it is shown, not judged.
    c.info(f"While nothing moves, GNOME Shell uses {i['cpu']:.1f} % of a processor core with glass and "
           f"{off['idle']['cpu']:.1f} % without (for information).")
    idle_glass = max((p["rate"] for p in i["panes"]), default=0)
    c.add(idle_glass <= lim["max_idle_glass_redraws"],
          f"While nothing moves, the busiest piece of glass redraws {idle_glass:.1f} times a second "
          f"(limit {lim['max_idle_glass_redraws']}).")

    pr = on["pointer"]["rate"]
    c.add(pr <= lim["max_pointer_glass_redraws"],
          f"While the pointer moves near a panel (lighting its rim), its glass redraws {pr:.1f} times a second "
          f"(limit {lim['max_pointer_glass_redraws']}; only the light should change, not the glass behind it).")

    b = on["busy"]
    real_box = stream_boxes[0]
    if real_box[0] < W:
        c.add(False, "Could not keep the streaming app on the second screen for the check.")
    unrelated = [p for p in b["panes"] if not overlaps(p, busy_box) and not overlaps(p, real_box)]
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
            bad = sh.json("const g = []; const w = a => { if (/FedoraGlass/.test(a.constructor.name) && (a.reactive || a.can_focus))"
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
    errs = [e for e in ctx.new_errors(log0) if ours(e)]
    c.add(not errs, "No Fedora Glass errors while locking." if not errs else
          f"{len(errs)} Fedora Glass errors while locking, first: {errs[0][-160:]}")
    theme_reloads_after_locks(ctx, c)
    sh.close_all()
    lgqa.kill_apps()
    lock_screens_change(ctx, c)
    screen_unplugged(ctx, c)
    login_backdrop(ctx, c)
    login_prompt(ctx, c)
    return c


def _theme_reloads(log: Path) -> int:
    try:
        return sum(1 for line in log.read_text(errors="replace").splitlines()
                   if "loading user theme" in line or "loading default theme" in line)
    except OSError:
        return 0


def theme_reloads_after_locks(ctx: Ctx, c: Check) -> None:
    """GNOME's User Themes leaves one more listener behind at every lock, and each one
    reloads the whole Shell theme when the theme name changes (Fedora Glass changes it
    twice at every dark/light switch). After the three locks above, one change of the
    name must reload the theme once."""
    sheets = ctx.sh.json("return imports.gi.St.ThemeContext.get_for_stage(global.stage).get_theme()"
                         ".get_custom_stylesheets().map(f => f ? f.get_basename() : null);")
    bad = sheets.count(None)
    c.add(not bad and "lock.css" not in sheets,
          "After three locks, the desktop's Shell theme has no lock screen styles and no broken entries."
          if not bad and "lock.css" not in sheets else
          f"After three locks, the desktop's Shell theme has {bad} broken entries and "
          f"{sheets.count('lock.css')} copies of the lock screen styles: the lock screen loaded its styles twice, "
          "and from now on every theme reload fails (User Themes breaks, dark/light stops switching).")
    log = lgqa.OUT / "shell.log"
    key = ["org.gnome.shell.extensions.user-theme", "name"]
    name = lgqa.subprocess.run(["gsettings", "get", *key], env=lgqa.ENV, capture_output=True, text=True).stdout.strip()
    if not name.strip("'"):
        c.add(False, "User Themes has no theme name set, so the theme reloads could not be counted.")
        return
    n0 = _theme_reloads(log)
    lgqa.subprocess.run(["gsettings", "set", *key, "''"], env=lgqa.ENV, check=False)
    settle(2)
    lgqa.subprocess.run(["gsettings", "set", *key, name], env=lgqa.ENV, check=False)
    settle(3)
    n = _theme_reloads(log) - n0
    c.add(n <= 2, f"After three locks, two theme changes reload the Shell theme {n} times (one each)." if n <= 2 else
          f"After three locks, two theme changes reload the Shell theme {n} times instead of 2: User Themes' "
          "leftover listeners from each lock are back (every dark/light switch gets slower with each lock).")


UNPLUG_PY = r"""
import sys
from gi.repository import Gio, GLib
bus = Gio.bus_get_sync(Gio.BusType.SESSION)
def call(m, a=None, s=None):
    return bus.call_sync("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                         "org.gnome.Mutter.DisplayConfig", m, a, s and GLib.VariantType(s), Gio.DBusCallFlags.NONE,
                         10000, None).unpack()
serial, monitors, _l, _p = call("GetCurrentState")
keep = int(sys.argv[2])
layout, x = [], 0
for i, ((conn, *_), modes, _mp) in enumerate(sorted(monitors, key=lambda m: m[0][0])[:keep]):
    mode = next((m for m in modes if m[6].get("is-current")), None) or \
        next((m for m in modes if m[6].get("is-preferred")), modes[0])
    scale = min(mode[5], key=lambda v: abs(v - float(sys.argv[1])))
    layout.append((x, 0, scale, 0, i == 0, [(conn, mode[0], {})]))
    x += round(mode[1] / scale)
call("ApplyMonitorsConfig", GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 1, layout, {})))
"""

PANEL_GLASS_JS = """(() => { let n = 0; const w = a => { if (a.constructor.name === 'FedoraGlassPane' && a.mapped
  && a.name === 'fedora-glass-glass' && a.height < 200 && a.width > 400) n++; a.get_children().forEach(w); };
  w(global.stage); return JSON.stringify({screens: global.display.get_n_monitors(),
  panels: global.dashToPanel?.panels?.length ?? 0, glass: n}); })()"""


def _screens(sh, keep: int) -> dict:
    scale = os.environ.get("LGQA_SCALE", "1.25")
    lgqa.subprocess.run(["python3", "-c", UNPLUG_PY, scale, str(keep)], env=lgqa.ENV, capture_output=True, timeout=30)
    settle(4)
    return sh.json(f"return JSON.parse({PANEL_GLASS_JS});")


def screen_unplugged(ctx: Ctx, c: Check) -> None:
    """The second screen unplugged (or switched off) and plugged back in: the panel
    that stays keeps its glass (1.5.4 left it in Dash to Panel's old box, with none)."""
    try:
        one = _screens(ctx.sh, 1)
        ok = one["screens"] == 1 and one["glass"] == one["panels"] >= 1
        c.add(ok, "Second screen unplugged: the panel left keeps its glass." if ok else
              f"Second screen unplugged: {one['glass']} of {one['panels']} panels have glass "
              f"({one['screens']} screens).")
    finally:
        two = _screens(ctx.sh, 2)
    ok = two["screens"] == 2 and two["glass"] == two["panels"] == 2
    c.add(ok, "Plugged back in: both panels have glass." if ok else
          f"Plugged back in: {two['glass']} of {two['panels']} panels have glass ({two['screens']} screens).")
    # The speed watch keeps one entry per screen it has seen drawn; 1.5.7 kept the old
    # screens' entries after every unplug (11 after three unplugs of two screens).
    views = ctx.sh.json(f"return Main.extensionManager.lookup('{LG}').stateObj?._speed?._views?.size ?? -1;")
    c.add(0 <= views <= two["screens"], f"The speed watch follows {views} screens after the unplug, as many as there are."
          if 0 <= views <= two["screens"] else
          f"The speed watch still follows {views} screens after the unplug, with {two['screens']} plugged in.")


LOCK_SHEETS_JS = """
const d = Main.screenShield._dialog;
const sheets = (d ? d.get_children() : []).filter(a => a.name === 'fedora-glass-lock-sheet').map(a => {
    const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size();
    return [x, y, w, h].map(Math.round); });
return {monitors: Main.layoutManager.monitors.map(m => [m.x, m.y, m.width, m.height]), sheets};
"""


def _sheets_fit(g: dict, pad: int = 120) -> bool:
    """One sheet for each screen, covering it, and not much bigger (a sheet has a margin)."""
    if len(g["sheets"]) != len(g["monitors"]):
        return False
    for mx, my, mw, mh in g["monitors"]:
        if not any(x <= mx and y <= my and x + w >= mx + mw and y + h >= my + mh
                   and w <= mw + 2 * pad and h <= mh + 2 * pad for x, y, w, h in g["sheets"]):
            return False
    return True


def lock_screens_change(ctx: Ctx, c: Check) -> None:
    """A screen rescaled (or plugged in, woken, taken away) while locked: the glass sheets
    must follow (1.5.2 kept the old places, leaving part of a screen without glass)."""
    sh = ctx.sh
    scale = os.environ.get("LGQA_SCALE", "1.25")
    sh.eval("Main.screenShield._lockScreenState = 0; Main.screenShield.lock(true); 1")
    if not sh.wait_for("return Main.screenShield.locked;", 10):
        c.add(False, "Lock 4: the screen did not lock.")
        return
    settle(2.5)
    before = sh.json(LOCK_SHEETS_JS)
    try:
        for want in ("1.0", scale):
            lgqa.subprocess.run(["python3", str(Path(__file__).with_name("scale.py")), want], env=lgqa.ENV,
                                capture_output=True, timeout=30)
            settle(3)
            g = sh.json(LOCK_SHEETS_JS)
            ok = _sheets_fit(g)
            c.add(ok, f"Screens changed to {float(want) * 100:.0f} % while locked: the lock screen glass covers each "
                  "screen again." if ok else
                  f"Screens changed to {float(want) * 100:.0f} % while locked: the glass sheets {g['sheets']} don't "
                  f"match the screens {g['monitors']} (before: {before['sheets']}).")
    finally:
        sh.eval("Main.screenShield.deactivate(true); 1")
        sh.wait_for("return !Main.screenShield.locked && Main.sessionMode.currentMode === 'user';", 15)
        settle(3)


GNOME_LOCK_GREY = (0x22, 0x22, 0x26)
LOGIN_MOCK_JS = """(() => { const {St, Gio} = imports.gi;
 globalThis._lgqaLoginCss = Gio.File.new_for_path(%s);
 St.ThemeContext.get_for_stage(global.stage).get_theme().load_stylesheet(globalThis._lgqaLoginCss);
 const [W, H] = global.stage.get_size(), m = Main.layoutManager.primaryMonitor;
 const g = new St.Widget({name: 'lockDialogGroup', x: 0, y: 0, width: W, height: H});
 const d = new St.Widget({style_class: 'login-dialog', x: m.x, y: m.y, width: m.width, height: m.height});
 const card = new St.BoxLayout({style_class: 'login-dialog-prompt-layout', vertical: true,
   x: Math.round(m.width / 2 - 180), y: Math.round(m.height / 2 - 90), width: 360, height: 180});
 card.add_child(new St.Entry({style_class: 'login-dialog-prompt-entry', hint_text: 'Password', x_expand: true}));
 d.add_child(card); g.add_child(d);
 Main.layoutManager.uiGroup.add_child(g); globalThis._lgqaLogin = g; return 1; })()"""
LOGIN_UNMOCK_JS = """(() => { globalThis._lgqaLogin?.destroy();
 if (globalThis._lgqaLoginCss) imports.gi.St.ThemeContext.get_for_stage(global.stage).get_theme()
   .unload_stylesheet(globalThis._lgqaLoginCss); return 1; })()"""


def login_backdrop(ctx: Ctx, c: Check) -> None:
    """The login screen's glass reaches every screen and looks the same on each (1.5.1 on Fedora
    left the second one GNOME's grey; 1.5.2 lit only the main one with a spotlight).

    GDM can't run here, so this draws the parts the login screen has, the screen-wide
    #lockDialogGroup with the login dialog on the main screen, with the rules Apply adds
    on Fedora (no gdm.css, the desktop's sheet shared), and looks at each screen.
    """
    sh = ctx.sh
    sys.path.insert(0, "/src")
    from fedoraglass import login_screen
    css = Path("/tmp/lgqa-login.css")
    css.write_text(login_screen.css("#3584e4", "#6a3fb5", 0.4, shared=True))
    css.chmod(0o644)
    try:
        sh.eval(LOGIN_MOCK_JS % json.dumps(str(css)))
        settle(1)
        now = lgqa.load(sh.shot("login-screens"))
    finally:
        sh.eval(LOGIN_UNMOCK_JS)
    mons = json.loads(sh.eval("JSON.stringify(Main.layoutManager.monitors.map(m => [m.x, m.y, m.width, m.height]))"))
    k = sh.scale

    def patch(x, y, w, h, fx, fy):
        p = now[int((y + h * fy) * k):int((y + h * (fy + 0.1)) * k), int((x + w * fx) * k):int((x + w * (fx + 0.1)) * k), :3]
        return p.reshape(-1, 3).mean(0)

    grey = [i + 1 for i, m in enumerate(mons) if np.abs(patch(*m, 0.05, 0.45) - np.array(GNOME_LOCK_GREY)).max() < 6]
    c.add(not grey, "The login screen's glass backdrop covers every screen (drawn with the Fedora rules)." if not grey
          else f"The login screen's glass backdrop is missing on screen {', '.join(map(str, grey))}: GNOME's plain "
          "grey shows there.", picture("login-screens", now))
    # Same spots on each screen, around the password card and in the corners: no spotlight on one screen only.
    spots = [(0.05, 0.05), (0.25, 0.45), (0.65, 0.45), (0.45, 0.15), (0.45, 0.75), (0.85, 0.85)]
    worst = 0.0
    if len(mons) > 1:
        for fx, fy in spots:
            base = patch(*mons[0], fx, fy)
            for m in mons[1:]:
                worst = max(worst, float(np.abs(patch(*m, fx, fy) - base).max()))
    lim = 4
    c.add(worst <= lim, f"The login backdrop looks the same on every screen (largest difference {worst:.0f} of 255; "
          f"limit {lim})." if worst <= lim else f"The login backdrop differs between screens by up to {worst:.0f} of "
          f"255 (limit {lim}): one screen is lit differently.")


LOGIN_PROMPT_JS = """(async () => { const {St, Gio, AccountsService} = imports.gi;
 const LD = await import('resource:///org/gnome/shell/gdm/loginDialog.js');
 globalThis._lgqaLoginCss = Gio.File.new_for_path(%s);
 St.ThemeContext.get_for_stage(global.stage).get_theme().load_stylesheet(globalThis._lgqaLoginCss);
 const [W, H] = global.stage.get_size();
 const g = new St.Widget({name: 'lockDialogGroup', x: 0, y: 0, width: W, height: H});
 Main.layoutManager.uiGroup.add_child(g); globalThis._lgqaLogin = g;
 const d = new LD.LoginDialog(g); d.show(); d._userSelectionBox.hide();
 const a = d._authPrompt;
 a.setUser(AccountsService.UserManager.get_default().get_user('dino'));
 a._onAskQuestion(null, 'gdm-password', 'Password:', true);
 a.opacity = 255; a.show(); return 1; })()"""
LOGIN_PROMPT_GEO_JS = """const a = globalThis._lgqaLogin.get_first_child()._authPrompt;
 const [x, y] = a.get_transformed_position(), [w, h] = a.get_transformed_size();
 const m = Main.layoutManager.primaryMonitor;
 return {prompt: [x, y, w, h], monitor: [m.x, m.y, m.width, m.height]};"""


def login_prompt(ctx: Ctx, c: Check) -> None:
    """After a click on your name, the login screen shows GNOME's own password prompt. 1.5.6 drew one
    big flat box around the picture, the name and the field; now each is its own small piece of
    glass with no box behind them, and the prompt is narrower than GNOME's.

    This builds GNOME's real login dialog (GDM can't run here) with the rules Apply adds on Fedora.
    """
    sh = ctx.sh
    sys.path.insert(0, "/src")
    from fedoraglass import login_screen
    css = Path("/tmp/lgqa-login.css")
    css.write_text(login_screen.css("#3584e4", "#6a3fb5", 0.4, shared=True))
    css.chmod(0o644)
    try:
        sh.eval(LOGIN_PROMPT_JS % json.dumps(str(css)))
        settle(1.5)
        geo = sh.json(LOGIN_PROMPT_GEO_JS)
        now = lgqa.load(sh.shot("login-prompt"))
    except lgqa.ShellError as e:
        c.add(False, f"GNOME's login password prompt could not be shown here: {str(e)[:160]}")
        return
    finally:
        sh.eval(LOGIN_UNMOCK_JS)
    x, y, w, h = geo["prompt"]
    mx, my, mw, mh = geo["monitor"]
    k = sh.scale
    c.add(0 < w <= mw * 0.2 + 1, f"The login password prompt is {w:.0f} px wide on a {mw} px screen (at most a fifth)."
          if 0 < w <= mw * 0.2 + 1 else f"The login password prompt is {w:.0f} px wide on a {mw} px screen: too big "
          "(more than a fifth).", picture("login-prompt", now[int(my * k):int((my + mh) * k), int(mx * k):int((mx + mw) * k)]))
    # No box behind the prompt: just beside the picture, inside the prompt's area, the backdrop shows
    # as it does at the same height outside the prompt.
    def mean(px, py):
        return now[int(py * k) - 3:int(py * k) + 3, int(px * k) - 3:int(px * k) + 3, :3].reshape(-1, 3).mean(0)
    worst = 0.0
    for fy in (0.15, 0.45):
        inside = mean(x + w * 0.06, y + h * fy)
        outside = mean(x - w * 0.35, y + h * fy)
        worst = max(worst, float(np.abs(inside - outside).max()))
    c.add(worst <= 4, f"No box is drawn behind the login password prompt (difference {worst:.0f} of 255; limit 4)."
          if worst <= 4 else f"A box is drawn behind the login password prompt (difference {worst:.0f} of 255; "
          "limit 4).")


# ---------------------------------------------------------------------------------------------
# 6. Extension restart order
# ---------------------------------------------------------------------------------------------
HEALTH_JS = """const m = Main.extensionManager, o = {};
 for (const u of %s) { const e = m.lookup(u); o[u] = e ? e.state : -1; }
 const arc = m.lookup('arcmenu@arcmenu.com')?.stateObj?.menuControllers;
 o.arcmenu_ok = !!(arc && arc.length && arc[0]._menuButton && arc[0]._menuButton.get_parent());
 o.panels = global.dashToPanel?.panels?.length ?? 0;
 let n = 0; const w = a => { if (a.constructor.name === 'FedoraGlassPane') n++; for (const c of a.get_children()) w(c); }; w(global.stage);
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
        bad.append("Fedora Glass draws no glass")
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
        errs = [e for e in ctx.new_errors(log0) if ours(e)]
        if bad:
            c.add(False, f"After switching {NAMES[u]} off and on: " + "; ".join(bad) + f" after {lim['settle_seconds']} s.")
        else:
            c.add(not errs, f"After switching {NAMES[u]} off and on, everything was back in {took:.0f} s"
                  + ("." if not errs else f", but Fedora Glass logged {len(errs)} errors: {errs[0][-140:]}"))
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
    p = lgqa.subprocess.run(["python3", "-m", "fedoraglass", *args], cwd=str(lgqa.HOME / "fedora-glass-src"),
                            env=lgqa.ENV, capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout + p.stderr).strip()


# Keys GNOME, the apps and the other extensions write by themselves while the test desktop
# runs, not Fedora Glass: window sizes, a terminal's first profile, the order GNOME restarts
# extensions in, Blur my Shell's and Dash to Panel's own settings upgrades (panel keys move
# to monitor names), Deja Window's remembered windows, ArcMenu taking the Super key.
RESTORE_IGNORE = re.compile(r"^/org/gnome/(Ptyxis/|nautilus/|gedit/state/|portal/|evolution-data-server/|shell/(enabled-extensions|"
                            r"disabled-extensions|app-picker-layout|command-history|welcome-dialog-last-shown-version)$)"
                            r"|^/org/gtk/|^/org/gnome/desktop/(notifications/application|app-folders)"
                            r"|^/org/gnome/mutter/overlay-key$|^/org/gnome/shell/extensions/deja-window/"
                            r"|^/org/gnome/shell/extensions/blur-my-shell/(pipelines|settings-version)$"
                            r"|^/org/gnome/shell/extensions/dash-to-panel/(extension-version|panel-(anchors|element-positions|lengths|positions|sizes))$")


def dconf_keys(text: str) -> dict[str, str]:
    """`dconf dump /` as {"/path/key": value}."""
    out, section = {}, "/"
    for line in text.splitlines():
        if line.startswith("[") and line.endswith("]"):
            section = "/" + line[1:-1].strip("/") + "/"
            section = "/" if section == "//" else section
        elif "=" in line:
            k, v = line.split("=", 1)
            out[section + k] = v
    return out


def as_set(v: str | None) -> set[str]:
    return set(re.findall(r"'([^']*)'", v or ""))


def schema_defaults() -> dict[str, str]:
    """{"/dconf/path/key": default value as dconf prints it} for every installed schema with a
    fixed path, the extensions' own schemas included."""
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    sources = [Gio.SettingsSchemaSource.get_default()]
    for sd in sorted((lgqa.HOME / ".local/share/gnome-shell/extensions").glob("*/schemas")):
        if (sd / "gschemas.compiled").exists():
            sources.append(Gio.SettingsSchemaSource.new_from_directory(str(sd), None, False))
    out = {}
    for src in sources:
        for sid in src.list_schemas(True)[0]:
            sch = src.lookup(sid, False)
            if sch is None or not sch.get_path():
                continue
            for k in sch.list_keys():
                out[sch.get_path() + k] = sch.get_key(k).get_default_value().print_(True)
    return out


def same_value(a: str | None, b: str | None) -> bool:
    if a == b:
        return True
    try:        # 0.40000000000000002 and 0.4, @as [] and []: the same value printed two ways
        from gi.repository import GLib
        return GLib.Variant.parse(None, a, None, None).equal(GLib.Variant.parse(None, b, None, None))
    except Exception:
        return False


def back_as_before(c: Check) -> None:
    """After Restore original, Dino's settings are what they were before the first Apply,
    and no Fedora Glass file is left in the home folder."""
    before_file = OUT / "dconf-before.ini"
    if not before_file.exists():
        c.info("No record of the settings from before the first Apply, so they were not compared.")
        return
    before = dconf_keys(before_file.read_text(errors="replace"))
    now = dconf_keys(lgqa.subprocess.run(["dconf", "dump", "/"], env=lgqa.ENV, capture_output=True,
                                         text=True, timeout=30).stdout)
    defaults = schema_defaults()

    same = same_value

    # A key that is not set has its default value: compare what GNOME and the apps see.
    changed, pinned = [], []
    for k in sorted(set(before) | set(now)):
        if RESTORE_IGNORE.search(k):
            continue
        was, isnow = before.get(k, defaults.get(k)), now.get(k, defaults.get(k))
        if not same(was, isnow):
            changed.append(f"{k} was {str(was)[:60]}, now {str(isnow)[:60]}")
        elif k not in before and k in now:
            pinned.append(k)
    c.add(not changed, "Every setting is back to what it was before the first Apply." if not changed else
          f"{len(changed)} settings differ from before the first Apply, first: " + "; ".join(changed[:3]))
    if pinned:
        c.info(f"{len(pinned)} settings that followed their default are now set to that same default "
               f"(no visible change): {', '.join(pinned[:4])}")
    # GNOME restarts the extensions in its own order, so only which ones are on counts.
    key = "/org/gnome/shell/enabled-extensions"
    on = as_set(before.get(key)) == as_set(now.get(key))
    c.add(on, "The same extensions are switched on as before the first Apply." if on else
          f"Switched-on extensions differ: before {sorted(as_set(before.get(key)))}, now {sorted(as_set(now.get(key)))}")
    ext = lgqa.HOME / ".local/share/gnome-shell/extensions" / LG
    leftovers = [str(ext.relative_to(lgqa.HOME))] if ext.exists() else []
    for base in (lgqa.HOME / ".config", lgqa.HOME / ".local/share"):
        for f in base.rglob("*"):
            # Fedora Glass's own settings folder stays on purpose; other extensions are not ours.
            if "liquid-glass" in f.parts or "extensions" in f.parts or not f.is_file() or f.is_symlink():
                continue
            try:
                head = f.open("rb").read(512)
            except OSError:
                continue
            if b"Fedora Glass" in head or b"Liquid Glass" in head:
                leftovers.append(str(f.relative_to(lgqa.HOME)))
    c.add(not leftovers, "No Fedora Glass files are left in the home folder (its own settings folder aside)."
          if not leftovers else f"{len(leftovers)} Fedora Glass files left behind, first: {', '.join(leftovers[:3])}")


def check_restore(ctx: Ctx) -> Check:
    c = Check("restore", "Restore original and Apply keep the desktop working",
              "Runs Restore original (it switches Fedora Glass off, so GNOME restarts the extensions after it), "
              "then Apply again, and checks every extension comes back each time, ArcMenu included.")
    sh, lim = ctx.sh, LIMITS["restart"]
    others = [u for u in DINO_EXTENSIONS if u not in (LG, "user-theme@gnome-shell-extensions.gcampax.github.com")
              and sh.ext_states().get(u) == 1]
    # The order that broke 1.4.3: GNOME's start order ending with Fedora Glass, ArcMenu,
    # Dash to Panel (it gets there when those are switched off and on in this order).
    for u in ("arcmenu@arcmenu.com", LG, "arcmenu@arcmenu.com", "dash-to-panel@jderose9.github.com"):
        sh.eval(f"Main.extensionManager.disableExtension('{u}'); 1")
        time.sleep(2)
        sh.eval(f"Main.extensionManager.enableExtension('{u}'); 1")
        wait_healthy(ctx, others + [LG], True, lim["settle_seconds"])
    order = sh.json("return Main.extensionManager._extensionOrder.slice(-3);")
    want = [LG, "arcmenu@arcmenu.com", "dash-to-panel@jderose9.github.com"]
    c.add(order == want, "Set up GNOME's start order to end with Fedora Glass, ArcMenu, Dash to Panel." if order == want
          else f"Could not set up the start order (it ends with {', '.join(NAMES.get(u, u) for u in order)}).")
    log0 = ctx.log_lines()
    rc, out = run_lg("revert")
    c.add(rc == 0, "Restore original finished." if rc == 0 else f"Restore original failed: {out[-200:]}")
    bad, took = wait_healthy(ctx, others, False, lim["settle_seconds"])
    c.add(not bad, f"After Restore original, Dino's other extensions were all working in {took:.0f} s." if not bad else
          "After Restore original: " + "; ".join(bad) + f" after {lim['settle_seconds']} s.")
    back_as_before(c)
    rc, out = run_lg("apply")
    c.add(rc == 0, "Apply finished." if rc == 0 else f"Apply failed: {out[-200:]}")
    expected = others + [LG]
    bad, took = wait_healthy(ctx, expected, True, lim["settle_seconds"] + 15)
    c.add(not bad, f"After Apply, the glass and every extension were back in {took:.0f} s." if not bad else
          "After Apply: " + "; ".join(bad) + ".")
    shell_parts_done(c, "After Restore original and Apply")
    glass_part_off(ctx, c, others)
    errs = [e for e in ctx.new_errors(log0) if ours(e)]
    c.add(not errs, "No Fedora Glass errors during Restore original and Apply." if not errs else
          f"{len(errs)} Fedora Glass errors, first: {errs[0][-160:]}")
    return c


def _set_target(name: str, on: bool) -> None:
    p = lgqa.HOME / ".config/liquid-glass/settings.json"
    d = json.loads(p.read_text())
    d.setdefault("targets", {})[name] = on
    p.write_text(json.dumps(d, indent=2))


def glass_part_off(ctx: Ctx, c: Check, others: list[str]) -> None:
    """Only "Fedora Glass effects" turned off in the app, then Apply: the glass extension goes
    off mid-session like in Restore original, so ArcMenu must survive that too (1.5.2 left
    it red), and the Shell theme's User Themes stays on (it shares GNOME's list)."""
    sh, lim = ctx.sh, LIMITS["restart"]
    for u in ("arcmenu@arcmenu.com", LG, "arcmenu@arcmenu.com", "dash-to-panel@jderose9.github.com"):
        sh.eval(f"Main.extensionManager.disableExtension('{u}'); 1")
        time.sleep(2)
        sh.eval(f"Main.extensionManager.enableExtension('{u}'); 1")
        wait_healthy(ctx, others + [LG], True, lim["settle_seconds"])
    _set_target("glass", False)
    try:
        rc, out = run_lg("apply")
        c.add(rc == 0, "Apply with only Fedora Glass effects turned off finished." if rc == 0 else
              f"Apply with Fedora Glass effects off failed: {out[-200:]}")
        bad, took = wait_healthy(ctx, others, False, lim["settle_seconds"])
        c.add(not bad, f"With Fedora Glass effects turned off, Dino's other extensions were all working in {took:.0f} s."
              if not bad else "With Fedora Glass effects turned off: " + "; ".join(bad) + ".")
        on = sh.json("return global.settings.get_strv('enabled-extensions');")
        theme = "user-theme@gnome-shell-extensions.gcampax.github.com"
        ok = theme in on and LG not in on
        c.add(ok, "GNOME's extension list lost only the glass extension; User Themes stayed on." if ok else
              f"GNOME's extension list is wrong after turning the glass off: glass {'on' if LG in on else 'off'}, "
              f"User Themes {'on' if theme in on else 'off'}.")
    finally:
        _set_target("glass", True)
    rc, out = run_lg("apply")
    bad, took = wait_healthy(ctx, others + [LG], True, lim["settle_seconds"] + 15)
    c.add(rc == 0 and not bad, f"Turned back on, the glass and every extension were back in {took:.0f} s." if rc == 0 and not bad
          else "Turning Fedora Glass effects back on: " + ("; ".join(bad) or out[-200:]) + ".")
    shell_parts_done(c, "With Fedora Glass effects turned back on")


def shell_parts_done(c: Check, when: str) -> None:
    """The glass extension came back live (GNOME already knew it), so the parts that wait for
    the glass were finished by the same Apply, not left for a restart (1.5.6 left them)."""
    p = lgqa.HOME / ".config/liquid-glass/pending-shell.json"
    try:
        waiting = json.loads(p.read_text()) if p.exists() else []
    except ValueError:
        waiting = ["unreadable"]
    theme = lgqa.subprocess.run(["gsettings", "get", "org.gnome.shell.extensions.user-theme", "name"], env=lgqa.ENV,
                                capture_output=True, text=True).stdout.strip()
    ok = not waiting and theme == "'FedoraGlass'"
    c.add(ok, f"{when}, the Shell theme, panel and menus were finished at once, with no restart needed." if ok else
          f"{when}, parts still wait for a restart ({', '.join(waiting) or 'none'}; Shell theme {theme}).")


# ---------------------------------------------------------------------------------------------
# 7. Log and Apply
# ---------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------
# Pop-ups and title bars that other themes or apps could paint over the glass
# ---------------------------------------------------------------------------------------------
# The surface's own fill (alpha) and whether a shown glass pane of about its size lies under it
# (covers at least 90 % of it and reaches at most 60 px past each side, which leaves out other glass).
SURFACE_JS = """const a = %s; if (!a || !a.mapped) return null;
 const [x, y] = a.get_transformed_position(), [w, h] = a.get_transformed_size();
 let glass = false; const walk = b => { if (!b.visible) return; if (b.constructor.name === 'FedoraGlassPane' && b.mapped && b.opacity > 0) {
   const [px, py] = b.get_transformed_position(), [pw, ph] = b.get_transformed_size();
   const ix = Math.max(0, Math.min(x + w, px + pw) - Math.max(x, px)), iy = Math.max(0, Math.min(y + h, py + ph) - Math.max(y, py));
   if (ix * iy >= 0.9 * w * h && pw <= w + 120 && ph <= h + 120) glass = true; } b.get_children().forEach(walk); };
 walk(Main.layoutManager.uiGroup);
 return {alpha: a.get_theme_node().get_background_color().alpha / 255, glass, box: [x, y, w, h]};"""
SWITCHER = "Main.layoutManager.uiGroup.get_children().find(c => c._switcherList)"
PREVIEWS = "global.dashToPanel.panels[0].taskbar.previewMenu"
RUN_DIALOG = "Main.layoutManager.modalDialogGroup.get_children().find(c => c.constructor.name === 'RunDialog')"
KEYS = {"alt": 0xffe9, "tab": 0xff09, "down": 0xff54, "escape": 0xff1b}


def _key(ctx: Ctx, name: str, down: bool) -> None:
    ctx.sh.eval("(globalThis._lgqaKb ||= global.stage.context.get_backend().get_default_seat()"
                ".create_virtual_device(imports.gi.Clutter.InputDeviceType.KEYBOARD_DEVICE))"
                ".notify_keyval(imports.gi.GLib.get_monotonic_time(), %d, imports.gi.Clutter.KeyState.%s); 1"
                % (KEYS[name], "PRESSED" if down else "RELEASED"))


def _glass_surface(c: Check, ctx: Ctx, label: str, js: str, lim: dict, shot: str) -> None:
    # A pop-up's glass is built when it first shows, so give it a moment.
    s = None
    for _ in range(8):
        s = ctx.sh.json(SURFACE_JS % js) or s
        if s and s["glass"] and s["alpha"] <= lim["max_surface_alpha"]:
            break
        settle(0.25)
    if not s:
        c.add(False, f"{label} did not show.")
        return
    img = picture(shot, lgqa.crop(lgqa.load(ctx.sh.shot(shot)), [v - 40 for v in ctx.px(s["box"][:2])]
                                  + [v + 80 for v in ctx.px(s["box"][2:])]), width=700)
    ok = s["glass"] and s["alpha"] <= lim["max_surface_alpha"]
    c.add(ok, f"{label} is glass (its own fill {s['alpha'] * 100:.0f} % opaque, glass under it: "
          f"{'yes' if s['glass'] else 'no'})." if ok else
          f"{label} is not glass: its own fill is {s['alpha'] * 100:.0f} % opaque (limit "
          f"{lim['max_surface_alpha'] * 100:.0f} %), glass under it: {'yes' if s['glass'] else 'no'}.", img)


PICKER_JS = """const ui = Main.screenshotUI; if (!ui._windowButton.checked) return null; const out = [];
 for (const s of ui._windowSelectors) for (const w of s.windows()) { if (!w.mapped) continue;
   const [x, y] = w.get_transformed_position(), [ww, wh] = w.get_transformed_size(); out.push([x, y, ww, wh]); }
 return {wins: out, depth: global.get_window_actors().map(a => a.z_position)};"""


def screenshot_window_picker(ctx: Ctx, c: Check) -> None:
    """GNOME's screenshot tool (Print Screen), Window mode: each window shows as a picture of
    itself. A window an animation left a hair off depth 0 shows as an empty box there (1.5.11)."""
    sh, lim = ctx.sh, LIMITS["popups"]
    lgqa.open_terminal()      # paints its whole area green, easy to find in the picture
    term = sh.wait_window(r"ptyxis|terminal|dino@|bash")
    sh.put(term["id"], 300, 200, 900, 560, focus=True)
    settle(2.5)                # opened with Fedora Glass's own open animation
    sh.eval("Main.screenshotUI.open(); 1")
    try:
        settle(1.5)
        sh.eval("Main.screenshotUI._windowButton.checked = true; 1")
        settle(1.5)
        p = sh.json(PICKER_JS)
        a = lgqa.load(sh.shot("popup-screenshot-picker"))
    finally:
        sh.eval("Main.screenshotUI.close(true); 1")
    settle(1)
    if not p or not p["wins"]:
        c.add(False, "The screenshot tool's Window mode showed no windows to pick.")
        return
    best, box = 0.0, None
    for b in p["wins"]:
        x, y, w, h = ctx.px(b)
        part = lgqa.crop(a, (x, y, w, h))
        share = float(lgqa.green(part).mean()) if part.size else 0.0
        if share >= best:
            best, box = share, (x, y, w, h)
    x, y, w, h = box
    img = picture("popup-screenshot-picker", lgqa.crop(a, (x - 40, y - 40, w + 80, h + 80)), width=700)
    off = [d for d in p["depth"] if d != 0]
    ok = best >= lim["min_picker_fill"] and not off
    c.add(ok, f"The screenshot tool's Window mode shows the terminal's picture ({best * 100:.0f} % of its box "
          f"is the terminal's green)." if ok else
          f"The screenshot tool's Window mode shows an empty box for the terminal ({best * 100:.0f} % of its box "
          f"is the terminal's green, at least {lim['min_picker_fill'] * 100:.0f} % expected; "
          f"{len(off)} window(s) left off depth 0).", img)
    sh.close_all()
    lgqa.kill_apps()


def check_popups(ctx: Ctx) -> Check:
    c = Check("popups", "Pop-ups and title bars show the glass",
              "Shows the volume pop-up and Alt+Tab (with an app's window previews) under Dino's Just Perfection "
              "theme, which paints them near-black, the taskbar's window previews, the Run a Command dialog, "
              "the screenshot tool's window pictures, and opens gedit, whose title bar is made of several bars.")
    sh, lim = ctx.sh, LIMITS["popups"]
    sh.close_all()
    lgqa.kill_apps()
    log0 = ctx.log_lines()

    # Volume pop-up.
    sh.eval("Main.osdWindowManager.showAll(imports.gi.Gio.Icon.new_for_string('audio-volume-medium-symbolic'), 'Volume', 0.5, 1); 1")
    settle(0.4)     # it hides itself after about 1.5 seconds
    _glass_surface(c, ctx, "The volume pop-up",
                   "(() => { let o = null; const w = b => { if (!o && b.has_style_class_name?.('osd-window') && b.mapped) o = b;"
                   " b.get_children().forEach(w); }; w(Main.layoutManager.uiGroup); return o; })()", lim, "popup-osd")

    # Alt+Tab, held down like a person does, with two Files windows for the previews.
    for d in ("/home/dino", "/home/dino/Documents"):
        lgqa.launch(["nautilus", "--new-window", d], log="nautilus")
        settle(2.5)
    lgqa.launch(["ptyxis", "--new-window"], log="ptyxis")
    term = sh.wait_window(r"ptyxis|terminal|dino@")
    sh.focus(term["id"])
    settle(2)
    _key(ctx, "alt", True)
    try:
        settle(0.2)
        _key(ctx, "tab", True)
        _key(ctx, "tab", False)
        settle(1.5)
        _glass_surface(c, ctx, "Alt+Tab", f"{SWITCHER}?._switcherList", lim, "popup-alttab")
        _key(ctx, "down", True)
        _key(ctx, "down", False)
        settle(1.5)
        _glass_surface(c, ctx, "Alt+Tab's window previews", f"{SWITCHER}?._thumbnails", lim, "popup-alttab-previews")
        _key(ctx, "escape", True)
        _key(ctx, "escape", False)
    finally:
        _key(ctx, "alt", False)
    settle(1.5)
    gone = sh.eval(f"String(!{SWITCHER})") == "true"
    c.add(gone, "Alt+Tab closes." if gone else "Alt+Tab stayed on screen after it was closed.")

    # Dash to Panel's window previews (hovering the Files icon), and a Shell dialog.
    sh.eval(f"{PREVIEWS}.open(global.dashToPanel.panels[0].taskbar._getAppIcons()"
            ".find(i => i.app?.get_id().includes('Nautilus'))); 1")
    settle(1)
    _glass_surface(c, ctx, "The taskbar's window previews", f"{PREVIEWS}.menu", lim, "popup-previews")
    sh.eval(f"{PREVIEWS}.close(true); 1")
    sh.eval("Main.openRunDialog(); 1")
    settle(1)
    _glass_surface(c, ctx, "The Run a Command dialog", f"{RUN_DIALOG}?.dialogLayout._dialog", lim, "popup-dialog")
    sh.eval(f"{RUN_DIALOG}?.close(); 1")
    settle(1)
    sh.close_all()
    lgqa.kill_apps()
    screenshot_window_picker(ctx, c)

    # gedit's title bar: two header bars inside a title bar. Nothing may paint the
    # square corner outside the window's rounded corner.
    lgqa.launch(["gedit", "--new-window"], log="gedit")
    w = sh.wait_window("gedit")
    sh.put(w["id"], 200, 150, 900, 500, focus=True)
    settle(2.5)
    w = sh.window_by_id(w["id"])
    a = lgqa.load(sh.shot("popup-gedit"))
    fx, fy, fw, _ = ctx.px(w["frame"])
    lift = []
    for inside, outside in (((fx + 9, fy + 2), (fx - 12, fy + 2)), ((fx + fw - 12, fy + 2), (fx + fw + 9, fy + 2))):
        lin = float(lgqa.lum(lgqa.crop(a, (*inside, 3, 3))).mean())
        lout = float(lgqa.lum(lgqa.crop(a, (*outside, 3, 3))).mean())
        lift.append(lin - lout)
    img = picture("popup-gedit-top", lgqa.crop(a, (fx - 30, fy - 30, fw + 60, 200)), width=900)
    worst = max(lift)
    c.add(worst <= lim["max_corner_lift"],
          "gedit's title bar has clean rounded corners." if worst <= lim["max_corner_lift"] else
          f"gedit's title bar paints square corners outside its rounded ones ({worst:.0f} brighter than the "
          f"desktop next to it, limit {lim['max_corner_lift']:.0f}).", img)
    sh.close_all()
    lgqa.kill_apps()
    errs = [e for e in ctx.new_errors(log0) if ours(e)]
    c.add(not errs, "No Fedora Glass errors." if not errs else f"{len(errs)} Fedora Glass errors, first: {errs[0][-160:]}")
    return c


def check_log(ctx: Ctx) -> Check:
    c = Check("log", "No errors from Fedora Glass",
              "Reads GNOME Shell's log for the whole run and the output of Apply.")
    apply_txt = (OUT / "apply.txt").read_text(errors="replace")
    failed = [l for l in apply_txt.splitlines() if l.startswith("✗")]
    c.add("apply exit 0" in apply_txt and not failed,
          "Apply finished without problems." if not failed else f"Apply reported: {failed[0]}")
    errs = [e for e in ctx.new_errors(0) if ours(e)]
    c.add(not errs, "GNOME Shell logged no Fedora Glass errors." if not errs else
          f"GNOME Shell logged {len(errs)} Fedora Glass errors. First: {errs[0][-200:]}")
    alive = lgqa.subprocess.run(["pgrep", "-u", "dino", "-x", "gnome-shell"], capture_output=True).returncode == 0
    c.add(alive, "GNOME Shell kept running for the whole test." if alive else "GNOME Shell crashed.")
    return c


def check_safe(ctx: Ctx) -> Check:
    c = Check("safe", "Quick restarts keep the glass on",
              "Before this login the PC was restarted twice within seconds of logging in (GNOME Shell started the "
              "glass and stopped cleanly). That is not a crash, so safe mode must stay off and the glass must draw "
              "(1.5.2 turned the glass off after two quick restarts).")
    try:
        quick = int((OUT / "quick-restarts.txt").read_text().strip())
    except (OSError, ValueError):
        quick = 0
    c.add(quick >= 2, f"The PC was restarted {quick} times right after logging in." if quick >= 2 else
          "The quick restarts did not run before this login.")
    try:
        state = json.loads((lgqa.HOME / ".cache/liquid-glass/safe-mode.json").read_text())
    except (OSError, ValueError):
        state = {}
    tripped = state.get("tripped") is True
    c.add(not tripped, "Safe mode stayed off." if not tripped else
          f"Safe mode turned on (reason: {state.get('reason', '?')}): the glass is off.")
    panes = ctx.sh.glass_panes()
    c.add(panes > 0, f"The glass draws ({panes} glass pieces)." if panes > 0 else "Fedora Glass draws no glass.")
    return c


# ---------------------------------------------------------------------------------------------
# 8. Upgrade from the last release (only with run.sh --from)
# ---------------------------------------------------------------------------------------------
def _code_dir(tree: Path) -> Path:
    """The app's code folder in a source tree: fedoraglass, or liquidglass up to 1.5.10."""
    return tree / "fedoraglass" if (tree / "fedoraglass").is_dir() else tree / "liquidglass"


def _version_of(tree: Path) -> str:
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", (_code_dir(tree) / "__init__.py").read_text())
    return m.group(1) if m else "?"


ERROR_LINE = re.compile(r"JS ERROR|TypeError|ReferenceError|Gjs-CRITICAL|(Liquid|Fedora) Glass:.*(fail|error)", re.I)


def _lg_errors(name: str) -> list[str]:
    p = OUT / name
    lines = p.read_text(errors="replace").splitlines() if p.exists() else []
    return [l for l in lines if ERROR_LINE.search(l) and "Xwayland" not in l
            and ours(l)]


def check_upgrade(ctx: Ctx) -> Check:
    old, new = _version_of(Path("/from")), _version_of(Path("/src"))
    c = Check("upgrade", "Upgrading from the last release",
              f"Dino's PC on {old}: applied and used for one session. Then {new} arrives the way dnf upgrade "
              "brings it, nobody presses Apply, and the PC restarts twice. The new glass must be running, "
              "with Dino's settings kept.")
    sh = ctx.sh
    txt = (OUT / "apply-old.txt").read_text(errors="replace")
    c.add("apply exit 0" in txt, f"{old} was applied." if "apply exit 0" in txt else
          f"Applying {old} failed: {txt.strip().splitlines()[-1][-160:] if txt.strip() else 'no output'}")
    errs = _lg_errors("shell-old.log")
    c.add(not errs, f"{old} ran its session without Fedora Glass errors." if not errs else
          f"{old} logged {len(errs)} Fedora Glass errors (this is the old version): {errs[0][-140:]}")
    watch = (OUT / "watch-upgrade.txt").read_text(errors="replace") if (OUT / "watch-upgrade.txt").exists() else ""
    said = f"updating the applied look from {old} to {new}" in watch
    c.add(said, f"At the first login after the upgrade, the look was brought up to {new} by itself." if said else
          "At the first login after the upgrade, the look was not brought up to date"
          + (f": {watch.strip().splitlines()[-1][-160:]}" if watch.strip() else "."))
    errs = _lg_errors("shell-upgrade.log")
    c.add(not errs, f"The {old} glass kept working with {new}'s settings until the restart." if not errs else
          f"{len(errs)} Fedora Glass errors in the session between the update and the restart: {errs[0][-140:]}")
    running = sh.json(f"return Main.extensionManager.lookup('{LG}')?.metadata?.['version-name'] ?? null;")
    c.add(running == new, f"After the next restart GNOME Shell runs the {new} glass." if running == new else
          f"After the next restart GNOME Shell runs the {running or 'no'} glass, not {new}.")
    try:
        saved = json.loads((lgqa.HOME / ".config/liquid-glass/settings.json").read_text())
    except (OSError, ValueError):
        saved = {}
    kept = saved.get("overview_off") is True and saved.get("start_on_desktop") is True
    c.add(kept, "Dino's own settings (no overview, start on the desktop) were kept." if kept else
          f"Dino's settings changed: {json.dumps(saved)[:160]}")
    others = [u for u in DINO_EXTENSIONS if sh.ext_states().get(u) == 1]
    bad = healthy(health(ctx, others), others)
    c.add(not bad, "The glass and all of Dino's extensions are working." if not bad else "; ".join(bad) + ".")
    return c


# ---------------------------------------------------------------------------------------------
# 9. Spawn (the other start menu)
# ---------------------------------------------------------------------------------------------
# Dino's PC runs ArcMenu, so the test desktop does too; this check switches to Spawn the way a
# person does (ArcMenu off, Spawn on) and back at the end, so it runs last.
SPAWN_KEYS = "/org/gnome/shell/extensions/spawn/"
# The glass parts of the popups that sit inside Spawn's menu: which look Fedora Glass gave each.
SPAWN_PARTS_JS = """const ext = Main.extensionManager.lookup('%s')?.stateObj;
 const pops = ext?._manager?._parts?.find(p => p.constructor.name === 'Popups');
 if (!pops?._followers) return null;
 const parts = [];
 for (const [surface, f] of pops._followers) {
   let a = surface; while (a && !a.has_style_class_name?.('spawn-menu-popup')) a = a.get_parent();
   if (a) parts.push(f.part); }
 return parts;""" % LG
# Spawn's menu is a PopupMenu: the box pointer carries `spawn-menu-popup`, its content is the surface.
SPAWN_SURFACE_JS = """(() => { let bp = null; const w = b => { if (!bp && b.mapped && b.has_style_class_name?.('spawn-menu-popup')) bp = b;
 b.get_children().forEach(w); }; w(Main.layoutManager.uiGroup); return bp?.bin?.get_child() ?? bp; })()"""


def spawn_keys() -> dict[str, str]:
    dump = lgqa.subprocess.run(["dconf", "dump", "/"], env=lgqa.ENV, capture_output=True, text=True, timeout=30).stdout
    return {k: v for k, v in dconf_keys(dump).items() if k.startswith(SPAWN_KEYS)}


def spawn_toggle(ctx: Ctx) -> None:
    """What the Super key and a click on the panel button do: D-Bus Toggle on Spawn's public interface."""
    ctx.sh.bus.call_sync("io.github.djshiye.Spawn", "/io/github/djshiye/Spawn", "io.github.djshiye.Spawn", "Toggle",
                         None, None, lgqa.Gio.DBusCallFlags.NONE, 8000, None)


def spawn_popup_boxes(ctx: Ctx) -> list:
    return actor_boxes(ctx, "spawn-menu-popup")


def spawn_wait_popup(ctx: Ctx, shown: bool, seconds: float = 8) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if bool(spawn_popup_boxes(ctx)) == shown:
            return True
        time.sleep(0.25)
    return False


def spawn_bad(ctx: Ctx, expected: list[str], glass: bool = True) -> list[str]:
    """What is wrong with the desktop: an extension that is not running (an error shows as such), no panel, no glass."""
    h = health(ctx, expected)
    bad = [NAMES.get(u, u) + (" is in an error state" if h[u] == 3 else " is not running") for u in expected if h[u] != 1]
    if not h["panels"]:
        bad.append("Dash to Panel has no panel")
    if glass and not h["panes"]:
        bad.append("Fedora Glass draws no glass")
    return bad


def spawn_wait_ok(ctx: Ctx, expected: list[str], seconds: float, glass: bool = True) -> tuple[list[str], float]:
    t0, bad = time.monotonic(), ["not checked"]
    while time.monotonic() - t0 < seconds:
        time.sleep(1)
        bad = spawn_bad(ctx, expected, glass)
        if not bad:
            break
    return bad, time.monotonic() - t0


def spawn_menu_glass(ctx: Ctx, c: Check, label: str, shot: str, look: str = "") -> None:
    """Open Spawn's menu: its box pointer has the glass, and Fedora Glass treated it as the ArcMenu part.
    With `look`, also the picture, compared with the reference picture of that name."""
    sh, lim = ctx.sh, LIMITS["popups"]
    spawn_toggle(ctx)
    if not spawn_wait_popup(ctx, True):
        c.add(False, f"{label}: Spawn's menu did not open.")
        return
    try:
        settle(1.5)
        if look:
            mask = clock_mask(ctx, lgqa.load(sh.shot(shot)).shape)
            now = steady_shot(sh, shot, mask)
            against_reference(ctx, c, look, "Spawn's menu", now, mask)
        # The glass under the menu's box pointer (a pane of about its size, drawn when it first shows).
        s = None
        for _ in range(8):
            s = sh.json(SURFACE_JS % SPAWN_SURFACE_JS) or s
            if s and s["glass"] and s["alpha"] <= lim["max_surface_alpha"]:
                break
            settle(0.25)
        if not s:
            c.add(False, f"{label}: could not find Spawn's menu on screen.")
        else:
            ok = s["glass"] and s["alpha"] <= lim["max_surface_alpha"]
            c.add(ok, f"{label}: Spawn's menu is glass (its own fill {s['alpha'] * 100:.0f} % opaque, glass under it: "
                  f"{'yes' if s['glass'] else 'no'})." if ok else
                  f"{label}: Spawn's menu is not glass: its own fill is {s['alpha'] * 100:.0f} % opaque (limit "
                  f"{lim['max_surface_alpha'] * 100:.0f} %), glass under it: {'yes' if s['glass'] else 'no'}.",
                  picture(shot + "-glass", lgqa.crop(lgqa.load(sh.shot(shot + "-glass")), [v - 40 for v in ctx.px(s["box"][:2])]
                                                    + [v + 80 for v in ctx.px(s["box"][2:])]), width=700))
        parts = sh.json(SPAWN_PARTS_JS)
        c.add(parts == ["arcmenu"],
              f"{label}: Fedora Glass gave Spawn's menu the ArcMenu look (part 'arcmenu')." if parts == ["arcmenu"] else
              f"{label}: Fedora Glass gave Spawn's menu {parts if parts is not None else 'no glass at all'} "
              "instead of the 'arcmenu' part.")
    finally:
        if spawn_popup_boxes(ctx):
            spawn_toggle(ctx)
        spawn_wait_popup(ctx, False)
        settle(1)


def check_spawn(ctx: Ctx) -> Check:
    c = Check("spawn", "Spawn, the other start menu, gets the glass",
              "Switches ArcMenu off and Spawn on (the way a person changes menus), Applies Fedora Glass with its "
              "Spawn target, opens Spawn's menu and looks at it, switches the glass off and on, then Restore original, "
              "and puts ArcMenu back. Spawn must come back running (not red) each time and the menu must be glass.")
    sh, lim = ctx.sh, LIMITS["restart"]
    sh.close_all()
    lgqa.kill_apps()
    settle(2)
    states = sh.ext_states()
    if states.get(SPAWN) is None:
        c.add(False, "Spawn is not installed on the test desktop.")
        return c
    log0 = ctx.log_lines()
    others = [u for u in DINO_EXTENSIONS if u not in (ARCMENU_UUID, LG, "user-theme@gnome-shell-extensions.gcampax.github.com")
              and states.get(u) == 1]
    running = others + [SPAWN, LG]
    c.add(states.get(SPAWN) != 1 and states.get(ARCMENU_UUID) == 1,
          "At the start ArcMenu is running and Spawn is off, like Dino's PC." if states.get(SPAWN) != 1 and
          states.get(ARCMENU_UUID) == 1 else "At the start ArcMenu is not the menu that runs (Spawn is on or ArcMenu is off).")
    try:
        # The theme keys start from scratch, so Apply has to write them.
        lgqa.subprocess.run(["dconf", "reset", "-f", SPAWN_KEYS], env=lgqa.ENV, capture_output=True, timeout=30)
        # Change menus.
        sh.eval(f"Main.extensionManager.disableExtension('{ARCMENU_UUID}'); 1")
        time.sleep(2)
        sh.eval(f"Main.extensionManager.enableExtension('{SPAWN}'); 1")
        on = sh.wait_for(f"return Main.extensionManager.lookup('{SPAWN}')?.state === 1;", 20)
        end = time.monotonic() + 20
        while on and not actor_boxes(ctx, "spawn-button") and time.monotonic() < end:
            time.sleep(0.5)
        button = bool(actor_boxes(ctx, "spawn-button"))
        c.add(on and button, "ArcMenu switched off and Spawn on: Spawn runs and has its button in the panel." if on and button
              else f"After switching to Spawn it is {'running but has no panel button' if on else 'not running (state ' + str(sh.ext_states().get(SPAWN)) + ')'}.")
        bad, took = spawn_wait_ok(ctx, others + [SPAWN, LG], lim["settle_seconds"])
        c.add(not bad, f"With Spawn instead of ArcMenu everything is running in {took:.0f} s." if not bad else
              "With Spawn instead of ArcMenu: " + "; ".join(bad) + ".")

        # Apply, with Fedora Glass's Spawn target.
        rc, out = run_lg("apply")
        failed = [l for l in out.splitlines() if l.startswith("✗")]
        c.add(rc == 0 and not failed, "Apply finished." if rc == 0 and not failed else
              f"Apply failed (exit {rc}): {(failed[0] if failed else out[-200:])}")
        keys = spawn_keys()
        wrote = keys.get(SPAWN_KEYS + "override-menu-theme") == "true" and SPAWN_KEYS + "menu-background-color" in keys
        c.add(wrote, f"Apply wrote the glass look into Spawn's settings ({len(keys)} keys set)." if wrote else
              "Apply did not write the glass look into Spawn's settings (override-menu-theme / menu-background-color not set).")
        bad, took = spawn_wait_ok(ctx, running, lim["settle_seconds"] + 15)
        c.add(not bad, f"After Apply, Spawn, the glass and every extension were running in {took:.0f} s." if not bad else
              "After Apply: " + "; ".join(bad) + ".")

        # Spawn's menu: the picture and the glass.
        sh.close_all()
        settle(1)
        spawn_menu_glass(ctx, c, "Spawn", "looks-spawn", look="spawn")

        # The glass switched off and on: GNOME restarts the extensions after it, Spawn included.
        sh.eval(f"Main.extensionManager.disableExtension('{LG}'); 1")
        time.sleep(3)
        sh.eval(f"Main.extensionManager.enableExtension('{LG}'); 1")
        bad, took = spawn_wait_ok(ctx, running, lim["settle_seconds"])
        c.add(not bad, f"After switching Fedora Glass off and on, Spawn was running again (state 1, not red) and the glass "
              f"was back in {took:.0f} s." if not bad else "After switching Fedora Glass off and on: " + "; ".join(bad) + ".")
        spawn_menu_glass(ctx, c, "After the restart", "spawn-restarted")

        # Restore original: Spawn's keys go back to what they were before the first Apply.
        rc, out = run_lg("revert")
        c.add(rc == 0, "Restore original finished." if rc == 0 else f"Restore original failed: {out[-200:]}")
        bad, took = spawn_wait_ok(ctx, others + [SPAWN], lim["settle_seconds"], glass=False)
        c.add(not bad, f"After Restore original, Spawn and Dino's other extensions were running in {took:.0f} s." if not bad
              else "After Restore original: " + "; ".join(bad) + ".")
        before_file = OUT / "dconf-before.ini"
        if before_file.exists():
            before = {k: v for k, v in dconf_keys(before_file.read_text(errors="replace")).items() if k.startswith(SPAWN_KEYS)}
            now = spawn_keys()
            defaults = schema_defaults()
            changed = []
            for k in sorted(set(before) | set(now)):
                was, isnow = before.get(k, defaults.get(k)), now.get(k, defaults.get(k))
                if not same_value(was, isnow):
                    changed.append(f"{k.rsplit('/', 1)[1]} was {str(was)[:50]}, now {str(isnow)[:50]}")
            c.add(not changed, "Every one of Spawn's settings is back to what it was before Apply." if not changed else
                  f"{len(changed)} of Spawn's settings differ from before Apply, first: " + "; ".join(changed[:3]))
        else:
            c.info("No record of the settings from before the first Apply, so Spawn's were not compared.")
        rc, out = run_lg("apply")
        c.add(rc == 0, "Apply finished again." if rc == 0 else f"Apply failed: {out[-200:]}")
    finally:
        # ArcMenu is the menu again, so the checks and the desktop are as they were.
        sh.eval(f"Main.extensionManager.disableExtension('{SPAWN}'); 1")
        time.sleep(2)
        sh.eval(f"Main.extensionManager.enableExtension('{ARCMENU_UUID}'); 1")
    bad, took = wait_healthy(ctx, others + [ARCMENU_UUID, LG], True, lim["settle_seconds"] + 15)
    spawn_off = sh.ext_states().get(SPAWN) != 1
    c.add(not bad and spawn_off, f"Spawn switched off and ArcMenu on again: everything was back in {took:.0f} s." if not bad and spawn_off
          else "Putting ArcMenu back: " + "; ".join(bad + ([] if spawn_off else ["Spawn is still running"])) + ".")
    errs = [e for e in ctx.new_errors(log0) if ours(e) or "spawn" in e.lower()]
    c.add(not errs, "No Fedora Glass or Spawn errors." if not errs else f"{len(errs)} Fedora Glass or Spawn errors, first: {errs[0][-160:]}")
    return c


ALL = {"looks": check_looks, "leftovers": check_leftovers, "resize": check_resize, "speed": check_speed,
       "popups": check_popups, "restart": check_restart, "restore": check_restore, "lock": check_lock,
       "log": check_log, "safe": check_safe, "upgrade": check_upgrade, "spawn": check_spawn}


# ---------------------------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------------------------
def write_report(checks: list[Check], meta: dict) -> bool:
    REPORT.mkdir(parents=True, exist_ok=True)
    passed = all(c.ok for c in checks)
    head = f"Fedora Glass {meta['version']}: " + ("all release checks passed" if passed else "release checks FAILED")
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
         f"<h1>Fedora Glass {html.escape(meta['version'])}</h1><p class=sub>Release checks on {html.escape(meta['desktop'])}. "
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
    # The upgrade check needs the older tree (run.sh --from) and goes first, before other
    # checks Apply or Restore.
    upgrade = ["upgrade"] if _code_dir(Path("/from")).is_dir() else []
    # "safe" looks at how this login started, so it goes before anything restarts the glass.
    ap.add_argument("--only", default=",".join(upgrade + ["safe"] + [k for k in ALL if k not in ("upgrade", "safe")]))
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
                                        Path("/src/fedoraglass/__init__.py").read_text()).group(1)
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
