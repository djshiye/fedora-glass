"""Popups (tooltips, dropdown lists, popovers) draw real glass through one shared
component. These checks read the QML source, so they run without a GUI."""

from __future__ import annotations

import re
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
    assert "tintAlphaDark: 0.80" in tip and "tintAlphaLight: 0.82" in tip
