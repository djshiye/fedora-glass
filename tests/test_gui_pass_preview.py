"""The settings app's live preview shows what Apply gives (PreviewDesktop.qml, GlassSurface.qml,
LockPreview.qml): colour bleed as on the desktop, dates and times in the app's language, and
the same blur for each part as the extension draws."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtGui")
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401 - the window comes back as a QQuickWindow

ROOT = Path(__file__).resolve().parents[1]


def _component(qml, source: bytes, name: str):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    comp = QQmlComponent(qml)
    comp.setData(source, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / name)))
    assert comp.status() == QQmlComponent.Status.Ready, comp.errorString()
    obj = comp.create()
    assert obj is not None, comp.errorString()
    _keep.append(comp)      # what it made lives only as long as its component
    return obj


_keep: list = []


def _settle(ms: int = 300) -> None:
    from PySide6.QtCore import QCoreApplication, QElapsedTimer
    t = QElapsedTimer()
    t.start()
    while t.elapsed() < ms:
        QCoreApplication.processEvents()


# ---- colour bleed ---------------------------------------------------------------------------

# The glass is a shader, which Qt's offscreen platform never draws (it renders in software):
# this draws it on a virtual X display, with Mesa's software OpenGL, as the screenshots do.
DRAW = r"""
import sys
from PySide6.QtCore import Property, QObject, QTimer, QUrl
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
from PySide6.QtQuick import QSGRendererInterface


class Ui(QObject):     # what Theme reads from the app
    uiDark = Property(bool, lambda self: True, constant=True)
    uiAccent = Property(QColor, lambda self: QColor("#3584e4"), constant=True)
    uiAccentFg = Property(QColor, lambda self: QColor("white"), constant=True)


app = QGuiApplication([])
ui = Ui()
qmlRegisterSingletonInstance(Ui, "FedoraGlass.Core", 1, 0, "Backend", ui)
engine = QQmlApplicationEngine()
engine.addImportPath(sys.argv[1])
engine.loadData(sys.argv[2].encode(), QUrl.fromLocalFile(sys.argv[1] + "/draw-test.qml"))
win = engine.rootObjects()[0]
def grab():
    if win.rendererInterface().graphicsApi() == QSGRendererInterface.GraphicsApi.Software:
        print("software")
    else:
        img = win.grabWindow()
        print(" ".join(img.pixelColor(int(x), int(y)).name() for x, y in
                       (p.split(",") for p in sys.argv[3:])))
    app.quit()
QTimer.singleShot(1500, grab)
app.exec()
"""


def _draw(source: str, *points: tuple[int, int]) -> list[str]:
    """The colours at `points` of a window drawn from `source`, with real shaders."""
    if not shutil.which("xvfb-run"):
        pytest.skip("needs xvfb-run to draw the glass shader")
    from fedoraglass.gui import app as gui_app
    env = {k: v for k, v in os.environ.items() if not k.startswith(("QT_", "DISPLAY", "WAYLAND"))}
    env.update(QT_QPA_PLATFORM="xcb", LIBGL_ALWAYS_SOFTWARE="1")
    out = subprocess.run(["xvfb-run", "-a", sys.executable, "-c", DRAW, str(gui_app.QML_DIR), source,
                          *(f"{x},{y}" for x, y in points)],
                         capture_output=True, text=True, timeout=90, env=env, cwd=ROOT)
    last = out.stdout.strip().splitlines()[-1:] or [""]
    if last[0] == "software" or out.returncode:
        pytest.skip(f"no OpenGL to draw the glass shader: {out.stderr.strip()[-300:]}")
    return last[0].split()


def test_an_accent_button_on_bleeding_glass_keeps_its_own_colour():
    """On the desktop the light a menu's content casts lies under the content (glass.js draws
    it below the theme's veil and the items): a Quick Settings toggle stays the accent blue,
    not a glowing cyan. Beside it, the glass still catches its light."""
    source = """
import QtQuick
import QtQuick.Window
import FedoraGlass
Window {
    width: 240; height: 160; visible: true; color: "black"
    Item {
        anchors.fill: parent
        Rectangle { id: back; anchors.fill: parent; color: "#202028" }
        GlassSurface {
            x: 20; y: 20; width: 200; height: 120
            radius: 16
            backdrop: back
            bleed: BLEED
            Rectangle { x: 50; y: 30; width: 100; height: 60; radius: 12; color: "#3584e4" }
        }
    }
}
"""
    centre, beside = _draw(source.replace("BLEED", "1"), (120, 80), (64, 80))
    assert centre == "#3584e4"
    _, plain = _draw(source.replace("BLEED", "0"), (120, 80), (64, 80))
    assert beside != plain      # the bleed still lights the glass around the button


@pytest.fixture
def preview(qml):
    pv = _component(qml, b"""
import QtQuick
import FedoraGlass
import FedoraGlass.Core
PreviewDesktop {
    width: 960; height: 540
    t: Backend.tokens
    dock: [{ id: "org.gnome.Nautilus.desktop", name: "Files", icon: "", running: true }]
    readonly property var be: Backend
}
""", "preview-test.qml")
    yield pv
    pv.deleteLater()


def _items(root):
    todo, out = [root], []
    while todo:
        it = todo.pop()
        out.append(it)
        todo.extend(it.childItems())
    return out


def test_app_windows_in_the_preview_get_no_colour_bleed(preview):
    """The desktop gives app windows no colour bleed (render/glass.py _window_look): the Files
    folders and the terminal prompt keep their own colours. The panel and menus still bleed."""
    t = preview.property("be").property("tokens")
    assert t["bleed"] > 0.3 and t["parts"]["windows"]["bleed"] > 0.3
    glass = [it for it in _items(preview) if it.property("rimOnTop") is not None]
    windows = [g for g in glass if g.property("rimOnTop")]
    assert len(windows) == 2                    # Files and the terminal
    assert [w.property("bleed") for w in windows] == [0, 0]
    assert any(g.property("bleed") > 0.3 for g in glass if not g.property("rimOnTop"))
