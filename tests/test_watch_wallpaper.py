"""The tint follows the wallpaper by itself: `fedora-glass watch` takes a new wallpaper's
colours into a look that matches the wallpaper, saves them in settings.json as the app would,
and applies them, without the app and without Qt."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from dataclasses import replace
from pathlib import Path

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import settings as settings_mod
from fedoraglass import wallcolour
from fedoraglass.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
BG = "org.gnome.desktop.background"
RED, BLUE, GREY = (200, 40, 40), (40, 60, 200), (128, 128, 128)


# ---- no Qt anywhere on the watcher's path -------------------------------------------------
def test_the_watcher_and_the_colour_maths_import_without_pyside6():
    code = (
        "import sys; sys.modules['PySide6'] = None\n"
        "import fedoraglass.__main__, fedoraglass.wallcolour as w\n"
        "assert w.as_tint(w.dominant([(200, 40, 40)] * 4)).startswith('#')\n"
        "assert 'PySide6' not in [m for m in sys.modules if m.startswith('PySide6') and sys.modules[m]]\n"
    )
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr


def test_the_app_and_the_watcher_share_the_colour_maths():
    from fedoraglass.gui import wallcolour as gui_wallcolour
    assert gui_wallcolour.dominant is wallcolour.dominant
    assert gui_wallcolour.as_tint is wallcolour.as_tint and gui_wallcolour.as_accent is wallcolour.as_accent
    assert gui_wallcolour.picture_key is wallcolour.picture_key


# ---- the pictures GNOME shows ---------------------------------------------------------------
def _pic(home: Path, name: str) -> Path:
    p = home / "Pictures" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"not decoded in these tests: " + name.encode())
    return p


def _show(env, light: Path | None, dark: Path | None = None, *, dark_key: bool = True) -> None:
    keys = {"picture-uri": f"'file://{light}'" if light else "''"}
    if dark_key:
        keys["picture-uri-dark"] = f"'file://{dark}'" if dark else "''"
    env.gs[(BG, None)] = keys


def test_the_picture_for_each_style(fake_env):
    light, dark = _pic(fake_env.home, "day.png"), _pic(fake_env.home, "night.png")
    _show(fake_env, light, dark)
    assert wallcolour.wallpaper_path(fake_env, False) == str(light)
    assert wallcolour.wallpaper_path(fake_env, True) == str(dark)
    _show(fake_env, light, None)
    assert wallcolour.wallpaper_path(fake_env, True) == str(light), "no dark picture: GNOME shows the light one"
    _show(fake_env, light, dark_key=False)
    assert wallcolour.wallpaper_path(fake_env, True) == str(light), "an older GNOME without picture-uri-dark"
    _show(fake_env, None, None)
    assert wallcolour.wallpaper_path(fake_env, False) == ""
    assert wallcolour.picture_path("'file:///no/such/picture.png'") == ""
    assert wallcolour.picture_path("'https://example.org/a.png'") == ""


# ---- rematch: the colours of a new picture, as the app takes them -------------------------
def _reader(colours: dict[str, tuple[int, int, int] | None]):
    """Decodes a picture to one colour, by its file name (None: can't read it)."""
    def read(path):
        c = colours[Path(path).name]
        return None if c is None else [c] * 16
    return read


def test_rematch_takes_the_switched_on_colours_and_notes_the_picture(tmp_path):
    pic = _pic(tmp_path, "red.png")
    read = _reader({"red.png": RED})
    s = Settings(tint_from_wallpaper=True, tint="#8fa8c8", accent="system")
    new = wallcolour.rematch(s, str(pic), True, read)
    assert new.tint == wallcolour.as_tint(RED) and new.accent == "system", "only the tint follows"
    assert new.wallpaper_match == wallcolour.picture_key(str(pic)) + "|dark"
    both = wallcolour.rematch(replace(s, accent_from_wallpaper=True), str(pic), False, read)
    assert both.accent == wallcolour.as_accent(RED) and both.wallpaper_match.endswith("|light")
    assert wallcolour.rematch(new, str(pic), True, read) is None, "the same picture: nothing to do"
    assert wallcolour.rematch(Settings(), str(pic), True, read) is None, "the look doesn't follow the wallpaper"
    assert wallcolour.rematch(s, "", True, read) is None, "no picture: the colour stays"


def test_rematch_leaves_an_unreadable_picture_and_notes_a_colourless_one(tmp_path):
    s = Settings(tint_from_wallpaper=True, tint="#8fa8c8")
    bad = _pic(tmp_path, "bad.png")
    assert wallcolour.rematch(s, str(bad), True, _reader({"bad.png": None})) is None
    grey = _pic(tmp_path, "grey.png")
    new = wallcolour.rematch(s, str(grey), True, _reader({"grey.png": GREY}))
    assert new.tint == "#8fa8c8" and new.wallpaper_match.startswith(str(grey)), "hardly any colour: as the app"


# ---- the watcher ----------------------------------------------------------------------------
class Eng:
    targets: tuple = ()

    def __init__(self, env, on=True):
        self.env, self.on, self.applied = env, on, []

    def look_on(self):
        return self.on

    def apply(self, s, only=None, if_applied=False, applied_only=False):
        self.applied.append({"tint": s.tint, "accent": s.accent, "only": only,
                             "if_applied": if_applied, "applied_only": applied_only})
        return []


@pytest.fixture
def wall(fake_env):
    """A home with a look that follows the wallpaper, applied while a red picture showed."""
    red, blue = _pic(fake_env.home, "red.png"), _pic(fake_env.home, "blue.png")
    _show(fake_env, red, red)
    s = Settings(tint_from_wallpaper=True, tint=wallcolour.as_tint(RED),
                 wallpaper_match=wallcolour.mark(wallcolour.picture_key(str(red)), True))
    settings_mod.save(s)
    eng = Eng(fake_env)
    w = cli.Watcher(eng)
    w.read_pixels = _reader({"red.png": RED, "blue.png": BLUE, "grey.png": GREY})
    return fake_env, eng, w, red, blue


def _saved() -> Settings:
    return settings_mod.load_checked().settings


def test_a_new_wallpaper_is_taken_saved_and_applied_everywhere(wall):
    env, eng, w, red, blue = wall
    _show(env, blue, blue)
    w.changed({cli.WALLPAPER})
    s = _saved()
    assert s.tint == wallcolour.as_tint(BLUE), "saved as the app would, so the app shows it"
    assert s.wallpaper_match == wallcolour.mark(wallcolour.picture_key(str(blue)), True)
    assert s.tint_from_wallpaper is True
    assert eng.applied == [{"tint": wallcolour.as_tint(BLUE), "accent": s.accent, "only": None,
                            "if_applied": True, "applied_only": True}], "a tint is in every applied part"


def test_the_same_picture_written_again_does_nothing(wall):
    env, eng, w, red, _ = wall
    path = settings_mod.settings_path()
    before = path.read_bytes(), path.stat().st_mtime_ns
    _show(env, red, red)        # a wallpaper app writes the key again, same picture
    w.changed({cli.WALLPAPER})
    w.changed({cli.WALLPAPER})
    assert eng.applied == []
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before, "settings.json untouched"


def test_a_new_picture_with_the_same_colour_is_noted_but_not_applied(wall):
    env, eng, w, red, _ = wall
    again = _pic(env.home, "red2.png")
    w.read_pixels = _reader({"red2.png": RED})
    _show(env, again, again)
    w.changed({cli.WALLPAPER})
    assert eng.applied == [], "nothing looks different"
    assert _saved().wallpaper_match.startswith(str(again)), "but the app no longer says the wallpaper changed"


def test_with_the_look_off_nothing_is_taken_or_applied(wall):
    env, eng, w, _, blue = wall
    eng.on = False      # Restore original
    path = settings_mod.settings_path()
    before = path.read_bytes()
    _show(env, blue, blue)
    w.changed({cli.WALLPAPER})
    assert eng.applied == [] and path.read_bytes() == before


def test_a_damaged_settings_file_is_never_touched(wall, capsys):
    env, eng, w, _, blue = wall
    path = settings_mod.settings_path()
    path.write_text("{ damaged")
    for p in path.parent.glob("settings.json.bak"):
        p.unlink()
    _show(env, blue, blue)
    w.changed({cli.WALLPAPER})
    assert eng.applied == []
    written = "".join(p.read_text() for p in path.parent.glob("settings*"))
    assert wallcolour.as_tint(BLUE) not in written, "no colour written over a damaged file"


def test_a_look_that_does_not_follow_the_wallpaper_is_left_alone(wall):
    env, eng, w, _, blue = wall
    settings_mod.save(replace(_saved(), tint_from_wallpaper=False, tint="#123456"))
    _show(env, blue, blue)
    w.changed({cli.WALLPAPER})
    assert eng.applied == [] and _saved().tint == "#123456"


def test_a_dark_light_switch_to_the_other_picture_takes_its_colour(wall):
    env, eng, w, red, blue = wall
    _show(env, blue, red)                   # light: blue, dark: red (shown now, the look's colour)
    env.gs[("org.gnome.desktop.interface", None)]["color-scheme"] = "'default'"
    w.changed({cli.SCHEME})
    assert _saved().tint == wallcolour.as_tint(BLUE)
    assert _saved().wallpaper_match.endswith("|light")
    assert [a["only"] for a in eng.applied] == [None], "one Apply, of every part: the tint changed"


def test_a_dark_light_switch_with_the_same_picture_is_the_usual_one(wall):
    env, eng, w, red, _ = wall
    w.only = {"shell"}
    env.gs[("org.gnome.desktop.interface", None)]["color-scheme"] = "'default'"
    w.changed({cli.SCHEME})
    assert [a["only"] for a in eng.applied] == [{"shell"}]
    assert _saved().wallpaper_match.endswith("|light"), "noted for this style"


def test_without_gdkpixbuf_it_says_so_once_and_changes_nothing(wall, monkeypatch, capsys):
    env, eng, w, _, blue = wall
    w.read_pixels = None
    monkeypatch.setattr(wallcolour, "can_read_pictures", lambda: False)
    _show(env, blue, blue)
    w.changed({cli.WALLPAPER})
    w.changed({cli.WALLPAPER})
    assert eng.applied == [] and _saved().tint == wallcolour.as_tint(RED)
    assert capsys.readouterr().err.count("GdkPixbuf") == 1


def test_a_picture_that_cannot_be_read_changes_nothing(wall):
    env, eng, w, _, _ = wall
    bad = _pic(env.home, "bad.png")
    w.read_pixels = _reader({"bad.png": None})
    _show(env, bad, bad)
    w.changed({cli.WALLPAPER})
    assert eng.applied == [] and _saved().tint == wallcolour.as_tint(RED)


def test_a_failing_save_does_not_apply_a_look_that_is_not_saved(wall, monkeypatch, capsys):
    env, eng, w, _, blue = wall

    def full(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(cli.settings_mod, "save", full)
    _show(env, blue, blue)
    w.changed({cli.WALLPAPER})
    assert eng.applied == []
    assert "No space left" in capsys.readouterr().err


# ---- the GSettings signal path: debounced -----------------------------------------------------
from tests.test_watch import GNOME, FakeGio, FakeGLib  # noqa: E402


class ClockGLib(FakeGLib):
    def get_monotonic_time(self):
        return int(self.now * 1e6)


def _gio_wall(monkeypatch, script, keys):
    glib, gio = ClockGLib(), FakeGio({k: set(v) for k, v in keys.items()})
    for t, schema, key in script:
        glib.at(t, lambda schema=schema, key=key: gio.change(schema, key))
    end = max((t for t, *_ in script), default=0) + 30
    calls = []

    class W:
        def __init__(self, eng):
            pass

        def start(self):
            pass

        def changed(self, got):
            calls.append((glib.now, set(got)))

        def poll(self):
            return 75 if glib.now >= end else None
    monkeypatch.setattr(cli, "Watcher", W)
    monkeypatch.setattr(cli, "_engine", lambda: None)
    monkeypatch.setattr(cli, "_gio", lambda: (gio, glib))
    return cli.cmd_watch(None), calls, gio


WALL_GNOME = {**GNOME, BG: {"picture-uri", "picture-uri-dark"}}


def test_signals_a_burst_of_wallpaper_writes_makes_one_look_after_it_settles(monkeypatch):
    script = [(1.0 + 0.3 * i, BG, "picture-uri") for i in range(5)] + [(2.0, BG, "picture-uri-dark")]
    code, calls, _ = _gio_wall(monkeypatch, script, WALL_GNOME)
    assert code == 75
    assert calls == [(pytest.approx(2.2 + cli.WALLPAPER_SETTLE_S), {cli.WALLPAPER})], "2 s after the last write"


def test_signals_wallpaper_writes_that_never_stop_are_still_looked_at(monkeypatch):
    script = [(1.0 + 0.5 * i, BG, "picture-uri") for i in range(60)]     # every half second for 30 s
    _code, calls, _ = _gio_wall(monkeypatch, script, WALL_GNOME)
    assert 2 <= len(calls) <= 5, "now and then, never once per write"
    assert all(got == {cli.WALLPAPER} for _, got in calls)


def test_signals_a_wallpaper_change_and_a_dark_light_switch_stay_apart(monkeypatch):
    script = [(1.0, BG, "picture-uri"), (1.1, "org.gnome.desktop.interface", "color-scheme")]
    _code, calls, _ = _gio_wall(monkeypatch, script, WALL_GNOME)
    assert [got for _, got in calls] == [{cli.SCHEME}, {cli.WALLPAPER}]


def test_signals_an_older_gnome_without_a_dark_picture_is_fine(monkeypatch):
    keys = {**GNOME, BG: {"picture-uri"}}
    code, calls, gio = _gio_wall(monkeypatch, [(1.0, BG, "picture-uri")], keys)
    assert code == 75 and [got for _, got in calls] == [{cli.WALLPAPER}]
    assert [set(s.handlers) for s in gio.made[BG]] == [{"changed::picture-uri"}]


def test_signals_no_background_schema_no_wallpaper_watch(monkeypatch):
    code, calls, gio = _gio_wall(monkeypatch, [(1.0, "org.gnome.desktop.interface", "color-scheme")], GNOME)
    assert code == 75 and BG not in gio.made and [got for _, got in calls] == [{cli.SCHEME}]


# ---- the `gsettings monitor` path ------------------------------------------------------------
def test_monitors_wait_for_the_wallpaper_to_settle():
    q: queue.Queue = queue.Queue()
    for _ in range(3):
        q.put(cli.WALLPAPER)
    got = cli._settle_wallpaper(q, {cli.WALLPAPER}, settle_s=0.05, max_s=5)
    assert got == {cli.WALLPAPER} and q.empty(), "the burst is taken together"
    # A monitor that ends meanwhile is passed on at once.
    q.put(None)
    assert None in cli._settle_wallpaper(q, {cli.WALLPAPER}, settle_s=5, max_s=5)
    # Writes that never stop: cut off at max_s.
    stop = threading.Event()

    def storm():
        while not stop.is_set():
            q.put(cli.WALLPAPER)
            stop.wait(0.01)
    t = threading.Thread(target=storm, daemon=True)
    t.start()
    try:
        import time
        start = time.monotonic()
        cli._settle_wallpaper(q, {cli.WALLPAPER}, settle_s=0.05, max_s=0.3)
        assert time.monotonic() - start < 2
    finally:
        stop.set()
        t.join()


def test_monitors_watch_only_the_wallpaper_keys_gnome_has(monkeypatch):
    from tests.test_watch import FakeProc
    started = []

    def popen(argv, **k):
        started.append(argv[-2:])
        return FakeProc(lines=["x\n"] if argv[-1] == "picture-uri" else (), hold=argv[-1] != "picture-uri")
    seen = []

    class W:
        def __init__(self, eng):
            pass

        def start(self):
            pass

        def changed(self, got):
            seen.append(set(got))

        def poll(self):
            return None
    monkeypatch.setattr(cli, "_wallpaper_keys", lambda: ((BG, "picture-uri"),))
    monkeypatch.setattr(cli, "_has_accent_key", lambda: False)
    monkeypatch.setattr(cli.subprocess, "Popen", popen)
    monkeypatch.setattr(cli, "Watcher", W)
    monkeypatch.setattr(cli, "_engine", lambda: None)
    monkeypatch.setattr(cli, "WALLPAPER_SETTLE_S", 0.05)
    assert cli.cmd_watch(None) == 1     # the wallpaper monitor ends after its line: the watcher stops
    assert started == [["org.gnome.desktop.interface", "color-scheme"],
                       ["org.gnome.desktop.a11y.interface", "high-contrast"], [BG, "picture-uri"]]


def test_the_wallpaper_keys_gnome_has(monkeypatch, fake_env):
    from fedoraglass import env as env_mod
    monkeypatch.setattr(env_mod, "Env", lambda: fake_env)
    fake_env.gs[(BG, None)] = {"picture-uri": "''"}
    assert cli.WALLPAPER_KEYS[0] in _real_wallpaper_keys()
    assert cli.WALLPAPER_KEYS[1] not in _real_wallpaper_keys(), "an older GNOME: no picture-uri-dark"


_real_wallpaper_keys = cli._wallpaper_keys      # before conftest's stand-in


# ---- the app follows what the watcher saved --------------------------------------------------
@pytest.fixture
def backend(tmp_path, monkeypatch):
    pytest.importorskip("PySide6.QtGui")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication

    from fedoraglass.env import Env
    from fedoraglass.gui.backend import Backend
    QGuiApplication.instance() or QGuiApplication([])
    for k in ("CONFIG", "CACHE", "STATE", "DATA"):
        monkeypatch.setenv(f"XDG_{k}_HOME", str(tmp_path / k.lower()))
    path = tmp_path / "config/liquid-glass/settings.json"

    def make():
        return Backend(env=Env(home=tmp_path), engine_factory=lambda: None,
                       settings_path=path, ui_dark=True, start=False)
    return make, path


def _bump(path: Path) -> None:
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))


def test_the_app_shows_the_colours_the_watcher_took(backend):
    make, path = backend
    s = Settings(tint_from_wallpaper=True, tint="#aabbcc", wallpaper_match="/old.png|1|2|dark")
    settings_mod.save(s, path)
    b = make()
    assert b.property("dirty") is False
    seen = []
    b.savedChanged.connect(lambda: seen.append(1))
    settings_mod.save(replace(s, tint="#cc8899", wallpaper_match="/new.png|1|2|dark"), path)
    _bump(path)
    b._poll_saved_colours()
    assert b.settings().tint == "#cc8899" and b.property("tint") == "#cc8899"
    assert b.property("dirty") is False, "applied by the watcher, not an unapplied change"
    assert b.property("tintFromWallpaper") is True
    assert seen == [1]
    b._poll_saved_colours()
    assert seen == [1], "once"


def test_the_app_never_loads_other_changes_or_a_tint_picked_by_hand(backend):
    make, path = backend
    s = Settings(tint_from_wallpaper=True, tint="#aabbcc", frost=0.4, wallpaper_match="/old.png|1|2|dark")
    settings_mod.save(s, path)
    b = make()
    # Something else changed too: not the watcher's doing, left alone.
    settings_mod.save(replace(s, tint="#cc8899", frost=0.9, wallpaper_match="/new.png|1|2|dark"), path)
    _bump(path)
    b._poll_saved_colours()
    assert b.settings().tint == "#aabbcc"
    # The watcher's change, while the user picked a tint of their own in the editor.
    settings_mod.save(s, path)
    b2 = make()
    b2.setProperty("frost", 0.7)
    settings_mod.save(replace(s, tint="#cc8899", wallpaper_match="/new.png|1|2|dark"), path)
    _bump(path)
    b2._poll_saved_colours()
    assert b2.settings().tint == "#cc8899", "the applied look has the new colour"
    assert b2.property("frost") == pytest.approx(0.7), "the user's unapplied change stays"
