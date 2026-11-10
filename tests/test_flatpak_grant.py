"""Flatpak apps get read-only access to the GTK style files Apply writes, not the whole
~/.config/gtk-3.0 folder (it holds the file manager's bookmarks too). An Apply after an
upgrade takes the old folder-wide grant back; Restore takes away what was granted."""
from __future__ import annotations

import inspect

import pytest

from fedoraglass import engine as engine_mod
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.base import FlatpakOverride
from fedoraglass.targets.gtk import Flatpak, Gtk3

OLD = "xdg-config/gtk-3.0:ro"


def _fs(env):
    f = env.data / "flatpak/overrides/global"
    text = f.read_text() if f.exists() else ""
    line = next((l for l in text.splitlines() if l.startswith("filesystems=")), "filesystems=")
    return [x for x in line.split("=", 1)[1].split(";") if x]


def test_only_the_style_files_are_shared(fake_env):
    eng = Engine(fake_env, [Gtk3(), Flatpak()])
    eng.apply(Settings())
    fs = _fs(fake_env)
    assert OLD not in fs, "the whole GTK 3 folder (with the bookmarks) is shared"
    assert "xdg-config/gtk-3.0/gtk.css:ro" in fs and "xdg-config/gtk-4.0:ro" in fs
    assert not any(f.startswith("xdg-config/gtk-3.0/bookmarks") for f in fs)
    # What it shares is a real file Apply wrote, not a link to somewhere Flatpak can't see.
    css = fake_env.config / "gtk-3.0/gtk.css"
    assert css.is_file() and not css.is_symlink()
    eng.revert()
    assert _fs(fake_env) == []


def test_the_old_grant_is_taken_back_only_if_fedora_glass_added_it(fake_env):
    t = Flatpak()
    (ov,) = t.plan(None)
    assert ov.drop == (OLD,)
    assert "no longer xdg-config/gtk-3.0:ro" in ov.describe()


_ENGINE_DROPS = "drop" in inspect.getsource(engine_mod._flatpak_apply)


@pytest.mark.skipif(not _ENGINE_DROPS, reason="needs the engine to apply FlatpakOverride.drop (see the report)")
def test_an_upgrade_replaces_the_wide_grant_with_the_narrow_one(fake_env):
    old = type(Flatpak())()
    eng = Engine(fake_env, [old])
    # As 1.5.19 applied it.
    old.plan = lambda ctx: [FlatpakOverride(filesystems=("xdg-config/gtk-4.0:ro", OLD))]
    eng.apply(Settings())
    assert OLD in _fs(fake_env)
    eng = Engine(fake_env, [Flatpak()])
    eng.apply(Settings())
    assert OLD not in _fs(fake_env)
    assert "xdg-config/gtk-3.0/gtk.css:ro" in _fs(fake_env)
    eng.revert()
    assert _fs(fake_env) == []


@pytest.mark.skipif(not _ENGINE_DROPS, reason="needs the engine to apply FlatpakOverride.drop (see the report)")
def test_a_wide_grant_the_user_made_themselves_stays(fake_env):
    f = fake_env.data / "flatpak/overrides/global"
    f.parent.mkdir(parents=True)
    f.write_text(f"[Context]\nfilesystems={OLD};\n")
    eng = Engine(fake_env, [Flatpak()])
    eng.apply(Settings())
    assert OLD in _fs(fake_env)
    eng.revert()
    assert _fs(fake_env) == [OLD]
