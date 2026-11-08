"""The app removes compiled-screen caches left by older versions, and nothing else."""
import os
from pathlib import Path

from fedoraglass.gui.app import tidy_qml_caches


def test_old_qml_caches_go_and_everything_else_stays(tmp_path: Path):
    for name in ("qmlcache-1.1.0", "qmlcache-1.5.6", "qmlcache-1.5.7"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "a.qmlc").write_bytes(b"x")
    (tmp_path / "speed.json").write_text("{}")
    (tmp_path / "qmlcache-notes").mkdir()                 # not a version: kept
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("mine")
    os.symlink(outside, tmp_path / "qmlcache-1.0.0")      # a link: never followed or removed
    (tmp_path / "qmlcache-1.2.0").write_text("a file")    # not a folder: kept

    assert tidy_qml_caches(tmp_path, "qmlcache-1.5.7") == 2
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["outside", "qmlcache-1.0.0", "qmlcache-1.2.0", "qmlcache-1.5.7", "qmlcache-notes", "speed.json"]
    assert (outside / "keep.txt").read_text() == "mine"
    assert (tmp_path / "qmlcache-1.5.7" / "a.qmlc").exists()


def test_missing_folder_is_fine(tmp_path: Path):
    assert tidy_qml_caches(tmp_path / "nope", "qmlcache-1.5.7") == 0
