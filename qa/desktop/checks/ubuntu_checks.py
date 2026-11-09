"""Fedora Glass on a stock Ubuntu desktop (run.sh --ubuntu-desktop).

The Ubuntu session as Ubuntu ships it (Ubuntu Dock, Desktop Icons, AppIndicator, Yaru,
Ubuntu's default settings), nobody's own extensions or theme. A new user's path: the stock
desktop, Apply from the running desktop, use it, then Restore original. Writes the same
report as run_checks.py.

    python3 ubuntu_checks.py
"""
from __future__ import annotations

import json
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

UBUNTU_EXTS = {"ubuntu-dock@ubuntu.com": "Ubuntu Dock", "ding@rastersoft.com": "Desktop Icons",
               "ubuntu-appindicators@ubuntu.com": "AppIndicator"}
USER_THEME = "user-theme@gnome-shell-extensions.gcampax.github.com"
# The dock's own box (Ubuntu Dock is Dash to Dock underneath).
DOCK_JS = """const d = Main.uiGroup.get_children().find(a => a.name === 'dashtodockContainer' || a.constructor.name === 'DockedDash');
 if (!d || !d.visible) return null; const [x, y] = d.get_transformed_position(); const [w, h] = d.get_transformed_size();
 return [x, y, w, h];"""


def ext_states(sh: Shell) -> dict:
    return sh.ext_states()


def ubuntu_running(c: Check, sh: Shell, when: str) -> None:
    st = ext_states(sh)
    off = [n for u, n in UBUNTU_EXTS.items() if st.get(u) != 1]
    c.add(not off, f"{when}, Ubuntu Dock, Desktop Icons and AppIndicator all run." if not off else
          f"{when}, not running: {', '.join(off)} (states {[st.get(u) for u in UBUNTU_EXTS]}).")


def dock_box(ctx: Ctx):
    try:
        return ctx.sh.json(DOCK_JS)
    except ShellError:
        return None


def dock_shot(ctx: Ctx, name: str, a: np.ndarray):
    box = dock_box(ctx)
    if not box:
        return None, None
    x, y, w, h = (int(round(v)) for v in ctx.px(box))
    pad = int(12 * ctx.s)
    crop = lgqa.crop(a, (max(x - pad, 0), max(y - pad, 0), w + 2 * pad, h + 2 * pad))
    return crop, picture(name, crop, 400)


def files_window(sh: Shell) -> dict | None:
    lgqa.open_files()
    try:
        w = sh.wait_window("Home|dino|Files", 40)
    except Exception:
        return None
    sh.place(w["id"], 520, 160, 900, 620, focus=True)
    time.sleep(2)
    return w


def qs_shot(sh: Shell, name: str) -> np.ndarray:
    sh.eval("Main.panel.statusArea.quickSettings.menu.open(); 1")
    time.sleep(2)
    a = lgqa.load(sh.shot(name))
    sh.eval("Main.panel.statusArea.quickSettings.menu.close(); 1")
    time.sleep(1)
    return a


def check_ubuntu(ctx: Ctx) -> Check:
    c = Check("ubuntu", "Fedora Glass on a stock Ubuntu desktop",
              "The Ubuntu session as Ubuntu ships it (Ubuntu Dock, Desktop Icons, AppIndicator, Yaru). "
              "Apply from the running desktop, then Restore original, the way a new Ubuntu user does it.")
    sh = ctx.sh
    mode = sh.eval("Main.sessionMode.currentMode")
    c.add(mode == "ubuntu", "The desktop runs Ubuntu's own session." if mode == "ubuntu" else
          f"The desktop runs session mode {mode!r}, not Ubuntu's.")
    ubuntu_running(c, sh, "Before Apply")
    # Every setting as the stock desktop has it once it runs (Tiling Assistant, for one, changes
    # some of GNOME's own when it starts): Restore original must bring these back.
    (OUT / "dconf-before.ini").write_text(lgqa.subprocess.run(
        ["dconf", "dump", "/"], env=lgqa.ENV, capture_output=True, text=True, timeout=30).stdout)
    stock = lgqa.load(sh.shot("stock-desktop"))
    c.info("The stock Ubuntu desktop before Apply.")
    c.steps[-1].images.append(picture("stock-desktop", stock))
    stock_qs = qs_shot(sh, "stock-quick-settings")
    stock_dock, _ = dock_shot(ctx, "stock-dock", stock)

    # ---- Apply ----
    log0 = ctx.log_lines()
    code, out = run_lg("apply")
    (OUT / "apply.txt").write_text(out + f"\napply exit {code}\n")
    failed = [l for l in out.splitlines() if l.startswith("✗")]
    c.add(code == 0 and not failed, "Apply finished without problems." if code == 0 and not failed else
          f"Apply failed (exit {code}): {(failed or out.splitlines() or ['no output'])[0][-200:]}")
    # GNOME only starts an extension it did not know at login after the next login, and Apply
    # says so ("Finishes after you restart your PC"). Then log in again, as the app asks.
    told = "after you restart" in out
    c.add(told, "Apply says the rest finishes after a restart." if told else
          "Apply does not say a restart is needed, but GNOME only starts the glass at the next login.")
    (OUT / "relogin").touch()
    end = time.monotonic() + 120
    while not (OUT / "relogged-in").exists() and time.monotonic() < end:
        time.sleep(1)
    try:
        sh.wait_for("return !Main.layoutManager._startingUp;", 90)
    except ShellError:
        pass
    up =sh.wait_for(f"return Main.extensionManager.lookup('{LG}')?.state === 1;", 60)
    c.add(up, "After logging in again, the glass extension runs." if up else
          "After logging in again, the glass extension is not running.")
    for _ in range(30):     # the login helper finishes the parts that waited for the glass
        if not (lgqa.HOME / ".config/liquid-glass/pending-shell.json").exists():
            break
        time.sleep(1)
    rc.shell_parts_done(c, "After logging in again")
    sh.eval("Main.overview.hide(); 1")
    time.sleep(5)
    panes = sh.glass_panes()
    c.add(panes > 0, f"The glass draws ({panes} glass pieces)." if panes > 0 else "Fedora Glass draws no glass.")
    ubuntu_running(c, sh, "After Apply")
    glass = lgqa.load(sh.shot("glass-desktop"))
    c.add(True, "The desktop with Fedora Glass.", picture("glass-desktop", glass))
    dock_now, dock_pic = dock_shot(ctx, "glass-dock", glass)
    c.add(dock_now is not None, "Ubuntu Dock is on screen with Fedora Glass." if dock_now is not None
          else "Ubuntu Dock is not on screen after Apply.", dock_pic)
    qs = qs_shot(sh, "glass-quick-settings")
    c.add(True, "Quick Settings with Fedora Glass.", picture("glass-quick-settings", qs))
    if stock_qs.shape == qs.shape:
        d = lgqa.compare(qs, stock_qs, rc.clock_mask(ctx, qs.shape))
        c.add(d.changed > 0.002, "The Quick Settings menu got the glass look." if d.changed > 0.002 else
              "Quick Settings look the same as before Apply: the glass did not reach them.")
    win = files_window(sh)
    if win:
        fa = lgqa.load(sh.shot("glass-files"))
        c.add(True, "Files with Fedora Glass.", picture("glass-files", fa))
    else:
        c.add(False, "Files did not open.")
    lgqa.kill_apps()
    time.sleep(2)
    errs = [e for e in ctx.new_errors(log0) if ours(e)]
    c.add(not errs, "No Fedora Glass errors in GNOME Shell's log after Apply." if not errs else
          f"{len(errs)} Fedora Glass errors after Apply, first: {errs[0][-200:]}")

    # ---- Restore original ----
    log1 = ctx.log_lines()
    code, out = run_lg("revert")
    c.add(code == 0, "Restore original finished." if code == 0 else f"Restore original failed: {out[-200:]}")
    gone = sh.wait_for(f"return Main.extensionManager.lookup('{LG}')?.state !== 1;", 30)
    c.add(gone, "The glass extension is off after Restore original." if gone else
          "The glass extension still runs after Restore original.")
    time.sleep(6)
    ubuntu_running(c, sh, "After Restore original")
    rc.back_as_before(c)
    back = lgqa.load(sh.shot("restored-desktop"))
    ignore = rc.clock_mask(ctx, back.shape)
    d = lgqa.compare(back, stock, ignore, threshold=24)
    same = d.changed < 0.002 and d.blob < 400
    c.add(same, "The desktop looks as it did before Apply." if same else
          f"The desktop looks different from before Apply ({d.changed * 100:.2f} % of the screen changed).",
          rc.triptych("restored-vs-stock", stock, back, d.image))
    if stock_dock is not None:
        back_dock, _ = dock_shot(ctx, "restored-dock", back)
        if back_dock is not None and back_dock.shape == stock_dock.shape:
            dd = lgqa.compare(back_dock, stock_dock, threshold=24)
            c.add(dd.changed < 0.005, "Ubuntu Dock looks as it did before Apply." if dd.changed < 0.005 else
                  f"Ubuntu Dock looks different after Restore original ({dd.changed * 100:.1f} % changed).")
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
        sh.wait_for("return Main.extensionManager.lookup('ubuntu-dock@ubuntu.com')?.state === 1;", 60)
        sh.eval("Main.overview.hide(); 1")
        time.sleep(3)
        sh.measure_scale()
    except ShellError as e:
        print(f"The test desktop did not start: {e}", file=sys.stderr)
        return 2
    ctx = Ctx(sh, False)
    version = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", Path("/src/fedoraglass/__init__.py").read_text()).group(1)
    shell = lgqa.subprocess.run(["gnome-shell", "--version"], capture_output=True, text=True).stdout.split()[-1]
    os_name = next((l.split("=", 1)[1].strip('"') for l in Path("/etc/os-release").read_text().splitlines()
                    if l.startswith("PRETTY_NAME=")), "Ubuntu")
    meta = {"version": version, "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "desktop": f"{os_name}, stock Ubuntu session, GNOME Shell {shell}"}
    print("== ubuntu", flush=True)
    try:
        checks = [check_ubuntu(ctx)]
    except Exception as e:  # a broken step must fail the check, never pass it
        traceback.print_exc()
        ch = Check("ubuntu", "Fedora Glass on a stock Ubuntu desktop", "")
        ch.crashed = f"{type(e).__name__}: {str(e)[:300]}"
        checks = [ch]
    ok = rc.write_report(checks, meta)
    print((rc.REPORT / "report.md").read_text())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
