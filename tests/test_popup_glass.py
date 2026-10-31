"""Popups (tooltips, dropdown lists, popovers) draw real glass through one shared
component. These checks read the QML source, so they run without a GUI."""

from __future__ import annotations

import re

import pytest
from pathlib import Path

QML = Path(__file__).resolve().parents[1] / "liquidglass/gui/qml"
LG = QML / "LiquidGlass"


def _src(name: str) -> str:
    return (LG / name).read_text()


def test_tooltip_and_dropdown_use_the_shared_glass():
    for name in ("LgToolTip.qml", "LgDropdown.qml", "ColorPicker.qml"):
        assert re.search(r"background:\s*PopupGlass\s*\{", _src(name)), name


def test_popup_glass_builds_on_glass_surface_and_the_shared_backdrop():
    src = _src("PopupGlass.qml")
    assert "GlassSurface" in src
    assert "Theme.backdrop" in src
    assert "mapToItem" in src               # the rect under the popup, in backdrop coordinates
    assert "live: root.shown" in src        # no capture while closed
    assert "!root.glassy" in src            # opaque fallback without a backdrop


def test_no_stock_tooltip_outside_lgtooltip():
    for f in QML.rglob("*.qml"):
        if f.name == "LgToolTip.qml":
            continue
        assert not re.search(r"\bC\.ToolTip\b|\bToolTip\s*\{", f.read_text()), f.name


def test_qmldir_registers_popup_glass():
    assert re.search(r"^PopupGlass 1\.0 PopupGlass\.qml$", _src("qmldir"), re.M)
    assert (LG / "PopupGlass.qml").exists()


def test_theme_has_radii_and_backdrop():
    src = _src("Theme.qml")
    for name, px in (("rXs", 8), ("rS", 12), ("rM", 16), ("rL", 24)):
        assert re.search(rf"readonly property int {name}: {px}\b", src), name
    assert "property Item backdrop" in src


def test_main_publishes_the_content_root_as_backdrop():
    src = (QML / "Main.qml").read_text()
    assert re.search(r"Binding\s*\{\s*target:\s*Theme;\s*property:\s*\"backdrop\";\s*value:\s*frame\s*\}", src)


def test_tooltip_text_follows_theme_and_tint_is_heavy():
    tip = _src("LgToolTip.qml")
    assert "color: Theme.text" in tip and "#f4f5f9" not in tip
    assert re.search(r"blurRadius:\s*(3[2-9]|[4-9]\d)", tip)



def _lum(rgb):
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = sorted((_lum(a), _lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.mark.parametrize("name", ["LgToolTip.qml", "LgDropdown.qml", "ColorPicker.qml"])
def test_popup_text_reads_over_the_worst_backdrop(name):
    """The tint over pure white (dark mode) or pure black (light mode) still gives
    Theme.text at least 4.5:1, even though more of the glass now shows through."""
    src = _src(name)
    dark = float(re.search(r"tintAlphaDark:\s*([\d.]+)", src).group(1))
    light = float(re.search(r"tintAlphaLight:\s*([\d.]+)", src).group(1))
    tint_d, tint_l = (0.075, 0.08, 0.10), (0.985, 0.987, 0.993)       # PopupGlass.qml
    text_d, text_l = (0xf2 / 255, 0xf3 / 255, 0xf7 / 255), (0x17 / 255, 0x18 / 255, 0x1d / 255)
    over_white = tuple(t * dark + 1 * (1 - dark) for t in tint_d)
    over_black = tuple(t * light for t in tint_l)
    assert _contrast(text_d, over_white) >= 4.5
    assert _contrast(text_l, over_black) >= 4.5
    assert dark < 0.85 and light < 0.9, "keep it glass: some backdrop must show through"
