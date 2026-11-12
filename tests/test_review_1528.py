"""Fixes from the 1.5.28 review: a look applied in the app is stamped with its version,
and a file nested too deep to parse is damaged, not a crash."""
import json

import pytest

from fedoraglass import settings as settings_mod
from fedoraglass.engine import Backup, BackupUnreadable, Engine, read_applied_version
from fedoraglass.settings import Settings
from fedoraglass import __version__

DEEP = b"[" * 100_000 + b"]" * 100_000


def test_the_apps_apply_is_stamped(fake_env):
    """The app applies every part in one call, told of each part as it starts, and that
    one call stamps the version (one `only=` call per part never did)."""
    eng = Engine(fake_env)
    s = Settings()
    for t in eng.targets[:3]:
        eng.apply(s, only={t.id})
    assert read_applied_version(fake_env) is None
    told = []
    eng.apply(s, progress=lambda i, n, name: told.append((i, n, name)))
    assert read_applied_version(fake_env) == __version__
    n = len(eng.targets)
    assert [(i, total) for i, total, _name in told] == [(i, n) for i in range(n)]
    assert all(isinstance(name, str) and name for _i, _n, name in told)


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
