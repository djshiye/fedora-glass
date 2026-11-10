"""What a source install (install.sh) left behind after the package was installed.

install.sh puts a copy of the app in ~/.local/share/liquid-glass, with a launcher in
~/.local/bin, a menu entry in ~/.local/share/applications and a user unit in
~/.config/systemd/user. A user unit and a menu entry in the home folder win over the
package's own (same names), so after switching to the package the old copy still runs
the dark/light watcher, and re-applies its older look at every login.

Only those exact files are ever touched, and only when their content says they are
install.sh's and point at its copy. Nothing else in the home folder is.
"""
from __future__ import annotations

import os
from pathlib import Path

from .env import Env

# Where the packages (rpm, deb, Arch) put the app; see packaging/install-tree.sh.
APP_DIR = Path("/usr/share/fedora-glass")
UNIT = "liquid-glass-watch.service"
DESKTOP = "io.github.djshiye.LiquidGlass.desktop"
NAMES = ("Fedora Glass", "Liquid Glass")     # the app was called Liquid Glass up to 1.4.4
MAX_BYTES = 8 * 1024


def from_package() -> bool:
    """This app runs from the package, not from a source install or a checkout."""
    try:
        return Path(__file__).resolve().is_relative_to(APP_DIR)
    except OSError:
        return False


def _launchers(env: Env) -> tuple[Path, Path]:
    # install.sh uses $HOME/.local/bin, whatever XDG says.
    b = env.home / ".local/bin"
    return b / "fedora-glass", b / "liquid-glass"


def _small_text(p: Path) -> str | None:
    """A regular file's text (never through a symlink), or None."""
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_BYTES:
            return None
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _command(line_value: str) -> str:
    v = line_value.strip()
    if v.startswith('"'):
        return v[1:].split('"', 1)[0]
    return v.split(" ", 1)[0]


def _value(text: str, key: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _launcher_is_ours(env: Env, p: Path) -> bool:
    text = _small_text(p)
    prefix = env.data / "liquid-glass"
    return text is not None and text.startswith("#!/bin/sh") \
        and f'sys.path.insert(0, "{prefix}")' in text \
        and ("from fedoraglass.__main__ import main" in text or "from liquidglass.__main__ import main" in text)


def _unit_is_ours(env: Env, p: Path) -> bool:
    text = _small_text(p)
    if text is None:
        return False
    desc, start = _value(text, "Description"), _value(text, "ExecStart")
    return desc is not None and any(desc.startswith(n + ":") for n in NAMES) and start is not None \
        and start.rstrip().endswith(" watch") and Path(_command(start)) in _launchers(env)


def _desktop_is_ours(env: Env, p: Path) -> bool:
    text = _small_text(p)
    if text is None:
        return False
    name, ex = _value(text, "Name"), _value(text, "Exec")
    return name in NAMES and ex is not None and Path(_command(ex)) in _launchers(env)


def find(env: Env) -> list[Path]:
    """The leftover files that make the old copy run instead of the package, in the order
    they are taken away. Empty when this app isn't the package, or nothing is left."""
    if not from_package():
        return []
    out: list[Path] = []
    units = env.config / "systemd/user"
    unit = units / UNIT
    if _unit_is_ours(env, unit):
        # `systemctl --user enable` linked it from the target it starts with.
        try:
            out += [w / UNIT for w in sorted(units.glob("*.wants"))
                    if (w / UNIT).is_symlink() and os.readlink(w / UNIT) == str(unit)]
        except OSError:
            pass
        out.append(unit)
    desktop = env.data / "applications" / DESKTOP
    if _desktop_is_ours(env, desktop):
        out.append(desktop)
    launcher, old_name = _launchers(env)
    if _launcher_is_ours(env, launcher):
        try:
            if old_name.is_symlink() and os.readlink(old_name) == "fedora-glass":
                out.append(old_name)
        except OSError:
            pass
        out.append(launcher)
    return out


def clean_up(env: Env) -> list[str]:
    """Take the leftovers away, then let systemd start the package's own watcher.
    Returns problems, in plain words (empty when all went)."""
    problems: list[str] = []
    gone_unit = False
    for p in find(env):
        try:
            p.unlink()
            gone_unit |= p.name == UNIT
        except FileNotFoundError:
            pass
        except OSError as e:
            problems.append(f"{p}: {e.strerror or e}")
    if gone_unit and not env.dry_run:
        env.run(["systemctl", "--user", "daemon-reload"], timeout=30)
        # The old copy's watcher is still running: start the package's in its place.
        env.run(["systemctl", "--user", "restart", UNIT], timeout=30)
    return problems
