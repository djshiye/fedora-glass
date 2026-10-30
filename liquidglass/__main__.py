"""liquid-glass command line.

  liquid-glass                 open the customizer
  liquid-glass apply [--frost 0.4] [--preset Frosted] [--only gtk4,shell]
  liquid-glass plan            show what Apply would change, change nothing
  liquid-glass status          list targets and whether they're available
  liquid-glass revert [TARGET] restore the original look (everything, or one target)
  liquid-glass watch           re-apply when GNOME switches dark/light (run by a user service)
"""

from __future__ import annotations

import argparse
import subprocess
import sys

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


def cmd_watch(args: argparse.Namespace) -> int:
    """Follow GNOME's dark/light switch. Only parts that can't switch by
    themselves (Shell theme, GTK 3, terminal, Qt) need a re-apply."""
    try:
        proc = subprocess.Popen(["gsettings", "monitor", "org.gnome.desktop.interface", "color-scheme"],
                                stdout=subprocess.PIPE, text=True)
    except OSError as e:
        print(f"gsettings not available: {e}", file=sys.stderr)
        return 1
    assert proc.stdout is not None
    eng = _engine()
    only = {t.id for t in eng.targets if t.scheme_dependent}
    for _line in proc.stdout:
        s = settings_mod.load()
        if s.scheme == "auto" and eng.is_applied():   # after Restore original, stay out of the way
            eng.apply(s, only=only)
    return proc.wait()


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
    sub.add_parser("watch", help="follow dark/light switches").set_defaults(func=cmd_watch)
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
