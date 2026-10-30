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

    def extension_dirs(self):
        # Only the throwaway home: extensions installed on the machine running the
        # tests must not change what the tests see.
        return [self.data / "gnome-shell/extensions"]

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
