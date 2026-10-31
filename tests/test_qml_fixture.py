"""Guard for the shared QML fixture (runs without PySide6 too)."""

from __future__ import annotations

from pathlib import Path

NEEDLE = "qmlRegisterSingleton" + "Instance("     # split, so this file doesn't match itself


def test_only_the_shared_fixture_registers_the_qml_singleton():
    """A second singleton registration in one test run breaks Qt's type registry and
    brings back order-dependent QML failures. QML tests take the session `qml` fixture
    in conftest.py instead."""
    here = Path(__file__).resolve().parent
    counts = {p.name: p.read_text(encoding="utf-8").count(NEEDLE) for p in here.glob("*.py")}
    assert {k: v for k, v in counts.items() if v} == {"conftest.py": 1}
