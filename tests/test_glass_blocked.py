"""When the glass extension can't start and a restart won't change that, the app says
the real reason (extensions switched off, a GNOME this version doesn't support yet, an
error), with a fix where there is one, and Apply doesn't wait for a glass that won't come."""
from __future__ import annotations

from pathlib import Path

import pytest

from fedoraglass import __main__ as cli
from fedoraglass.engine import pending_path, read_pending
from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from test_glass_version import OLD
from test_wait_for_glass import ARC, DTP, desktop, statuses

SHELL_PARTS = ("shell", "dash-to-panel", "arcmenu", "spawn")
GS = ("org.gnome.shell", None)


def _glass_on(env):
    from test_shell import switch_on
    switch_on(env, rg.UUID)


def test_extensions_switched_off(fake_env):
    fake_env.gs[GS] = {"disable-user-extensions": "true"}
    assert ts.glass_state(fake_env).kind == "off"
    assert ts.glass_blocked(fake_env) == "off"
    assert ts.glass_problem(fake_env) == ("off", ts.GLASS_BLOCKED["off"], "")
    assert ts.glass_problem(fake_env, wanted=False) == ("", "", ""), "glass part off: nothing to say about it"


@pytest.mark.parametrize("state, kind", [("4.0", "out-of-date"), ("3.0", "error")])
def test_out_of_date_and_error_count_only_for_the_wanted_glass(fake_env, state, kind):
    fake_env.ext_info[rg.UUID] = (state, "")
    assert ts.glass_state(fake_env).kind == "not-started", "GNOME marks a switched-off one too"
    assert ts.glass_blocked(fake_env) == ""
    _glass_on(fake_env)
    assert ts.glass_state(fake_env).kind == kind
    assert ts.glass_blocked(fake_env) == kind


def test_the_error_text_is_kept_for_details(fake_env):
    _glass_on(fake_env)
    fake_env.ext_info[rg.UUID] = ("3.0", "TypeError: this._panel is null")
    kind, note, details = ts.glass_problem(fake_env)
    assert (kind, note) == ("error", ts.GLASS_BLOCKED["error"])
    assert details == "TypeError: this._panel is null"


@pytest.mark.parametrize("state", ["3.0", "4.0"])
def test_an_older_version_failing_is_fixed_by_the_restart(fake_env, state):
    """After an upgrade the old code (or its list of GNOME versions) failed: the new
    version loads at the next login, so the parts wait for it."""
    _glass_on(fake_env)
    fake_env.ext_info[rg.UUID] = (state, "old bug")
    fake_env.ext_version[rg.UUID] = OLD
    assert ts.glass_state(fake_env).kind == "old"
    assert ts.glass_blocked(fake_env) == ""
    assert ts.glass_problem(fake_env)[0] == "old"


def test_safe_mode_is_not_mixed_up_with_these(fake_env):
    """In its own safe mode the extension runs (GNOME says so) and says it in its own file;
    the app has its own note for that."""
    _glass_on(fake_env)
    assert ts.glass_problem(fake_env) == ("", "", "")


@pytest.mark.parametrize("why", ["off", "out-of-date", "error"])
def test_apply_leaves_the_shell_parts_as_they_are_instead_of_waiting(fake_env, why):
    engine = desktop(fake_env)
    if why == "off":
        fake_env.gs[GS]["disable-user-extensions"] = "true"
    else:
        _glass_on(fake_env)
        fake_env.ext_info[rg.UUID] = ("4.0" if why == "out-of-date" else "3.0", "boom")
    got = statuses(engine.apply(Settings()))
    for tid in SHELL_PARTS:
        assert got[tid] == ("skipped", ts.GLASS_BLOCKED_PART[why]), tid
    assert got["glass"][0] == "applied", "the glass extension is still put in place"
    assert not pending_path().exists(), "left waiting for a glass that won't come"
    assert set(fake_env.gs[(ARC, None)].values()) == {"'theirs'"}
    assert set(fake_env.gs[(DTP, None)].values()) <= {"'theirs'", "true"}


def test_the_watcher_does_not_wait_for_a_glass_that_cant_start(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    assert read_pending()
    fake_env.gs[GS]["disable-user-extensions"] = "true"       # switched off before the restart
    naps = []
    assert cli.finish_pending(engine, wait_s=120, step_s=2, sleep=naps.append) is False
    assert naps == []
    assert read_pending(), "kept: switching extensions on again and restarting finishes them"


def test_a_glass_still_starting_is_waited_for_as_before(fake_env):
    engine = desktop(fake_env)
    fake_env.glass_loaded = False
    engine.apply(Settings())
    naps = []
    assert cli.finish_pending(engine, wait_s=4, step_s=2, sleep=naps.append) is False
    assert naps == [2, 2]


def test_the_glass_note_gives_the_reason_not_restart(fake_env):
    from fedoraglass.engine import Engine
    fake_env.gs[GS] = {"disable-user-extensions": "true"}
    ctx = Engine(fake_env, ts.TARGETS).context(Settings())
    notes = ts.GlassEffects().live_notes(ctx)
    assert ts.GLASS_BLOCKED["off"] in notes
    assert not any("Restart your PC" in n for n in notes)


# ---- the app ------------------------------------------------------------------------
@pytest.fixture
def backend(fake_env):
    QtGui = pytest.importorskip("PySide6.QtGui")
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    from fedoraglass.engine import Engine
    from fedoraglass.gui.backend import Backend
    b = Backend(env=fake_env, engine_factory=lambda: Engine(fake_env, ts.TARGETS),
                settings_path=fake_env.config / "liquid-glass/settings.json", ui_dark=True, start=False)
    yield b
    b.waitIdle()
    _KEEP.append(b)


_KEEP: list = []        # backends live for the whole run (see test_gui_backend)


def test_the_app_switches_extensions_on_only_when_asked(backend, fake_env):
    fake_env.gs[GS] = {"disable-user-extensions": "true"}
    backend.refreshTargets()
    assert backend.waitIdle()
    assert backend.property("glassProblem") == "off" and backend.property("glassBlocked") is True
    assert fake_env.gs[GS]["disable-user-extensions"] == "true", "changed without a click"
    said = []
    backend.noticed.connect(said.append)
    backend.switchExtensionsOn()
    assert fake_env.gs[GS]["disable-user-extensions"] == "false"
    assert said == ["Extensions are on again. Press Apply to finish your look."]
    assert backend.waitIdle()
    assert backend.property("glassProblem") == ""


def test_the_app_copies_the_error_details(backend, fake_env):
    from PySide6.QtGui import QGuiApplication
    _glass_on(fake_env)
    fake_env.ext_info[rg.UUID] = ("3.0", "TypeError: boom")
    backend.refreshTargets()
    assert backend.waitIdle()
    assert backend.property("glassProblem") == "error"
    assert backend.property("glassProblemDetails") == "TypeError: boom"
    said = []
    backend.noticed.connect(said.append)
    backend.copyGlassDetails()
    assert QGuiApplication.clipboard().text() == "TypeError: boom"
    assert said == ["Error details copied"]


@pytest.mark.parametrize("kind, button", [("off", "extensionsOn"), ("error", "copyGlassDetails"),
                                          ("out-of-date", None)])
def test_the_banner_has_its_own_message_and_fix(qml, kind, button):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    b = probe.create().property("b")
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    try:
        b._problem = (kind, ts.GLASS_BLOCKED[kind], "details" if kind == "error" else "")
        b.targetsChanged.emit()
        assert win.findChild(QObject, "glassBanner").property("shown") is True
        assert win.findChild(QObject, "glassNote").property("text") == ts.GLASS_BLOCKED[kind]
        for name in ("extensionsOn", "copyGlassDetails"):
            assert win.findChild(QObject, name).property("wanted") is (name == button), name
    finally:
        b._problem = ("", "", "")
        b.targetsChanged.emit()
        win.deleteLater()


@pytest.mark.parametrize("kind, title", [
    ("", "Applied. Restart your PC to finish"),             # a first Apply: as before
    ("old", "Applied. Restart your PC to finish"),
    ("off", "Applied, but the glass can't start"),
    ("error", "Applied, but the glass can't start"),
])
def test_the_results_say_restart_only_when_a_restart_helps(qml, kind, title):
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlComponent
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    b = probe.create().property("b")
    comp = QQmlComponent(qml)
    comp.setData(b"import QtQuick\nimport FedoraGlass\nResultsSheet {}", QUrl())
    sheet = comp.create()
    assert sheet is not None, comp.errorString()
    try:
        b._glass_live = False
        b._problem = (kind, ts.UPDATE_WAITS if kind == "old" else ts.GLASS_BLOCKED.get(kind, ""), "")
        b.targetsChanged.emit()
        sheet.setProperty("results", [{"id": "glass", "name": "Fedora Glass effects", "status": "applied", "message": ""},
                                      {"id": "shell", "name": "GNOME Shell", "status": "skipped",
                                       "message": ts.GLASS_BLOCKED_PART.get(kind, "")}])
        assert sheet.property("title") == title
        if kind:
            assert sheet.property("subtitle") == b.property("glassProblemNote")
    finally:
        b._problem = ("", "", "")
        b.targetsChanged.emit()
        sheet.deleteLater()
