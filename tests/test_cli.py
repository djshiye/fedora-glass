"""The command line: a part id that isn't one is an error, never a quiet success."""
from __future__ import annotations

import json

from fedoraglass import __main__ as cli
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.gtk import Gtk3, Gtk4


def _use(monkeypatch, fake_env):
    eng = Engine(fake_env, [Gtk3(), Gtk4()])
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    return eng


def test_apply_only_an_unknown_part_is_refused(fake_env, monkeypatch, capsys):
    eng = _use(monkeypatch, fake_env)
    assert cli.main(["apply", "--only", "gtk4,typo"]) == 2
    err = capsys.readouterr().err
    assert "typo" in err and "gtk4" in err, "names the bad one and the good ones"
    assert not eng.is_applied() and not settings_mod.settings_path().exists()
    assert cli.main(["apply", "--only", ","]) == 2


def test_revert_an_unknown_part_is_refused(fake_env, monkeypatch, capsys):
    eng = _use(monkeypatch, fake_env)
    eng.apply(Settings())
    assert cli.main(["revert", "typo"]) == 2
    assert "typo" in capsys.readouterr().err
    assert eng.is_applied()
    assert cli.main(["revert", "gtk4"]) == 0
    from fedoraglass.engine import Backup
    assert Backup(fake_env).targets_with_changes() == {"gtk3"}


def test_a_part_an_older_version_applied_can_still_be_restored(fake_env, monkeypatch):
    eng = _use(monkeypatch, fake_env)
    eng.apply(Settings())
    monkeypatch.setattr(cli, "_engine", lambda: Engine(fake_env, [Gtk4()]))   # gtk3 gone from this version
    assert cli.main(["revert", "gtk3"]) == 0


def test_apply_only_does_not_save_the_settings(fake_env, monkeypatch):
    _use(monkeypatch, fake_env)
    settings_mod.save(Settings(frost=0.2))
    assert cli.main(["apply", "--only", "gtk4", "--frost", "0.9"]) == 0
    assert json.loads(settings_mod.settings_path().read_text())["frost"] == 0.2
    assert cli.main(["apply", "--frost", "0.9"]) == 0
    assert settings_mod.load().frost == 0.9
