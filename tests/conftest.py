"""Shared fixtures: a throwaway home and an Env with fake gsettings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from liquidglass.env import Env, RunResult  # noqa: E402


class FakeEnv(Env):
    """Env with an in-memory gsettings store and a command log."""

    def __init__(self, home: Path):
        super().__init__(home=home)
        self.gs: dict[tuple[str, str | None], dict[str, str]] = {
            ("org.gnome.desktop.interface", None): {
                "color-scheme": "'prefer-dark'", "accent-color": "'blue'", "gtk-theme": "'Adwaita'",
            },
        }
        self.commands: list[list[str]] = []
        self.glass_loaded = True    # whether the fake GNOME Shell runs our glass extension

    def gsettings_keys(self, schema, path=None):
        return set(self.gs.get((schema, path), {}))

    def gsettings_get(self, schema, key, path=None):
        return self.gs.get((schema, path), {}).get(key)

    def gsettings_set(self, schema, key, value, path=None):
        self.gs.setdefault((schema, path), {})[key] = value
        return RunResult(0, "", "")

    def which(self, name):
        return f"/usr/bin/{name}"

    def extension_dirs(self):
        # Only the fake home: extensions installed on the machine running the tests don't count.
        return [self.data / "gnome-shell/extensions"]

    def run(self, argv, timeout=30):
        self.commands.append(list(argv))
        if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv:
            state = "1.0" if self.glass_loaded else "6.0"
            return RunResult(0, f"({{'uuid': <'{argv[-1]}'>, 'state': <{state}>}},)", "")
        return RunResult(0, "", "")


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_STATE_HOME", ".local/state")):
        monkeypatch.setenv(var, str(home / sub))
    monkeypatch.setenv("HOME", str(home))
    return FakeEnv(home)


@pytest.fixture(scope="session")
def qml(tmp_path_factory):
    """The one QML engine for the whole test run, with one Backend registered as the
    singleton, as the app does. Registering the singleton a second time in one process
    breaks Qt's type registry: the next engine then rejects QtQuick.Effects types
    ("Cannot assign object of type QQuickRectangularShadow to list property data"). So
    every QML test, in any file, takes this fixture and never registers its own."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtGui = pytest.importorskip("PySide6.QtGui")
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlEngine, qmlRegisterSingletonInstance

    from liquidglass.engine import Engine
    from liquidglass.gui import app as gui_app
    from liquidglass.gui.backend import Backend
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    home = tmp_path_factory.mktemp("qml-home")
    mp = pytest.MonkeyPatch()
    for key, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data")):
        mp.setenv(key, str(home / sub))
    env = FakeEnv(home)
    b = Backend(env=env, engine_factory=lambda: Engine(env, []),
                settings_path=home / "config/liquid-glass/settings.json", ui_dark=True, start=False)
    mp.undo()        # a session fixture: don't leave its home for the tests after it
    qmlRegisterSingletonInstance(Backend, "LiquidGlass.Core", 1, 0, "Backend", b)
    engine = QQmlEngine()
    engine.addImportPath(str(gui_app.QML_DIR))
    engine.rootContext().setContextProperty("appIconUrl", QUrl())
    yield engine
