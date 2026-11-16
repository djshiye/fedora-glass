"""An update installed while a Fedora Glass process runs (the watcher, or the app left open)
must not leave a half-updated glass extension behind.

What happened on 1.7.0 -> 1.7.2: the watcher still running 1.7.0 applied once during the
`dnf upgrade`. Its code listed 1.7.0's extension files, but read their text from disk, now
1.7.2's: it wrote 1.7.2's metadata.json and modules, but not gcsweep.js (new in 1.7.2).
At the next login the step before GNOME Shell (`before-login`) read "1.7.2" in metadata.json
and did nothing, GNOME failed to import gcsweep.js, and the glass stopped until a logout."""

from __future__ import annotations

from fedoraglass import __main__ as cli
from fedoraglass import __version__, engine as engine_mod
from fedoraglass import settings as settings_mod
from fedoraglass.engine import applied_version_path
from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings
from fedoraglass.targets import shell as ts
from fedoraglass.targets.base import Context, WriteFile
from test_wait_for_glass import desktop


def _ext(env):
    return ts.GlassEffects().ext_dir(env)


def _applied(fake_env):
    engine = desktop(fake_env)
    mine = Settings(frost=0.7, overview_off=True)
    settings_mod.save(mine)
    engine.apply(mine)
    return engine, mine


def test_a_new_version_with_a_missing_file_is_finished_before_the_shell_starts(fake_env):
    engine, _ = _applied(fake_env)
    assert cli.glass_files_current(engine)
    # The state Dino's PC was in: this version's metadata.json, an older stamp, one file missing.
    (_ext(fake_env) / "gcsweep.js").unlink()
    applied_version_path(fake_env).write_text("1.7.0\n")
    assert cli.installed_glass_version(engine) == __version__
    assert not cli.glass_files_current(engine)
    fake_env.glass_loaded = False          # before login: no GNOME Shell yet
    assert cli.update_glass_before_login(engine) is True
    assert (_ext(fake_env) / "gcsweep.js").read_text() == (rg.SOURCE / "gcsweep.js").read_text()
    assert cli.glass_files_current(engine)
    assert cli.update_glass_before_login(engine) is False, "and nothing more to do after"


def test_an_older_module_under_the_new_metadata_is_replaced_too(fake_env):
    engine, _ = _applied(fake_env)
    (_ext(fake_env) / "glass.js").write_text("// older\n")
    fake_env.glass_loaded = False
    assert cli.update_glass_before_login(engine) is True
    assert cli.glass_files_current(engine)


def test_a_process_older_than_the_installed_version_writes_nothing(fake_env, monkeypatch):
    engine, mine = _applied(fake_env)
    (_ext(fake_env) / "gcsweep.js").unlink()
    before = {p.name: p.read_bytes() for p in _ext(fake_env).iterdir()}
    monkeypatch.setattr(engine_mod, "disk_version", lambda: "99.0")
    # The watcher (it restarts as the new version within a minute): quietly nothing.
    assert engine.apply(mine, if_applied=True, applied_only=True) == []
    # The user's Apply in an app left open: told to open it again.
    res = engine.apply(mine)
    assert [(r.target, r.status) for r in res] == [("apply", "failed")]
    assert "open it again" in res[0].message
    assert {p.name: p.read_bytes() for p in _ext(fake_env).iterdir()} == before


def test_the_installed_version_applies_as_before(fake_env, monkeypatch):
    engine, mine = _applied(fake_env)
    monkeypatch.setattr(engine_mod, "disk_version", lambda: __version__)
    assert engine_mod.runs_installed_version()
    assert any(r.status == "applied" for r in engine.apply(mine))
    monkeypatch.setattr(engine_mod, "disk_version", lambda: None)   # unreadable: no change from before
    assert engine_mod.runs_installed_version()


def test_the_cli_reads_the_same_version_on_disk():
    assert cli.disk_version() == engine_mod.disk_version() == __version__


def test_extension_js_and_metadata_go_in_last(fake_env):
    engine, mine = _applied(fake_env)
    ctx: Context = engine.context(mine)
    names = [a.path.name for a in ts.GlassEffects().plan(ctx)
             if isinstance(a, WriteFile) and a.path.parent == _ext(fake_env)]
    assert set(names) == set(rg.FILES)
    assert names[-2:] == ["extension.js", "metadata.json"], \
        "a write stopped part way leaves the older version's name, so the next login finishes it"
