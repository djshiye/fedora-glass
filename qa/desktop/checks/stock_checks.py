"""Fedora Glass on stock GNOME (run.sh --stock-desktop [--with-dock]).

GNOME as GNOME ships it, as a new Fedora Workstation user has it: the top bar, Activities,
the overview with its dash, search and app grid, and no extensions (or only Dash to Dock
with --with-dock). A new user's path: the stock desktop, Apply from the running desktop,
log in again, use the overview, then Restore original. Writes the same report as
run_checks.py.

    python3 stock_checks.py
"""
from __future__ import annotations

import os
import re
import sys
import time
import traceback
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lgqa  # noqa: E402
import run_checks as rc  # noqa: E402
from lgqa import LG, OUT, Shell, ShellError  # noqa: E402
from run_checks import Check, Ctx, ours, picture, run_lg  # noqa: E402

DOCK = "dash-to-dock@micxgx.gmail.com"
WITH_DOCK = DOCK in os.environ.get("LGQA_STOCK_EXTS", "")
USER_THEME = "user-theme@gnome-shell-extensions.gcampax.github.com"

# The overview's dash: how many app icons it has and how many of them show.
DASH_JS = """const d = Main.overview.dash; const kids = d._box.get_children().filter(c => c.child && !c.animatingOut);
 return {icons: kids.length, shown: kids.filter(c => c.scale_x > 0.99 && c.opacity > 250).length,
         favorites: global.settings.get_strv('favorite-apps').length};"""
# Glass panes on screen and the stage rectangle of each.
PANES_JS = """const all = [];
 const walk = a => { for (const c of a.get_children()) { if (c.name === 'fedora-glass-glass' && c.visible && c.mapped) {
     const [x, y] = c.get_transformed_position(); const [w, h] = c.get_transformed_size(); all.push([x, y, w, h]); }
   if (c.name !== 'fedora-glass-glass' && c.get_n_children?.()) walk(c); } };
 walk(Main.uiGroup); return all;"""
BOX_JS = """const a = @ACTOR@; if (!a || !a.mapped) return null;
 const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size(); return [x, y, w, h];"""
DASH_BOX = BOX_JS.replace("@ACTOR@", "Main.overview.dash._background")
DOCK_BOX = BOX_JS.replace("@ACTOR@", "Main.uiGroup.get_children().find(a => a.name === 'dashtodockContainer')?.dash?._background")


def covered(panes: list, box) -> bool:
    """A glass pane sits under the surface: its rectangle holds the surface's middle."""
    if not box:
        return False
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    return any(x <= cx <= x + w and y <= cy <= y + h for x, y, w, h in panes)


def overview_open(sh: Shell) -> None:
    sh.eval("Main.overview.show(); 1")
    sh.wait_for("return Main.overview.visible && !Main.overview.animationInProgress;", 15)
    time.sleep(3)


def overview_close(sh: Shell) -> None:
    sh.eval("Main.overview.searchEntry.set_text(''); Main.overview.hide(); 1")
    sh.wait_for("return !Main.overview.visible;", 15)
    time.sleep(2)


def dash_complete(c: Check, sh: Shell, when: str) -> None:
    d = sh.json(DASH_JS)
    ok = d["icons"] >= d["favorites"] > 0 and d["shown"] == d["icons"]
    c.add(ok, f"{when}, the overview's dash shows all its {d['icons']} app icons." if ok else
          f"{when}, the overview's dash shows {d['shown']} of its {d['icons']} app icons "
          f"({d['favorites']} favourites): the others are invisible.")


def shoot(ctx: Ctx, tag: str) -> dict[str, np.ndarray]:
    sh = ctx.sh
    out = {}
    overview_close(sh)
    out["desktop"] = lgqa.load(sh.shot(f"{tag}-desktop"))
    overview_open(sh)
    out["overview"] = lgqa.load(sh.shot(f"{tag}-overview"))
    sh.eval("Main.overview.searchEntry.set_text('se'); 1")
    time.sleep(4)
    out["search"] = lgqa.load(sh.shot(f"{tag}-search"))
    overview_close(sh)
    return out


def check_stock(ctx: Ctx) -> Check:
    name = "Fedora Glass on stock GNOME" + (" with Dash to Dock" if WITH_DOCK else "")
    c = Check("stock", name,
              "GNOME as it ships (top bar, Activities, the overview's dash, search, Adwaita)"
              + (" with Dash to Dock" if WITH_DOCK else " and no extensions")
              + ". Apply from the running desktop, log in again, use the overview, then Restore original.")
    sh = ctx.sh
    st = sh.ext_states()
    others = sorted(u for u, s in st.items() if s == 1 and u not in (DOCK,))
    c.add(not others, "No other extensions run." if not others else f"Extensions running that stock GNOME has not: {others}")
    if WITH_DOCK:
        c.add(st.get(DOCK) == 1, "Dash to Dock runs." if st.get(DOCK) == 1 else f"Dash to Dock is not running (state {st.get(DOCK)}).")
    (OUT / "dconf-before.ini").write_text(lgqa.subprocess.run(
        ["dconf", "dump", "/"], env=lgqa.ENV, capture_output=True, text=True, timeout=30).stdout)
    stock = shoot(ctx, "stock")
    c.info("The stock desktop and overview before Apply.")
    c.steps[-1].images += [picture("stock-desktop", stock["desktop"]), picture("stock-overview", stock["overview"])]

    # ---- Apply, then log in again as the app asks ----
    log0 = ctx.log_lines()
    code, out = run_lg("apply")
    (OUT / "apply.txt").write_text(out + f"\napply exit {code}\n")
    failed = [l for l in out.splitlines() if l.startswith("✗")]
    c.add(code == 0 and not failed, "Apply finished without problems." if code == 0 and not failed else
          f"Apply failed (exit {code}): {(failed or out.splitlines() or ['no output'])[0][-200:]}")
    (OUT / "relogin").touch()
    end = time.monotonic() + 120
    while not (OUT / "relogged-in").exists() and time.monotonic() < end:
        time.sleep(1)
    try:
        sh.wait_for("return !Main.layoutManager._startingUp;", 90)
    except ShellError:
        pass
    up = sh.wait_for(f"return Main.extensionManager.lookup('{LG}')?.state === 1;", 60)
    c.add(up, "After logging in again, the glass extension runs." if up else
          "After logging in again, the glass extension is not running.")
    for _ in range(30):
        if not (lgqa.HOME / ".config/liquid-glass/pending-shell.json").exists():
            break
        time.sleep(1)
    rc.shell_parts_done(c, "After logging in again")
    # "Start on the desktop" is on by default: GNOME skipped its startup overview.
    on_desktop = sh.eval("Main.overview.visible ? 'overview' : 'desktop'") == "desktop"
    c.add(on_desktop, "GNOME started on the desktop." if on_desktop else "GNOME started in the overview.")
    # GNOME fills the dash in while hidden within 20 s of login (its deferred work).
    time.sleep(22)
    overview_open(sh)
    dash_complete(c, sh, "After logging in on the desktop")
    panes = sh.json(PANES_JS)
    dash_box = sh.json(DASH_BOX)
    if WITH_DOCK:
        c.add(dash_box is None, "Dash to Dock took the overview's dash." if dash_box is None else
              "The overview shows GNOME's dash beside Dash to Dock.")
    else:
        c.add(covered(panes, dash_box), "Glass is behind the overview's dash." if covered(panes, dash_box) else
              "No glass behind the overview's dash.")
    overview_close(sh)
    if WITH_DOCK:
        panes = sh.json(PANES_JS)
        dock = sh.json(DOCK_BOX)
        c.add(covered(panes, dock), "Glass is behind Dash to Dock." if covered(panes, dock) else
              "No glass behind Dash to Dock.")
    panel = sh.json(BOX_JS.replace("@ACTOR@", "Main.panel"))
    panes = sh.json(PANES_JS)
    c.add(covered(panes, panel), "Glass is behind the top bar." if covered(panes, panel) else "No glass behind the top bar.")
    glass = shoot(ctx, "glass")
    c.add(True, "The desktop, the overview and search with Fedora Glass.",
          picture("glass-desktop", glass["desktop"]))
    c.steps[-1].images += [picture("glass-overview", glass["overview"]), picture("glass-search", glass["search"])]
    errs = [e for e in ctx.new_errors(log0) if ours(e) or "dash.js" in e or "firstIcon" in e]
    c.add(not errs, "No Fedora Glass or dash errors in GNOME Shell's log after Apply." if not errs else
          f"{len(errs)} errors after Apply, first: {errs[0][-200:]}")

    # ---- Restore original ----
    log1 = ctx.log_lines()
    code, out = run_lg("revert")
    c.add(code == 0, "Restore original finished." if code == 0 else f"Restore original failed: {out[-200:]}")
    gone = sh.wait_for(f"return Main.extensionManager.lookup('{LG}')?.state !== 1;", 30)
    c.add(gone, "The glass extension is off after Restore original." if gone else
          "The glass extension still runs after Restore original.")
    time.sleep(6)
    rc.back_as_before(c)
    overview_open(sh)
    dash_complete(c, sh, "After Restore original")
    overview_close(sh)
    back = lgqa.load(sh.shot("restored-desktop"))
    ignore = rc.clock_mask(ctx, back.shape)
    d = lgqa.compare(back, stock["desktop"], ignore, threshold=24)
    same = d.changed < 0.002 and d.blob < 400
    c.add(same, "The desktop looks as it did before Apply." if same else
          f"The desktop looks different from before Apply ({d.changed * 100:.2f} % of the screen changed).",
          rc.triptych("restored-vs-stock", stock["desktop"], back, d.image))
    errs = [e for e in ctx.new_errors(log1) if ours(e)]
    c.add(not errs, "No Fedora Glass errors during Restore original." if not errs else
          f"{len(errs)} Fedora Glass errors during Restore original, first: {errs[0][-200:]}")
    alive = lgqa.subprocess.run(["pgrep", "-u", "dino", "-x", "gnome-shell"], capture_output=True).returncode == 0
    c.add(alive, "GNOME Shell kept running for the whole test." if alive else "GNOME Shell crashed.")
    return c


def main() -> int:
    sh = Shell()
    try:
        sh.wait_for("return !Main.layoutManager._startingUp;", 60)
        if WITH_DOCK:
            sh.wait_for(f"return Main.extensionManager.lookup('{DOCK}')?.state === 1;", 60)
        sh.eval("Main.overview.hide(); 1")
        time.sleep(3)
        sh.measure_scale()
    except ShellError as e:
        print(f"The test desktop did not start: {e}", file=sys.stderr)
        return 2
    ctx = Ctx(sh, False)
    version = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", Path("/src/fedoraglass/__init__.py").read_text()).group(1)
    shell = lgqa.subprocess.run(["gnome-shell", "--version"], capture_output=True, text=True).stdout.split()[-1]
    meta = {"version": version, "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "desktop": f"stock GNOME Shell {shell}" + (" with Dash to Dock" if WITH_DOCK else ", no extensions")}
    print("== stock", flush=True)
    try:
        checks = [check_stock(ctx)]
    except Exception as e:  # a broken step must fail the check, never pass it
        traceback.print_exc()
        ch = Check("stock", "Fedora Glass on stock GNOME", "")
        ch.crashed = f"{type(e).__name__}: {str(e)[:300]}"
        checks = [ch]
    ok = rc.write_report(checks, meta)
    print((rc.REPORT / "report.md").read_text())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
