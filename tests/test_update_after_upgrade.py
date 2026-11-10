"""After `dnf upgrade`, the next login brings the applied look up to the new version
with the user's own settings, without them pressing Apply."""

from __future__ import annotations

import json

from fedoraglass import __main__ as cli
from fedoraglass import __version__
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from test_wait_for_glass import desktop


def _meta(env):
    return ts.GlassEffects().ext_dir(env) / "metadata.json"


def _age(env, version="1.4.3"):
    """Pretend the applied extension came from an older release."""
    m = _meta(env)
    data = json.loads(m.read_text())
    data["version-name"] = version
    m.write_text(json.dumps(data))
    (m.parent / "extension.js").write_text("// old\n")


def test_an_older_applied_version_is_updated_at_login_with_the_users_settings(fake_env):
    engine = desktop(fake_env)
    mine = Settings(frost=0.7, overview_off=True)
    settings_mod.save(mine)
    engine.apply(mine)
    _age(fake_env)
    assert cli.installed_glass_version(engine) == "1.4.3"
    assert cli.update_after_upgrade(engine) is True
    assert cli.installed_glass_version(engine) == __version__
    assert (_meta(fake_env).parent / "extension.js").read_text() != "// old\n"
    cfg = json.loads(ts.GlassEffects().config_path(fake_env).read_text())
    assert settings_mod.load().frost == 0.7, "their settings are kept"
    assert cfg, "the glass config is written again"


def test_nothing_happens_when_up_to_date_after_restore_or_never_applied(fake_env):
    engine = desktop(fake_env)
    assert cli.update_after_upgrade(engine) is False          # never applied
    engine.apply(Settings())
    assert cli.update_after_upgrade(engine) is False          # same version
    _age(fake_env)
    engine.revert()
    assert not _meta(fake_env).exists() or cli.update_after_upgrade(engine) is False


def test_a_linked_metadata_file_is_not_trusted(fake_env, tmp_path):
    engine = desktop(fake_env)
    engine.apply(Settings())
    m = _meta(fake_env)
    elsewhere = tmp_path / "x.json"
    elsewhere.write_text(json.dumps({"version-name": "0.1"}))
    m.unlink()
    m.symlink_to(elsewhere)
    assert cli.installed_glass_version(engine) is None
    assert cli.update_after_upgrade(engine) is False


def test_with_the_glass_part_off_the_other_parts_are_still_updated(fake_env):
    """No glass extension to read the version from: the version of the last Apply counts."""
    from fedoraglass.engine import applied_version_path
    engine = desktop(fake_env)
    mine = Settings(targets={"glass": False})
    settings_mod.save(mine)
    engine.apply(mine)
    assert not _meta(fake_env).exists()
    assert cli.update_after_upgrade(engine) is False          # same version
    applied_version_path(fake_env).write_text("1.0.0\n")      # applied by an older release
    css = ts.GnomeShell().css_path(fake_env)
    css.write_text("/* Fedora Glass 1.0.0 */\n")
    assert cli.update_after_upgrade(engine) is True
    assert css.read_text() != "/* Fedora Glass 1.0.0 */\n", "the Shell theme is written again"
    assert applied_version_path(fake_env).read_text().strip() == __version__
    engine.revert()
    assert not applied_version_path(fake_env).exists()
    assert cli.update_after_upgrade(engine) is False


def test_only_the_parts_applied_now_are_redone(fake_env):
    """A part restored on its own (or one the user never applied, such as a part a newer
    version adds) waits for the user's own Apply: an update never turns it on."""
    from fedoraglass.engine import Backup
    from test_wait_for_glass import ARC
    engine = desktop(fake_env)
    mine = Settings()
    settings_mod.save(mine)
    engine.apply(mine)
    assert engine.revert("arcmenu") == []
    theirs = dict(fake_env.gs[(ARC, None)])
    _age(fake_env)
    assert cli.update_after_upgrade(engine) is True
    assert cli.installed_glass_version(engine) == __version__
    assert fake_env.gs[(ARC, None)] == theirs, "ArcMenu keeps the user's own look"
    assert "arcmenu" not in Backup(fake_env).targets_with_changes()
    assert "glass" in Backup(fake_env).targets_with_changes()
