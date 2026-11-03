"""Safe mode: the extension turns the glass off when it keeps failing, and the app shows
why with one button that turns it back on."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from liquidglass.render import glass as rg

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
EXT = ROOT / "liquidglass/data/extension/liquid-glass@djshiye.github.io"


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_safe_mode_turns_on_and_off_in_the_extension():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/safety.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_safety_is_installed_and_wired_in():
    assert "safety.js" in rg.FILES
    ext = (EXT / "extension.js").read_text()
    assert "new Safety(" in ext and "this._safety?.destroy()" in ext
    # Every signal handler connected through Signals reports instead of throwing.
    assert "guarded(signal, fn)" in (EXT / "common.js").read_text()


# ---- the app ---------------------------------------------------------------------------
@pytest.fixture
def backend(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtGui")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from liquidglass.env import Env
    from liquidglass.gui.backend import Backend
    QGuiApplication.instance() or QGuiApplication([])
    for k in ("CONFIG", "CACHE", "STATE", "DATA"):
        monkeypatch.setenv(f"XDG_{k}_HOME", str(tmp_path / k.lower()))

    def make():
        return Backend(env=Env(home=tmp_path), engine_factory=lambda: None,
                       settings_path=tmp_path / "config/liquid-glass/settings.json", ui_dark=True, start=False)
    return make, tmp_path


def _state(home: Path, **data) -> Path:
    p = home / "cache/liquid-glass/safe-mode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    return p


def test_no_note_while_the_glass_runs(backend):
    make, home = backend
    assert make().property("safeMode") is False
    _state(home, tripped=False, reason="")
    assert make().property("safeMode") is False


@pytest.mark.parametrize("reason,words", [("errors", "it hit errors"),
                                          ("restarts", "GNOME Shell restarted twice"),
                                          ("start", "it could not start"),
                                          ("<b>odd</b>", "it hit errors")])
def test_the_note_says_why_in_plain_words(backend, reason, words):
    make, home = backend
    _state(home, tripped=True, reason=reason)
    b = make()
    assert b.property("safeMode") is True
    note = b.property("safeModeNote")
    assert words in note and "<" not in note
    assert note.endswith("Your desktop works as usual.")


def test_a_linked_or_huge_state_file_is_not_read(backend):
    make, home = backend
    real = home / "elsewhere.json"
    real.write_text(json.dumps({"tripped": True}))
    p = home / "cache/liquid-glass/safe-mode.json"
    p.parent.mkdir(parents=True)
    p.symlink_to(real)
    assert make().property("safeMode") is False
    p.unlink()
    p.write_text(json.dumps({"tripped": True, "pad": "x" * 20000}))
    assert make().property("safeMode") is False


def test_turning_glass_back_on_writes_a_private_request(backend):
    make, home = backend
    _state(home, tripped=True, reason="errors")
    b = make()
    b.resumeGlass()
    req = home / "config/liquid-glass/safe-mode-reset.json"
    data = json.loads(req.read_text())
    assert set(data) == {"id"} and len(data["id"]) == 16 and int(data["id"], 16) >= 0
    assert stat.S_IMODE(req.stat().st_mode) == 0o600
    first = data["id"]
    b.resumeGlass()
    assert json.loads(req.read_text())["id"] != first, "each click is a new request"
    assert not list(req.parent.glob("*.tmp"))
    # The extension clears its state; the app notices.
    seen = []
    b.safeModeChanged.connect(lambda: seen.append(1))
    _state(home, tripped=False)
    b._poll_safe_mode()
    assert b.property("safeMode") is False and seen == [1]


def test_the_banner_shows_only_in_safe_mode(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent

    from liquidglass.gui import app as gui_app
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport LiquidGlass.Core\nQtObject { property var b: Backend }", QUrl())
    b = probe.create().property("b")
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    from PySide6.QtCore import QObject
    banner = win.findChild(QObject, "safeBanner")
    assert banner.property("shown") is False
    try:
        b._safe = {"reason": "restarts", "resetId": ""}
        b.safeModeChanged.emit()
        assert banner.property("shown") is True
        assert "restarted twice" in win.findChild(QObject, "safeNote").property("text")
        assert win.findChild(QObject, "resumeGlass").property("text") == "Turn glass back on"
    finally:
        b._safe = {}
        b.safeModeChanged.emit()
        win.deleteLater()
