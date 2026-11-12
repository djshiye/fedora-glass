"""Tools that CI must have, so that a test which needs one cannot quietly skip there.

A test that needs gresource and glib-compile-resources skips on a machine without them, which
is right on a developer's laptop and wrong in CI: 16 login screen tests once never ran for
months because the CI images did not have the tools. A CI job names what it has installed in
FEDORAGLASS_REQUIRE (for example "glib yaml"); a test that then finds one missing fails
instead of skipping.
"""
from __future__ import annotations

import os


def required(name: str) -> bool:
    """Whether this run was told that tool group `name` is installed (and so may not be skipped)."""
    return name in os.environ.get("FEDORAGLASS_REQUIRE", "").replace(",", " ").split()
