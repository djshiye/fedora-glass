"""fedora-glass command line.

  fedora-glass                 open the customizer
  fedora-glass apply [--frost 0.4] [--preset Frosted] [--only gtk4,shell]
  fedora-glass plan            show what Apply would change, change nothing
  fedora-glass status          list targets and whether they're available
  fedora-glass revert [TARGET] restore the original look (everything, or one target)
  fedora-glass watch           re-apply when GNOME switches dark/light, High Contrast or its accent colour (run by a user service)
  fedora-glass on-remove       restore the original look before the package manager takes the app away (run by dnf, apt or pacman)
"""

from __future__ import annotations

import argparse
import queue
import subprocess
import sys
import threading
import time

from . import __version__, settings as settings_mod


def _engine():
    from .engine import Engine
    return Engine()


def _part_ids(eng) -> set[str]:
    """The parts this version knows, and any part an older one applied that is still on
    record (so it can still be restored on its own)."""
    from .engine import Backup, BackupUnreadable
    ids = {t.id for t in eng.targets}
    try:
        ids |= Backup(eng.env).targets_with_changes()
    except BackupUnreadable:
        pass
    return ids


def _unknown_parts(eng, wanted: set[str]) -> bool:
    """Say so, and True, when a part id isn't one: a typo must not look like success."""
    known = _part_ids(eng)
    if not (bad := sorted(wanted - known)):
        return False
    print(f"fedora-glass: no part called {', '.join(bad)}. The parts are: {', '.join(sorted(known))}",
          file=sys.stderr)
    return True


def cmd_apply(args: argparse.Namespace) -> int:
    s = settings_mod.load()
    if args.preset:
        s = settings_mod.apply_preset(s, args.preset)
    if args.frost is not None:
        s.frost = args.frost
    if args.scheme:
        s.scheme = args.scheme
    s = s.normalized()
    eng = _engine()
    only = {x.strip() for x in args.only.split(",") if x.strip()} if args.only is not None else None
    if only is not None and (not only or _unknown_parts(eng, only)):
        if not only:
            print("fedora-glass: --only needs at least one part", file=sys.stderr)
        return 2
    results = eng.apply(s, only=only)
    if only is None:
        # Only an Apply of everything makes these the settings of the look: saved after
        # `--only gtk4 --frost 0.9`, the other parts would take 0.9 at the next dark/light
        # switch without anyone applying it to them.
        settings_mod.save(s)
    width = max((len(r.name) for r in results), default=0)
    failed = False
    for r in results:
        mark = {"applied": "✓", "info": "i", "reverted": "↺", "skipped": "–", "failed": "✗"}[r.status]
        line = f"{mark} {r.name.ljust(width)}  {r.status}"
        if r.message:
            line += f": {r.message}"
        print(line)
        failed |= r.status == "failed"
    return 1 if failed else 0


def cmd_plan(args: argparse.Namespace) -> int:
    # Commands that only look move and write nothing, not even a damaged settings file.
    for tid, actions in _engine().plan(settings_mod.load(fix=False)).items():
        print(f"[{tid}]")
        for a in actions:
            print(f"  {a.describe()}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    eng = _engine()
    s = settings_mod.load(fix=False)
    for t in eng.targets:
        d = t.detect(eng.env)
        state = "on " if s.target_enabled(t.id) else "off"
        avail = "available" if d.available else f"not available ({d.detail})"
        print(f"{state}  {t.id:<16} {t.name}: {avail}")
    return 0


def cmd_revert(args: argparse.Namespace) -> int:
    eng = _engine()
    if args.target is not None and _unknown_parts(eng, {args.target}):
        return 2
    problems = eng.revert(args.target)
    for p in problems:
        print(f"✗ {p}", file=sys.stderr)
    if not problems:
        print("Original look restored." if not args.target else f"Restored {args.target}.")
    return 1 if problems else 0


def cmd_on_remove(args: argparse.Namespace) -> int:
    """Run by `dnf remove fedora-glass`, as each person with a look applied (never as root),
    before the app's files go: Restore original, unless they turned that off in the app.
    It reads the settings and changes none of them: a damaged file stays where it is."""
    s = settings_mod.load(fix=False)
    if not s.undo_on_remove:
        print("Fedora Glass: your look stays as it is (you turned off undo on removal).")
        return 0
    eng = _engine()
    if not eng.is_applied():
        return 0
    problems = eng.revert()
    for p in problems:
        print(f"Fedora Glass: could not restore {p}")
    if problems:
        print("Fedora Glass: the rest of your original look is back. The backup of what could not "
              "be restored is kept in ~/.local/state/liquid-glass.")
        return 1
    print("Fedora Glass: your original look is back. Restart your PC to finish.")
    return 0


def _take_all(q: queue.Queue) -> set:
    """Wait for one item, then take every other one already waiting, so a quick
    run of switches makes one apply instead of one each."""
    got = {q.get()}
    while True:
        try:
            got.add(q.get_nowait())
        except queue.Empty:
            return got


_said: set[str] = set()


def _say_once(line: str, key: str | None = None) -> None:
    """The watcher runs all session: a problem it keeps meeting goes in the log once
    (`key`: lines that word the same problem differently count as one)."""
    if (key or line) not in _said:
        _said.add(key or line)
        print(line, file=sys.stderr)


def _auto_settings():
    """The user's settings for an Apply nobody asked for (the watcher, the upgrade step), or
    None when there is no good settings file to go on: a damaged one stands in as the
    defaults, and applying those would replace the user's look with them."""
    s, problem, usable = settings_mod.load_checked()
    if not usable:
        _say_once(f"fedora-glass watch: not applying anything by itself: {problem}", key="settings")
        return None
    _said.discard("settings")      # good again: a later problem is worth a line of its own
    return s


def _guarded(what: str, fn, *args, **kwargs):
    """Run one step of the watcher; a failure is logged (once) and the watcher goes on.
    Ending it would only have its user service start it again every few seconds, failing
    the same way each time."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:  # noqa: BLE001 - any failure of one step, never the whole watcher
        _say_once(f"fedora-glass watch: {what} failed: {type(e).__name__}: {e}")
        return None


def finish_pending(eng, wait_s: float = 120.0, step_s: float = 2.0, sleep=time.sleep) -> bool:
    """At login, finish the Shell parts an Apply left waiting for the glass extension
    (see engine.WAITING). GNOME starts extensions a little after the session, so wait
    for ours to run. Returns True when there was nothing left to do or it finished."""
    from .engine import read_pending
    if not read_pending() or not eng.look_on():
        return True
    if (s := _auto_settings()) is None:
        return False
    waited = 0.0
    while not eng.glass_running(s):
        if (why := _glass_waits_for_login(eng)):
            # No point waiting: it won't change before the next login.
            _say_once(f"fedora-glass watch: {why}; Shell parts still wait")
            return False
        if waited >= wait_s:
            _say_once("fedora-glass watch: the glass extension isn't running; Shell parts still wait")
            return False
        sleep(step_s)
        waited += step_s
    eng.apply(s, only=read_pending() | {"glass"}, if_applied=True)   # glass too: it hands blur over from Blur my Shell
    return not read_pending()


def _glass_waits_for_login(eng) -> str:
    """Why the glass extension won't start running this version by itself now (it only
    changes at the next login, or with the user's help), or ""."""
    env = getattr(eng, "env", None)
    if env is None:
        return ""
    from .targets.shell import glass_state
    st = glass_state(env)
    return {"old": f"GNOME runs the glass of Fedora Glass {st.version} until the next login",
            "off": "extensions are switched off in GNOME",
            "out-of-date": "GNOME says the glass extension doesn't support this GNOME version",
            "error": f"the glass extension failed to start ({st.error or 'no details'})"}.get(st.kind, "")


def installed_glass_version(eng) -> str | None:
    """The version of the glass extension Apply last installed for this user, or None."""
    import json
    from .render import glass as rg
    env = getattr(eng, "env", None)
    if env is None:
        return None
    meta = env.data / "gnome-shell/extensions" / rg.UUID / "metadata.json"
    try:
        if meta.is_symlink() or meta.stat().st_size > 64 * 1024:
            return None
        v = json.loads(meta.read_text(encoding="utf-8")).get("version-name")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) else None


def update_after_upgrade(eng) -> bool:
    """After `dnf upgrade` the app is new but the look this user applied (the glass
    extension in their home folder, the theme files) is still the old version's. Apply
    it again with the user's own saved settings, the parts they applied and no others.
    Nothing happens after Restore original, or when the versions already match.
    The watcher runs this at login and again a minute after an upgrade, while GNOME still
    runs the old glass extension (it only loads new code at the next login): then the
    Shell parts, which need the new glass behind them, wait for that login (see
    GlassEffects.running and finish_pending). Returns True when it applied."""
    if not eng.look_on():
        return False
    stamped = None
    if getattr(eng, "env", None) is not None:
        from .engine import read_applied_version
        stamped = read_applied_version(eng.env)
    if stamped == __version__:
        # An Apply of every part by this version already ran (Engine._stamp), even if the
        # glass part failed in it twice: applying all again at every login would not help.
        return False
    had = installed_glass_version(eng)
    if had is None or had == __version__:
        # The glass part is off, so there is no extension to ask, or the step before login
        # (update_glass_before_login) already brought the extension up to this version:
        # the other parts still need the new version's look (1.5.2 never updated them),
        # and the stamp says which version they have.
        had = stamped
    if had is None or had == __version__:
        return False
    if (s := _auto_settings()) is None:
        return False
    print(f"fedora-glass watch: updating the applied look from {had} to {__version__}", file=sys.stderr)
    eng.apply(s, if_applied=True, applied_only=True)
    return True


def update_glass_before_login(eng) -> bool:
    """Run before GNOME Shell starts (the fedora-glass-before-login user service). An update
    installed while nobody was logged in (GNOME Software's "Restart & Update", dnf
    offline-upgrade, an update just before a restart) leaves the older glass extension in
    the home folder, and GNOME Shell loads it at this login: the new glass would only run
    after yet another restart. So the glass part alone is brought up to this version here,
    with the user's own saved settings, before the Shell reads it. Files and GNOME settings
    only: the Shell isn't there to ask, and the other parts follow from the watcher once the
    session runs (update_after_upgrade). Nothing happens after Restore original, when the
    glass part is off or not applied, or when the versions already match."""
    if not eng.look_on():
        return False
    from .engine import Backup, BackupUnreadable
    try:
        if "glass" not in Backup(eng.env).targets_with_changes():
            return False
    except BackupUnreadable:
        return False
    had = installed_glass_version(eng)
    if had is None or had == __version__:
        return False
    if (s := _auto_settings()) is None or not s.target_enabled("glass"):
        return False
    print(f"fedora-glass: bringing the glass from {had} up to {__version__} before GNOME Shell starts", file=sys.stderr)
    eng.apply(s, only={"glass"}, if_applied=True, applied_only=True)
    return installed_glass_version(eng) == __version__


def cmd_before_login(args: argparse.Namespace) -> int:
    """`fedora-glass before-login`: see update_glass_before_login. Never fails the login."""
    _guarded("updating the glass before login", lambda: update_glass_before_login(_engine()))
    return 0


def disk_version() -> str | None:
    """The app version on disk now; after `dnf upgrade` it differs from the running one."""
    import re
    from pathlib import Path
    try:
        text = (Path(__file__).resolve().parent / "__init__.py").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"__version__\s*=\s*['\"]([^'\"]+)", text)
    return m.group(1) if m else None


TICK = "tick"
UPGRADE_POLL_S = 60.0
# After the first try at login, the Shell parts that wait for the glass are looked at again
# at each wake-up for this long: on a slow login GNOME starts the extensions late.
PENDING_RETRY_S = 30 * 60.0
# A run of switches this close together makes one Apply.
SETTLE_MS = 150

SCHEME, CONTRAST, ACCENT = 0, 1, 2
WATCH_KEYS = (("org.gnome.desktop.interface", "color-scheme"), ("org.gnome.desktop.a11y.interface", "high-contrast"))
ACCENT_KEY = ("org.gnome.desktop.interface", "accent-color")


def _has_accent_key() -> bool:
    """GNOME 47 and later have an accent colour. On an older one `gsettings monitor` for it
    would end at once, and take the watcher with it."""
    from .env import Env
    try:
        return ACCENT_KEY[1] in Env().gsettings_keys(ACCENT_KEY[0])
    except Exception:
        return False


class Watcher:
    """What `fedora-glass watch` does, whatever tells it about a change (GSettings signals,
    or `gsettings monitor` where there is no PyGObject)."""

    def __init__(self, eng, clock=time.monotonic):
        self.eng = eng
        self.only = {t.id for t in eng.targets if t.scheme_dependent}
        self.clock = clock
        self.pending_left = True
        self.pending_until = clock() + PENDING_RETRY_S

    def start(self) -> None:
        """At login: bring the look up to this version, and finish the waiting Shell parts."""
        _guarded("updating the look after an upgrade", update_after_upgrade, self.eng)
        self.pending_left = _guarded("finishing the Shell parts", finish_pending, self.eng) is not True
        self.pending_until = self.clock() + PENDING_RETRY_S

    def retry_pending(self) -> None:
        """At a later wake-up, for a while: the glass may run by now (a slow login)."""
        if self.pending_left and self.clock() < self.pending_until:
            self.pending_left = _guarded("finishing the Shell parts", finish_pending, self.eng,
                                         wait_s=0.0) is not True

    def changed(self, got: set) -> None:
        """GNOME switched dark/light (SCHEME), High Contrast (CONTRAST) or its accent (ACCENT)."""
        self.retry_pending()
        if (s := _auto_settings()) is None:
            return
        scheme = SCHEME in got and s.scheme == "auto"
        contrast = CONTRAST in got
        accent = ACCENT in got and getattr(s, "accent", "") == "system"
        # After Restore original, stay out of the way.
        if (scheme or contrast or accent) and _guarded("checking the look", self.eng.look_on):
            _guarded("Apply", self.eng.apply, s, only=None if contrast or accent else self.only,
                     if_applied=True, applied_only=True)

    def poll(self) -> int | None:
        """Every minute. 75 when `dnf upgrade` put a new version on disk: the user service
        then starts the new version's watcher, which brings the look up to date."""
        v = disk_version()
        if v is not None and v != __version__:
            print(f"fedora-glass watch: Fedora Glass {v} was installed; starting it", file=sys.stderr)
            return 75
        self.retry_pending()
        return None


def _gio():
    """PyGObject's Gio and GLib, or None (then the watcher falls back to `gsettings monitor`)."""
    try:
        import gi
        gi.require_version("Gio", "2.0")
        gi.require_version("GLib", "2.0")
        from gi.repository import Gio, GLib
    except (ImportError, ValueError):
        return None
    return Gio, GLib


def cmd_watch(args: argparse.Namespace) -> int:
    """Follow GNOME's dark/light switch, its High Contrast switch and its accent colour.
    A dark/light switch only needs the parts that can't switch by themselves (Shell theme,
    GTK 3, terminal, Qt); High Contrast changes every part (glass goes opaque). The accent
    colour is written into every part, so a new one changes them all, when the look the
    user applied says "follow the system" (Apply turned that on, so this is no surprise).
    Exits 75 when a new version is installed, 1 when it can no longer watch."""
    mods = _gio()
    if mods is not None:
        return _watch_gio(*mods)
    return _watch_monitors()


def _watch_gio(Gio, GLib) -> int:
    """Settings' own change signals, in this process: no `gsettings monitor` children
    running all session, and the process sleeps until something changes."""
    source = Gio.SettingsSchemaSource.get_default()

    def has(schema: str, key: str) -> bool:
        found = source.lookup(schema, True) if source is not None else None
        return found is not None and found.has_key(key)
    keys = WATCH_KEYS + ((ACCENT_KEY,) if has(*ACCENT_KEY) else ())
    for schema, key in WATCH_KEYS:
        if not has(schema, key):
            # Gio.Settings would abort the process on a schema that isn't there.
            print(f"fedora-glass watch: GNOME has no setting {schema} {key}", file=sys.stderr)
            return 1
    loop = GLib.MainLoop()
    got: set[int] = set()
    state = {"code": 0, "settle": 0}

    def settle() -> bool:
        state["settle"] = 0
        which = set(got)
        got.clear()
        watcher.changed(which)
        return False

    def on_change(i: int):
        def changed(_settings, _key) -> None:
            got.add(i)
            if not state["settle"]:
                state["settle"] = GLib.timeout_add(SETTLE_MS, settle)
        return changed

    held = []                   # kept, or they would be collected and stop signalling
    for i, (schema, key) in enumerate(keys):
        gs = Gio.Settings.new(schema)
        gs.connect(f"changed::{key}", on_change(i))
        gs.get_value(key)       # GSettings only reports changes to a key once it was read
        held.append(gs)
    # Created before the first Apply, so a switch during it is not missed: it waits in the loop.
    watcher = Watcher(_engine())
    watcher.start()

    def tick() -> bool:
        code = watcher.poll()
        if code is None:
            return True
        state["code"] = code
        loop.quit()
        return False
    GLib.timeout_add_seconds(max(1, round(UPGRADE_POLL_S)), tick)
    loop.run()
    return state["code"]


def _watch_monitors() -> int:
    """Without PyGObject: one `gsettings monitor` per key."""
    keys = WATCH_KEYS
    if _has_accent_key():
        keys += (ACCENT_KEY,)
    procs: list[subprocess.Popen] = []

    def stop_all() -> None:
        for p in procs:
            if p.poll() is None:
                p.kill()
            p.wait()

    try:
        for schema, key in keys:
            procs.append(subprocess.Popen(["gsettings", "monitor", schema, key], stdout=subprocess.PIPE, text=True))
    except OSError as e:
        stop_all()              # never leave the first monitor running on its own
        print(f"gsettings not available: {e}", file=sys.stderr)
        return 1
    watcher = Watcher(_engine())
    watcher.start()
    changes: queue.Queue[int | str | None] = queue.Queue()

    def follow(i: int, p: subprocess.Popen) -> None:
        assert p.stdout is not None
        for _line in p.stdout:
            changes.put(i)
        changes.put(None)       # that monitor ended

    def poll() -> None:
        while True:
            time.sleep(UPGRADE_POLL_S)
            changes.put(TICK)

    for i, p in enumerate(procs):
        threading.Thread(target=follow, args=(i, p), daemon=True).start()
    threading.Thread(target=poll, daemon=True).start()
    try:
        while True:
            got = _take_all(changes)
            if TICK in got and (code := watcher.poll()) is not None:
                return code
            if None in got:
                # Half a watcher would miss switches: stop, and let the user service start a fresh one.
                print("fedora-glass watch: a gsettings monitor stopped", file=sys.stderr)
                return 1
            if got - {TICK}:
                watcher.changed(got - {TICK})
    finally:
        stop_all()


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import main
    except ImportError as e:
        from . import distro
        print(f"The customizer needs PySide6: {distro.hint('pyside6', 'install PySide6')} ({e})", file=sys.stderr)
        return 1
    return main(args.qt_args)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="fedora-glass", description="Glass theme for Fedora GNOME")
    p.add_argument("--version", action="version", version=f"fedora-glass {__version__}")
    sub = p.add_subparsers(dest="cmd")

    a = sub.add_parser("apply", help="apply the theme with saved settings")
    a.add_argument("--frost", type=float, help="0 = liquid, 1 = frosted")
    a.add_argument("--preset", choices=sorted(settings_mod.PRESETS))
    a.add_argument("--scheme", choices=settings_mod.SCHEMES)
    a.add_argument("--only", help="comma-separated target ids")
    a.set_defaults(func=cmd_apply)

    sub.add_parser("plan", help="show what apply would change").set_defaults(func=cmd_plan)
    sub.add_parser("status", help="list targets").set_defaults(func=cmd_status)
    r = sub.add_parser("revert", help="restore the original look")
    r.add_argument("target", nargs="?")
    r.set_defaults(func=cmd_revert)
    sub.add_parser("watch", help="follow dark/light, High Contrast and accent colour switches").set_defaults(func=cmd_watch)
    sub.add_parser("before-login", help="bring the glass up to date before GNOME Shell starts (run by the user service at login)").set_defaults(func=cmd_before_login)
    sub.add_parser("on-remove", help="restore the original look before the app is removed (run by dnf, apt or pacman)").set_defaults(func=cmd_on_remove)
    g = sub.add_parser("gui", help="open the customizer")
    g.add_argument("qt_args", nargs=argparse.REMAINDER)
    g.set_defaults(func=cmd_gui)

    raw = sys.argv[1:] if argv is None else list(argv)
    if raw[:1] == ["gui"]:
        # argparse's REMAINDER drops leading options (gui --screenshot ...), so hand them over as-is.
        return cmd_gui(argparse.Namespace(qt_args=raw[1:]))
    args = p.parse_args(raw)
    if not args.cmd:
        return cmd_gui(argparse.Namespace(qt_args=raw))
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
