"""Reading and writing below an app's own folder (a Flatpak's, a Snap's, an Obsidian vault)
never follows a link: not on the way, not at the file, not even when the app swaps a folder
for a link between two of our steps."""
from __future__ import annotations

import errno
import os
import shutil
import threading
from pathlib import Path

import pytest

from fedoraglass import safefs
from fedoraglass.safefs import Box, LinkInside, box_root


@pytest.fixture
def box(tmp_path):
    """An app's folder with config/app below it, and a folder of the person's outside it."""
    home = tmp_path / "home"
    root = home / ".var/app/org.example.App"
    (root / "config/app").mkdir(parents=True)
    outside = home / ".config/secret"
    outside.mkdir(parents=True)
    return Box(root, home), root, outside


def files_in(folder: Path) -> list[str]:
    return sorted(str(p.relative_to(folder)) for p in folder.rglob("*"))


# ---- which folders are an app's own -------------------------------------------------------
def test_the_app_folders_are_found_from_the_path_alone(tmp_path):
    home = tmp_path / "home"
    fp = home / ".var/app/org.example.App"
    assert box_root(fp / "config/x.json", home) == fp
    assert box_root(home / "snap/firefox/common/.mozilla/x", home) == home / "snap/firefox"
    assert box_root(tmp_path / "notes/.obsidian/themes/x.css", home) == tmp_path / "notes"
    # A vault inside a Flatpak's folder: the outer one, so nothing below it is followed.
    assert box_root(fp / "vault/.obsidian/appearance.json", home) == fp
    # The folder itself, and the way to it, are the person's own.
    assert box_root(fp, home) is None
    assert box_root(home / ".var/app", home) is None
    assert box_root(home / "snap/firefox", home) is None
    for p in (home / ".config/Code/User/settings.json", home / ".local/share/themes/x/gtk.css",
              home / "md.obsidian.Obsidian/x", tmp_path / "elsewhere/x"):
        assert box_root(p, home) is None, p


def test_a_home_called_snap_is_not_an_app_folder(tmp_path):
    home = tmp_path / "snap"
    assert box_root(home / ".config/gtk-4.0/gtk.css", home) is None
    assert box_root(home / "snap/x/y", home) == home / "snap/x"


# ---- reading ------------------------------------------------------------------------------
def test_read_gives_the_bytes_of_a_plain_file(box):
    b, root, _out = box
    (root / "config/app/a.json").write_bytes(b'{"a": 1}\r\n')
    assert b.read_bytes(root / "config/app/a.json") == b'{"a": 1}\r\n'
    assert b.read_text(root / "config/app/a.json") == '{"a": 1}\r\n'
    assert b.head(root / "config/app/a.json", 3) == b'{"a'


@pytest.mark.parametrize("level", ["config", "config/app"])
def test_read_never_goes_through_a_linked_folder(box, level):
    b, root, out = box
    (out / "app").mkdir()
    (out / "a.json").write_text("secret")
    (out / "app/a.json").write_text("secret")
    os.rename(root / level, root / (level + ".old"))
    (root / level).symlink_to(out)
    with pytest.raises(LinkInside) as e:
        b.read_bytes(root / "config/app/a.json")
    assert e.value.folder == root / level
    assert "links inside an app's own folder are not followed" in str(e.value)
    assert isinstance(e.value, OSError)


def test_read_never_goes_through_a_link_at_the_file(box):
    b, root, out = box
    (out / "id_ed25519").write_text("secret")
    (root / "config/app/a.json").symlink_to(out / "id_ed25519")
    with pytest.raises(LinkInside):
        b.read_bytes(root / "config/app/a.json")
    assert b.is_symlink(root / "config/app/a.json")
    assert not b.is_file(root / "config/app/a.json")
    assert b.readlink(root / "config/app/a.json") == str(out / "id_ed25519")


def test_a_fifo_is_refused_at_once(box):
    b, root, _out = box
    os.mkfifo(root / "config/app/a.json")
    with pytest.raises(OSError):
        b.read_bytes(root / "config/app/a.json")
    assert not b.same_file(root / "config/app/a.json", b"", 0o644)


def test_a_file_bigger_than_the_cap_is_not_read(box):
    b, root, _out = box
    (root / "config/app/a.json").write_bytes(b"x" * 11)
    assert b.read_bytes(root / "config/app/a.json", 11) == b"x" * 11
    with pytest.raises(OSError) as e:
        b.read_bytes(root / "config/app/a.json", 10)
    assert e.value.errno == errno.EFBIG


def test_questions_about_a_missing_file(box):
    b, root, _out = box
    for p in (root / "config/app/none", root / "nothing/here/at/all"):
        assert b.lstat(p) is None
        assert not b.exists(p) and not b.is_file(p) and not b.is_dir(p) and not b.is_symlink(p)
    assert b.is_dir(root / "config/app")
    assert b.missing_dirs(root / "config/app/new/deeper/f") == [
        str(root / "config/app/new/deeper"), str(root / "config/app/new")]
    assert b.missing_dirs(root / "config/app/f") == []


def test_a_name_that_climbs_out_is_refused(box):
    b, root, _out = box
    with pytest.raises(OSError):
        b.read_bytes(root / "config/../../../.config/secret/x")
    with pytest.raises(OSError):
        b.write(root / "config/../../../.config/secret/x", b"x")


# ---- writing ------------------------------------------------------------------------------
def test_write_makes_missing_folders_and_sets_the_mode(box):
    b, root, _out = box
    b.write(root / "data/x/y/f.css", b"body {}", 0o640)
    f = root / "data/x/y/f.css"
    assert f.read_bytes() == b"body {}" and f.stat().st_mode & 0o777 == 0o640
    b.write(f, b"new", 0o644)
    assert f.read_bytes() == b"new" and f.stat().st_mode & 0o777 == 0o644
    assert files_in(root / "data") == ["x", "x/y", "x/y/f.css"]     # no temp file left


@pytest.mark.parametrize("level", ["config", "config/app"])
def test_write_never_goes_through_a_linked_folder(box, level):
    b, root, out = box
    (out / "app").mkdir()
    os.rename(root / level, root / (level + ".old"))
    (root / level).symlink_to(out)
    with pytest.raises(LinkInside) as e:
        b.write(root / "config/app/f.sh", b"echo hi", 0o755)
    assert e.value.folder == root / level
    assert files_in(out) == ["app"]


def test_write_replaces_a_link_at_the_file_and_leaves_its_target_alone(box):
    b, root, out = box
    (out / "bashrc").write_text("mine")
    (root / "config/app/f").symlink_to(out / "bashrc")
    b.write(root / "config/app/f", b"ours")
    assert not (root / "config/app/f").is_symlink()
    assert (root / "config/app/f").read_bytes() == b"ours"
    assert (out / "bashrc").read_text() == "mine"


def test_a_dangling_link_in_place_of_a_missing_folder_is_never_followed(box):
    b, root, out = box
    (root / "config/app/themes").symlink_to(out / "made-by-the-app")
    with pytest.raises(LinkInside):
        b.write(root / "config/app/themes/x.css", b"x")
    with pytest.raises(LinkInside):
        b.symlink("anything", root / "config/app/themes/x.css")
    with pytest.raises(LinkInside):
        b.missing_dirs(root / "config/app/themes/x.css")
    assert not (out / "made-by-the-app").exists()


def test_a_failed_write_leaves_no_temp_file(box):
    b, root, _out = box
    (root / "config/app/f/inside").mkdir(parents=True)      # a folder where the file goes
    with pytest.raises(OSError):
        b.write(root / "config/app/f", b"x")
    assert files_in(root / "config/app") == ["f", "f/inside"]


def test_the_temp_file_has_the_shape_the_sweep_knows(box, monkeypatch):
    b, root, _out = box
    seen = []
    real = os.replace

    def spy(src, dst, **kw):
        seen.append(src)
        return real(src, dst, **kw)
    monkeypatch.setattr(safefs.os, "replace", spy)
    b.write(root / "config/app/settings.json", b"{}")
    from fedoraglass.engine import _temp_of
    assert len(seen) == 1 and _temp_of(seen[0], {"settings.json"})


# ---- unlink, rmdir, links -----------------------------------------------------------------
@pytest.mark.parametrize("level", ["config", "config/app"])
def test_unlink_rmdir_and_symlink_never_go_through_a_linked_folder(box, level):
    b, root, out = box
    (out / "app").mkdir()
    (out / "app/f").write_text("mine")
    (out / "f").write_text("mine")
    (out / "app/d").mkdir()
    (out / "d").mkdir()
    os.rename(root / level, root / (level + ".old"))
    (root / level).symlink_to(out)
    for step in (lambda: b.unlink(root / "config/app/f"), lambda: b.rmdir(root / "config/app/d"),
                 lambda: b.symlink("x", root / "config/app/new"),
                 lambda: b.readlink(root / "config/app/f")):
        with pytest.raises(LinkInside):
            step()
    assert files_in(out) == ["app", "app/d", "app/f", "d", "f"]


def test_unlink_takes_the_link_itself_away(box):
    b, root, out = box
    (out / "f").write_text("mine")
    (root / "config/app/f").symlink_to(out / "f")
    b.unlink(root / "config/app/f")
    assert not (root / "config/app/f").is_symlink() and (out / "f").read_text() == "mine"
    b.symlink("../elsewhere", root / "config/app/new/l")
    assert os.readlink(root / "config/app/new/l") == "../elsewhere"
    b.unlink(root / "config/app/new/l")
    b.rmdir(root / "config/app/new")
    assert not (root / "config/app/new").exists()


def test_copy_keeps_bytes_mode_and_times_and_refuses_a_link(box, tmp_path):
    b, root, out = box
    src = root / "config/app/a.conf"
    src.write_bytes(b"pw=hash")
    os.chmod(src, 0o600)
    os.utime(src, ns=(1_000_000_000, 2_000_000_000))
    dest = tmp_path / "copy"
    assert b.copy(src, dest) == 0o600
    assert dest.read_bytes() == b"pw=hash" and dest.stat().st_mode & 0o777 == 0o600
    assert dest.stat().st_mtime_ns == 2_000_000_000
    (out / "id_ed25519").write_text("secret")
    src.unlink()
    src.symlink_to(out / "id_ed25519")
    with pytest.raises(LinkInside):
        b.copy(src, tmp_path / "copy2")
    assert not (tmp_path / "copy2").exists()


def test_copy_of_a_file_bigger_than_the_cap_is_refused_and_leaves_nothing(box, tmp_path):
    b, root, _out = box
    src = root / "config/app/a.conf"
    with open(src, "wb") as f:
        f.truncate(safefs.APP_FILE_MAX + 1)     # sparse: no disk used, but would fill the backup
    with pytest.raises(OSError) as e:
        b.copy(src, tmp_path / "copy")
    assert e.value.errno == errno.EFBIG and not (tmp_path / "copy").exists()
    src.write_bytes(b"x" * 11)
    with pytest.raises(OSError) as e:
        b.copy(src, tmp_path / "copy", 10)
    assert e.value.errno == errno.EFBIG and not (tmp_path / "copy").exists()


# ---- the race -----------------------------------------------------------------------------
def test_a_folder_flipped_to_a_link_and_back_never_lets_a_write_out(box):
    """The app swaps its folder for a link to the person's folder and back, as fast as it
    can, while we write: not one write may land outside."""
    b, root, out = box
    here, other, spare = root / "config/themes", root / "config/other", root / "config/spare"
    here.mkdir()
    other.symlink_to(out)
    stop = threading.Event()
    flips = []

    def flip():
        # Two names traded back and forth: `themes` is now the real folder, now the link.
        while not stop.is_set():
            os.rename(here, spare)
            while True:
                try:
                    os.rename(other, here)
                    break
                except OSError:
                    shutil.rmtree(here, ignore_errors=True)     # a folder a write made meanwhile
            os.rename(spare, other)
            flips.append(1)
    t = threading.Thread(target=flip, daemon=True)
    t.start()
    done = refused = 0
    try:
        for i in range(400):
            try:
                b.write(here / f"f{i % 7}.css", b"ours")
                done += 1
            except OSError:
                refused += 1
    finally:
        stop.set()
        t.join(5)
    assert files_in(out) == [], (done, refused)
    assert flips and done and refused, (len(flips), done, refused)
