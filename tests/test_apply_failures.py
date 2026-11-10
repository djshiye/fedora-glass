"""An Apply that meets a disk problem says so as a failed part instead of raising, so the
watcher (whose user service restarts it after a crash) never goes round in a crash loop.
The applied version is stamped only by a full Apply in which nothing failed."""
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
