"""Paused from Quick Settings: the Glass tile pauses the glass for the session, the
extension says so in ~/.cache/liquid-glass/paused.json (pausestate.js), and the app shows
it plainly, with one button that resumes the glass, instead of acting as if it shows."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from fedoraglass.render import glass as rg

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"
QML = ROOT / "fedoraglass/gui/qml"


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_extension_says_and_clears_the_pause():
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/pause-state.test.mjs",
                        "tests/js/extension-pause.test.mjs", "tests/js/quick-toggle.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


def test_the_pause_state_is_installed_and_wired_in():
    assert "pausestate.js" in rg.FILES
    ext = (EXT / "extension.js").read_text()
    assert "new PauseState(" in ext and "this._pauseState?.destroy()" in ext
    assert "this._pauseState?.set(paused)" in ext


def test_safe_mode_and_a_pause_are_said_apart():
    """"Paused" is the user's own pause; safe mode is the glass turning itself off."""
    backend = (ROOT / "fedoraglass/gui/backend.py").read_text()
    assert "Glass is paused because" not in backend
    assert "Glass turned itself off because" in backend
    assert "pauses itself" not in (QML / "Main.qml").read_text()


# ---- the app ---------------------------------------------------------------------------
@pytest.fixture
def backend(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtGui")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from fedoraglass.env import Env
    from fedoraglass.gui.backend import Backend
    QGuiApplication.instance() or QGuiApplication([])
    for k in ("CONFIG", "CACHE", "STATE", "DATA"):
        monkeypatch.setenv(f"XDG_{k}_HOME", str(tmp_path / k.lower()))

    def make():
        return Backend(env=Env(home=tmp_path), engine_factory=lambda: None,
                       settings_path=tmp_path / "config/liquid-glass/settings.json", ui_dark=True, start=False)
    return make, tmp_path


def _paused(home: Path, text: str) -> Path:
    p = home / "cache/liquid-glass/paused.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return p


def test_not_paused_without_the_file_or_when_it_says_so(backend):
    make, home = backend
    assert make().property("glassPaused") is False
    _paused(home, json.dumps({"version": 1, "paused": False}))
    assert make().property("glassPaused") is False
    _paused(home, json.dumps({"version": 1, "paused": "yes"}))
    assert make().property("glassPaused") is False, "only true counts"
    _paused(home, "{not json")
    assert make().property("glassPaused") is False


def test_paused_when_the_extension_says_so(backend):
    make, home = backend
    _paused(home, json.dumps({"version": 1, "paused": True}))
    assert make().property("glassPaused") is True


def test_a_linked_or_huge_pause_file_is_not_read(backend):
    make, home = backend
    real = home / "elsewhere.json"
    real.write_text(json.dumps({"paused": True}))
    p = home / "cache/liquid-glass/paused.json"
    p.parent.mkdir(parents=True)
    p.symlink_to(real)
    assert make().property("glassPaused") is False
    p.unlink()
    p.write_text(json.dumps({"paused": True, "pad": "x" * 2000}))
    assert make().property("glassPaused") is False


def test_safe_mode_wins_over_a_pause(backend):
    make, home = backend
    _paused(home, json.dumps({"paused": True}))
    s = home / "cache/liquid-glass/safe-mode.json"
    s.write_text(json.dumps({"tripped": True, "reason": "errors"}))
    b = make()
    assert b.property("safeMode") is True and b.property("glassPaused") is False


def test_resume_writes_a_private_request_and_the_app_notices(backend):
    make, home = backend
    p = _paused(home, json.dumps({"version": 1, "paused": True}))
    b = make()
    b.resumePausedGlass()
    req = home / "config/liquid-glass/resume-glass.json"
    data = json.loads(req.read_text())
    assert set(data) == {"id"} and len(data["id"]) == 16 and int(data["id"], 16) >= 0
    assert stat.S_IMODE(req.stat().st_mode) == 0o600
    first = data["id"]
    b.resumePausedGlass()
    assert json.loads(req.read_text())["id"] != first, "each click is a new request"
    assert not list(req.parent.glob(".*.tmp"))
    assert not (home / "config/liquid-glass/safe-mode-reset.json").exists(), "not a safe mode reset"
    # The extension resumes and says so; the app notices.
    seen = []
    b.glassPausedChanged.connect(lambda: seen.append(1))
    p.write_text(json.dumps({"version": 1, "paused": False}))
    b._poll_safe_mode()
    assert b.property("glassPaused") is False and seen == [1]
    b._poll_safe_mode()
    assert seen == [1], "said once"


def test_check_speed_does_nothing_while_paused(backend):
    make, home = backend
    _paused(home, json.dumps({"paused": True}))
    b = make()
    b._glass_live = True
    b.checkSpeed()
    assert b.property("speedState") == "idle"
    assert not (home / "config/liquid-glass/speed-check.json").exists(), "no check the glass can't answer"


def _probe(qml):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    return probe.create().property("b")


def test_the_banner_shows_the_pause_and_resume_asks_the_extension(qml, tmp_path, monkeypatch):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    b = _probe(qml)
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    banner = win.findChild(QObject, "pauseBanner")
    assert banner.property("shown") is False
    asked = []
    with monkeypatch.context() as mp:
        mp.setattr(b, "_ask_extension", lambda name: asked.append(name) or True)
        try:
            b._paused = True
            b.glassPausedChanged.emit()
            assert banner.property("shown") is True
            assert win.findChild(QObject, "pauseNote").property("text").startswith("Glass is paused from Quick Settings")
            assert win.findChild(QObject, "safeBanner").property("shown") is False, "not said as safe mode"
            button = win.findChild(QObject, "resumePaused")
            assert button.property("text") == "Resume"
            button.clicked.emit()
            assert asked == ["resume-glass.json"]
        finally:
            b._paused = False
            b.glassPausedChanged.emit()
            win.deleteLater()


def test_check_speed_and_results_say_the_glass_is_paused(qml):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    b = _probe(qml)
    speed = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "FedoraGlass/SpeedCard.qml")))
    card = speed.create()
    assert card is not None, speed.errorString()
    results = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "FedoraGlass/ResultsSheet.qml")))
    sheet = results.create()
    assert sheet is not None, results.errorString()
    was_live = b._glass_live
    try:
        b._glass_live = True
        b.targetsChanged.emit()
        check = card.findChild(QObject, "speedCheck")
        assert check.property("enabled") is True
        sheet.setProperty("results", [{"id": "glass", "name": "Glass", "status": "applied", "message": ""}])
        assert sheet.property("title") == "Fedora Glass is on"
        b._paused = True
        b.glassPausedChanged.emit()
        assert check.property("enabled") is False
        assert "paused from Quick Settings" in check.property("tip")
        assert sheet.property("title") == "Your new look is saved", "not claimed as showing"
        assert "once you resume it" in sheet.property("subtitle")
        assert sheet.property("glassOff") is True
        assert sheet.findChild(QObject, "resultsResume").property("text") == "Resume glass"
    finally:
        b._paused = False
        b._glass_live = was_live
        b.glassPausedChanged.emit()
        b.targetsChanged.emit()
        card.deleteLater()
        sheet.deleteLater()
