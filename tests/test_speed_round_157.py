"""Guards for the speed pass after 1.5.6 (window rim strips, menus that grow, cheaper shader
steps), read from the extension's source. The release checks measure the effect."""
from __future__ import annotations

import re
from pathlib import Path

EXT = Path(__file__).resolve().parents[1] / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def src(file: str) -> str:
    return (EXT / file).read_text()


def body(file: str, name: str) -> str:
    m = re.search(rf"\n    {re.escape(name)}\([^)]*\) {{\n(.*?)\n    }}\n", src(file), re.S)
    assert m, f"{name} not found in {file}"
    return m.group(1)


def code(text: str) -> str:
    return "\n".join(line.split("//")[0] for line in text.splitlines())


def shader() -> str:
    m = re.search(r"const SHADER = `(.*?)`;", src("glass.js"), re.S)
    return code(m.group(1))


def test_window_rim_is_four_strip_panes_not_clones_of_a_window_sized_pane():
    # One window-sized rim pane, shown through four clipped clones, made every change
    # behind a window copy the backdrop of the whole window and repaint all of it.
    w = code(src("windows.js"))
    assert "Clutter.Clone" not in w
    assert "new GlassPane('rim')" in w and "setPart(parts[i])" in w
    assert len(re.findall(r"\[\s*0, 0, W \+ 2 \* rp|\[0, rp \+ H - t|\[0, rp \+ t|\[rp \+ W - 4", w)) == 4


def test_part_shape_is_laid_out_over_the_whole_glass():
    s = shader()
    for u in ("shape_w", "shape_h", "shape_x", "shape_y"):
        assert f"uniform float {u};" in s
    assert "vec2 c = px + at0 - whole * 0.5;" in s
    # The texture is still read in the pane's own px.
    assert "clamp(px, vec2(0.5), size - vec2(0.5))" in s


def test_rim_returns_before_the_lens_for_all_but_its_outer_px():
    s = shader()
    early = s.index("if (mode > 2.5 && sd < -2.8)")
    assert early < s.index("vec2 L = lightDir(toPtr, h);") < s.index("float band = smoothstep(2.8, 1.2, inside);")


def test_ceiling_reads_the_area_only_above_its_knee():
    s = shader()
    i = s.index("if (ceil_y > OFF)")
    block = s[i:s.index("// Reflection of the real surroundings", i) if "// Reflection" in s else i + 2000]
    assert block.index("if (Yp > knee)") < block.index("at(px + vec2(6.0, 0.0))")


def test_content_light_skips_the_paint_search_where_there_is_no_colour():
    s = shader()
    i = s.index("bool nearRim = inside < bevel + 4.0;")
    loop = s.index("for (int i = 0; i < 8; i++)", i)
    cond = s[i:loop]
    assert "max(mc.r, max(mc.g, mc.b)) > 0.0005" in cond and "nearRim ? 0.0005 : 0.004" in cond
    assert "inside < bevel + 8.0" not in s


def test_moving_window_keeps_no_copy_of_its_glass_until_it_settles():
    w = code(body("windows.js", "_moved"))
    assert "p.setKeep(false)" in w and "SETTLE_MS" in w
    assert "p.setKeep(true)" in w
    assert "this._moved()" in code(body("windows.js", "_place"))
    assert "GLib.source_remove(this._settle)" in code(body("windows.js", "_release"))


def test_growing_menu_keeps_its_glass_in_place():
    f = code(body("follower.js", "sync"))
    assert "this._scaledRoom(target" in f
    assert "pane.place(glx, gly, gw, gh, radii, gx, gy, [sx, sy, w, h])" in f
    room = code(body("follower.js", "_scaledRoom"))
    assert "get_scale()" in room and "fits ?" in room
    # An inner shape change repaints the lens only; the pane is not moved.
    place = code(body("glass.js", "place"))
    assert "innerChanged" in place and "this._applyShape();" in place
