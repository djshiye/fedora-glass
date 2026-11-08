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
    assert b.property("targetStates") == {}
    b.setTargetEnabled("gtk4", False)
    assert b.property("targetStates") == {"gtk4": False}
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
    assert pv.property("menuOpen")
    pv.setProperty("scene", "quicksettings")
    assert not pv.property("menuOpen")
    closeup = pv.findChild(QQuickItem, "edgeCloseUp")
    assert closeup is not None
    pv.setProperty("closeUp", True)
    assert pv.property("closeUp")
