"""Light glass keeps no grey frame: what its rounded edge mirrors may shade it only a little."""
import re
from pathlib import Path

EXT = Path(__file__).resolve().parent.parent / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def _reflection_block() -> str:
    src = (EXT / "glass.js").read_text()
    start = src.index("// Reflection of the real surroundings.")
    return src[start:src.index("// The caustic gathers", start)]


def test_a_dark_room_cannot_grey_the_edge_of_light_glass():
    """Up to 1.7.8 a light menu over a dark wallpaper had its whole bevel 10 steps greyer than
    its middle (207 against 217 of 255), ending in a line where the bevel starts: a picture
    frame inside the glass. The mirror may now darken light glass by 0.03 at most."""
    block = _reflection_block()
    m = re.search(r"if \(light_glass > 0\.5\)\s*seen = max\(seen, base - vec3\((0\.\d+)\)\);", block)
    assert m, "the mirror on light glass is no longer held near the glass's own lightness"
    assert float(m.group(1)) <= 0.03
    # After the brightness restraint (which it mirrors) and before the mirror is mixed in.
    assert block.index("seen = min(seen * (1.15") < m.start() < block.index("col.rgb = min(col.rgb * (1.0 - a) + seen")


def test_dark_glass_keeps_its_mirror():
    """The restraint is for light glass only: dark glass gets its edge from what it mirrors."""
    block = _reflection_block()
    assert block.count("base - vec3(") == 1
    assert "if (light_glass > 0.5)\n            seen = max(seen, base - vec3(0.03));" in block
