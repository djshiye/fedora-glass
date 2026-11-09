"""Glass behind a see-through title bar (Slack) must look the same on every frame.

1.5.13: Mutter skipped drawing the parts of the windows below that the focused window's
solid body covers, while the glass under that window was copying them. The glass came
out different depending on when it was redrawn, and a glow came and went.
"""
from pathlib import Path

EXT = Path(__file__).resolve().parent.parent / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def test_focused_window_keeps_the_windows_below_whole():
    js = (EXT / "windows.js").read_text()
    # An enabled effect on the window makes Mutter leave it out of its covered-area pass.
    assert "extends Clutter.Effect" in js
    assert "this._keepBelowWhole(sources.some(s => s.meta_window));" in js
    # Taken off again when the glass hides or goes away.
    assert js.count("this._keepBelowWhole(false);") == 2
    assert "remove_effect_by_name(NO_CULL)" in js


def test_catch_up_render_waits_for_a_whole_redraw():
    js = (EXT / "glass.js").read_text()
    start = js.index("Time to catch up, but this frame redraws only part")
    block = js[start:start + 800]
    assert "a?.queueFull?.();" in block
    assert "super.vfunc_paint(node, paintContext, flags & ~dirty);" in block


def test_glass_renders_only_while_its_own_screen_paints():
    """1.5.15: with two screens, a pane reaching over the seam could render while the
    other screen painted. Mutter then drew the windows behind it only on that screen,
    and the glass showed wallpaper where they should be until it rendered again."""
    js = (EXT / "glass.js").read_text()
    assert "global.stage.connect('before-paint', (_s, view) => (painting.view = view))" in js
    assert "global.stage.connect('after-paint', () => (painting.view = null))" in js
    # Followed only while there is glass, and let go with the last pane.
    assert "followPainting(true);" in js
    assert "followPainting(panes.size > 0);" in js
    start = js.index("const home = (flags & dirty)")
    block = js[start:start + 600]
    assert "(this._offHome ?? 0) < 3" in block      # never more than three skips in a row
    assert "a?.queueFull?.(home);" in block
    assert "super.vfunc_paint(node, paintContext, flags & ~dirty);" in block
    # A failure there must never stop the glass rendering.
    assert "return null;     // never stop the glass from rendering" in js
