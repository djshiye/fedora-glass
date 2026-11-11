"""Which Linux this is (Fedora, Ubuntu/Debian or Arch), for the right install, remove and
repair commands. Everything else in Fedora Glass works the same on all three.

Read from /etc/os-release (ID, then ID_LIKE). Anything unknown is treated like Fedora's
upstream GNOME, with commands left generic.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

OS_RELEASE = (Path("/etc/os-release"), Path("/usr/lib/os-release"))


@dataclass(frozen=True)
class Distro:
    family: str          # "fedora", "debian", "arch" or "other"
    install: str         # command prefix to add packages, e.g. "sudo dnf install"
    manager: str         # absolute path of the package tool the app may call through pkexec
    remove_args: tuple   # its arguments to remove a package (the name goes last)
    owner_cmd: tuple     # asks which installed package owns a path (the path goes last)
    packages: dict       # what each need is called here ("" = not packaged)

    def hint(self, need: str) -> str:
        """`sudo <tool> install <package>` for a need ("pyside6", "kvantum", ...), or ""."""
        name = self.packages.get(need, "")
        return f"{self.install} {name}" if name else ""

    def remove_command(self, package: str = "fedora-glass") -> str:
        return {"fedora": f"sudo dnf remove {package}",
                "debian": f"sudo apt purge {package}",
                "arch": f"sudo pacman -R {package}"}.get(self.family, f"remove the {package} package")

    @property
    def tool_name(self) -> str:
        return Path(self.manager).name


FEDORA = Distro(
    "fedora", "sudo dnf install", "/usr/bin/dnf", ("remove", "-y", "--no-autoremove"),
    ("rpm", "-qf", "--qf", "%{NAME}"),
    {"pyside6": "python3-pyside6", "kvantum": "kvantum", "adw-gtk3": "adw-gtk3-theme",
     "user-theme": "gnome-shell-extension-user-theme", "gnome-shell": "gnome-shell"})
# purge, not remove: the package's repository entry (/etc/apt/sources.list.d) is a
# config file, and `remove` leaves config files behind, so apt kept asking that repository.
DEBIAN = Distro(
    "debian", "sudo apt install", "/usr/bin/apt-get", ("purge", "-y"),
    ("dpkg-query", "-S"),
    # Ubuntu splits PySide6 per Qt module and QML per module.
    {"pyside6": "python3-pyside6.qtquick python3-pyside6.qtquickcontrols2 qml6-module-qtquick-controls "
                "qml6-module-qtquick-effects qml6-module-qtquick-shapes qml6-module-qtquick-window qml6-module-qtquick-dialogs",
     "kvantum": "qt6-style-kvantum", "adw-gtk3": "",
     "user-theme": "gnome-shell-extension-user-theme", "gnome-shell": "gnome-shell"})
ARCH = Distro(
    "arch", "sudo pacman -S", "/usr/bin/pacman", ("-R", "--noconfirm"),
    ("pacman", "-Qqo"),
    {"pyside6": "pyside6", "kvantum": "kvantum", "adw-gtk3": "adw-gtk-theme",
     "user-theme": "gnome-shell-extensions", "gnome-shell": "gnome-shell"})
OTHER = Distro("other", "", "", (), (), {})


def _read_os_release(paths=OS_RELEASE) -> dict:
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out = {}
        for line in text.splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().isidentifier():
                out[key.strip()] = value.strip().strip('"').strip("'")
        return out
    return {}


def from_os_release(info: dict) -> Distro:
    ids = [info.get("ID", "").lower()] + info.get("ID_LIKE", "").lower().split()
    for i in ids:
        if i in ("fedora", "rhel", "centos"):
            return FEDORA
        if i in ("ubuntu", "debian"):
            return DEBIAN
        if i in ("arch", "archlinux"):
            return ARCH
    return OTHER


@functools.cache
def current() -> Distro:
    return from_os_release(_read_os_release())


def hint(need: str, fallback: str = "") -> str:
    """Install command for a need on this PC, e.g. "sudo apt install qt6-style-kvantum"."""
    return current().hint(need) or fallback
