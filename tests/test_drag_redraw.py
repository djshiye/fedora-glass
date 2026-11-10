"""Guards for the drag repaint fix (1.5.18), read from the extension's source."""
from __future__ import annotations

import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[1] / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"
GLASS = (EXT / "glass.js").read_text()


def body(name: str) -> str:
    m = re.search(rf"\n    {re.escape(name)}\([^)]*\) {{\n(.*?)\n    }}\n", GLASS, re.S)
    assert m, f"{name} not found in glass.js"
    return m.group(1)


def test_copies_report_only_their_clip_to_clutter():
    # A plain Clutter.Clone reports the size of what it copies, whatever its clip, and
    # Clutter redraws all of a moved actor's old and new paint volume. A dragged window's
    # glass moves its copies every frame: the copy of the wallpaper (both screens) and of
    # every window behind were repainted on every frame.
    assert "new Clutter.Clone(" not in GLASS
    assert "new GlassClone({source: src})" in body("setSources")
    vol = body("vfunc_get_paint_volume")
    assert "this.get_clip()" in vol and "return true;" in vol


def test_copies_are_clipped_to_the_pane():
    sync = body("_syncClones")
    assert sync.index("this._clipClone(clone") < sync.index("clone.show()")
    clip = body("_clipClone")
    assert "this._size" in clip and "clone.set_clip(" in clip
    # unchanged clips are not set again (each set_clip queues a redraw)
    assert "clone._clipKey === key" in clip
