"""All theming targets, in the order they're applied and listed in the app."""

from __future__ import annotations

import importlib

from .base import Target

# Each module exposes TARGETS: list[Target].
_MODULES = ("shell", "gtk", "terminal", "qt", "apps", "myapps")


def all_targets() -> list[Target]:
    out: list[Target] = []
    for name in _MODULES:
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except ModuleNotFoundError as e:
            if e.name == f"{__name__}.{name}":
                continue
            raise
        out.extend(mod.TARGETS)
    return out
