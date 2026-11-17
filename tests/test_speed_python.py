"""The speed-ups of the Python side after 1.7.7 give exactly the answers of the code they
replaced: the backup's save that skips unchanged manifests and the linked-folder check."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fedoraglass import engine as eng_mod
from fedoraglass.engine import Backup


# ---- Backup.save ----------------------------------------------------------------------------
def _writes(monkeypatch) -> list[str]:
    seen: list[str] = []
    real = eng_mod.atomic_write

    def counting(path, data, *a, **k):
        seen.append(Path(path).name)
        return real(path, data, *a, **k)
    monkeypatch.setattr(eng_mod, "atomic_write", counting)
    return seen


def test_save_writes_each_change_and_nothing_when_nothing_changed(fake_env, monkeypatch):
    b = Backup(fake_env)
    writes = _writes(monkeypatch)
    b.data["files"]["/x"] = {"target": "gtk4", "kind": "missing", "new_dirs": []}
    b.save()
    assert writes == ["manifest.json"]
    b.save()
    b.save()
    assert writes == ["manifest.json"]          # nothing new: nothing written
    # A change made in place, inside an entry, is still seen.
    b.data["files"]["/x"]["wrote"] = "abc"
    b.save()
    assert writes == ["manifest.json", "manifest.json.bak", "manifest.json"]
    on_disk = json.loads(b.manifest_path.read_text())
    assert on_disk["files"]["/x"]["wrote"] == "abc"
    assert b.manifest_path.read_bytes() == json.dumps(b.data, indent=1).encode()
    # Only the order of the keys changes: the file still follows it, as before.
    e = b.data["files"]["/x"]
    b.data["files"]["/x"] = {k: e[k] for k in reversed(list(e))}
    b.save()
    assert b.manifest_path.read_bytes() == json.dumps(b.data, indent=1).encode()
    assert writes[-1] == "manifest.json"


def test_a_manifest_in_another_layout_is_written_again_at_the_first_save(fake_env, monkeypatch):
    # Same values, but not the text save() writes (an older version's layout, a hand
    # edit): the first save writes it out in the usual layout, as it always did.
    b = Backup(fake_env)
    b.data["files"]["/x"] = {"target": "gtk4", "kind": "missing", "new_dirs": []}
    b.save()
    b.manifest_path.write_text(json.dumps(b.data))      # compact, no indent
    b2 = Backup(fake_env)
    writes = _writes(monkeypatch)
    b2.save()
    assert writes == ["manifest.json.bak", "manifest.json"]
    assert b2.manifest_path.read_bytes() == json.dumps(b2.data, indent=1).encode()
    b2.save()
    assert writes == ["manifest.json.bak", "manifest.json"]


def test_a_failed_write_is_tried_again_at_the_next_save(fake_env, monkeypatch):
    b = Backup(fake_env)
    b.data["files"]["/x"] = {"target": "gtk4", "kind": "missing", "new_dirs": []}
    real = eng_mod.atomic_write

    def full(path, data, *a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(eng_mod, "atomic_write", full)
    with pytest.raises(OSError):
        b.save()
    monkeypatch.setattr(eng_mod, "atomic_write", real)
    b.save()
    assert json.loads(b.manifest_path.read_text())["files"]["/x"]["target"] == "gtk4"


# ---- Backup.linked_folder -------------------------------------------------------------------
def _linked_folder_before(b: Backup, path: Path) -> Path | None:
    """The check as 1.7.7 wrote it, for comparing."""
    roots = sorted((r for r in (b.env.config, b.env.data, b.env.state)
                    if path.is_relative_to(r)), key=lambda r: len(r.parts), reverse=True)
    if not roots:
        return None
    d = roots[0]
    for part in path.parent.relative_to(roots[0]).parts:
        d = d / part
        if d.is_symlink():
            return d
    return None


def test_linked_folder_answers_as_before(fake_env, tmp_path, monkeypatch):
    home = fake_env.home
    elsewhere = tmp_path / "dotfiles"
    (elsewhere / "gtk-4.0").mkdir(parents=True)
    fake_env.config.mkdir(parents=True)
    (fake_env.config / "gtk-4.0").symlink_to(elsewhere / "gtk-4.0")
    (fake_env.data / "themes/A").mkdir(parents=True)
    (fake_env.data / "themes/B").symlink_to(fake_env.data / "themes/A")
    paths = [fake_env.config / "gtk-4.0/gtk.css", fake_env.config / "gtk-4.0/sub/x.css",
             fake_env.config / "btop/btop.conf", fake_env.data / "themes/B/gtk-3.0/gtk.css",
             fake_env.data / "themes/A/x", fake_env.state / "liquid-glass/x", fake_env.config / "x",
             home / "elsewhere/x", Path("/etc/passwd"), Path("relative/x")]
    b = Backup(fake_env)
    for p in paths:
        assert b.linked_folder(p) == _linked_folder_before(b, p), p
    # One root inside another (XDG_DATA_HOME inside XDG_CONFIG_HOME): the deeper one counts.
    monkeypatch.setenv("XDG_DATA_HOME", str(fake_env.config / "data"))
    (fake_env.config / "data").mkdir()
    (fake_env.config / "data/link").symlink_to(elsewhere)
    for p in paths + [fake_env.config / "data/link/x", fake_env.config / "data/x"]:
        assert b.linked_folder(p) == _linked_folder_before(b, p), p
    assert b.linked_folder(fake_env.config / "data/link/x") == fake_env.config / "data/link"


def test_linked_folder_of_a_root_itself_fails_as_before(fake_env):
    b = Backup(fake_env)
    with pytest.raises(ValueError):
        _linked_folder_before(b, fake_env.config)
    with pytest.raises(ValueError):
        b.linked_folder(fake_env.config)
