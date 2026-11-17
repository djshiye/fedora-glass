"""The speed-ups of the Python side after 1.7.7 give exactly the answers of the code they
replaced: the backup's save that skips unchanged manifests, the linked-folder check, and
the terminal palette handed to every terminal of one Apply, the parts loaded when first
needed."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fedoraglass import engine as eng_mod, palette
from fedoraglass.engine import Backup
from fedoraglass.render import terminal as rt
from fedoraglass.settings import Settings


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


# ---- the terminal palette -------------------------------------------------------------------
@pytest.mark.parametrize("dark", [True, False])
def test_the_palette_handed_out_again_is_the_one_derived(dark):
    for s in (Settings(frost=0.2), Settings(frost=0.9, accent="#e62d42"), Settings(tint="#ff8800")):
        t = palette.build(s, dark=dark)
        args = (t.dark, t.parts["terminal"]["view"].with_alpha(1.0), t.fg.with_alpha(1.0),
                t.accent.with_alpha(1.0), t.accent_text.with_alpha(1.0))
        assert rt.derive(t) == rt._derive.__wrapped__(*args)
        assert rt.derive(t) is rt.derive(palette.build(s, dark=dark))


def test_other_colours_give_another_palette():
    a = rt.derive(palette.build(Settings(accent="#e62d42"), dark=True))
    b = rt.derive(palette.build(Settings(accent="#3584e4"), dark=True))
    assert a != b and a.accent != b.accent


# ---- the parts, loaded when first needed ----------------------------------------------------
def test_an_engine_has_every_part_once_asked(fake_env):
    from fedoraglass.engine import Engine
    from fedoraglass.targets import all_targets
    e = Engine(fake_env)
    assert [t.id for t in e.targets] == [t.id for t in all_targets()]
    assert e.targets is e.targets
    e.targets = []
    assert e.targets == []
    assert Engine(fake_env, []).targets == []


def test_before_login_with_nothing_to_do_loads_no_part(tmp_path):
    # It runs at every login before GNOME Shell starts: the parts' modules (renderers for
    # every app) are only loaded when there is something to apply.
    root = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
           "XDG_STATE_HOME": str(home / ".local/state"), "XDG_DATA_HOME": str(home / ".local/share")}
    code = ("import sys; from fedoraglass import __main__ as m; m._is_root = lambda: False; "
            "m.main(['before-login']); print(sorted(n for n in sys.modules if n.startswith('fedoraglass.targets.')))")
    r = subprocess.run([sys.executable, "-c", code], cwd=root, env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "['fedoraglass.targets.base', 'fedoraglass.targets.shell']"


# ---- reading the po files -------------------------------------------------------------------
def test_po_strings_read_as_with_the_old_pattern():
    import re
    from fedoraglass import i18n
    old = re.compile(r'"((?:[^"\\]|\\.)*)"')
    texts = [p.read_text(encoding="utf-8") for p in sorted(i18n.PO_DIR.glob("*.po*"))]
    texts.append('msgid "a\\\\"\nmsgstr "b\\"c\\n\\q"\n\nmsgid "x"\nmsgstr "\\\\\\\\ \\t"\n')
    seen = 0
    for text in texts:
        for line in text.splitlines():
            rest = line.strip()
            if rest.startswith(("msgid ", "msgstr ", "msgctxt ")):
                rest = rest.split(None, 1)[1]
            elif not rest.startswith('"'):
                continue
            a, b = old.fullmatch(rest), i18n._STRING.fullmatch(rest)
            assert (a and a.group(1)) == (b and b.group(1)), line
            seen += 1
    assert seen > 5000
    for bad in ('"a"b"', '"a\\"', '"a', '"\\"'):
        assert old.fullmatch(bad) is None and i18n._STRING.fullmatch(bad) is None
    assert i18n._unquote("plain") == "plain"
    assert i18n._unquote('a\\"b\\n\\\\\\q') == 'a"b\n\\q'


# ---- pointer pictures -----------------------------------------------------------------------
def _xcursor(sizes, frames: int = 1) -> bytes:
    import struct
    chunks = [(s, struct.pack("<9I", 36, 0xFFFD0002, s, 1, s, s, s // 4, s // 5, 50) + bytes([i, s, 7, 255]) * (s * s))
              for s in sizes for i in range(frames)]
    pos, toc, body = 16 + 12 * len(chunks), b"", b""
    for s, c in chunks:
        toc += struct.pack("<III", 0xFFFD0002, s, pos + len(body))
        body += c
    return b"Xcur" + struct.pack("<III", 16, 0x10000, len(chunks)) + toc + body


def test_a_pointer_file_read_in_parts_gives_what_reading_it_whole_gives(tmp_path):
    # The plain-file way (header, table and one frame) against the whole-file one, which
    # still reads anything that is not a plain file: also on damaged files.
    import random
    from fedoraglass import cursors
    p = tmp_path / "left_ptr"
    files = [_xcursor((24, 32, 48)), _xcursor((24, 30, 32, 36, 48, 64), frames=6), _xcursor((32,))]
    rng = random.Random(7)
    for _ in range(300):
        b = bytearray(rng.choice(files)[:rng.choice([0, 3, 15, 16, 30, 52, 200, 10 ** 6])])
        for _ in range(rng.randint(0, 5)):
            if b:
                b[rng.randrange(len(b))] = rng.randrange(256)
        files.append(bytes(b))
    found = 0
    for data in files:
        p.write_bytes(data)
        for want in (1, 24, 40, 64, 200):
            whole = cursors._parse_xcursor(data, want)
            assert cursors.read_xcursor(p, want) == whole
            found += whole is not None
    assert found > 10


def test_the_pointer_box_is_found_as_pixel_by_pixel(app_qt):
    from PySide6.QtGui import QColor, QImage
    from fedoraglass.gui import cursor_picker as cp

    def by_pixel(img):
        a = img.convertToFormat(QImage.Format.Format_ARGB32)
        xs, ys = [], []
        for y in range(a.height()):
            row = [a.pixelColor(x, y).alpha() for x in range(a.width())]
            if any(v > 24 for v in row):
                ys.append(y)
                xs += [next(i for i, v in enumerate(row) if v > 24), max(i for i, v in enumerate(row) if v > 24)]
        return (min(xs), ys[0], max(xs) + 1, ys[-1] + 1) if ys else None
    img = QImage(37, 23, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    assert cp._bbox(img) is None
    for x, y, alpha in ((5, 3, 200), (30, 19, 25), (12, 8, 24), (0, 22, 255), (36, 0, 26)):
        img.setPixelColor(x, y, QColor(255, 255, 255, alpha))
        assert cp._bbox(img) == by_pixel(img), (x, y)


@pytest.fixture
def app_qt():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtGui = pytest.importorskip("PySide6.QtGui")
    return QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
