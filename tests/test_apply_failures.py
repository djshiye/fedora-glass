"""An Apply that meets a disk problem says so as a failed part instead of raising, so the
watcher (whose user service restarts it after a crash) never goes round in a crash loop.
The applied version is stamped only by a full Apply in which nothing failed, or nothing failed
that had not failed in the one before it as well."""
from __future__ import annotations

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import __version__
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Backup, Engine, applied_version_path
from fedoraglass.settings import Settings, config_dir
from test_wait_for_glass import desktop


def test_a_tokens_file_that_cannot_be_written_is_a_failed_part(fake_env):
    eng = desktop(fake_env)
    eng.apply(Settings())
    (config_dir() / "tokens.json").unlink()
    (config_dir() / "tokens.json").mkdir()      # stands in for any OSError (disk full, EROFS)
    got = eng.apply(Settings(frost=0.9), if_applied=True, applied_only=True)
    failed = [r for r in got if r.status == "failed"]
    assert [r.target for r in failed] == ["tokens"] and failed[0].message


@pytest.mark.parametrize("where", ["tidy_folders", "context"])
def test_a_failure_before_the_parts_is_a_failed_result(fake_env, monkeypatch, where):
    eng = desktop(fake_env)
    eng.apply(Settings())

    def boom(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(Backup if where == "tidy_folders" else Engine, where, boom)
    got = eng.apply(Settings(), if_applied=True)
    assert [(r.status, "No space left" in r.message) for r in got] == [("failed", True)]


def test_a_partial_apply_does_not_stamp_the_version(fake_env):
    eng = desktop(fake_env)
    s = Settings(targets={"glass": False})
    settings_mod.save(s)
    eng.apply(s)
    applied_version_path(fake_env).write_text("1.0.0\n")
    eng.apply(s, only={"gtk4"})
    assert applied_version_path(fake_env).read_text().strip() == "1.0.0"
    assert cli.update_after_upgrade(eng) is True, "the other parts are still updated"
    assert applied_version_path(fake_env).read_text().strip() == __version__


def test_an_apply_with_a_failed_part_does_not_stamp_the_version(fake_env):
    eng = desktop(fake_env)
    s = Settings(targets={"glass": False})
    eng.apply(s)
    applied_version_path(fake_env).write_text("1.0.0\n")
    (config_dir() / "tokens.json").unlink()
    (config_dir() / "tokens.json").mkdir()
    assert any(r.status == "failed" for r in eng.apply(s))
    assert applied_version_path(fake_env).read_text().strip() == "1.0.0"


def test_a_part_that_fails_again_does_not_hold_the_stamp_back_for_ever(fake_env):
    """One part failing on every Apply after an upgrade must not have every login apply
    everything again: it gets a second try, then the version is stamped anyway."""
    from fedoraglass.engine import failed_parts_path
    eng = desktop(fake_env)
    s = Settings(targets={"glass": False})
    settings_mod.save(s)
    eng.apply(s)
    applied_version_path(fake_env).write_text("1.0.0\n")       # applied by an older release
    (config_dir() / "tokens.json").unlink()
    (config_dir() / "tokens.json").mkdir()                       # fails every time from now on
    assert cli.update_after_upgrade(eng) is True                 # first try: fails, no stamp
    assert applied_version_path(fake_env).read_text().strip() == "1.0.0"
    assert cli.update_after_upgrade(eng) is True                 # second try: fails the same way
    assert applied_version_path(fake_env).read_text().strip() == __version__
    assert not failed_parts_path(fake_env).exists()
    assert cli.update_after_upgrade(eng) is False, "the next login leaves the look alone"


def test_a_new_failure_still_holds_the_stamp_back(fake_env):
    from fedoraglass.engine import failed_parts_path
    eng = desktop(fake_env)
    s = Settings(targets={"glass": False})
    eng.apply(s)
    applied_version_path(fake_env).write_text("1.0.0\n")
    failed_parts_path(fake_env).write_text('{"version": "0.9", "failed": ["tokens"]}')   # another version's
    (config_dir() / "tokens.json").unlink()
    (config_dir() / "tokens.json").mkdir()
    eng.apply(s)
    assert applied_version_path(fake_env).read_text().strip() == "1.0.0"


def test_the_glass_part_failing_twice_also_stops_the_reapplies(fake_env, monkeypatch):
    """With the glass on, the extension's version says what is applied; a glass part that
    keeps failing leaves it old, so the stamp must count too."""
    from fedoraglass.targets import shell as ts
    eng = desktop(fake_env)
    s = Settings()
    settings_mod.save(s)
    eng.apply(s)
    applied_version_path(fake_env).write_text("1.0.0\n")
    calls = []

    def boom(self, ctx):
        calls.append(1)
        raise OSError("read-only file system")
    monkeypatch.setattr(ts.GlassEffects, "plan", boom)
    monkeypatch.setattr(cli, "installed_glass_version", lambda eng: "1.0.0")
    assert cli.update_after_upgrade(eng) is True
    assert cli.update_after_upgrade(eng) is True
    assert cli.update_after_upgrade(eng) is False
    assert len(calls) == 2
