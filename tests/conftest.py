"""Shared fixtures: a throwaway home and an Env with fake gsettings."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fedoraglass.env import Env, RunResult  # noqa: E402


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
        self.ext_info: dict[str, tuple[str, str]] = {}   # uuid -> (state, error) the fake Shell reports
        self.ext_version: dict[str, str] = {}           # uuid -> the version-name the fake Shell has loaded
        self.naps: list[float] = []

    def sleep(self, seconds):
        self.naps.append(seconds)

    def gsettings_keys(self, schema, path=None):
        return set(self.gs.get((schema, path), {}))

    def gsettings_get(self, schema, key, path=None):
        return self.gs.get((schema, path), {}).get(key)

    def gsettings_set(self, schema, key, value, path=None):
        self.gs.setdefault((schema, path), {})[key] = value
        self.unset.discard((schema, path, key))
        return RunResult(0, "", "")

    # Keys named in `defaults` follow their default value until something sets them.
    @property
    def defaults(self):
        return self.__dict__.setdefault("_defaults", {})

    @property
    def unset(self):
        return self.__dict__.setdefault("_unset", set())

    def follow_default(self, schema, key, value, path=None):
        self.defaults[(schema, path, key)] = value
        self.gs.setdefault((schema, path), {})[key] = value
        self.unset.add((schema, path, key))

    def gsettings_user_set(self, schema, key, path=None):
        if (schema, path, key) in self.defaults:
            return (schema, path, key) not in self.unset
        return None

    def gsettings_is_default(self, schema, key, value, path=None):
        d = self.defaults.get((schema, path, key))
        return None if d is None else d == value

    def gsettings_reset(self, schema, key, path=None):
        if (schema, path, key) in self.defaults:
            self.gs.setdefault((schema, path), {})[key] = self.defaults[(schema, path, key)]
            self.unset.add((schema, path, key))
        else:
            self.gs.get((schema, path), {}).pop(key, None)
        return RunResult(0, "", "")

    def which(self, name):
        return f"/usr/bin/{name}"

    def extension_dirs(self):
        # Only the fake home: extensions installed on the machine running the tests don't count.
        return [self.data / "gnome-shell/extensions"]

    def run(self, argv, timeout=30):
        self.commands.append(list(argv))
        for method, state in (("DisableExtension", "2.0"), ("EnableExtension", "1.0")):
            if f"org.gnome.Shell.Extensions.{method}" in argv and argv[-1] in self.ext_info:
                self.ext_info[argv[-1]] = (state, "")
        if "org.gnome.Shell.Extensions.GetExtensionInfo" in argv:
            v = self.ext_version.get(argv[-1])
            version = f", 'version-name': <'{v}'>" if v is not None else ""
            if argv[-1] in self.ext_info:
                state, error = self.ext_info[argv[-1]]
                return RunResult(0, f"({{'uuid': <'{argv[-1]}'>, 'state': <{state}>, 'error': <'{error}'>{version}}},)", "")
            state = "1.0" if self.glass_loaded else "6.0"
            return RunResult(0, f"({{'uuid': <'{argv[-1]}'>, 'state': <{state}>{version}}},)", "")
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

    from fedoraglass.engine import Engine
    from fedoraglass.gui import app as gui_app
    from fedoraglass.gui.backend import Backend
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    home = tmp_path_factory.mktemp("qml-home")
    mp = pytest.MonkeyPatch()
    for key, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_STATE_HOME", "state"), ("XDG_DATA_HOME", "data")):
        mp.setenv(key, str(home / sub))
    env = FakeEnv(home)
    b = Backend(env=env, engine_factory=lambda: Engine(env, []),
                settings_path=home / "config/liquid-glass/settings.json", ui_dark=True, start=False)
    mp.undo()        # a session fixture: don't leave its home for the tests after it
    qmlRegisterSingletonInstance(Backend, "FedoraGlass.Core", 1, 0, "Backend", b)
    engine = QQmlEngine()
    engine.addImportPath(str(gui_app.QML_DIR))
    engine.rootContext().setContextProperty("appIconUrl", QUrl())
    yield engine


@pytest.fixture(autouse=True)
def _fedora_by_default(monkeypatch):
    """Tests see a Fedora PC wherever they run (install hints, remove command);
    tests/test_distro.py covers Ubuntu and Arch."""
    from fedoraglass import distro
    monkeypatch.setattr(distro, "current", lambda: distro.FEDORA)
