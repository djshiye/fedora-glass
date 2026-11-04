"""Guards for the speed fixes after 1.5.3, read from the extension's source."""
from __future__ import annotations

import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[1] / "liquidglass/data/extension/liquid-glass@djshiye.github.io"


def body(file: str, name: str) -> str:
    src = (EXT / file).read_text()
    m = re.search(rf"\n    {re.escape(name)}\([^)]*\) {{\n(.*?)\n    }}\n", src, re.S)
    assert m, f"{name} not found in {file}"
    return m.group(1)


def code(text: str) -> str:
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def test_pointer_light_only_repaints_the_lens():
    # queue_redraw() marks the pane dirty, so the backdrop is copied and blurred again:
    # 1.5.3 did that for every pointer step near a panel (about 300 % CPU in the release
    # checks' desktop). setFloats already queues a repaint of the lens alone.
    assert "queue_redraw" not in code(body("glass.js", "_applyMotion"))
    assert "this.queue_repaint()" in body("glass.js", "setFloats")


def test_window_open_or_close_keeps_taskbar_hover():
    # Rebuilding every watch reset each hovered or landing icon to rest.
    assert "_unwatchHover" not in code(body("animations.js", "_queueRefresh"))


def test_restack_keeps_window_connections():
    assert ".clear()" not in code(body("common.js", "_watchAll"))


def test_sources_always_restack():
    # Its relayout redraws the whole pane as a window grows; skipping it left black patches.
    b = code(body("glass.js", "setSources"))
    assert "set_child_above_sibling(clone, below)" in b and "get_previous_sibling" not in b


def test_panels_kept_when_nothing_changed():
    assert "pairs.every" in code(body("panels.js", "rescan"))
