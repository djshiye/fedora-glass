"""Every setting shows in the Look page's preview as it changes (PreviewDesktop.qml).

The preview reads the tokens for looks; these tests cover the switches that act on
how the desktop draws (glass on/off, what shows through, quality, the Apps page's
switches, the terminal's own style and colours) and the scenes for parts that are
not on the desktop (Quick Settings, the calendar, the overview)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtGui")
from test_gui_backend import app, home, make_backend  # noqa: E402,F401


def test_backend_hands_the_preview_the_app_switches_and_terminal_colours(make_backend):
    b = make_backend()
    # Opt-in parts (the Firefox theme) are listed as off: for the preview a missing id is on.
    assert b.property("targetStates") == {"firefox-theme": False}
    b.setTargetEnabled("gtk4", False)
    assert b.property("targetStates") == {"firefox-theme": False, "gtk4": False}
    pal = b.property("terminalPalettes")
    assert set(pal) == {"dark", "light"}
    assert {"bg", "fg", "green", "blue", "yellow", "dim", "cursor"} <= set(pal["dark"])
    assert pal["dark"]["bg"].lightness() < pal["light"]["bg"].lightness()


def test_switching_the_glass_app_off_rebuilds_the_tokens(make_backend):
    """The theme draws the panel's edges itself once the glass is off; the preview must see it."""
    b = make_backend()
    assert b.property("tokens")["glass_panel_edges"] is True
    b.setTargetEnabled("glass", False)
    assert b.property("tokens")["glass_panel_edges"] is False


@pytest.fixture
def preview(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml)
    comp.setData(b"""
import QtQuick
import FedoraGlass
import FedoraGlass.Core
PreviewDesktop {
    width: 960; height: 540
    t: Backend.tokens
    dock: [{ id: "org.gnome.Nautilus.desktop", name: "Files", icon: "", running: true }]
    readonly property var be: Backend
}
""", QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "preview-test.qml")))
    assert comp.status() == QQmlComponent.Status.Ready, comp.errorString()
    obj = comp.create()
    assert obj is not None, comp.errorString()
    backend = obj.property("be")
    saved = {k: backend.property(k) for k in (
        "glassSeeWindows", "glassPanel", "glassMenus", "glassQuality", "terminalColors",
        "terminalFollowsStyle", "previewDark", "overviewOff")}
    yield obj, backend
    for k, v in saved.items():
        backend.setProperty(k, v)
    for target in ("glass", "gtk4", "ptyxis", "dash-to-panel", "shell"):
        backend.setTargetEnabled(target, True)
    obj.deleteLater()


def test_glass_switches_and_quality_reach_the_preview(preview):
    pv, b = preview
    assert pv.property("seeWindows") and pv.property("panelGlass") and pv.property("menuGlass")
    b.setProperty("glassSeeWindows", False)
    assert not pv.property("seeWindows")
    b.setProperty("glassSeeWindows", True)
    b.setProperty("glassQuality", "lightest")            # the lightest glass shows only the wallpaper
    assert not pv.property("seeWindows")
    b.setProperty("glassQuality", "full")
    assert pv.property("seeWindows")
    b.setProperty("glassPanel", False)
    b.setProperty("glassMenus", False)
    assert not pv.property("panelGlass") and not pv.property("menuGlass")


def test_app_switches_give_parts_gnome_s_own_look(preview):
    pv, b = preview
    b.setTargetEnabled("glass", False)
    assert not pv.property("glassOn") and not pv.property("panelGlass")
    b.setTargetEnabled("dash-to-panel", False)
    assert not pv.property("floating")                    # Dash to Panel's own bar along the edge
    b.setTargetEnabled("gtk4", False)
    assert pv.property("rWin") == 12                       # libadwaita's own corners


def test_terminal_follows_its_own_style_and_colours(preview):
    pv, b = preview
    b.setProperty("previewDark", False)
    b.setProperty("terminalFollowsStyle", False)
    assert pv.property("termDark")                         # Ptyxis stays dark by itself
    b.setProperty("terminalFollowsStyle", True)
    assert not pv.property("termDark")
    b.setProperty("terminalColors", False)
    assert not pv.property("glassTermColors")
    b.setProperty("terminalColors", True)
    assert pv.property("glassTermColors")


def test_scenes_show_the_part_being_edited(preview):
    from PySide6.QtQuick import QQuickItem
    pv, b = preview
    for scene in ("quicksettings", "calendar", "overview", "desktop"):
        pv.setProperty("scene", scene)
        assert pv.property("scene") == scene
    # The desktop scene opens the start menu when the desktop has one (ArcMenu, Spawn or
    # Dash to Panel's bar); on GNOME's own top bar without them there is none to show.
    assert pv.property("menuOpen") == pv.property("hasMenu")
    pv.setProperty("scene", "quicksettings")
    assert not pv.property("menuOpen")
    closeup = pv.findChild(QQuickItem, "edgeCloseUp")
    assert closeup is not None
    pv.setProperty("closeUp", True)
    assert pv.property("closeUp")


def test_how_liquid_slider_plays_a_press_on_the_preview_taskbar(preview):
    """Moving How liquid plays a short press-and-drag along the preview's taskbar, and the
    taskbar glass gives under it; the factor matches the extension's (render/glass.py)."""
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    from PySide6.QtQuick import QQuickItem

    from fedoraglass.render.glass import liquid_factor
    pv, b = preview
    saved = b.property("liquidStrength")
    try:
        for v in (0.0, 0.4, 1.0):
            b.setProperty("liquidStrength", v)
            assert abs(pv.property("liquid") - liquid_factor(v)) < 1e-6
        panel = pv.findChild(QQuickItem, "liquidPanel")
        assert panel is not None
        assert panel.property("liquid") == pv.property("liquid")
        t = QElapsedTimer()
        t.start()
        peak = 0.0
        while t.elapsed() < 1500:
            QCoreApplication.processEvents()
            peak = max(peak, panel.property("press"))
        assert peak > 0.8, peak                       # it pressed in
        # Very liquid: drawn out towards the pointer while it moves.
        assert pv.property("liquid") == 2.5
        t.restart()
        while t.elapsed() < 2500 and (pv.property("pressHeld") or panel.property("press") > 0.002):
            QCoreApplication.processEvents()
        assert panel.property("press") < 0.01          # and let go
    finally:
        b.setProperty("liquidStrength", saved)
