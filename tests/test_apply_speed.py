"""Apply reads settings and asks GNOME Shell in this process, not through a program per
question, and leaves files that are already right alone. The answers must be exactly
what `gsettings` and `gdbus` print, because backups store that text."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from fedoraglass import engine as eng_mod
from fedoraglass.env import Env, RunResult

ROOT = Path(__file__).resolve().parent.parent
TOOLS = all(shutil.which(t) for t in ("gsettings", "glib-compile-schemas", "dbus-run-session"))
DCONF = any(Path(d, "dconf/dconf-service").exists() or Path(d, "dconf-service").exists()
            for d in ("/usr/libexec", "/usr/lib", "/usr/lib/x86_64-linux-gnu", "/usr/lib64"))

SCHEMAS = """<?xml version="1.0" encoding="UTF-8"?>
<schemalist>
  <schema id="org.example.glasstest" path="/org/example/glasstest/">
    <key name="word" type="s"><default>"it's"</default></key>
    <key name="flag" type="b"><default>true</default></key>
    <key name="count" type="u"><default>7</default></key>
    <key name="ratio" type="d"><default>0.5</default></key>
    <key name="list" type="as"><default>[]</default></key>
    <key name="pairs" type="aa{ss}"><default>[{'a': 'b'}]</default></key>
    <child name="part" schema="org.example.glasstest.part"/>
  </schema>
  <schema id="org.example.glasstest.part" path="/org/example/glasstest/part/">
    <key name="size" type="i"><default>-3</default></key>
  </schema>
  <schema id="org.example.glasstest.profile">
    <key name="name" type="s"><default>'none'</default></key>
  </schema>
</schemalist>
"""

# Runs in its own process: GLib picks its settings store once per process.
COMPARE = textwrap.dedent("""
    import json, subprocess, sys
    sys.path.insert(0, sys.argv[1])
    from fedoraglass.env import Env
    e = Env()
    assert e._gio_module() is not None, "reading here is on (dconf)"
    cases = [("org.example.glasstest", None), ("org.example.glasstest.part", None),
             ("org.example.glasstest.profile", "/org/example/profiles/one/"),
             ("org.example.glasstest.profile", None), ("org.example.glasstest", "/not/relocatable/"),
             ("org.example.glasstest.profile", "no-slashes"), ("org.example.glasstest.profile", "/a//b/"),
             ("org.example.missing", None)]
    subprocess.run(["gsettings", "set", "org.example.glasstest", "list", "['x', 'y']"], check=True)
    subprocess.run(["gsettings", "set", "org.example.glasstest.profile:/org/example/profiles/one/", "name", "'mine'"], check=True)
    out = []
    for schema, path in cases:
        sid = f"{schema}:{path}" if path else schema
        r = subprocess.run(["gsettings", "list-keys", sid], capture_output=True, text=True)
        want_keys = sorted(r.stdout.split()) if r.returncode == 0 else []
        keys = sorted(e.gsettings_keys(schema, path))
        for key in sorted(set(want_keys) | {"word", "nope"}):
            r = subprocess.run(["gsettings", "get", sid, key], capture_output=True, text=True)
            want = r.stdout.strip() if r.returncode == 0 else None
            out.append([sid, key, e.gsettings_get(schema, key, path), want])
        out.append([sid, "<keys>", keys, want_keys])
    # Another program's write is seen at once.
    for v in ("1", "2", "3"):
        subprocess.run(["gsettings", "set", "org.example.glasstest", "count", v], check=True)
        out.append(["fresh", v, e.gsettings_get("org.example.glasstest", "count"), f"uint32 {v}"])
    print(json.dumps(out))
""")


@pytest.mark.skipif(not (TOOLS and DCONF), reason="needs gsettings, glib-compile-schemas, a session bus and dconf")
def test_settings_read_here_match_gsettings_exactly(tmp_path):
    pytest.importorskip("gi")
    schemas = tmp_path / "schemas"
    schemas.mkdir()
    (schemas / "org.example.glasstest.gschema.xml").write_text(SCHEMAS)
    subprocess.run(["glib-compile-schemas", str(schemas)], check=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path),
           "XDG_CONFIG_HOME": str(tmp_path / "config"), "XDG_DATA_HOME": str(tmp_path / "data"),
           "XDG_RUNTIME_DIR": str(tmp_path / "run"), "GSETTINGS_SCHEMA_DIR": str(schemas)}
    (tmp_path / "run").mkdir(mode=0o700)
    r = subprocess.run(["dbus-run-session", "--", sys.executable, "-c", COMPARE, str(ROOT)], env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    rows = json.loads(r.stdout.strip().splitlines()[-1])
    wrong = [row for row in rows if row[2] != row[3]]
    assert not wrong, wrong
    assert ["org.example.glasstest", "word", "\"it's\"", "\"it's\""] in rows
    assert ["org.example.glasstest", "list", "['x', 'y']", "['x', 'y']"] in rows
    assert ["org.example.glasstest.profile:/org/example/profiles/one/", "name", "'mine'", "'mine'"] in rows


def test_faked_commands_still_answer_settings(tmp_path):
    """Tests (and anything else) that fake Env.run keep seeing every question."""
    asked = []

    class Fake(Env):
        def run(self, argv, timeout=30):
            asked.append(argv)
            return RunResult(0, "'prefer-dark'\n", "")

    e = Fake(home=tmp_path)
    assert e.gsettings_get("org.gnome.desktop.interface", "color-scheme") == "'prefer-dark'"
    assert any(a[0] == "gsettings" and "get" in a for a in asked)


def test_only_known_shell_calls_skip_gdbus():
    e = Env()
    base = ["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell", "--method"]
    for argv in (base + ["org.gnome.Shell.Eval", "1"],                         # never in-process
                 base + ["org.gnome.Shell.Extensions.GetExtensionInfo"],       # no argument
                 ["gdbus", "call", "--system"] + base[3:] + ["org.gnome.Shell.Extensions.GetExtensionInfo", "x"],
                 ["gsettings", "get", "a", "b"]):
        assert e._shell_call_here(argv, 5) is None, argv


@pytest.mark.skipif(not shutil.which("dbus-daemon"), reason="needs dbus-daemon")
def test_shell_call_here_gives_gdbus_error_without_a_shell(tmp_path):
    """No GNOME Shell on the bus: a failed call, as gdbus gives, never an exception."""
    pytest.importorskip("gi")
    script = textwrap.dedent("""
        import sys; sys.path.insert(0, sys.argv[1])
        from fedoraglass.env import Env
        r = Env().run(["gdbus", "call", "--session", "--dest", "org.gnome.Shell", "--object-path", "/org/gnome/Shell",
                       "--method", "org.gnome.Shell.Extensions.GetExtensionInfo", "x@y"], timeout=5)
        print(r.code, bool(r.err))
    """)
    r = subprocess.run(["dbus-run-session", "--", sys.executable, "-c", script, str(ROOT)],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0 and "dbus-run-session" in r.stderr:
        pytest.skip("no session bus here")
    assert r.stdout.split()[-2:] == ["1", "True"], r.stdout + r.stderr


def test_schema_folders_found_once_per_apply(tmp_path, monkeypatch):
    ext = tmp_path / "exts"
    for name, ids in (("a@x", ["org.a", "org.a.child"]), ("b@x", ["org.b", "org.a"])):
        sd = ext / name / "schemas"
        sd.mkdir(parents=True)
        (sd / "gschemas.compiled").write_bytes(b"")
        body = "".join(f'<schema id="{i}"></schema>' for i in ids)
        (sd / f"{ids[0]}.gschema.xml").write_text(f"<schemalist>{body}</schemalist>")
    e = Env(home=tmp_path)
    monkeypatch.setattr(e, "extension_dirs", lambda: [ext])
    reads = []
    real = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: (reads.append(self), real(self, *a, **k))[1])
    assert e._schemadir_for("org.a") == ext / "a@x/schemas"
    assert e._schemadir_for("org.a.child") == ext / "a@x/schemas", "a child schema in its parent's file"
    assert e._schemadir_for("org.b") == ext / "b@x/schemas"
    assert e._schemadir_for("org.gnome.desktop.interface") is None
    assert len(reads) == 2, "each schema file read once, not once per schema asked about"
    e.forget_cache()
    assert e._schemadir_for("org.a") == ext / "a@x/schemas"
    assert len(reads) == 4, "read again after each Apply starts (extensions come and go)"


def test_unchanged_files_are_not_written_again(tmp_path):
    p = tmp_path / "gtk.css"
    eng_mod.write_if_changed(p, b"one", 0o644)
    ino = p.stat().st_ino
    eng_mod.write_if_changed(p, b"one", 0o644)
    assert p.stat().st_ino == ino, "same bytes and mode: left as it is"
    eng_mod.write_if_changed(p, b"two", 0o644)
    assert p.read_bytes() == b"two" and p.stat().st_ino != ino
    ino = p.stat().st_ino
    eng_mod.write_if_changed(p, b"two", 0o600)
    assert p.stat().st_mode & 0o777 == 0o600, "a new mode is written"
    # Never through a link, even to a file that holds the same bytes.
    other = tmp_path / "other.css"
    other.write_bytes(b"two")
    link = tmp_path / "linked.css"
    link.symlink_to(other)
    eng_mod.write_if_changed(link, b"two", 0o644)
    assert not link.is_symlink() and other.read_bytes() == b"two"


def test_lock_takes_popup_styles_away_after_the_lock(tmp_path):
    """extension.js hands the pop-up sheet to destroyLater at a lock (see popupstyle.test.mjs)."""
    src = (ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io/extension.js").read_text()
    lock = src[src.index("if (locked) {"):src.index("this._lock?.destroy();")]
    assert "this._popupStyle = null;" in lock and "this._popupsLater(popups);" in lock
    assert lock.index("this._popupStyle = null;") < lock.index("this._stopSession();")
    start = src[src.index("_startGlass(cfg) {"):src.index("_stopGlass() {")]
    assert start.index("this._dropLeavingPopups();") < start.index("new PopupStyle(cfg)")


@pytest.mark.skipif(not shutil.which("gsettings"), reason="needs gsettings")
def test_stand_in_settings_stores_are_asked_through_gsettings(tmp_path):
    """GLib's keyfile store doesn't see another program's write until its main loop runs, so
    without dconf every answer still comes from gsettings."""
    pytest.importorskip("gi")
    script = "import sys; sys.path.insert(0, sys.argv[1]); from fedoraglass.env import Env; print(Env()._gio_module())"
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path), "GSETTINGS_BACKEND": "keyfile",
           "XDG_CONFIG_HOME": str(tmp_path / "config")}
    r = subprocess.run([sys.executable, "-c", script, str(ROOT)], env=env, capture_output=True, text=True, timeout=60)
    assert r.stdout.strip() == "None", r.stdout + r.stderr
