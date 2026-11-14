"""The glass login screen (run.sh --login-screen): GNOME Shell in GDM's own "gdm" mode with
the Fedora Glass login add-on, as GDM runs it (see container/login-session.sh).

Runs as root inside the test container: it switches the add-on on and off the way the root
helper does (the real helper fedoraglass/login_glass.py when it works here, otherwise by
hand, see turn_on), restarts the login screen for each look, and talks to the greeter's
GNOME Shell over its session bus. Writes the same report as run_checks.py, and full-size
pictures of each look in /out/pictures for people to judge.

    python3 login_checks.py [--update-references] [--only plain,glass,...]
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import secrets
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from gi.repository import Gio

sys.path.insert(0, str(Path(__file__).parent))
import lgqa  # noqa: E402
import run_checks as rc  # noqa: E402
from lgqa import OUT, Shell, ShellError  # noqa: E402
from run_checks import Check, Ctx, picture  # noqa: E402

UUID = "fedora-glass-login@djshiye.github.io"
GREETER = "gdm-greeter"
G = pwd.getpwnam(GREETER).pw_uid
# The greeter's session bus, not dino's (lgqa points at dino's when it is imported).
os.environ.update({"DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{G}/bus", "XDG_RUNTIME_DIR": f"/run/user/{G}",
                   "HOME": "/root"})
CONF = Path("/etc/fedora-glass/login")
LOOK = CONF / "look.json"
NOTE = Path("/var/lib/gdm3/seat0/state/fedora-glass-login/health.json")
STYLE = Path(f"/run/user/{G}/fedora-glass-login/login.css")
DB = Path("/etc/dconf/db/gdm.d")
KEYFILE, LOCKS = DB / "90-fedora-glass-login", DB / "locks" / "90-fedora-glass-login"
HELPER = Path("/src/fedoraglass/login_glass.py")
WALLPAPER = Path("/opt/lgqa/wallpaper.png")
PICTURES = OUT / "pictures"
GNOME = os.environ.get("LGQA_GNOME", "50")
rc.REFS = Path(__file__).resolve().parent.parent / "references" / "login" / f"gnome{GNOME}"
# The login screen keeps one set of reference pictures per GNOME, at its own screen size.
rc.SCREEN = "2000x1125"
DEFAULTS = {"accent": "#3584e4", "tint": "#1e1e2a", "tint_amount": 0.2, "frost": 0.35, "blur": 60, "dim": 0.28,
            "card": True, "clock": "bold", "picture": "wallpaper", "fit": "zoom", "battery": True, "message": ""}
MESSAGE = "Welcome back. This PC belongs to Dino: call 555-0100 if found."

# ---------------------------------------------------------------------------------------------
# JavaScript run inside the greeter
# ---------------------------------------------------------------------------------------------
DIALOG = "Main.screenShield._dialog"
READY_JS = f"return !Main.layoutManager._startingUp && !!{DIALOG}?._authPrompt;"
# GDM_GREETER_TEST delays GNOME's startup-prepared, so its login dialog misses the
# startup-complete that makes it load the user list (with GDM it never does): load it now.
USERLIST_JS = f"""const d = {DIALOG}; if (!d._userListLoaded && d._disableUserList === undefined) d._updateDisableUserList();
 return d._userList._items.size > 0 && d._userSelectionBox.visible;"""
ACTIVATE_JS = f"{DIALOG}._userList._items.get('dino').emit('activate'); 1"
# The password question the way GDM's verifier asks it (GNOME 51 passes one object).
ASK_JS = f"""const a = {DIALOG}._authPrompt, v = a._userVerifier;
 if (a._onAskQuestion.length === 1) v.emit('ask-question', {{serviceName: 'gdm-password', question: 'Password:', secret: true, answerHandler: () => {{}}}});
 else v.emit('ask-question', 'gdm-password', 'Password:', true);
 return 1;"""
PROMPT_UP_JS = f"const a = {DIALOG}._authPrompt; return a.mapped && a.opacity === 255 && a._entry.mapped && !{DIALOG}._userSelectionBox.visible;"
CANCEL_JS = f"{DIALOG}._authPrompt.cancel(); 1"
LIST_UP_JS = f"const d = {DIALOG}; return d._userSelectionBox.visible && d._userList.mapped && !d._authPrompt.visible;"
STATE_JS = """const g = Main.screenShield._lockDialogGroup, kids = g.get_children();
 const L = kids.find(k => k.name === 'fedora-glass-login');
 const box = a => { if (!a || !a.mapped || !a.visible) return null; const [x, y] = a.get_transformed_position();
   const [w, h] = a.get_transformed_size(); return [x, y, w, h]; };
 let takes = 0; const all = []; const walk = a => { all.push(a); if (a.reactive || a.can_focus) takes++; a.get_children().forEach(walk); };
 if (L) walk(L);
 const named = n => all.filter(a => a.name === n);
 const theme = imports.gi.St.ThemeContext.get_for_stage(global.stage).get_theme();
 const dm = Main.panel.statusArea.dateMenu?.container;
 return {layer: L ? kids.indexOf(L) : -1, children: kids.map(k => k.name || k.constructor.name),
   reactive: L ? L.reactive : null, takes, actors: all.length,
   sheets: named('fedora-glass-login-sheet').map(s => { const b = box(s), p = s.pad ?? 0;
     return b && [b[0] + p, b[1] + p, b[2] - 2 * p, b[3] - 2 * p]; }),
   card: named('fedora-glass-login-card').map(s => { const b = box(s), p = s.pad ?? 0;
     return b && [b[0] + p, b[1] + p, b[2] - 2 * p, b[3] - 2 * p]; })[0] ?? null,
   opacity: L ? L.opacity : null,
   top: box(named('fedora-glass-login-top')[0]),
   messageShown: Boolean(box(named('fedora-glass-login-message')[0])),
   time: all.find(a => a.style_class === 'unlock-dialog-clock-time')?.text ?? null,
   message: named('fedora-glass-login-message')[0]?.text ?? null,
   smallClock: dm ? dm.visible : null,
   styles: theme.get_custom_stylesheets().filter(f => f).map(f => f.get_path()),
   monitors: Main.layoutManager.monitors.map(m => [m.x, m.y, m.width, m.height, m.geometry_scale]),
   prompt: box(Main.screenShield._dialog._authPrompt), list: box(Main.screenShield._dialog._userList),
   state: Main.extensionManager.lookup('""" + UUID + """')?.state ?? null};"""
CENSUS_JS = "let n = 0; const w = a => { n++; a.get_children().forEach(w); }; w(global.stage); return n;"
# A picture that is laid out before what is around it, as GNOME Shell does at a slow start (it lays
# the children of its uiGroup out on their own): its box is set while the new actor above it has
# none yet, then that one is laid out and the picture's box stays the same, so nothing tells the glass.
LATE_MAKE_JS = """const {Clutter} = imports.gi;
 const L = Main.screenShield._lockDialogGroup.get_children().find(k => k.name === 'fedora-glass-login');
 const sheet = L.get_children().find(k => k.name === 'fedora-glass-login-sheet');
 const outer = new Clutter.Actor({name: 'lgqa-late-outer', opacity: 0, x: 0, y: 0, width: 300, height: 200});
 const src = new Clutter.Actor({x: 0, y: 0, width: 300, height: 200});
 let pane = null;
 try {
   outer.add_child(src); L.add_child(outer);
   pane = new sheet.constructor('full'); pane.name = 'lgqa-late-pane'; L.add_child(pane);
   pane.setSources([src]); pane.place(100, 100, 300, 200, [0, 0, 0, 0], 100, 100);
   src.allocate(new Clutter.ActorBox({x1: 0, y1: 0, x2: 300, y2: 200}));
   return {before: [...pane._clones.values()][0].visible};
 } catch (e) { pane?.destroy(); outer.destroy(); throw e; }"""
# Reads the copy and takes the staging away again, whatever happens.
LATE_READ_JS = """const kids = Main.screenShield._lockDialogGroup.get_children().find(k => k.name === 'fedora-glass-login').get_children();
 const pane = kids.find(k => k.name === 'lgqa-late-pane'), outer = kids.find(k => k.name === 'lgqa-late-outer');
 try {
   const copy = [...pane._clones.values()][0];
   return {shown: copy.visible, clipped: copy.has_clip, at: [copy.x, copy.y], pad: pane.pad};
 } finally { pane?.destroy(); outer?.destroy(); }"""
KEYS_JS = """(async () => { const {Clutter, GLib} = imports.gi;
 const seat = global.stage.context.get_backend().get_default_seat();
 const k = globalThis._lgqaKb ??= seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
 const wait = ms => new Promise(r => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { r(); return false; }));
 const desc = () => { let a = global.stage.get_key_focus(); if (a instanceof Clutter.Text) a = a.get_parent();
   return a ? `${a.constructor.name}${a.style_class ? '.' + a.style_class.split(' ')[0] : ''}` : 'none'; };
 const out = [desc()];
 for (const kv of %s) { k.notify_keyval(GLib.get_monotonic_time(), kv, Clutter.KeyState.PRESSED);
   k.notify_keyval(GLib.get_monotonic_time(), kv, Clutter.KeyState.RELEASED); await wait(120); out.push(desc()); }
 return JSON.stringify(out); })()"""
TYPE_JS = """(async () => { const {Clutter, GLib} = imports.gi;
 const seat = global.stage.context.get_backend().get_default_seat();
 const k = globalThis._lgqaKb ??= seat.create_virtual_device(Clutter.InputDeviceType.KEYBOARD_DEVICE);
 const wait = ms => new Promise(r => GLib.timeout_add(GLib.PRIORITY_DEFAULT, ms, () => { r(); return false; }));
 const e = Main.screenShield._dialog._authPrompt._entry;
 const focused = global.stage.get_key_focus() === e.clutter_text;
 for (const ch of 'Glass 42') { const kv = Clutter.unicode_to_keysym(ch.charCodeAt(0));
   k.notify_keyval(GLib.get_monotonic_time(), kv, Clutter.KeyState.PRESSED);
   k.notify_keyval(GLib.get_monotonic_time(), kv, Clutter.KeyState.RELEASED); await wait(40); }
 await wait(300); const t = e.get_text(); e.set_text(''); return JSON.stringify({focused, text: t}); })()"""
TAB, DOWN, UP, SHIFT_TAB = 0xff09, 0xff54, 0xff52, 0xfe20
# The card and what the prompt shows: every visible control, icon and label with text.
CARD_JS = """const St = imports.gi.St, p = """ + DIALOG + """._authPrompt;
 const box = a => { const [x, y] = a.get_transformed_position(); const [w, h] = a.get_transformed_size(); return [x, y, w, h]; };
 let r = null; const add = b => { if (!(b[2] > 1 && b[3] > 1)) return;
   r = r ? [Math.min(r[0], b[0]), Math.min(r[1], b[1]), Math.max(r[2], b[0] + b[2]), Math.max(r[3], b[1] + b[3])]
     : [b[0], b[1], b[0] + b[2], b[1] + b[3]]; };
 const walk = a => { if (!a.visible || a.opacity === 0 || !a.mapped) return;
   if (a instanceof St.Label) { if (a.text) add(box(a)); return; }
   if (a instanceof St.Entry || a instanceof St.Button || a instanceof St.Icon) { add(box(a)); return; }
   a.get_children().forEach(walk); };
 p.get_children().forEach(walk);
 const kids = []; const all = a => { kids.push(a); a.get_children().forEach(all); };
 Main.screenShield._lockDialogGroup.get_children().filter(k => k.name === 'fedora-glass-login').forEach(all);
 const c = kids.find(k => k.name === 'fedora-glass-login-card');
 const cb = c && c.visible ? box(c) : null, pad = c?.pad ?? 0;
 const d = """ + DIALOG + """, m = Main.layoutManager.primaryMonitor;
 let list = null;
 if (d._userSelectionBox.visible && d._userList.mapped) {
   const u = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];
   const q = a => { const b = box(a); return [b[0], b[1], b[0] + b[2], b[1] + b[3]]; };
   list = q(d._userList); if (d._notListedButton?.mapped) list = u(list, q(d._notListedButton)); }
 const top = kids.find(k => k.name === 'fedora-glass-login-top');
 return {card: cb && [cb[0] + pad, cb[1] + pad, cb[2] - 2 * pad, cb[3] - 2 * pad], content: r, prompt: box(p), list,
   opacity: c ? c.opacity : null, screen: [m.x, m.y, m.width, m.height], top: top?.mapped ? box(top) : null,
   message: p._message?.visible && p._message.opacity ? p._message.text : ''};"""
# How GNOME's theme draws the user that has the keyboard: our light and white rim, and no ring of GNOME's.
ROW_JS = f"""const St = imports.gi.St, it = {DIALOG}._userList._items.get('dino'), n = it.get_theme_node();
 const col = c => [c.red, c.green, c.blue, c.alpha], sh = n.get_box_shadow();
 return {{focus: it.has_style_pseudo_class('focus') || it.has_style_pseudo_class('selected'),
   border: col(n.get_border_color(St.Side.TOP)), fill: col(n.get_background_color()),
   shadow: sh ? {{inset: sh.inset, spread: sh.spread, color: col(sh.color)}} : null}};"""
ERROR_TEXT = "Sorry, that didn\u2019t work. Please try again."
SET_ERROR_JS = f"{DIALOG}._authPrompt.setMessage('{ERROR_TEXT}', 3); 1"
CLEAR_MESSAGE_JS = f"{DIALOG}._authPrompt.setMessage('', 0); 1"
# A message far longer than GNOME keeps room for (a list of ways to log in is as tall).
LONG_LINES = 14
LONG_MESSAGE_JS = f"""{DIALOG}._authPrompt.setMessage(Array.from({{length: {LONG_LINES}}},
  (_, i) => `Line ${{i + 1}} of a long message from the system`).join('\\n'), 3); 1"""
# Large Text, as the accessibility menu on the login screen sets it (and back).
TEXT_SCALE_JS = "new imports.gi.Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).set_double('text-scaling-factor', %s); 1"
# GNOME's login dialog faded as GNOME itself does it (out once somebody has logged in, in again when the session
# does not start), and what of ours is seen then.
FADE_JS = f"const d = {DIALOG}; d.ease({{opacity: %d, duration: 250, mode: imports.gi.Clutter.AnimationMode.EASE_OUT_QUAD}}); 1"
PARTS_JS = f"""const all = []; const walk = a => {{ all.push(a); a.get_children().forEach(walk); }};
 const L = Main.screenShield._lockDialogGroup.get_children().find(k => k.name === 'fedora-glass-login'); if (L) walk(L);
 const one = n => all.find(a => a.name === n);
 return {{dialog: {DIALOG}.opacity, layer: L?.opacity ?? null, card: one('fedora-glass-login-card')?.opacity ?? null,
   top: one('fedora-glass-login-top')?.opacity ?? null,
   sheets: all.filter(a => a.name === 'fedora-glass-login-sheet').map(a => a.visible ? a.opacity : 0)}};"""
USERS_JS = f"return {DIALOG}._userList._items.size;"
MORE_USERS = ["ana", "boris", "clara", "dmitri", "elena"]
CARD_PAD = 28      # px of card around the user list, and beside the prompt
PROMPT_PAD = 40    # px of card above the avatar and under the field


# ---------------------------------------------------------------------------------------------
# Switching it on and off, as the root helper does
# ---------------------------------------------------------------------------------------------
class Switch:
    """Turns the add-on on with a look. Uses the real root helper when it exists and works in
    this container; otherwise writes what it writes by hand (by_hand), so the checks still
    test the add-on. Which way was used is said in the report."""

    def __init__(self) -> None:
        self.token = secrets.token_hex(16)
        self.way = ""
        self.helper_note = ""

    def on(self, values: dict | None = None, picture: Path = WALLPAPER) -> None:
        v = {**DEFAULTS, **(values or {})}
        if self.way != "by-hand" and HELPER.is_file():
            data = picture.read_bytes() if v["picture"] == "wallpaper" else b""
            r = subprocess.run(["python3", "-I", "-S", str(HELPER), "on", json.dumps(v)], input=data,
                               capture_output=True, timeout=120)
            if r.returncode == 0:
                self.way = "helper"
                look = json.loads(LOOK.read_text())
                self.token = look["token"]
                return
            self.helper_note = f"exit {r.returncode}: {(r.stdout + r.stderr).decode(errors='replace').strip()[:200]}"
            if self.way == "helper":
                raise RuntimeError(f"the root helper stopped working: {self.helper_note}")
        self.way = "by-hand"
        self.by_hand(v, picture)

    # ---- what the helper writes, by hand (swap for the helper once it runs here) ----
    def by_hand(self, v: dict, picture: Path) -> None:
        CONF.mkdir(parents=True, exist_ok=True)
        os.chmod(CONF, 0o755)
        for old in CONF.glob("picture.*"):
            old.unlink()
        bg = ""
        if v["picture"] == "wallpaper":
            pic = CONF / ("picture.png" if picture.read_bytes()[:4] == b"\x89PNG" else "picture.jpg")
            shutil.copyfile(picture, pic)
            os.chmod(pic, 0o644)
            uri = f"file://{pic}"
            bg = (f"\n[org/gnome/desktop/background]\npicture-uri='{uri}'\npicture-uri-dark='{uri}'\n"
                  f"picture-options='{v['fit']}'\n")
        LOOK.write_text(json.dumps({"version": 1, "token": self.token, **v}))
        os.chmod(LOOK, 0o644)
        KEYFILE.write_text(f"[org/gnome/shell]\nenabled-extensions=['{UUID}']\ndisable-user-extensions=false\n"
                           f"disabled-extensions=@as []\n{bg}")
        LOCKS.parent.mkdir(parents=True, exist_ok=True)
        LOCKS.write_text("/org/gnome/shell/enabled-extensions\n/org/gnome/shell/disable-user-extensions\n"
                         "/org/gnome/shell/disabled-extensions\n"
                         + ("/org/gnome/desktop/background/picture-uri\n/org/gnome/desktop/background/picture-uri-dark\n"
                            "/org/gnome/desktop/background/picture-options\n" if bg else ""))
        subprocess.run(["dconf", "update"], check=True)

    def off(self) -> None:
        if self.way == "helper":
            subprocess.run(["python3", "-I", "-S", str(HELPER), "off"], capture_output=True, timeout=120, check=False)
        for p in (KEYFILE, LOCKS):
            p.unlink(missing_ok=True)
        shutil.rmtree(CONF, ignore_errors=True)
        subprocess.run(["dconf", "update"], check=True)


SWITCH = Switch()


# ---------------------------------------------------------------------------------------------
# Driving the login screen
# ---------------------------------------------------------------------------------------------
def restart(sh: Shell, monitors: int = 1, kill: bool = False) -> None:
    """A fresh login screen (GDM starts a new greeter at each boot and after each logout).
    kill: GNOME Shell is killed first (SIGKILL), as in a crash: no clean stop."""
    (OUT / "monitors").write_text(str(monitors))
    (OUT / "relogged-in").unlink(missing_ok=True)
    (OUT / "relogin").write_text("kill" if kill else "")
    end = time.monotonic() + 150
    while not (OUT / "relogged-in").exists():
        if time.monotonic() > end:
            raise ShellError("the login screen did not start again")
        time.sleep(0.5)
    reconnect(sh)
    if not sh.wait_for(READY_JS, 60):
        raise ShellError("GNOME's login dialog did not show")
    if not sh.wait_for(USERLIST_JS, 20):
        raise ShellError("the user list did not show")
    sh.measure_scale()
    time.sleep(3)


def reconnect(sh: Shell) -> None:
    """Each greeter has its own session bus (as under GDM): talk to the new one."""
    sh.bus = Gio.DBusConnection.new_for_address_sync(
        os.environ["DBUS_SESSION_BUS_ADDRESS"],
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)


def show_prompt(sh: Shell) -> bool:
    sh.eval(ACTIVATE_JS)
    time.sleep(1.5)
    sh.json(ASK_JS)
    ok = sh.wait_for(PROMPT_UP_JS, 10)
    time.sleep(1.5)
    return ok


def back_to_list(sh: Shell) -> bool:
    sh.eval(CANCEL_JS)
    ok = sh.wait_for(LIST_UP_JS, 10)
    time.sleep(1.5)
    return ok


def set_users(n: int) -> None:
    """The test user plus n - 1 more accounts that the login screen lists (1: only the test user again).
    The next login screen shows them (restart)."""
    want = MORE_USERS[:max(0, n - 1)]
    for u in MORE_USERS:
        have = subprocess.run(["id", u], capture_output=True).returncode == 0
        if u in want and not have:
            subprocess.run(["useradd", "-m", "-c", u.title(), u], check=True)
            # GNOME lists no account without a password. A throwaway one: nobody logs in here.
            subprocess.run(["chpasswd"], input=f"{u}:{secrets.token_urlsafe(16)}".encode(), check=True)
            Path(f"/var/lib/AccountsService/users/{u}").write_text("[User]\nSystemAccount=false\n")
        elif u not in want and have:
            subprocess.run(["userdel", "-r", u], capture_output=True)
            Path(f"/var/lib/AccountsService/users/{u}").unlink(missing_ok=True)
    # The accounts service reads its list at its start (it comes back by itself when asked).
    subprocess.run(["pkill", "-x", "accounts-daemon"], check=False)
    time.sleep(1)


def state(sh: Shell) -> dict:
    return sh.json(STATE_JS)


def note() -> dict:
    try:
        return json.loads(NOTE.read_text())
    except (OSError, ValueError):
        return {}


def wait_note(phase: str, seconds: float = 10) -> dict:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        n = note()
        if n.get("phase") == phase:
            return n
        time.sleep(0.3)
    return note()


def keys(sh: Shell, seq: list[int]) -> list[str]:
    return json.loads(sh.eval(KEYS_JS % json.dumps(seq), 30))


def typed(sh: Shell) -> dict:
    return json.loads(sh.eval(TYPE_JS, 30))


def shot(sh: Shell, name: str) -> np.ndarray:
    """A picture of the whole login screen, kept full size in /out/pictures too."""
    p = sh.shot(name)
    PICTURES.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(p, PICTURES / f"{name}.png")
    return lgqa.load(p)


def region(a: np.ndarray, sh: Shell, box) -> np.ndarray:
    k = sh.scale
    x, y, w, h = (int(round(v * k)) for v in box)
    return a[max(y, 0):y + h, max(x, 0):x + w]


def backdrop_stats(a: np.ndarray, sh: Shell, st: dict) -> tuple[float, float]:
    """Mean and spread of brightness on the left part of the first screen, clear of the dialog."""
    mx, my, mw, mh = st["monitors"][0][:4]
    r = region(a, sh, (mx + mw * 0.03, my + mh * 0.3, mw * 0.2, mh * 0.5))
    lum = lgqa.lum(r)
    return float(lum.mean()), float(lum.std())


def hug(c: Check, sh: Shell, when: str, message: bool = False, middle: bool = True) -> None:
    """The card hugs what the prompt shows: 40 px above and below, 28 px beside it, nothing of
    GNOME's outside it. Without a message it stands in the middle of the screen (middle=False:
    not asked, as on a short screen, where it stands under the big clock)."""
    k = sh.json(CARD_JS)
    card, content = k["card"], k["content"]
    if not card or not content:
        c.add(False, f"The card {when}: card {card}, content {content}.")
        return
    pads = [content[0] - card[0], content[1] - card[1], card[0] + card[2] - content[2], card[1] + card[3] - content[3]]
    mid = k["prompt"][0] + k["prompt"][2] / 2
    centred = abs(card[0] + card[2] / 2 - mid) <= 2
    # 40 px above and below; sideways centred on the prompt, 28 px beside its farther side.
    ok = abs(pads[1] - PROMPT_PAD) <= 2 and abs(pads[3] - PROMPT_PAD) <= 2 and min(pads[0], pads[2]) >= CARD_PAD - 2 \
        and abs(min(pads[0], pads[2]) - CARD_PAD) <= 2 and centred and (not message or bool(k["message"])) \
        and k["opacity"] == 255
    c.add(ok, f"The card hugs the prompt {when}: {PROMPT_PAD} px above and below, centred, nothing of GNOME's outside "
          f"it (left, top, right, bottom: {', '.join(f'{v:.0f}' for v in pads)}), {card[3]:.0f} px tall." if ok else
          f"The card does not hug the prompt {when}: padding {[round(v) for v in pads]} around {content}, "
          f"message {k['message']!r}, opacity {k['opacity']}.")
    if not message and middle:
        sx, sy, sw, sh_ = k["screen"]
        off = [card[0] + card[2] / 2 - (sx + sw / 2), card[1] + card[3] / 2 - (sy + sh_ / 2)]
        ok = abs(off[0]) <= 2 and abs(off[1]) <= 6
        c.add(ok, f"The prompt's card stands in the middle of the screen {when} ({off[0]:+.0f}, {off[1]:+.0f} px off)."
              if ok else f"The prompt's card is not in the middle of the screen {when}: {off[0]:+.0f}, {off[1]:+.0f} px off "
              f"(card {[round(v) for v in card]} on {k['screen']}).")


def hug_list(c: Check, sh: Shell, when: str) -> None:
    """One card around the user list: 28 px around the rows and "Not listed?", in the middle of the screen."""
    k = sh.json(CARD_JS)
    card, rows = k["card"], k["list"]
    if not card or not rows:
        c.add(False, f"No card around the user list {when}: card {card}, list {rows}.")
        return
    pads = [rows[0] - card[0], rows[1] - card[1], card[0] + card[2] - rows[2], card[1] + card[3] - rows[3]]
    sx, sy, sw, sh_ = k["screen"]
    off = [card[0] + card[2] / 2 - (sx + sw / 2), card[1] + card[3] / 2 - (sy + sh_ / 2)]
    ok = all(abs(v - CARD_PAD) <= 2 for v in pads) and abs(off[0]) <= 2 and abs(off[1]) <= 4 and k["opacity"] == 255
    c.add(ok, f"One glass card around the user list {when}: {CARD_PAD} px around the names and \"Not listed?\", in the "
          f"middle of the screen ({off[0]:+.0f}, {off[1]:+.0f} px off), {card[2]:.0f} x {card[3]:.0f} px." if ok else
          f"The card does not sit around the user list {when}: padding {[round(v) for v in pads]}, "
          f"{off[0]:+.0f}, {off[1]:+.0f} px off the middle, opacity {k['opacity']} (card {[round(v) for v in card]}, "
          f"list {[round(v) for v in rows]}).")


def clock_place(c: Check, sh: Shell, st: dict, when: str) -> None:
    """The clock block stands in the middle of the room above the prompt's card."""
    k = sh.json(CARD_JS)
    top, card, (sx, sy, sw, _) = k["top"], k["card"], k["screen"]
    if not top or not card:
        c.add(False, f"The clock's place {when}: clock {top}, card {card}.")
        return
    above, below = top[1] - sy, card[1] - (top[1] + top[3])
    side = top[0] + top[2] / 2 - (sx + sw / 2)
    ok = abs(above - below) <= 3 and abs(side) <= 2 and below >= 24
    c.add(ok, f"The clock stands in the middle of the room above the card {when}: {above:.0f} px above it, "
          f"{below:.0f} px between it and the card." if ok else
          f"The clock is not in the middle above the card {when}: {above:.0f} px above, {below:.0f} px below, "
          f"{side:+.0f} px sideways.")


def backdrop_shot(sh: Shell, st: dict, name: str, dark: float) -> tuple[np.ndarray, float, float, str]:
    """A picture and its backdrop_stats. GNOME loads the picture on its own (another process
    decodes it), now and then a moment after the login screen shows: a backdrop darker
    than `dark` is looked at again for up to 15 s, and the wait is said, so a picture that
    never comes still fails and a late one is not hidden."""
    a = shot(sh, name)
    mean, spread = backdrop_stats(a, sh, st)
    waited = 0
    while mean <= dark and waited < 15:
        time.sleep(1)
        waited += 1
        a = shot(sh, name)
        mean, spread = backdrop_stats(a, sh, st)
    return a, mean, spread, (f" The picture came {waited} s late." if waited else "")


def mask_for(sh: Shell, st: dict, shape) -> np.ndarray:
    """The clocks change every minute: leave them out of picture comparisons."""
    boxes = [b for b in [st.get("top")] if b]
    boxes += rc.actor_boxes(Ctx(sh, False), "DateMenuButton|clock-display")
    return lgqa.rect_mask(shape, [[v * sh.scale for v in b] for b in boxes], grow=8)


# ---------------------------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------------------------
class Lane:
    def __init__(self, sh: Shell, update: bool) -> None:
        self.sh, self.ctx = sh, Ctx(sh, update)
        self.base: dict = {}

    def errors_since(self, mark: int) -> list[str]:
        return [e for e in self.ctx.new_errors(mark) if rc.ours(e)]


def check_plain(lane: Lane) -> Check:
    c = Check("plain", "The plain login screen (add-on off)",
              "GNOME's own login screen with the add-on installed but switched off: the baseline for the "
              "focus order, the typing test, the actor count and the idle redraws.")
    sh = lane.sh
    SWITCH.off()
    NOTE.unlink(missing_ok=True)
    restart(sh)
    st = state(sh)
    c.add(st["layer"] == -1 and st["state"] != 1, "Switched off, the add-on draws nothing."
          if st["layer"] == -1 else "Switched off, the add-on still drew something.")
    lane.base["census"] = sh.json(CENSUS_JS)
    lane.base["idle"] = rc.timed(lane.ctx, 6)
    lane.base["list_keys"] = keys(sh, [TAB, TAB, TAB, DOWN, UP, SHIFT_TAB])
    back_to_list(sh) if not sh.wait_for(LIST_UP_JS, 1) else None
    plain = shot(sh, f"login-g{GNOME}-plain-userlist")
    c.add(show_prompt(sh), "The password prompt shows after a click on Dino.")
    lane.base["prompt_keys"] = keys(sh, [TAB, TAB, TAB])
    sh.eval(f"{DIALOG}._authPrompt._entry.grab_key_focus(); 1")
    t = typed(sh)
    c.add(t["text"] == "Glass 42", f"Typed into the password field: {t['text']!r}.")
    shot(sh, f"login-g{GNOME}-plain-prompt")
    c.info(f"Plain login screen: {lane.base['census']} actors, {lane.base['idle']['frames']} frames in "
           f"{lane.base['idle']['seconds']:.0f} s at rest. Focus order (user list): {' > '.join(lane.base['list_keys'])}.")
    c.steps[-1].images.append(picture("plain-userlist", plain))
    return c


def check_glass(lane: Lane) -> Check:
    c = Check("glass", "Glass on the login screen",
              "Switched on with the default look: the add-on starts and says ok, draws in one container under "
              "GNOME's login dialog that takes no input, a sheet per screen showing the picture, one card in the "
              "middle of the screen around the user list and then around the password prompt, the clock in the "
              "middle above it, and GNOME's prompt still works exactly as without it.")
    sh = lane.sh
    NOTE.unlink(missing_ok=True)
    SWITCH.on({"message": MESSAGE})
    c.info(f"Switched on by {'the real root helper' if SWITCH.way == 'helper' else 'hand (the root helper does not run here: ' + SWITCH.helper_note + ')'}.")
    mark = lane.ctx.log_lines()
    restart(sh)
    st = state(sh)
    c.add(st["state"] == 1, f"GNOME Shell runs the add-on in gdm mode (state {st['state']}).")
    n = wait_note("ok", 10)
    c.add(n.get("phase") == "ok" and n.get("token") == SWITCH.token,
          f"The health note says ok with this look's token ({n})." if n.get("phase") == "ok" else
          f"The health note does not say ok: {n}.")
    c.add(st["layer"] == 0 and "LoginDialog" in st["children"][1:],
          f"Our layer is the bottom child of the lock dialog group, under GNOME's login dialog: {st['children']}."
          if st["layer"] == 0 else f"Our layer is not the bottom child of the lock dialog group: {st['children']}.")
    c.add(st["reactive"] is False and st["takes"] == 0, "Nothing of ours takes clicks or keyboard focus."
          if st["takes"] == 0 and st["reactive"] is False else f"{st['takes']} of our actors can take clicks or focus.")
    c.add(len(st["sheets"]) == len(st["monitors"]) and all(st["sheets"]),
          f"One glass sheet per screen ({len(st['sheets'])} for {len(st['monitors'])}).")
    c.add(STYLE.exists() and str(STYLE) in st["styles"], "The add-on's own stylesheet is loaded from the greeter's "
          "private runtime folder." if STYLE.exists() else "The add-on's stylesheet is not loaded.")
    c.add(st["smallClock"] is False and bool(st["time"]), f"The big clock shows ({st['time']}) and the panel's small "
          "clock is hidden." if st["smallClock"] is False else "The panel's small clock still shows beside the big one.")
    c.add(st["message"] == MESSAGE, "The message shows under the clock, as plain text." if st["message"] == MESSAGE
          else f"The message shows as {st['message']!r}.")
    c.add(st["opacity"] == 255, "The glass has come up fully (it fades in once its picture is there)."
          if st["opacity"] == 255 else f"The glass did not come up fully: opacity {st['opacity']} of 255.")
    hug_list(c, sh, "at the start")
    row = sh.json(ROW_JS)
    # A rim anyone can see (a third white or more), on a little white: never a faint hint only.
    lit = row["focus"] and row["shadow"] is None and row["border"][:3] == [255, 255, 255] and row["border"][3] >= 120 \
        and row["fill"][:3] == [255, 255, 255] and 16 < row["fill"][3] < 64
    c.add(lit, f"The user that has the keyboard is plain to see (a little white and a clear white rim, "
          f"{row['border'][3] * 100 // 255} % white), with no coloured ring around it." if lit else
          f"The user that has the keyboard is not drawn as a lit row with a clear white rim: {row}.")
    a, mean, spread, late = backdrop_shot(sh, st, f"login-g{GNOME}-userlist", 6)
    c.add(mean > 6 and spread > 1.5, f"The glass shows the wallpaper: brightness {mean:.1f}, spread {spread:.1f} "
          f"(not black, not flat).{late}" if mean > 6 and spread > 1.5 else
          f"The glass does not show the wallpaper: brightness {mean:.1f}, spread {spread:.1f}.{late}", picture("userlist", a))
    rc.against_reference(lane.ctx, c, "userlist", "The user list", a, mask_for(sh, st, a.shape))
    # Rest: nothing moves, so nothing should draw (the clock ticks once a minute).
    idle = rc.timed(lane.ctx, 6)
    renders = max([p["rate"] for p in idle["panes"]] or [0])
    base = lane.base.get("idle", {"frames": 0})["frames"]
    c.add(idle["frames"] <= base + 3 and renders <= 0.5,
          f"At rest the login screen draws {idle['frames']} frames in {idle['seconds']:.0f} s ({base} without the add-on), "
          f"the glass renders at most {renders:.2f} times a second." if idle["frames"] <= base + 3 and renders <= 0.5 else
          f"At rest the login screen keeps drawing: {idle['frames']} frames in {idle['seconds']:.0f} s ({base} without), "
          f"glass {renders:.2f} renders a second.")
    # A slow start: GNOME lays the picture out before the screen around it. The glass kept its copy
    # of the picture hidden for good then, and the login screen stayed dark behind the glass.
    staged = sh.json(LATE_MAKE_JS)
    time.sleep(1)
    copy = sh.json(LATE_READ_JS)
    if staged["before"]:
        c.info("A picture laid out before the screen around it has its place at once on this GNOME: nothing to wait for.")
    else:
        c.add(copy["shown"] and copy["clipped"], "A picture laid out before the screen around it (a slow start) still "
              "shows through the glass: its copy is placed once the rest is laid out." if copy["shown"] else
              "A picture laid out before the screen around it never shows through the glass: a dark login screen "
              f"after a slow start ({copy}).")
    lk = keys(sh, [TAB, TAB, TAB, DOWN, UP, SHIFT_TAB])
    if "list_keys" in lane.base:
        c.add(lk == lane.base["list_keys"], "Tab and the arrow keys move through the user list exactly as without "
              f"the add-on ({' > '.join(lk)})." if lk == lane.base["list_keys"] else
              f"The keyboard focus moves differently: {lk} instead of {lane.base['list_keys']}.")
    c.add(show_prompt(sh), "The password prompt shows after a click on Dino.")
    st = state(sh)
    # GDM's test mode leaves "Authentication error" from the first try: the empty prompt first.
    sh.eval(CLEAR_MESSAGE_JS)
    time.sleep(1)
    hug(c, sh, "(empty)")
    clock_place(c, sh, st, "with the prompt")
    c.add(st["messageShown"] and st["smallClock"] is False, "The clock and the message stay with the prompt up."
          if st["messageShown"] and st["smallClock"] is False else
          f"With the prompt up the message shows: {st['messageShown']}, the small clock: {st['smallClock']}.")
    pk = keys(sh, [TAB, TAB, TAB])
    if "prompt_keys" in lane.base:
        c.add(pk == lane.base["prompt_keys"], f"Tab moves through the prompt exactly as without the add-on ({' > '.join(pk)})."
              if pk == lane.base["prompt_keys"] else f"Tab moves differently in the prompt: {pk} instead of {lane.base['prompt_keys']}.")
    sh.eval(f"{DIALOG}._authPrompt._entry.grab_key_focus(); 1")
    t = typed(sh)
    c.add(t["text"] == "Glass 42", f"Typing on the keyboard reaches GNOME's password field ({t['text']!r})."
          if t["text"] == "Glass 42" else f"Typing did not reach the password field: {t}.")
    p = shot(sh, f"login-g{GNOME}-prompt")
    c.add(True, "The password prompt with glass.", picture("prompt", p))
    rc.against_reference(lane.ctx, c, "prompt", "The password prompt", p, mask_for(sh, st, p.shape))
    # A wrong password: GNOME's own message under the entry, and the card grows to it.
    sh.eval(SET_ERROR_JS)
    time.sleep(1.5)
    hug(c, sh, "with GNOME's message after a wrong password", message=True)
    e = shot(sh, f"login-g{GNOME}-prompt-error")
    c.add(True, "The password prompt after a wrong password.", picture("prompt-error", e))
    sh.eval(CLEAR_MESSAGE_JS)
    time.sleep(1.5)
    hug(c, sh, "with the message gone again")
    c.add(back_to_list(sh), "Back to the user list.")
    hug_list(c, sh, "after the prompt went")
    errs = lane.errors_since(mark)
    c.add(not errs, "No Fedora Glass errors in GNOME Shell's log." if not errs else
          f"{len(errs)} Fedora Glass errors in the log, first: {errs[0][-200:]}")
    # Last: a successful check (GNOME then tries to start the session, which GDM_GREETER_TEST can't).
    sh.eval(f"{DIALOG}._authPrompt._userVerifier.emit('verification-complete'); 1")
    time.sleep(1)
    n = note()
    c.add(n.get("verified") == SWITCH.token and n.get("phase") == "ok",
          "A successful password check is written down (verified = the token), the phase stays ok."
          if n.get("verified") == SWITCH.token else f"A successful password check was not written down: {n}.")
    return c


def check_disable(lane: Lane) -> Check:
    c = Check("disable", "Turning the add-on off takes everything away",
              "Disabling the add-on in the running login screen removes every actor it made, its stylesheet and file, "
              "and gives the panel's small clock back.")
    sh = lane.sh
    restart(sh)
    st = state(sh)
    on = sh.json(CENSUS_JS)
    # The root helper locks enabled-extensions and disabled-extensions, so GNOME's own
    # disableExtension() (which only writes those keys) cannot turn it off any more ...
    sh.eval(f"Main.extensionManager.disableExtension('{UUID}'); 1")
    time.sleep(1.5)
    c.info("GNOME's disableExtension() leaves it on (the switch's keys are locked)."
           if state(sh)["layer"] == 0 else "GNOME's disableExtension() turned it off (the switch's keys are not locked).")
    # ... so turn it off the way GNOME Shell itself does (the same call its settings path makes).
    sh.eval(f"const m = Main.extensionManager; m._callExtensionDisableWithRebase ? "
            f"m._callExtensionDisableWithRebase('{UUID}') : m._callExtensionDisable('{UUID}'); 1")
    time.sleep(1.5)
    after = state(sh)
    off = sh.json(CENSUS_JS)
    c.add(after["layer"] == -1 and off == on - st["actors"], f"{st['actors']} actors of ours before, none after: "
          f"{on} actors in all, then {off}." if off == on - st["actors"] and after["layer"] == -1 else
          f"Actors left behind: {on} with the add-on ({st['actors']} ours), {off} after.")
    c.add(str(STYLE) not in after["styles"] and not STYLE.exists(), "The stylesheet is unloaded and its file gone."
          if not STYLE.exists() else "The stylesheet file is still there.")
    c.add(after["smallClock"] is True, "The panel's small clock is back." if after["smallClock"] else "The panel's small clock stayed hidden.")
    base = lane.base.get("census")
    if base:
        c.info(f"A fresh plain login screen has {base} actors.")
    # On again the way GNOME Shell does it.
    sh.eval(f"Main.extensionManager._callExtensionEnable('{UUID}'); 1")
    back = sh.wait_for("return Main.screenShield._lockDialogGroup.get_children().some(k => k.name === 'fedora-glass-login');", 10)
    c.add(back, "Switched on again in the running login screen, the glass is back."
          if back else "Switched on again, the glass did not come back.")
    return c


def check_looks(lane: Lane) -> Check:
    c = Check("looks", "Each look", "The clock styles, the glow and system pictures, the light style, no card, and "
              "pictures of each to judge.")
    sh = lane.sh
    for name, values, what in (
            ("thin", {"clock": "thin"}, "Thin clock"),
            ("gnome", {"clock": "gnome", "message": MESSAGE}, "GNOME's own clock (no big clock)"),
            ("glow", {"picture": "glow", "accent": "#c061cb", "tint": "#241f31", "tint_amount": 0.3}, "The glow picture"),
            ("system", {"picture": "system", "card": False}, "The greeter's own background, no card")):
        SWITCH.on(values)
        restart(sh)
        st = state(sh)
        if name == "gnome":
            c.add(st["time"] is None and st["smallClock"] is True and st["message"] == MESSAGE,
                  "With GNOME's clock: no big clock, the small one stays, the message shows."
                  if st["time"] is None and st["smallClock"] else "With GNOME's clock the big clock still shows.")
        elif name == "thin":
            c.add(bool(st["time"]), f"The thin clock shows ({st['time']}).")
        a, mean, spread, late = backdrop_shot(sh, st, f"login-g{GNOME}-{name}-userlist", 4)
        c.add(mean > 4, f"{what}: the glass shows a picture (brightness {mean:.1f}, spread {spread:.1f}).{late}",
              picture(f"{name}-userlist", a))
        if name in ("thin", "glow"):
            show_prompt(sh)
            p = shot(sh, f"login-g{GNOME}-{name}-prompt")
            c.add(True, f"{what}, password prompt.", picture(f"{name}-prompt", p))
        if name == "system":
            show_prompt(sh)
            st = state(sh)
            c.add(st["card"] is None, "Without the card setting, no card behind the prompt.")
    # Light style: GDM shows a light login screen when the greeter's colour scheme asks for one. Ubuntu's
    # GDM theme has no light sheet, so GNOME's own light sheet stands in (test only).
    SWITCH.on({})
    restart(sh)
    sh.eval("""const {Gio, St} = imports.gi; Main.sessionMode.stylesheetName = 'gnome-shell.css';
     new Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).set_string('color-scheme', 'prefer-light'); 1""")
    time.sleep(3)
    variant = sh.eval("Main.getStyleVariant()")
    st = state(sh)
    colour = sh.json(f"""const l = {DIALOG}._userList._items.get('dino').get_first_child?.() ?? null;
     const lab = []; const w = a => {{ if (a instanceof imports.gi.St.Label && a.mapped) lab.push(a); a.get_children().forEach(w); }};
     w({DIALOG}._userList); const c = lab[0]?.get_theme_node().get_foreground_color();
     return c ? [c.red, c.green, c.blue] : null;""")
    a = shot(sh, f"login-g{GNOME}-light-userlist")
    c.add(variant == "light" and str(STYLE) in st["styles"] and colour and min(colour) >= 240,
          f"Light style ({variant}): our stylesheet is in the new theme and names read white on the glass ({colour})."
          if colour and min(colour) >= 240 else f"Light style: names are drawn in {colour}, not white.", picture("light-userlist", a))
    show_prompt(sh)
    p = shot(sh, f"login-g{GNOME}-light-prompt")
    c.add(True, "Light style, password prompt.", picture("light-prompt", p))
    sh.eval("new imports.gi.Gio.Settings({schema_id: 'org.gnome.desktop.interface'}).reset('color-scheme'); 1")
    return c


def check_contrast(lane: Lane) -> Check:
    c = Check("contrast", "High contrast: no glass", "With high contrast on, nothing of ours shows; it follows the "
              "setting live, both ways.")
    sh = lane.sh
    SWITCH.on({})
    restart(sh)
    a11y = "new imports.gi.Gio.Settings({schema_id: 'org.gnome.desktop.a11y.interface'})"
    sh.eval(f"{a11y}.set_boolean('high-contrast', true); 1")
    gone = sh.wait_for("return !Main.screenShield._lockDialogGroup.get_children().some(k => k.name === 'fedora-glass-login');", 10)
    time.sleep(2)
    st = state(sh)
    a = shot(sh, f"login-g{GNOME}-high-contrast")
    c.add(gone and str(STYLE) not in st["styles"] and st["smallClock"] is True,
          "High contrast on: no layer, no stylesheet, GNOME's own clock." if gone and str(STYLE) not in st["styles"]
          else f"High contrast on, but ours is still there ({st['children']}, {st['styles']}).", picture("high-contrast", a))
    sh.eval(f"{a11y}.set_boolean('high-contrast', false); 1")
    back = sh.wait_for("return Main.screenShield._lockDialogGroup.get_children().some(k => k.name === 'fedora-glass-login');", 10)
    c.add(back, "High contrast off again: the glass comes back." if back else "The glass did not come back after high contrast.")
    sh.eval(f"{a11y}.reset('high-contrast'); 1")
    return c


def check_safe(lane: Lane) -> Check:
    c = Check("safe", "A start that never finished: no glass",
              "With a 'starting' note for this look already there (the last start crashed), the add-on draws nothing "
              "and says safe; it stays safe at the next start in the same boot.")
    sh = lane.sh
    # First a greeter without the add-on: a greeter with it writes its own note as it shuts
    # down, which would overwrite the one put there below.
    SWITCH.off()
    restart(sh)
    SWITCH.on({})
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    NOTE.parent.mkdir(parents=True, exist_ok=True)
    NOTE.write_text(json.dumps({"v": 1, "token": SWITCH.token, "boot": boot, "phase": "starting", "verified": ""}))
    shutil.chown(NOTE, GREETER, GREETER)
    shutil.chown(NOTE.parent, GREETER, GREETER)
    restart(sh)
    st = state(sh)
    n = wait_note("safe", 5)
    c.add(st["layer"] == -1 and n.get("phase") == "safe", "Nothing drawn, the note says safe."
          if st["layer"] == -1 and n.get("phase") == "safe" else f"Drawn anyway ({st['layer']}) or note {n}.")
    c.add(show_prompt(sh), "The plain login screen works: the password prompt shows.")
    restart(sh)
    st = state(sh)
    c.add(st["layer"] == -1 and note().get("phase") == "safe", "The next start in the same boot stays safe.")
    NOTE.unlink(missing_ok=True)
    return c


def check_broken(lane: Lane) -> Check:
    c = Check("broken", "A broken look.json: no glass", "look.json with a value out of range: nothing drawn, the "
              "note says error, GNOME's login screen is intact and works.")
    sh = lane.sh
    SWITCH.on({})
    look = json.loads(LOOK.read_text())
    look["blur"] = 500
    look["accent"] = "#3584e4; } * { color: red"
    LOOK.write_text(json.dumps(look))
    NOTE.unlink(missing_ok=True)
    mark = lane.ctx.log_lines()
    restart(sh)
    st = state(sh)
    n = wait_note("error", 5)
    c.add(st["layer"] == -1 and n.get("phase") == "error" and str(STYLE) not in st["styles"],
          "Nothing drawn, no stylesheet, the note says error." if st["layer"] == -1 and n.get("phase") == "error"
          else f"layer {st['layer']}, note {n}.")
    c.add(show_prompt(sh), "The plain login screen works: the password prompt shows.")
    sh.eval(f"{DIALOG}._authPrompt._entry.grab_key_focus(); 1")
    t = typed(sh)
    c.add(t["text"] == "Glass 42", f"Typing reaches the password field ({t['text']!r}).")
    log = [line for line in lane.ctx.log.read_text(errors="replace").splitlines()[mark:] if "look.json refused" in line]
    c.add(bool(log), "The log says why: " + (log[0][-120:] if log else "nothing."))
    return c


def check_screens(lane: Lane) -> Check:
    c = Check("screens", "Two screens at 125 %", "Two screens side by side at 125 %: a sheet on each, in place.")
    sh = lane.sh
    SWITCH.on({})
    restart(sh, monitors=2)
    r = subprocess.run(["python3", str(Path(__file__).parent / "scale.py"), "1.25"], capture_output=True, text=True,
                       env=os.environ, timeout=60)
    c.info(f"Scaling: {(r.stdout + r.stderr).strip()[:200]}")
    time.sleep(4)
    sh.measure_scale()
    st = state(sh)
    fit = len(st["sheets"]) == len(st["monitors"]) == 2 and all(
        s and abs(s[0] - m[0]) < 2 and abs(s[2] - m[2]) < 2 for s, m in zip(sorted(st["sheets"]), sorted(st["monitors"])))
    a = shot(sh, f"login-g{GNOME}-two-screens")
    c.add(fit, f"A sheet on each screen, in place: {st['sheets']} on {st['monitors']}." if fit else
          f"The sheets do not match the screens: {st['sheets']} on {st['monitors']}.", picture("two-screens", a))
    ok, why = seam_ok(a, sh, st)
    c.add(ok, f"No stripe along the seam: {why}." if ok else f"A stripe along the seam: {why}.")
    c.add(show_prompt(sh), "The password prompt shows.")
    p = shot(sh, f"login-g{GNOME}-two-screens-prompt")
    c.add(True, "Two screens, password prompt.", picture("two-screens-prompt", p))
    ok, why = seam_ok(p, sh, st)
    c.add(ok, f"No stripe along the seam with the prompt: {why}." if ok else f"A stripe along the seam with the prompt: {why}.")
    # One wide picture spanned over both screens: it goes on across the seam.
    wide = OUT / "wide.png"
    make_wide(wide)
    SWITCH.on({"fit": "spanned"}, picture=wide)
    restart(sh, monitors=2)
    subprocess.run(["python3", str(Path(__file__).parent / "scale.py"), "1.25"], capture_output=True, text=True,
                   env=os.environ, timeout=60)
    time.sleep(4)
    sh.measure_scale()
    st = state(sh)
    a = shot(sh, f"login-g{GNOME}-two-screens-spanned")
    ok, why = spanned_ok(a, sh, st)
    c.add(ok, f"Spanned: the picture goes on across the seam ({why})." if ok else f"Spanned: {why}.",
          picture("two-screens-spanned", a))
    SWITCH.on({})
    restart(sh, monitors=1)
    return c


def prompt_margin() -> int | None:
    """The room the add-on's stylesheet puts above GNOME's prompt (px); None: left to GNOME."""
    m = re.search(r"prompt-layout \{[^}]*margin-top: (\d+)px", STYLE.read_text() if STYLE.exists() else "")
    return int(m.group(1)) if m else None


def check_room(lane: Lane) -> Check:
    c = Check("room", "A short screen, a long prompt, Large Text",
              "At 125 % (a laptop) the big clock still fits above the card. A prompt that grows too long for the "
              "screen gets GNOME's own place back and stays on the screen. Large Text is followed.")
    sh = lane.sh
    mark = lane.ctx.log_lines()
    SWITCH.on({})
    restart(sh, monitors=1)
    r = subprocess.run(["python3", str(Path(__file__).parent / "scale.py"), "1.25"], capture_output=True, text=True,
                       env=os.environ, timeout=60)
    c.info(f"Scaling: {(r.stdout + r.stderr).strip()[:200]}")
    time.sleep(4)
    sh.measure_scale()
    st, k = state(sh), sh.json(CARD_JS)
    top, card, (_, sy, _, sh_) = k["top"], k["card"], k["screen"]
    gap = card[1] - (top[1] + top[3]) if top and card else -1
    ok = st["smallClock"] is False and bool(st["time"]) and gap >= 24
    c.add(ok, f"On a {k['screen'][2]:.0f} x {sh_:.0f} screen the big clock shows above the user list's card "
          f"({gap:.0f} px between them)." if ok else
          f"On a short screen the big clock does not stand above the user list: clock {top}, card {card}, "
          f"small clock shown {st['smallClock']}.")
    c.add(show_prompt(sh), "The password prompt shows.")
    sh.eval(CLEAR_MESSAGE_JS)
    time.sleep(1.2)
    hug(c, sh, "on the short screen", middle=False)
    st, k = state(sh), sh.json(CARD_JS)
    top, card, prompt = k["top"], k["card"], k["prompt"]
    gap = card[1] - (top[1] + top[3]) if top and card else -1
    under = sy + sh_ - (prompt[1] + prompt[3])
    margin = prompt_margin()
    ok = st["smallClock"] is False and gap >= 24 and under >= 8 and margin is not None
    a = shot(sh, f"login-g{GNOME}-short-prompt")
    c.add(ok, f"The prompt stands under the big clock ({gap:.0f} px between the clock and the card), and GNOME's room "
          f"for its messages ends {under:.0f} px above the screen's bottom." if ok else
          f"The prompt on the short screen: {gap:.0f} px between the clock and the card, {under:.0f} px under GNOME's "
          f"prompt, room above it {margin}, small clock shown {st['smallClock']}.", picture("short-prompt", a))
    sh.eval(SET_ERROR_JS)
    time.sleep(1.5)
    hug(c, sh, "on the short screen with GNOME's message after a wrong password", message=True)
    k = sh.json(CARD_JS)
    under = sy + sh_ - (k["card"][1] + k["card"][3]) if k["card"] else -1
    c.add(under >= 0, f"With that message the card ends {under:.0f} px above the screen's bottom." if under >= 0 else
          f"With that message the card ends {-under:.0f} px below the screen's bottom.")
    # A prompt that grows long must stay on the screen. Where GNOME fixes its top (GNOME 51 and
    # later) it would end below the screen with our room above it: GNOME's own, higher place comes
    # back. Where GNOME centres it (GNOME 50) it moves up by itself as it grows.
    fixed = sh.json(f"return typeof {DIALOG}._getFixedTopActorAllocation === 'function';")
    before = k["prompt"][1]
    sh.eval(LONG_MESSAGE_JS)
    time.sleep(2.5)
    st, k = state(sh), sh.json(CARD_JS)
    prompt, card = k["prompt"], k["card"]
    under = sy + sh_ - (prompt[1] + prompt[3])
    on_screen = bool(card) and card[1] >= sy and card[1] + card[3] <= sy + sh_
    back = prompt_margin() is None
    ok = (back or not fixed) and prompt[1] < before and under >= 0 and on_screen and len(st["styles"]) == 1
    how = "gets GNOME's own place back" if back else "moves up as it grows (this GNOME centres it)"
    a = shot(sh, f"login-g{GNOME}-long-prompt")
    c.add(ok, f"A prompt with {LONG_LINES} lines under the field {how}: its top goes from {before:.0f} to "
          f"{prompt[1]:.0f} px, it ends {under:.0f} px above the screen's bottom, and the card is around all of it."
          if ok else
          f"A prompt with {LONG_LINES} lines under the field: room above it {prompt_margin()}, top {before:.0f} to "
          f"{prompt[1]:.0f} px, {under:.0f} px above the bottom, card {card}, stylesheets {st['styles']}.",
          picture("long-prompt", a))
    # The big clock has no room now: the small one stands in, and it stays so (nothing comes and goes).
    seen = []
    for _ in range(4):
        s2 = state(sh)
        seen.append((s2["smallClock"], bool(s2["top"] and s2["top"][3] > 1)))
        time.sleep(0.5)
    # Only the field's cursor blinks (a clock coming and going would draw every frame).
    idle = rc.timed(lane.ctx, 4)
    ok = all(v == (True, False) for v in seen) and idle["frames"] <= 40
    c.add(ok, f"The big clock makes room and the panel's small clock stands in; it stays so, and nothing but the "
          f"field's cursor moves ({idle['frames']} frames in {idle['seconds']:.0f} s)." if ok else
          f"With the long prompt the clocks do not settle: small clock shown and big clock shown {seen}, "
          f"{idle['frames']} frames in {idle['seconds']:.0f} s.")
    sh.eval(CLEAR_MESSAGE_JS)
    time.sleep(1)
    c.add(back_to_list(sh), "Back to the user list.")
    # Smaller still (150 %): the prompt has less to spare under it, and must still keep its place.
    restart(sh, monitors=1)
    subprocess.run(["python3", str(Path(__file__).parent / "scale.py"), "1.5"], capture_output=True, text=True,
                   env=os.environ, timeout=60)
    time.sleep(4)
    sh.measure_scale()
    shown = show_prompt(sh)
    sh.eval(SET_ERROR_JS)
    time.sleep(1.5)
    st, k = state(sh), sh.json(CARD_JS)
    top, card, (_, sy, _, sh_) = k["top"], k["card"], k["screen"]
    gap = card[1] - (top[1] + top[3]) if top and card and top[3] > 1 else -1
    under = sy + sh_ - (card[1] + card[3]) if card else -1
    ok = shown and prompt_margin() is not None and st["smallClock"] is False and gap >= 24 and under >= 0
    a = shot(sh, f"login-g{GNOME}-shorter-prompt")
    c.add(ok, f"On a {k['screen'][2]:.0f} x {sh_:.0f} screen the prompt keeps its place under the big clock "
          f"({gap:.0f} px between them), and with GNOME's message the card ends {under:.0f} px above the screen's "
          "bottom." if ok else
          f"On a {k['screen'][2]:.0f} x {sh_:.0f} screen: prompt shown {shown}, room above it {prompt_margin()}, "
          f"{gap:.0f} px between the clock and the card, {under:.0f} px under the card, small clock shown "
          f"{st['smallClock']}.", picture("shorter-prompt", a))
    sh.eval(CLEAR_MESSAGE_JS)
    # Large Text switched on at the login screen itself (its accessibility menu): followed at once.
    SWITCH.on({})
    restart(sh, monitors=1)
    usual = prompt_margin()
    try:
        sh.eval(TEXT_SCALE_JS % "1.25")
        time.sleep(4)
        st = state(sh)
        large = prompt_margin()
        ok = st["opacity"] == 255 and large is not None and large != usual
        c.add(ok, f"Large Text switched on: the glass is built again for it (the room above the prompt goes from "
              f"{usual} to {large} px)." if ok else
              f"Large Text switched on: glass opacity {st['opacity']}, room above the prompt {usual} then {large}.")
        hug_list(c, sh, "with Large Text")
        c.add(show_prompt(sh), "The password prompt shows with Large Text.")
        sh.eval(CLEAR_MESSAGE_JS)
        time.sleep(1.2)
        hug(c, sh, "with Large Text")
        a = shot(sh, f"login-g{GNOME}-large-text")
        c.add(True, "The password prompt with Large Text.", picture("large-text", a))
        sh.eval(TEXT_SCALE_JS % "1.0")
        time.sleep(4)
        hug(c, sh, "with Large Text off again")
        c.add(prompt_margin() == usual, f"Large Text off again: the room above the prompt is {usual} px again."
              if prompt_margin() == usual else f"Large Text off again: the room above the prompt is {prompt_margin()}, not {usual}.")
    finally:
        sh.eval(TEXT_SCALE_JS % "1.0")
    errs = lane.errors_since(mark)
    c.add(not errs, "No Fedora Glass errors in GNOME Shell's log." if not errs else
          f"{len(errs)} Fedora Glass errors in the log, first: {errs[0][-200:]}")
    SWITCH.on({})
    restart(sh, monitors=1)
    return c


def check_users(lane: Lane) -> Check:
    c = Check("users", "A PC with several users",
              "A longer list of users grows downward from where the password card begins, with the clock and the "
              "message above it where they are; picking a user moves nothing but the card's lower edge; the list "
              "stays on the screen.")
    sh = lane.sh
    SWITCH.on({"message": MESSAGE})
    count = len(MORE_USERS) + 1
    try:
        set_users(count)
        mark = lane.ctx.log_lines()
        restart(sh)
        n = sh.json(USERS_JS)
        c.add(n == count, f"The login screen lists {n} users." if n == count else
              f"The login screen lists {n} users, not {count}.")
        st, k = state(sh), sh.json(CARD_JS)
        card, rows, top = k["card"], k["list"], k["top"]
        sx, sy, sw, sh_ = k["screen"]
        if not card or not rows or not top:
            c.add(False, f"With {count} users: card {card}, list {rows}, clock {top}.")
            return c
        pads = [rows[0] - card[0], rows[1] - card[1], card[0] + card[2] - rows[2], card[1] + card[3] - rows[3]]
        ok = all(abs(v - CARD_PAD) <= 2 for v in pads) and abs(card[0] + card[2] / 2 - (sx + sw / 2)) <= 2
        c.add(ok, f"One glass card around all {count} names and \"Not listed?\", {CARD_PAD} px around them, "
              f"{card[2]:.0f} x {card[3]:.0f} px." if ok else
              f"The card does not sit around the {count} users: padding {[round(v) for v in pads]} "
              f"(card {[round(v) for v in card]}, list {[round(v) for v in rows]}).")
        ok = st["messageShown"] and st["smallClock"] is False and top[1] + top[3] + 24 <= card[1] + 2
        c.add(ok, "The big clock and the message both show above the list, clear of its card "
              f"({card[1] - top[1] - top[3]:.0f} px between them)." if ok else
              f"The clock or the message gave way to the list: message {st['messageShown']}, small clock "
              f"{st['smallClock']}, clock {[round(v) for v in top]}, card {[round(v) for v in card]}.")
        clock_place(c, sh, st, f"with {count} users")
        ok = card[1] + card[3] <= sy + sh_ - 8 and card[1] >= sy
        c.add(ok, f"The whole list is on the screen ({sy + sh_ - card[1] - card[3]:.0f} px left under its card)."
              if ok else f"The list's card leaves the screen: {[round(v) for v in card]} on {k['screen']}.")
        a = shot(sh, f"login-g{GNOME}-users")
        c.add(True, f"The user list with {count} users.", picture("users", a))
        c.add(show_prompt(sh), "A user picked: GNOME's password prompt shows.")
        p = sh.json(CARD_JS)
        hug(c, sh, f"with {count} users")
        if p["card"] and p["top"]:
            ok = abs(p["card"][1] - card[1]) <= 2 and all(abs(x - y) <= 1 for x, y in zip(p["top"], top))
            c.add(ok, "The list's card begins where the password card begins, and the clock stands still: picking "
                  f"a user only shortens the card (both begin at {card[1]:.0f} px)." if ok else
                  f"Picking a user makes the screen jump: the list's card begins at {card[1]:.0f} px, the password "
                  f"card at {p['card'][1]:.0f} px; clock {[round(v) for v in top]} then {[round(v) for v in p['top']]}.")
        c.add(back_to_list(sh), "Back to the user list.")
        b = sh.json(CARD_JS)
        ok = bool(b["card"]) and all(abs(x - y) <= 2 for x, y in zip(b["card"], card))
        c.add(ok, "Back at the list, its card is where it was." if ok else
              f"Back at the list its card moved: {[round(v) for v in card]} then {b['card'] and [round(v) for v in b['card']]}.")
        errs = lane.errors_since(mark)
        c.add(not errs, "No Fedora Glass errors in GNOME Shell's log." if not errs else
              f"{len(errs)} Fedora Glass errors in the log, first: {errs[0][-200:]}")
    finally:
        set_users(1)
    # One user again: the short list goes back to the middle of the screen.
    restart(sh)
    n = sh.json(USERS_JS)
    c.add(n == 1, "One user again." if n == 1 else f"{n} users are still listed after the extra ones were removed.")
    hug_list(c, sh, "with one user again")
    return c


def check_leave(lane: Lane) -> Check:
    c = Check("leave", "Logging in: the card and the clock leave with GNOME's dialog",
              "GNOME fades its login dialog out once somebody has logged in. The card and the clock go with it "
              "(no empty card, no clock left standing), the frosted picture stays until the desktop comes, and "
              "everything comes back should the session not start.")
    sh = lane.sh
    SWITCH.on({"message": MESSAGE})
    mark = lane.ctx.log_lines()
    restart(sh)
    st = state(sh)
    was = sh.json(PARTS_JS)
    full = was["card"] == 255 and was["top"] == 255 and was["layer"] == 255 and was["sheets"] and all(v == 255 for v in was["sheets"])
    c.add(full, "At rest everything of ours is fully there." if full else f"At rest: {was}.")
    before = shot(sh, f"login-g{GNOME}-leave-before")
    try:
        sh.eval(FADE_JS % 0)
        gone = sh.wait_for(f"return {DIALOG}.opacity === 0;", 5)
        time.sleep(0.5)
        now = sh.json(PARTS_JS)
        ok = gone and now["card"] == 0 and now["top"] == 0
        c.add(ok, "GNOME's dialog faded out: the card and the clock went with it." if ok else
              f"GNOME's dialog faded out, but ours stayed: {now}.")
        ok = now["layer"] == 255 and now["sheets"] and all(v == 255 for v in now["sheets"])
        a = shot(sh, f"login-g{GNOME}-leave")
        mean, spread = backdrop_stats(a, sh, st)
        ok = ok and mean > 6 and spread > 1.5
        c.add(ok, f"The frosted picture stays (brightness {mean:.1f}, spread {spread:.1f})." if ok else
              f"The frosted picture did not stay: {now}, brightness {mean:.1f}, spread {spread:.1f}.", picture("leave", a))
        if st["card"]:
            diff = float(np.abs(region(a, sh, st["card"]).astype(np.int16) - region(before, sh, st["card"]).astype(np.int16)).mean())
            c.add(diff > 1.5, f"Where the card stood only the picture is left (the pixels there changed by {diff:.1f})."
                  if diff > 1.5 else f"The card can still be seen where it stood (the pixels there changed by {diff:.1f}).")
    finally:
        sh.eval(FADE_JS % 255)
    back = sh.wait_for(f"return {DIALOG}.opacity === 255;", 5)
    time.sleep(0.5)
    now = sh.json(PARTS_JS)
    ok = back and now["card"] == 255 and now["top"] == 255 and now["layer"] == 255
    c.add(ok, "The session did not start, GNOME brings its dialog back: the card and the clock are back too."
          if ok else f"After GNOME's dialog came back: {now}.")
    hug_list(c, sh, "after the dialog came back")
    errs = lane.errors_since(mark)
    c.add(not errs, "No Fedora Glass errors in GNOME Shell's log." if not errs else
          f"{len(errs)} Fedora Glass errors in the log, first: {errs[0][-200:]}")
    return c


def row_lum(a: np.ndarray, sh: Shell, st: dict) -> np.ndarray:
    """Brightness along the middle third of the screens' height, per physical px column."""
    my, mh = st["monitors"][0][1], st["monitors"][0][3]
    y0, y1 = int((my + mh * 0.55) * sh.scale), int((my + mh * 0.75) * sh.scale)
    return lgqa.lum(a[y0:y1]).mean(axis=0)


def seam_ok(a: np.ndarray, sh: Shell, st: dict) -> tuple[bool, str]:
    """No stripe: next to the seam the brightness changes no faster than a little farther in."""
    seam = int(round(st["monitors"][1][0] * sh.scale))
    lum = row_lum(a, sh, st)
    near_l, far_l = abs(lum[seam - 2] - lum[seam - 60]), abs(lum[seam - 60] - lum[seam - 118])
    near_r, far_r = abs(lum[seam + 60] - lum[seam + 1]), abs(lum[seam + 118] - lum[seam + 60])
    ok = near_l <= far_l + 2.0 and near_r <= far_r + 2.0
    return ok, (f"in the last 60 px before it the brightness changes {near_l:.1f} (60 px farther in {far_l:.1f}), "
                f"after it {near_r:.1f} ({far_r:.1f})")


def make_wide(path: Path) -> None:
    """A picture as wide as both screens: red on the left turning blue on the right, smoothly."""
    from PIL import Image
    w, h = 3072, 864
    t = np.linspace(0, 1, w)[None, :, None]
    left, right = np.array([200, 40, 30]), np.array([30, 60, 210])
    img = np.broadcast_to(left + (right - left) * t, (h, w, 3)).astype(np.uint8)
    Image.fromarray(img).save(path)
    os.chmod(path, 0o644)


def spanned_ok(a: np.ndarray, sh: Shell, st: dict) -> tuple[bool, str]:
    """The left screen shows the red half, the right one the blue half, and no jump at the seam."""
    seam = int(round(st["monitors"][1][0] * sh.scale))
    my, mh = st["monitors"][0][1], st["monitors"][0][3]
    y0, y1 = int((my + mh * 0.55) * sh.scale), int((my + mh * 0.75) * sh.scale)
    band = a[y0:y1].astype(float).mean(axis=0)[:, :3]
    red = band[:, 0] - band[:, 2]
    left, right = red[int(seam * 0.1):int(seam * 0.4)].mean(), red[seam + int(seam * 0.6):seam + int(seam * 0.9)].mean()
    jump = abs(red[seam - 3] - red[seam + 3])
    step = abs(red[seam - 63] - red[seam - 3]) / 10
    ok = left > 10 and right < -10 and jump <= step + 3
    return ok, (f"red minus blue {left:.0f} on the left screen, {right:.0f} on the right, a step of {jump:.1f} "
                f"over the seam where 6 px elsewhere change {step:.1f}")


def check_picture(lane: Lane) -> Check:
    c = Check("picture", "A picture that will not load: never black",
              "A picture that does not decode, or that never finishes loading: no black login screen; the glow "
              "instead, the note still ok.")
    sh = lane.sh
    for name, spoil, what in (("garbage", "garbage", "A picture that does not decode"),
                              ("stuck", "fifo", "A picture that never finishes loading")):
        SWITCH.on({})
        pic = next(CONF.glob("picture.*"))
        pic.unlink()
        if spoil == "garbage":
            # JPEG's first bytes (as the helper checks), then nonsense.
            pic.write_bytes(b"\xff\xd8\xff\xe0" + secrets.token_bytes(4000))
        else:
            os.mkfifo(pic)   # reading it waits for ever
        os.chmod(pic, 0o644)
        mark = lane.ctx.log_lines()
        restart(sh)
        time.sleep(4 if spoil == "fifo" else 0)
        st = state(sh)
        a, mean, spread, _ = backdrop_shot(sh, st, f"login-g{GNOME}-picture-{name}", 0)
        log = [line for line in lane.ctx.log.read_text(errors="replace").splitlines()[mark:] if "the glow instead" in line]
        n = wait_note("ok", 10)
        ok = mean > 4 and bool(log) and len(st["sheets"]) == 1 and all(st["sheets"]) and n.get("phase") == "ok"
        c.add(ok, f"{what}: the glow shows (brightness {mean:.1f}), the note says ok, the log says why: "
              f"{log[0][-90:] if log else ''}" if ok else
              f"{what}: brightness {mean:.1f}, sheets {st['sheets']}, note {n.get('phase')}, log {log[:1]}.",
              picture(f"picture-{name}", a))
        c.add(show_prompt(sh), f"{what}: the password prompt works.")
        if spoil == "fifo":
            pic.unlink()
    SWITCH.on({})
    restart(sh)
    return c


def check_crashes(lane: Lane) -> Check:
    c = Check("crashes", "Crashes later than 2 s: safe after two",
              "GNOME Shell killed (SIGKILL, as in a crash) twice in a row after the glass started fine: the third start "
              "draws nothing and the note says safe. One kill and then a clean stop: the glass again.")
    sh = lane.sh
    SWITCH.off()
    restart(sh)
    SWITCH.on({})
    restart(sh)
    seen = []
    for i in range(3):
        n = wait_note("ok", 10)
        st = state(sh)
        seen.append((st["layer"], n.get("phase")))
        if i < 2:
            restart(sh, kill=True)
    ok = seen[0] == (0, "ok") and seen[1] == (0, "ok") and seen[2][0] == -1 and note().get("phase") == "safe"
    c.add(ok, f"Killed twice after it reached ok: the third start draws nothing and says safe ({seen})." if ok
          else f"Not safe after two kills: {seen}, note {note().get('phase')}.")
    c.add(show_prompt(sh), "The plain login screen works: the password prompt shows.")
    # A new look (a new trial), then one kill and a clean stop: no loop.
    SWITCH.off()
    restart(sh)
    SWITCH.on({})
    restart(sh)
    wait_note("ok", 10)
    restart(sh, kill=True)
    a = state(sh)["layer"]
    wait_note("ok", 10)
    restart(sh)
    b = state(sh)["layer"]
    n = wait_note("ok", 10)
    ok = a == 0 and b == 0 and n.get("phase") == "ok"
    c.add(ok, "One kill, then a clean stop: the glass after each (no loop)." if ok else
          f"After one kill and a clean stop: layer {a} then {b}, note {n.get('phase')}.")
    return c


ALL = {"plain": check_plain, "glass": check_glass, "disable": check_disable, "looks": check_looks,
       "contrast": check_contrast, "safe": check_safe, "broken": check_broken, "screens": check_screens,
       "room": check_room, "users": check_users, "leave": check_leave, "picture": check_picture,
       "crashes": check_crashes}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(ALL))
    ap.add_argument("--update-references", action="store_true")
    args = ap.parse_args()
    # As root's login shell has it (docker exec gives 0000): files the checks make are not world-writable.
    os.umask(0o022)
    lgqa.SHOTS.mkdir(parents=True, exist_ok=True)
    os.chmod(lgqa.SHOTS, 0o777)
    sh = Shell()
    try:
        sh.wait_for(READY_JS, 60)
        sh.measure_scale()
    except ShellError as e:
        print(f"The login screen did not start: {e}", file=sys.stderr)
        return 2
    lane = Lane(sh, args.update_references)
    version = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", Path("/src/fedoraglass/__init__.py").read_text()).group(1)
    shell = subprocess.run(["gnome-shell", "--version"], capture_output=True, text=True).stdout.split()[-1]
    meta = {"version": version, "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
            "desktop": f"the GDM login screen, GNOME Shell {shell} in gdm mode"}
    checks = []
    for key in args.only.split(","):
        print(f"== {key}", flush=True)
        try:
            checks.append(ALL[key](lane))
        except Exception as e:  # a broken step must fail the check, never pass it
            traceback.print_exc()
            ch = Check(key, ALL[key].__name__.replace("check_", "").title(), "")
            ch.crashed = f"{type(e).__name__}: {str(e)[:300]}"
            checks.append(ch)
    SWITCH.off()
    ok = rc.write_report(checks, meta)
    print((rc.REPORT / "report.md").read_text())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
