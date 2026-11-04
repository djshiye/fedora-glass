"""Helpers for the release checks: drive GNOME Shell, open apps, take and compare screenshots.

Runs inside the test container as the user "dino". GNOME Shell runs with --unsafe-mode
(test container only), so org.gnome.Shell.Eval can run JavaScript in it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from gi.repository import Gio, GLib
from PIL import Image

OUT = Path(os.environ.get("LGQA_OUT", "/out"))
SHOTS = OUT / "shots"
LG = "liquid-glass@djshiye.github.io"
HOME = Path("/home/dino")
ENV = {
    **os.environ,
    "HOME": str(HOME), "XDG_RUNTIME_DIR": "/run/user/1000", "WAYLAND_DISPLAY": "wayland-0",
    "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus", "XDG_SESSION_TYPE": "wayland",
    "XDG_CURRENT_DESKTOP": "GNOME", "LIBGL_ALWAYS_SOFTWARE": "1", "NO_AT_BRIDGE": "1",
    "ADW_DEBUG_COLOR_SCHEME": "prefer-dark",   # no settings portal in the container
}
os.environ.update({k: v for k, v in ENV.items() if k not in ("PATH",)})


class ShellError(RuntimeError):
    pass


class Shell:
    def __init__(self) -> None:
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        self.scale = 1.0       # screenshot pixels per stage pixel, set by measure_scale()

    def eval(self, js: str, timeout: float = 20) -> str:
        res = self.bus.call_sync("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell", "Eval",
                                 GLib.Variant("(s)", (js,)), GLib.VariantType("(bs)"),
                                 Gio.DBusCallFlags.NONE, int(timeout * 1000), None)
        ok, out = res.unpack()
        if not ok:
            raise ShellError(out.strip()[:400])
        # The Shell sends results as JSON: a string comes back quoted.
        try:
            val = json.loads(out) if out else ""
        except ValueError:
            return out
        return val if isinstance(val, str) else json.dumps(val)

    def json(self, js: str, timeout: float = 20):
        return json.loads(self.eval(f"JSON.stringify((() => {{ {js} }})())", timeout))

    def wait_for(self, js: str, timeout: float = 20, every: float = 0.25) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if self.eval(f"(() => {{ {js} }})() ? 1 : 0") == "1":
                    return True
            except ShellError:
                pass
            time.sleep(every)
        return False

    # ---- screenshots (taken inside the Shell, so they also work on the lock screen) ----
    def shot(self, name: str) -> Path:
        SHOTS.mkdir(parents=True, exist_ok=True)
        path = SHOTS / f"{name}.png"
        path.unlink(missing_ok=True)
        self.eval(_SHOT_JS.replace("@PATH@", str(path)))
        end = time.monotonic() + 30
        while time.monotonic() < end:
            state = self.eval("String(globalThis._lgqaShot)")
            if state == "1":
                return path
            if state not in ("0", "undefined"):
                raise ShellError(f"screenshot failed: {state}")
            time.sleep(0.1)
        raise ShellError("screenshot timed out")

    def measure_scale(self) -> float:
        p = self.shot("_scale")
        w = Image.open(p).size[0]
        self.scale = w / float(self.eval("global.stage.width"))
        p.unlink()
        return self.scale

    # ---- windows ----
    def windows(self) -> list[dict]:
        return self.json(_WINDOWS_JS)

    def window(self, pattern: str) -> dict | None:
        for w in self.windows():
            if re.search(pattern, w["title"], re.I) or re.search(pattern, w["wm_class"], re.I):
                return w
        return None

    def window_by_id(self, wid: int) -> dict | None:
        return next((w for w in self.windows() if w["id"] == wid), None)

    def wait_window(self, pattern: str, timeout: float = 40) -> dict:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            w = self.window(pattern)
            if w and w["frame"][2] > 50:
                return w
            time.sleep(0.5)
        raise ShellError(f"window {pattern!r} did not open")

    def win_js(self, wid: int, body: str) -> str:
        """Run body with `w` (MetaWindow) and `a` (its actor) bound."""
        return self.eval(
            "(() => { const a = global.get_window_actors().find(a => a.meta_window.get_id() == %d);"
            " if (!a) return 'gone'; const w = a.meta_window; %s })()" % (wid, body))

    def place(self, wid: int, x: int, y: int, w: int, h: int, focus: bool = False) -> None:
        self.win_js(wid, f"if (w.maximized_horizontally || w.maximized_vertically) w.unmaximize(Meta.MaximizeFlags.BOTH);"
                         f" w.move_resize_frame(true, {x}, {y}, {w}, {h});"
                         + (" w.activate(global.get_current_time());" if focus else "") + " return 1;")

    def put(self, wid: int, x: int, y: int, w: int, h: int, focus: bool = False) -> None:
        """Place a window and make sure it stays there (Deja Window restores saved places
        just after a window opens, which could otherwise win the race)."""
        for _ in range(8):
            self.place(wid, x, y, w, h, focus)
            time.sleep(0.6)
            f = (self.window_by_id(wid) or {}).get("frame")
            if f and abs(f[0] - x) <= 2 and abs(f[1] - y) <= 2:
                return
        raise ShellError(f"window {wid} would not stay at {x},{y}")

    # A real drag: grab the window's bottom-right corner with a virtual pointer and move it,
    # the way a person resizes (GNOME and Fedora Glass treat that differently from a
    # resize asked for by an app).
    def drag_begin(self, wid: int) -> bool:
        return self.win_js(wid, _DRAG_BEGIN_JS) == "true"

    def drag_to(self, x: float, y: float) -> None:
        self.eval("globalThis._lgqaVp.notify_absolute_motion(imports.gi.GLib.get_monotonic_time(), %f, %f); 1" % (x, y))

    def drag_end(self) -> None:
        self.eval("(() => { const {Clutter, GLib} = imports.gi; const v = globalThis._lgqaVp;"
                  " v.notify_button(GLib.get_monotonic_time(), Clutter.BUTTON_PRIMARY, Clutter.ButtonState.PRESSED);"
                  " v.notify_button(GLib.get_monotonic_time(), Clutter.BUTTON_PRIMARY, Clutter.ButtonState.RELEASED); return 1; })()")

    def focus(self, wid: int) -> None:
        self.win_js(wid, "w.activate(global.get_current_time()); return 1;")

    def close_all(self) -> None:
        self.eval("global.get_window_actors().forEach(a => { try { a.meta_window.delete(global.get_current_time()); } catch (e) {} }); 1")
        end = time.monotonic() + 10
        while self.windows() and time.monotonic() < end:
            time.sleep(0.3)

    # ---- extensions ----
    def ext_states(self) -> dict[str, int]:
        return self.json("const o = {}; for (const [u, e] of Main.extensionManager._extensions) o[u] = e.state; return o;")

    def glass_panes(self) -> int:
        return int(self.eval("(() => { let n = 0; const w = a => { if (a.constructor.name === 'LiquidGlassPane') n++;"
                             " for (const c of a.get_children()) w(c); }; w(global.stage); return n; })()"))

    def uninhibit_animations(self) -> None:
        self.eval("const S = imports.gi.St.Settings.get(); if (!S.enable_animations) S.uninhibit_animations(); 1")


_SHOT_JS = """(() => { const {Shell, Gio} = imports.gi; globalThis._lgqaShot = 0;
 const part = Gio.File.new_for_path('@PATH@.part'); const st = part.replace(null, false, Gio.FileCreateFlags.NONE, null);
 new Shell.Screenshot().screenshot(false, st, (o, r) => {
   try { o.screenshot_finish(r); st.close(null); part.move(Gio.File.new_for_path('@PATH@'), Gio.FileCopyFlags.OVERWRITE, null, null); globalThis._lgqaShot = 1; }
   catch (e) { globalThis._lgqaShot = 'error ' + e; } });
 return 1; })()"""

_DRAG_BEGIN_JS = """const {Clutter, Meta, GLib} = imports.gi; const be = global.stage.context.get_backend();
 const v = globalThis._lgqaVp || (globalThis._lgqaVp = be.get_default_seat().create_virtual_device(Clutter.InputDeviceType.POINTER_DEVICE));
 const f = w.get_frame_rect(); w.activate(global.get_current_time());
 v.notify_absolute_motion(GLib.get_monotonic_time(), f.x + f.width - 2, f.y + f.height - 2);
 return w.begin_grab_op(Meta.GrabOp.RESIZING_SE, be.get_pointer_sprite(global.stage), global.get_current_time(), null);"""

_WINDOWS_JS = """return global.get_window_actors().filter(a => a.meta_window.get_window_type() === 0).map(a => {
  const w = a.meta_window, f = w.get_frame_rect(), b = w.get_buffer_rect();
  const [ax, ay] = a.get_transformed_position(), [aw, ah] = a.get_transformed_size();
  const kids = a.get_children().filter(c => !c.name).map(c => { const [x, y] = c.get_transformed_position(); const [cw, ch] = c.get_transformed_size(); return [x, y, cw, ch]; });
  return {id: w.get_id(), title: w.get_title() || '', wm_class: w.get_wm_class() || '', focus: w.has_focus(),
          minimized: w.minimized, frame: [f.x, f.y, f.width, f.height], buffer: [b.x, b.y, b.width, b.height],
          actor: [ax, ay, aw, ah], scale: [a.scale_x, a.scale_y], translation: [a.translation_x, a.translation_y],
          opacity: a.opacity, surfaces: kids, client: w.get_client_type() === 0 ? 'wayland' : 'x11'};
});"""


# ---------------------------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------------------------
_procs: list[subprocess.Popen] = []


def launch(cmd: list[str], extra_env: dict | None = None, log: str = "app") -> subprocess.Popen:
    f = open(OUT / f"{log}.log", "ab")
    p = subprocess.Popen(cmd, env={**ENV, **(extra_env or {})}, stdout=f, stderr=subprocess.STDOUT, cwd=str(HOME))
    _procs.append(p)
    return p


def xwayland_env(sh: Shell) -> dict:
    disp = sh.eval("imports.gi.GLib.getenv('DISPLAY') || ''")
    auths = sorted(Path("/run/user/1000").glob(".mutter-Xwaylandauth.*"))
    env = {"DISPLAY": disp or ":0"}
    if auths:
        env["XAUTHORITY"] = str(auths[-1])
    return env


def open_terminal() -> None:
    # Ptyxis with a shell that paints its whole area green and writes a tag in the
    # top-left corner, again after every resize.
    launch(["ptyxis", "--new-window", "-x", "bash /opt/lgqa/suite/checks/term-fill.sh"], log="ptyxis")


def open_files() -> None:
    launch(["nautilus", "--new-window", str(HOME)], log="nautilus")


def open_electron(x11: bool = False, busy: bool = False, title: str = "", maximize_after_ms: int = 0) -> None:
    """maximize_after_ms: open like Claude Desktop (no frame, shown once drawn), then maximize it that
    long after it shows, while it is still opening."""
    flags = ["--ozone-platform=x11"] if x11 else ["--ozone-platform=wayland"]
    title = title or ("LGQA Electron X11" if x11 else "LGQA Electron")
    like = {"LGQA_LIKE_CLAUDE": "1", "LGQA_MAXIMIZE_AFTER_MS": str(maximize_after_ms)} if maximize_after_ms else {}
    launch(["/opt/electron/electron", "--no-sandbox", "--disable-gpu-sandbox", *flags, "/opt/lgqa/suite/electron-app"],
           {"LGQA_TITLE": title, "LGQA_BUSY": "1" if busy else "0", **like, **(XENV if x11 else {})},
           log="electron-x11" if x11 else "electron")


XENV: dict = {}


def kill_apps() -> None:
    for p in _procs:
        if p.poll() is None:
            p.terminate()
    for p in _procs:
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
    _procs.clear()
    subprocess.run(["pkill", "-u", "dino", "-f", "^(nautilus|ptyxis|/opt/electron)"], check=False)


# ---------------------------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------------------------
def load(p: Path) -> np.ndarray:
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)


def lum(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def magenta(a: np.ndarray) -> np.ndarray:
    """Pixels that look like the Electron test page (strong pink-magenta)."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (r > 150) & (b > 110) & (g < 90) & (r - g > 90)


def green(a: np.ndarray) -> np.ndarray:
    """Pixels that look like the terminal test fill (strong green)."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (g > 140) & (r < 90) & (b < 140) & (g - r > 80)


def largest_blob(mask: np.ndarray, cell: int = 4, min_hits: int = 3) -> tuple[int, tuple[int, int, int, int] | None]:
    """Size in pixels of the biggest connected patch of `mask`, and its box (x, y, w, h).

    Works on cell x cell blocks (a block counts when at least min_hits pixels are set), which
    ignores single-pixel noise such as anti-aliasing and is fast in plain Python.
    """
    h, w = mask.shape
    H, W = h // cell, w // cell
    if H == 0 or W == 0:
        return 0, None
    blocks = mask[:H * cell, :W * cell].reshape(H, cell, W, cell).sum(axis=(1, 3)) >= min_hits
    seen = np.zeros_like(blocks)
    best, box = 0, None
    for y0, x0 in zip(*np.nonzero(blocks)):
        if seen[y0, x0]:
            continue
        q = deque([(y0, x0)])
        seen[y0, x0] = True
        n, ys, xs = 0, [], []
        while q:
            y, x = q.popleft()
            n += 1
            ys.append(y)
            xs.append(x)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                yy, xx = y + dy, x + dx
                if 0 <= yy < H and 0 <= xx < W and blocks[yy, xx] and not seen[yy, xx]:
                    seen[yy, xx] = True
                    q.append((yy, xx))
        if n > best:
            best = n
            box = (min(xs) * cell, min(ys) * cell, (max(xs) - min(xs) + 1) * cell, (max(ys) - min(ys) + 1) * cell)
    return best * cell * cell, box


@dataclass
class Diff:
    mean_l: float           # average brightness difference (0-255)
    changed: float          # share of pixels that changed a lot (0-1)
    blob: int               # biggest connected changed patch, in pixels
    box: tuple | None
    brightness_now: float
    brightness_ref: float
    image: np.ndarray = field(repr=False, default=None)


def compare(now: np.ndarray, ref: np.ndarray, ignore: np.ndarray | None = None, threshold: float = 40) -> Diff:
    if now.shape != ref.shape:
        h, w = min(now.shape[0], ref.shape[0]), min(now.shape[1], ref.shape[1])
        now, ref = now[:h, :w], ref[:h, :w]
        if ignore is not None:
            ignore = ignore[:h, :w]
    d = np.abs(now - ref).max(axis=-1)
    keep = np.ones(d.shape, bool) if ignore is None else ~ignore
    dl = np.abs(lum(now) - lum(ref))
    big = (d > threshold) & keep
    blob, box = largest_blob(big)
    n = max(int(keep.sum()), 1)
    vis = np.repeat(lum(now)[..., None] * 0.45, 3, axis=-1)
    vis[big] = (255, 40, 40)
    if ignore is not None:
        vis[ignore] = vis[ignore] * 0.4 + np.array([40, 40, 90]) * 0.6
    return Diff(float(dl[keep].mean()), float(big.sum() / n), blob, box,
                float(lum(now)[keep].mean()), float(lum(ref)[keep].mean()), vis.astype(np.uint8))


def save(a: np.ndarray, p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(p, optimize=True)
    return p


def crop(a: np.ndarray, box) -> np.ndarray:
    x, y, w, h = (int(round(v)) for v in box)
    x, y = max(x, 0), max(y, 0)
    return a[y:y + h, x:x + w]


def rect_mask(shape, rects, grow: int = 0) -> np.ndarray:
    m = np.zeros(shape[:2], bool)
    for x, y, w, h in rects:
        x0, y0 = max(int(x) - grow, 0), max(int(y) - grow, 0)
        m[y0:int(y + h) + grow, x0:int(x + w) + grow] = True
    return m


def shell_cpu_seconds() -> float:
    pid = subprocess.run(["pgrep", "-u", "dino", "-x", "gnome-shell"], capture_output=True, text=True).stdout.split()
    if not pid:
        return float("nan")
    fields = Path(f"/proc/{pid[0]}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
