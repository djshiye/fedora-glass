"""Guards for the idle-CPU pass after 1.5.17, read from the extension's source. The release
checks (speed: "a window behind changing far from the glass") measure the effect."""
from __future__ import annotations

import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[1] / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def code(text: str) -> str:
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def glass() -> str:
    return code((EXT / "glass.js").read_text())


def test_window_copies_add_no_redraw_area_of_their_own():
    # Clutter passes each redraw of a window on to its copies whole: a clock ticking in a
    # terminal re-rendered the glass of every window over any part of it, once a second.
    g = glass()
    m = re.search(r"class FedoraGlassWindowCopy extends Clutter\.Clone \{(.*?)\n\}\);", g, re.S)
    assert m, "the window copy class is gone"
    assert re.search(r"vfunc_get_paint_volume\(_?volume\) \{\s*return true;", m.group(1))
    assert "src.meta_window && QUIET_COPIES ? new WindowCopy({source: src}) : new GlassClone({source: src})" in g
    assert "const QUIET_COPIES = (parseInt(PACKAGE_VERSION) || 0) >= 51;" in g


def test_a_window_behind_changing_forces_a_full_render_only_on_gnome_50():
    # 'damaged' -> queueFull() re-rendered every pane that copied the window, wherever in
    # the window the change was. GNOME 50 redraws the whole pane anyway, so it keeps it there.
    g = glass()
    assert "if (!QUIET_COPIES && GObject.signal_lookup('damaged', src.constructor.$gtype))" in g
    assert "frozen.has(src) || this._glass.behindChanged()" in g
    assert g.count("'damaged'") == 2


def test_a_source_that_never_stops_is_followed_at_half_rate():
    g = glass()
    assert "const BUSY_AFTER_US = 3e6;" in g
    assert "BUSY_RERENDER_US = 2 * RERENDER_US;" in g
    assert "busy ? BUSY_RERENDER_US : 0" in g
    # Busy only while renders follow each other closely; a pause starts over.
    assert "t - this._renderedAt > BUSY_GAP_US" in g
