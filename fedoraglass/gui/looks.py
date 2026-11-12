"""Saved looks live in fedoraglass/looks.py, without Qt, so the `fedora-glass watch`
service uses them too (day and night looks). The app and its tests use them from here:
this name is that same module, not a copy."""

from __future__ import annotations

import sys

from .. import looks as _core

sys.modules[__name__] = _core
