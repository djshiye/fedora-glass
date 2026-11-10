"""After an upgrade GNOME keeps running the old glass extension until the next login (it
can't load new code mid-session). The new look's Shell parts need the new glass behind
them, so they wait for that login, as on a first Apply, and the app says to restart."""
from __future__ import annotations

from pathlib import Path

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import __version__
from fedoraglass import settings as settings_mod
from fedoraglass.engine import WAITING, pending_path, read_pending
from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from test_update_after_upgrade import _age
from test_wait_for_glass import ARC, DTP, desktop, statuses

SHELL_PARTS = {"shell", "dash-to-panel", "arcmenu", "spawn"}


def _older(v: str) -> str:
    parts = [int(p) for p in v.split(".")]
    parts[-1] -= 1
    if parts[-1] < 0:
        parts[-2], parts[-1] = parts[-2] - 1, 0
    return ".".join(map(str, parts))


OLD = _older(__version__)


@pytest.mark.parametrize("running, kind", [
    (None, "running"),          # GNOME doesn't say: as before
    (__version__, "running"),
    (OLD, "old"),
    ("99.0", "running"),        # a newer one (the app went back a version): as before
    ("dev", "running"),         # can't be compared: as before
])
def test_the_running_version_counts(fake_env, running, kind):
    if running is not None:
        fake_env.ext_version[rg.UUID] = running
    st = ts.glass_state(fake_env)
    assert st.kind == kind
    assert ts.GlassEffects.running(fake_env) is (kind == "running")


def test_a_glass_that_is_not_running_is_not_old(fake_env):
    fake_env.glass_loaded = False
    fake_env.ext_version[rg.UUID] = OLD
    assert ts.glass_state(fake_env).kind == "not-started"


def _upgraded(env):
    """Applied with the old version, then `dnf upgrade`: the old glass still runs."""
    engine = desktop(env)
    settings_mod.save(Settings(frost=0.2))
    engine.apply(Settings(frost=0.2))
    _age(env, OLD)
    env.ext_version[rg.UUID] = OLD
    settings_mod.save(Settings(frost=0.9))       # what the new version's look is made from
    return engine


def test_after_an_upgrade_the_shell_parts_wait_for_the_new_glass(fake_env):
    engine = _upgraded(fake_env)
    css = ts.GnomeShell().css_path(fake_env)
    before_css = css.read_text()
    before_dtp = dict(fake_env.gs[(DTP, None)])
    assert cli.update_after_upgrade(engine) is True
    # The new glass extension is on disk for the next login ...
    assert cli.installed_glass_version(engine) == __version__
    # ... but the Shell theme, Dash to Panel, ArcMenu and Spawn keep the old look over the old glass.
    assert css.read_text() == before_css
    assert fake_env.gs[(DTP, None)] == before_dtp
    assert read_pending() == SHELL_PARTS


def test_the_watcher_does_not_wait_for_a_glass_that_comes_at_the_next_login(fake_env):
    engine = _upgraded(fake_env)
    cli.update_after_upgrade(engine)
    naps = []
    assert cli.finish_pending(engine, wait_s=120, step_s=2, sleep=naps.append) is False
    assert naps == [], "waited two minutes for a glass that only comes at the next login"
    assert read_pending() == SHELL_PARTS
    # The next login: GNOME runs the new glass, and the watcher finishes the Shell parts.
    fake_env.ext_version[rg.UUID] = __version__
    css = ts.GnomeShell().css_path(fake_env)
    before = css.read_text()
    assert cli.finish_pending(engine, sleep=naps.append) is True
    assert css.read_text() != before
    assert not pending_path().exists()
    assert "'theirs'" not in fake_env.gs[(ARC, None)].values()


def test_an_apply_over_the_old_glass_says_restart(fake_env):
    engine = _upgraded(fake_env)
    got = statuses(engine.apply(Settings(frost=0.9)))
    for tid in SHELL_PARTS:
        assert got[tid] == ("info", WAITING)
    assert got["glass"][0] == "applied"
    kind, note, _ = ts.glass_problem(fake_env)
    assert kind == "old" and note == ts.UPDATE_WAITS


def test_without_a_version_from_gnome_everything_applies_as_before(fake_env):
    engine = _upgraded(fake_env)
    del fake_env.ext_version[rg.UUID]
    assert cli.update_after_upgrade(engine) is True
    assert not pending_path().exists()
    assert ts.glass_problem(fake_env) == ("", "", "")


def test_the_upgrade_brings_back_only_the_parts_the_user_applied(fake_env):
    """Applied with Dash to Panel and ArcMenu left out (`--only`): the upgrade leaves them out too."""
    engine = desktop(fake_env)
    settings_mod.save(Settings())
    engine.apply(Settings(), only={"shell", "glass", "spawn"})
    _age(fake_env, OLD)
    before_dtp, before_arc = dict(fake_env.gs[(DTP, None)]), dict(fake_env.gs[(ARC, None)])
    assert cli.update_after_upgrade(engine) is True
    assert cli.installed_glass_version(engine) == __version__
    assert fake_env.gs[(DTP, None)] == before_dtp
    assert fake_env.gs[(ARC, None)] == before_arc


def test_the_glass_note_says_restart_to_finish_the_update(fake_env):
    fake_env.ext_version[rg.UUID] = OLD
    from fedoraglass.engine import Engine
    ctx = Engine(fake_env, ts.TARGETS).context(Settings())
    assert ts.UPDATE_WAITS in ts.GlassEffects().live_notes(ctx)


def test_the_app_shows_restart_to_finish_the_update(qml, tmp_path):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    b = probe.create().property("b")
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    banner = win.findChild(QObject, "glassBanner")
    assert banner.property("shown") is False
    try:
        b._problem = ("old", ts.UPDATE_WAITS, "")
        b.targetsChanged.emit()
        assert banner.property("shown") is True
        assert win.findChild(QObject, "glassNote").property("text") == ts.UPDATE_WAITS
    finally:
        b._problem = ("", "", "")
        b.targetsChanged.emit()
        win.deleteLater()
