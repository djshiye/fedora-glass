"""Fixes from the 1.5.28 review: a look applied in the app is stamped with its version,
and a file nested too deep to parse is damaged, not a crash."""
import json

import pytest

from fedoraglass import settings as settings_mod
from fedoraglass.engine import Backup, BackupUnreadable, Engine, read_applied_version
from fedoraglass.settings import Settings
from fedoraglass import __version__

DEEP = b"[" * 100_000 + b"]" * 100_000


def test_part_by_part_apply_can_be_stamped(fake_env):
    """The app applies one part at a time; none of those calls stamps the version."""
    eng = Engine(fake_env)
    s = Settings()
    results = []
    for t in eng.targets:
        results += eng.apply(s, only={t.id})
    assert read_applied_version(fake_env) is None
    eng.stamp_applied(results)
    assert read_applied_version(fake_env) == __version__


def test_deeply_nested_settings_are_damaged_not_a_crash(fake_env, tmp_path):
    p = tmp_path / "settings.json"
    p.write_bytes(DEEP)
    loaded = settings_mod.load_checked(p)
    assert not loaded.usable or loaded.settings == Settings()


def test_deeply_nested_manifest_is_unreadable_not_a_crash(fake_env):
    b = Backup(fake_env)
    b.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    b.manifest_path.write_bytes(DEEP)
    with pytest.raises(BackupUnreadable):
        Backup(fake_env)
