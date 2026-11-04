"""fedora-glass command line.

  fedora-glass                 open the customizer
  fedora-glass apply [--frost 0.4] [--preset Frosted] [--only gtk4,shell]
  fedora-glass plan            show what Apply would change, change nothing
  fedora-glass status          list targets and whether they're available
  fedora-glass revert [TARGET] restore the original look (everything, or one target)
  fedora-glass watch           re-apply when GNOME switches dark/light or High Contrast (run by a user service)
  fedora-glass on-remove       restore the original look before `dnf remove` takes the app away (run by dnf)
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


def cmd_apply(args: argparse.Namespace) -> int:
    s = settings_mod.load()
    if args.preset:
        s = settings_mod.apply_preset(s, args.preset)
    if args.frost is not None:
        s.frost = args.frost
    if args.scheme:
        s.scheme = args.scheme
    s = s.normalized()
    only = set(args.only.split(",")) if args.only else None
    results = _engine().apply(s, only=only)
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
    for tid, actions in _engine().plan(settings_mod.load()).items():
        print(f"[{tid}]")
        for a in actions:
            print(f"  {a.describe()}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    eng = _engine()
    s = settings_mod.load()
    for t in eng.targets:
        d = t.detect(eng.env)
        state = "on " if s.target_enabled(t.id) else "off"
        avail = "available" if d.available else f"not available ({d.detail})"
        print(f"{state}  {t.id:<16} {t.name}: {avail}")
    return 0


def cmd_revert(args: argparse.Namespace) -> int:
    problems = _engine().revert(args.target)
    for p in problems:
        print(f"✗ {p}", file=sys.stderr)
    if not problems:
        print("Original look restored." if not args.target else f"Restored {args.target}.")
    return 1 if problems else 0


def cmd_on_remove(args: argparse.Namespace) -> int:
    """Run by `dnf remove fedora-glass`, as each person with a look applied (never as root),
    before the app's files go: Restore original, unless they turned that off in the app."""
    s = settings_mod.load()
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


def finish_pending(eng, wait_s: float = 120.0, step_s: float = 2.0, sleep=time.sleep) -> bool:
    """At login, finish the Shell parts an Apply left waiting for the glass extension
    (see engine.WAITING). GNOME starts extensions a little after the session, so wait
    for ours to run. Returns True when there was nothing left to do or it finished."""
    from .engine import read_pending
    if not read_pending() or not eng.is_applied():
        return True
    s = settings_mod.load()
    waited = 0.0
    while not eng.glass_running(s):
        if waited >= wait_s:
            print("fedora-glass watch: the glass extension isn't running; Shell parts still wait", file=sys.stderr)
            return False
        sleep(step_s)
        waited += step_s
    eng.apply(s, only=read_pending() | {"glass"})   # glass too: it hands blur over from Blur my Shell
    return not read_pending()


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
    extension in their home folder, the theme files) is still the old version's. At the
    next login, apply it again with the user's own saved settings, the way pressing Apply
    would. Nothing happens after Restore original, or when the versions already match.
    Returns True when it applied."""
    if not eng.is_applied():
        return False
    had = installed_glass_version(eng)
    if had is None and getattr(eng, "env", None) is not None:
        # The glass part is off, so there is no extension to ask: the other parts still
        # need the new version's look (1.5.2 never updated them).
        from .engine import read_applied_version
        had = read_applied_version(eng.env)
    if had is None or had == __version__:
        return False
    print(f"fedora-glass watch: updating the applied look from {had} to {__version__}", file=sys.stderr)
    eng.apply(settings_mod.load())
    return True


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


UPGRADED = "upgraded"
UPGRADE_POLL_S = 60.0


def cmd_watch(args: argparse.Namespace) -> int:
    """Follow GNOME's dark/light switch and its High Contrast switch. A dark/light
    switch only needs the parts that can't switch by themselves (Shell theme,
    GTK 3, terminal, Qt); High Contrast changes every part (glass goes opaque)."""
    keys = (("org.gnome.desktop.interface", "color-scheme"), ("org.gnome.desktop.a11y.interface", "high-contrast"))
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
    eng = _engine()
    only = {t.id for t in eng.targets if t.scheme_dependent}
    update_after_upgrade(eng)
    finish_pending(eng)
    changes: queue.Queue[int | None] = queue.Queue()

    def follow(i: int, p: subprocess.Popen) -> None:
        assert p.stdout is not None
        for _line in p.stdout:
            changes.put(i)
        changes.put(None)       # that monitor ended

    def notice_upgrade() -> None:
        while True:
            time.sleep(UPGRADE_POLL_S)
            v = disk_version()
            if v is not None and v != __version__:
                changes.put(UPGRADED)
                return

    for i, p in enumerate(procs):
        threading.Thread(target=follow, args=(i, p), daemon=True).start()
    threading.Thread(target=notice_upgrade, daemon=True).start()
    try:
        while True:
            got = _take_all(changes)
            if UPGRADED in got:
                # The user service starts the new version's watcher, which brings the look up to date.
                print(f"fedora-glass watch: Fedora Glass {disk_version()} was installed; starting it", file=sys.stderr)
                return 75
            if None in got:
                # Half a watcher would miss switches: stop, and let the user service start a fresh one.
                print("fedora-glass watch: a gsettings monitor stopped", file=sys.stderr)
                return 1
            s = settings_mod.load()
            contrast = 1 in got
            # After Restore original, stay out of the way.
            if eng.is_applied() and (contrast or s.scheme == "auto"):
                eng.apply(s, only=None if contrast else only, if_applied=True)
    finally:
        stop_all()


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import main
    except ImportError as e:
        print(f"The customizer needs PySide6: sudo dnf install python3-pyside6 ({e})", file=sys.stderr)
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
    sub.add_parser("watch", help="follow dark/light and High Contrast switches").set_defaults(func=cmd_watch)
    sub.add_parser("on-remove", help="restore the original look before the app is removed (run by dnf)").set_defaults(func=cmd_on_remove)
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
