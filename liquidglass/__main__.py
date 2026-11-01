"""liquid-glass command line.

  liquid-glass                 open the customizer
  liquid-glass apply [--frost 0.4] [--preset Frosted] [--only gtk4,shell]
  liquid-glass plan            show what Apply would change, change nothing
  liquid-glass status          list targets and whether they're available
  liquid-glass revert [TARGET] restore the original look (everything, or one target)
  liquid-glass watch           re-apply when GNOME switches dark/light or High Contrast (run by a user service)
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
            print("liquid-glass watch: the glass extension isn't running; Shell parts still wait", file=sys.stderr)
            return False
        sleep(step_s)
        waited += step_s
    eng.apply(s, only=read_pending() | {"glass"})   # glass too: it hands blur over from Blur my Shell
    return not read_pending()


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
    finish_pending(eng)
    changes: queue.Queue[int | None] = queue.Queue()

    def follow(i: int, p: subprocess.Popen) -> None:
        assert p.stdout is not None
        for _line in p.stdout:
            changes.put(i)
        changes.put(None)       # that monitor ended

    for i, p in enumerate(procs):
        threading.Thread(target=follow, args=(i, p), daemon=True).start()
    try:
        while True:
            got = _take_all(changes)
            if None in got:
                # Half a watcher would miss switches: stop, and let the user service start a fresh one.
                print("liquid-glass watch: a gsettings monitor stopped", file=sys.stderr)
                return 1
            s = settings_mod.load()
            contrast = 1 in got
            # After Restore original, stay out of the way.
            if eng.is_applied() and (contrast or s.scheme == "auto"):
                eng.apply(s, only=None if contrast else only)
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
    p = argparse.ArgumentParser(prog="liquid-glass", description="Liquid Glass theme for Fedora GNOME")
    p.add_argument("--version", action="version", version=f"liquid-glass {__version__}")
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
