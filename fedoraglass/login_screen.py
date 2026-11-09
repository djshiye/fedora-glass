#!/usr/bin/python3 -IS
"""Glass on the login screen (GDM), opt in, with a one-click undo.

GDM runs its own GNOME Shell as the gdm user, with no extensions and no access to your
wallpaper, so the login screen can only change through GNOME Shell's own style sheet,
gdm.css, which sits inside a system file (gnome-shell-theme.gresource). Changing it needs
root, so the app runs this file through pkexec, which asks for your password.

What it does, as root:
  apply   copies the original file to /var/lib/liquid-glass, then writes a copy of it where
          only the login screen's style sheet differs: a block of Fedora Glass rules added at
          its end. That is gdm.css where there is one (Ubuntu), else gnome-shell-dark.css and
          gnome-shell-light.css (upstream GNOME 49 and later, so Fedora). Every other file
          inside is checked to be byte for byte the same before the copy goes in.
  undo    puts the original back, only if the file is still the one this wrote.
  status  says whether the glass is on (no root needed).

It takes three colours or numbers, never a path or any other text, and only ever writes
the file GNOME Shell reads for the login screen, its backup and a small state file. A
gnome-shell update replaces the file and so turns the glass off again by itself; the app
then says so. Reinstalling gnome-shell (dnf, apt or pacman) always brings the original back too.

Runs with python3 -I -S (no environment, no user or site packages): standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SHELL_DIR = "/usr/share/gnome-shell"
STATE_DIR = "/var/lib/liquid-glass"
BACKUP = "login-screen-original.gresource"
STATE = "login-screen.json"
GDM_CSS = "/org/gnome/shell/theme/gdm.css"
# Upstream GNOME 49+ (Fedora) has no gdm.css: the login screen reads the same dark or
# light style sheet as the desktop. Ubuntu still adds gdm.css.
SHARED_CSS = ("/org/gnome/shell/theme/gnome-shell-dark.css", "/org/gnome/shell/theme/gnome-shell-light.css")
GRESOURCE = "/usr/bin/gresource"
COMPILE = "/usr/bin/glib-compile-resources"
RESTORECON = "/usr/sbin/restorecon"
MARK_START = "/* Fedora Glass login screen: start */"
MARK_END = "/* Fedora Glass login screen: end */"
MAX_SIZE = 64 << 20                      # the real file is under 1 MB

HEX = re.compile(r"#[0-9a-fA-F]{6}")
RESOURCE_PATH = re.compile(r"/org/gnome/shell/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*")


class LoginScreenError(Exception):
    """Something is not as expected; nothing was changed."""


# ---- the look ----------------------------------------------------------------------

def reinstall_hint(os_release: str = "/etc/os-release", shell_dir: str = SHELL_DIR) -> str:
    """The command that puts GNOME's own login screen file back, for this Linux."""
    ids = []
    try:
        with open(os_release, encoding="utf-8", errors="replace") as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key in ("ID", "ID_LIKE"):
                    ids += value.strip('"\'').lower().split()
    except OSError:
        pass
    if "ubuntu" in ids or "debian" in ids:
        # Ubuntu's login screen file can come from the Yaru theme package: ask dpkg.
        pkg = "gnome-shell-common"
        try:
            real = os.path.realpath(target(shell_dir))
            r = subprocess.run(["/usr/bin/dpkg-query", "-S", real], capture_output=True, text=True, timeout=10)
            name = r.stdout.split(":")[0].strip() if r.returncode == 0 else ""
            if re.fullmatch(r"[a-z0-9][a-z0-9.+-]+", name):
                pkg = name
        except (OSError, LoginScreenError, subprocess.SubprocessError):
            pass
        return f"sudo apt install --reinstall {pkg}"
    if "arch" in ids:
        return "sudo pacman -S gnome-shell"
    return "sudo dnf reinstall gnome-shell"

def _rgb(hex6: str) -> tuple[int, int, int]:
    return int(hex6[1:3], 16), int(hex6[3:5], 16), int(hex6[5:7], 16)


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> str:
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def check_values(accent: str, tint: str, frost: float) -> tuple[str, str, float]:
    if not (isinstance(accent, str) and HEX.fullmatch(accent)):
        raise LoginScreenError("the accent colour must look like #3584e4")
    if not (isinstance(tint, str) and HEX.fullmatch(tint)):
        raise LoginScreenError("the tint colour must look like #3584e4")
    try:
        frost = float(frost)
    except (TypeError, ValueError):
        raise LoginScreenError("frost must be a number from 0 to 1") from None
    if not 0.0 <= frost <= 1.0:
        raise LoginScreenError("frost must be a number from 0 to 1")
    return accent.lower(), tint.lower(), round(frost, 3)


def css(accent: str, tint: str, frost: float, shared: bool = False) -> str:
    """The rules added to the login screen's style sheet. Built only from the three checked values.

    The login screen can't see a wallpaper, so the backdrop is a deep glow of the glass
    tint, and the user list, picture, password field and buttons are panes of glass on
    it: a little white that is lighter at the top, a bright rim that is brightest along
    the top edge, and a soft shadow. Text stays GNOME's white, at least 7:1 on every pane.

    After a click on a name there is no box around the prompt (1.5.6 drew one big flat
    card around the picture, the name and the field): the picture floats, the field is
    a glass pill, and the prompt is a little narrower and the picture a little smaller
    than GNOME's, so the whole thing stays compact.

    The login dialog only fills the main screen. Every screen shows #lockDialogGroup,
    which spans them all, so the backdrop lives there and the login dialog stays clear:
    each screen gets the same tint, near black at the top (so the top bar reads) and
    deepening into the glass colour at the bottom. A radial glow would only light the main
    screen, or centre on the seam between two.

    shared: the style sheet is also the desktop's (no gdm.css). Every rule must then match
    only the login screen (all of them sit under .login-dialog, so the desktop's own lock
    screen is never touched), or be one the desktop never shows: the desktop's lock screen
    covers #lockDialogGroup with your wallpaper, so only its colour changes there, from
    GNOME's flat near black to a near-black tint.
    """
    accent, tint, frost = check_values(accent, tint, frost)
    black = (0, 0, 0)
    t = _rgb(tint)
    top = _mix(t, black, 0.90)           # near black at the top, so the top bar reads
    bottom = _mix(t, black, 0.52)        # the glass colour at the bottom of every screen
    pane = 0.07 + 0.07 * frost           # white in each pane: clear glass to frost
    hover = pane + 0.05
    lit = pane + 0.08                    # the top of a pane, where the light falls
    edge = 0.20 + 0.10 * frost           # a bright rim, as on the desktop's glass
    shine = min(0.30, edge + 0.10)       # the rim's top edge catches the most light
    ring = f"st-transparentize({accent}, 0.15)"
    return f"""
{MARK_START}
#lockDialogGroup {{
  background-color: {top};
  background-gradient-direction: vertical;
  background-gradient-start: {top};
  background-gradient-end: {bottom}; }}
.login-dialog {{
  background-color: transparent;
  background-gradient-direction: none; }}
.login-dialog .login-dialog-prompt-layout {{
  width: 23em;
  min-width: 23em;
  padding: 0;
  background-color: transparent;
  border-width: 0;
  box-shadow: none; }}
.login-dialog .login-dialog-user-list-view .login-dialog-user-list .login-dialog-user-list-item,
.login-dialog .login-dialog-not-listed-button,
.login-dialog .login-dialog-auth-list-item {{
  background-color: rgba(255, 255, 255, {pane:.3f});
  background-gradient-direction: vertical;
  background-gradient-start: rgba(255, 255, 255, {lit:.3f});
  background-gradient-end: rgba(255, 255, 255, {pane:.3f});
  border: 1px solid rgba(255, 255, 255, {edge:.3f});
  border-top-color: rgba(255, 255, 255, {shine:.3f});
  border-radius: 18px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28); }}
.login-dialog .login-dialog-user-list-view .login-dialog-user-list .login-dialog-user-list-item:hover,
.login-dialog .login-dialog-not-listed-button:hover,
.login-dialog .login-dialog-auth-list-item:hover {{
  background-gradient-start: rgba(255, 255, 255, {lit + 0.05:.3f});
  background-gradient-end: rgba(255, 255, 255, {hover:.3f}); }}
.login-dialog .login-dialog-user-list-view .login-dialog-user-list .login-dialog-user-list-item:selected,
.login-dialog .login-dialog-user-list-view .login-dialog-user-list .login-dialog-user-list-item:focus {{
  background-gradient-start: rgba(255, 255, 255, {lit + 0.05:.3f});
  background-gradient-end: rgba(255, 255, 255, {hover:.3f});
  border-color: {accent}; }}
.login-dialog .login-dialog-prompt-entry {{
  background-color: rgba(255, 255, 255, {pane:.3f});
  background-gradient-direction: vertical;
  background-gradient-start: rgba(255, 255, 255, {lit:.3f});
  background-gradient-end: rgba(255, 255, 255, {pane:.3f});
  border: 1px solid rgba(255, 255, 255, {edge:.3f});
  border-top-color: rgba(255, 255, 255, {shine:.3f});
  border-radius: 999px;
  padding: 9px 14px;
  min-width: 14em;
  color: #ffffff;
  caret-color: #ffffff;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.30); }}
.login-dialog .login-dialog-prompt-entry:hover {{
  background-gradient-start: rgba(255, 255, 255, {lit + 0.05:.3f});
  background-gradient-end: rgba(255, 255, 255, {hover:.3f}); }}
.login-dialog .login-dialog-prompt-entry:focus {{
  background-gradient-start: rgba(255, 255, 255, {lit + 0.05:.3f});
  background-gradient-end: rgba(255, 255, 255, {hover:.3f});
  border-color: {accent};
  box-shadow: inset 0 0 0 1px {ring} !important; }}
.login-dialog .login-dialog-button.a11y-button, .login-dialog .login-dialog-button.cancel-button,
.login-dialog .login-dialog-button.switch-user-button, .login-dialog .login-dialog-button.login-dialog-auth-menu-button,
.login-dialog .login-dialog-button.login-dialog-session-list-button {{
  background-color: rgba(255, 255, 255, {pane:.3f});
  background-gradient-direction: vertical;
  background-gradient-start: rgba(255, 255, 255, {lit:.3f});
  background-gradient-end: rgba(255, 255, 255, {pane:.3f});
  border: 1px solid rgba(255, 255, 255, {edge:.3f});
  border-top-color: rgba(255, 255, 255, {shine:.3f}); }}
.login-dialog .login-dialog-button.a11y-button:hover, .login-dialog .login-dialog-button.cancel-button:hover,
.login-dialog .login-dialog-button.switch-user-button:hover, .login-dialog .login-dialog-button.login-dialog-auth-menu-button:hover,
.login-dialog .login-dialog-button.login-dialog-session-list-button:hover {{
  background-gradient-start: rgba(255, 255, 255, {lit + 0.05:.3f});
  background-gradient-end: rgba(255, 255, 255, {hover:.3f}); }}
.login-dialog .user-widget .user-icon {{
  background-color: rgba(255, 255, 255, {pane:.3f});
  background-gradient-direction: vertical;
  background-gradient-start: rgba(255, 255, 255, {lit:.3f});
  background-gradient-end: rgba(255, 255, 255, {pane:.3f});
  border: 1px solid rgba(255, 255, 255, {edge:.3f});
  border-top-color: rgba(255, 255, 255, {shine:.3f});
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.32); }}
.login-dialog .user-widget.vertical .user-icon {{
  icon-size: 128px; }}
.login-dialog .user-widget.vertical .user-icon StIcon {{
  padding: 24px; }}
.login-dialog .user-widget.vertical {{
  spacing: 16px; }}
.login-dialog .user-widget.vertical .user-widget-label {{
  margin-bottom: 0.4em; }}
{MARK_END}
"""


# ---- the file ----------------------------------------------------------------------
def target(shell_dir: str = SHELL_DIR) -> str:
    """The file GNOME Shell reads gdm.css from in login-screen mode.

    Upstream GNOME (Fedora, Arch) reads gnome-shell-theme.gresource; Ubuntu adds
    gdm-theme.gresource, a link (through /etc/alternatives) to that file or to its Yaru
    theme's theme/Yaru/gnome-shell-theme.gresource. The file must stay inside shell_dir.
    """
    base = os.path.realpath(shell_dir)
    for name in ("gdm-theme.gresource", "gnome-shell-theme.gresource"):
        p = os.path.join(base, name)
        if os.path.lexists(p):
            real = os.path.realpath(p)
            if not real.startswith(base + os.sep) or not real.endswith(".gresource"):
                raise LoginScreenError(f"{p} points outside {base}")
            return real
    raise LoginScreenError(f"GNOME Shell's theme file is not in {base}")


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _run(*args: str) -> bytes:
    r = subprocess.run(args, capture_output=True, timeout=60, env={"PATH": "/usr/bin:/usr/sbin", "LC_ALL": "C"})
    if r.returncode != 0:
        raise LoginScreenError(f"{os.path.basename(args[0])} failed: {r.stderr.decode(errors='replace')[:300]}")
    return r.stdout


def list_files(path: str) -> list[str]:
    names = _run(GRESOURCE, "list", path).decode().split()
    for n in names:
        if not RESOURCE_PATH.fullmatch(n) or "/../" in n or n.endswith("/.."):
            raise LoginScreenError(f"unexpected name inside the theme file: {n[:80]}")
    sheets(names)
    return sorted(names)


def sheets(names: list[str]) -> list[str]:
    """The style sheets the login screen reads, inside a theme file with these names."""
    if GDM_CSS in names:
        return [GDM_CSS]
    found = [n for n in SHARED_CSS if n in names]
    if not found:
        raise LoginScreenError("the theme file has no style sheet for the login screen")
    return found


def extract(path: str, name: str) -> bytes:
    return _run(GRESOURCE, "extract", path, name)


def strip_block(text: str) -> str:
    """gdm.css without a Fedora Glass block (one left by an older version, say)."""
    i = text.find("\n" + MARK_START)
    if i < 0:
        return text
    j = text.find(MARK_END, i)
    return text[:i] + (text[j + len(MARK_END) + 1:] if j >= 0 else "")


def _check_file(path: str) -> None:
    st = os.lstat(path)
    if not os.path.isfile(path) or os.path.islink(path):
        raise LoginScreenError(f"{path} is not a plain file")
    if st.st_size > MAX_SIZE:
        raise LoginScreenError(f"{path} is unexpectedly large")


def build(original: str, out: str, accent: str, tint: str, frost: float) -> str:
    """Write to out a copy of original whose login screen style sheets end with our block; checked.
    Returns the block."""
    _check_file(original)
    names = list_files(original)
    targets = sheets(names)
    block = css(accent, tint, frost, shared=targets != [GDM_CSS])
    work = tempfile.mkdtemp(prefix="liquid-glass-login-")
    try:
        files = {}
        for n in names:
            data = extract(original, n)
            if n in targets:
                data = (strip_block(data.decode()) + block).encode()
            files[n] = data
            dest = os.path.join(work, "root" + n)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(data)
        xml = ['<?xml version="1.0" encoding="UTF-8"?>', "<gresources>", '  <gresource prefix="/">']
        xml += [f"    <file>{n.lstrip('/')}</file>" for n in names]
        xml += ["  </gresource>", "</gresources>", ""]
        with open(os.path.join(work, "theme.gresource.xml"), "w") as f:
            f.write("\n".join(xml))
        _run(COMPILE, f"--sourcedir={work}/root", f"--target={out}", os.path.join(work, "theme.gresource.xml"))
        # The copy must hold exactly the same files, all the same except the login screen's sheets.
        if list_files(out) != names:
            raise LoginScreenError("the new theme file lists different files")
        for n in names:
            if extract(out, n) != files[n]:
                raise LoginScreenError(f"{n} came out different in the new theme file")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return block


def _write_into(src: str, dest: str) -> None:
    """Copy src over dest atomically. The new file is made inside dest's folder, so it
    gets that folder's owner and SELinux label like the file it replaces."""
    folder = os.path.dirname(dest)
    fd, tmp = tempfile.mkstemp(prefix=".liquid-glass-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f, open(src, "rb") as s:
            shutil.copyfileobj(s, f)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    if os.access(RESTORECON, os.X_OK):
        subprocess.run([RESTORECON, dest], capture_output=True, timeout=30)


def _state(state_dir: str) -> dict:
    try:
        with open(os.path.join(state_dir, STATE)) as f:
            s = json.load(f)
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def block_targets(path: str) -> list[str]:
    return sheets(list_files(path))


def look_id(accent: str, tint: str, frost: float, shared: bool) -> str:
    """What apply() records for these colours with this version's rules."""
    accent, tint, frost = check_values(accent, tint, frost)
    return hashlib.sha256(css(accent, tint, frost, shared=shared).encode()).hexdigest()


def up_to_date(accent: str, tint: str, frost: float, state_dir: str = STATE_DIR) -> bool:
    """Whether the glass on the login screen is the one these colours give with this version
    of Fedora Glass. Glass put on by an older version (no record of its look) is out of date.
    Reads only the state file, so no root is needed."""
    s = _state(state_dir)
    look = s.get("look")
    if not isinstance(look, str):
        return False
    try:
        return look == look_id(accent, tint, frost, shared=bool(s.get("shared")))
    except LoginScreenError:
        return False


def status(shell_dir: str = SHELL_DIR, state_dir: str = STATE_DIR) -> str:
    """"on", "off" or "undone" (a GNOME update replaced the file since it was turned on)."""
    s = _state(state_dir)
    if not s.get("written"):
        return "off"
    try:
        return "on" if sha256(target(shell_dir)) == s["written"] else "undone"
    except (OSError, LoginScreenError):
        return "off"


def apply(accent: str, tint: str, frost: float, shell_dir: str = SHELL_DIR, state_dir: str = STATE_DIR) -> None:
    check_values(accent, tint, frost)
    dest = target(shell_dir)
    _check_file(dest)
    os.makedirs(state_dir, mode=0o755, exist_ok=True)
    backup = os.path.join(state_dir, BACKUP)
    s = _state(state_dir)
    now = sha256(dest)
    if s.get("written") == now and os.path.isfile(backup) and sha256(backup) == s.get("original"):
        original = backup                         # already on: start again from the original
    else:
        # Only ever save a file as "the original" when it really is GNOME's own.
        if s.get("written") == now or any(MARK_START in extract(dest, n).decode(errors="replace")
                                          for n in sheets(list_files(dest))):
            raise LoginScreenError("the login screen file was changed before but its original is missing; "
                                   "run: " + reinstall_hint())
        shutil.copyfile(dest, backup + ".new")    # the file as GNOME installed it
        os.chmod(backup + ".new", 0o644)
        os.replace(backup + ".new", backup)
        original, s = backup, {"original": sha256(backup)}
    fd, out = tempfile.mkstemp(prefix="liquid-glass-login-", suffix=".gresource")
    os.close(fd)
    try:
        block = build(original, out, accent, tint, frost)
        written = sha256(out)
        _write_into(out, dest)
    finally:
        os.unlink(out)
    # Which look went in, so the app can tell when Apply or an update of the app makes it old.
    s.update(written=written, target=dest, look=hashlib.sha256(block.encode()).hexdigest(),
             shared=GDM_CSS not in block_targets(original))
    tmp = os.path.join(state_dir, STATE + ".new")
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, os.path.join(state_dir, STATE))


def undo(shell_dir: str = SHELL_DIR, state_dir: str = STATE_DIR) -> str:
    """Put the original back. Returns what happened, for the app to show."""
    s = _state(state_dir)
    backup = os.path.join(state_dir, BACKUP)
    if not s.get("written"):
        return "it was already off"
    dest = target(shell_dir)
    done = "a GNOME update had already put the normal login screen back"
    if sha256(dest) == s["written"]:
        if not (os.path.isfile(backup) and sha256(backup) == s.get("original")):
            raise LoginScreenError("the saved original is missing or changed; run: " + reinstall_hint())
        _write_into(backup, dest)
        done = "the normal login screen is back"
    for name in (STATE, BACKUP):
        try:
            os.unlink(os.path.join(state_dir, name))
        except FileNotFoundError:
            pass
    return done


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "status" and len(argv) == 2:
            print(status())
            return 0
        if os.geteuid() != 0:
            print("Run this through pkexec (it needs root).", file=sys.stderr)
            return 77
        if cmd == "apply" and len(argv) == 5:
            apply(argv[2], argv[3], argv[4])
            print("on")
            return 0
        if cmd == "undo" and len(argv) == 2:
            print(undo())
            return 0
    except (LoginScreenError, OSError, subprocess.SubprocessError) as e:
        print(f"Nothing was changed: {e}", file=sys.stderr)
        return 1
    print("Usage: liquid-glass-login-screen status | apply ACCENT TINT FROST | undo", file=sys.stderr)
    return 64


if __name__ == "__main__":
    sys.exit(main(sys.argv))
