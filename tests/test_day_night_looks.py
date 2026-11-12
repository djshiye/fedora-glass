"""Day and night looks, without Qt: a saved look for GNOME's light style and one for its dark
style. The settings that name them, the merge (looks.day_night) and `fedora-glass watch`,
which puts the matching look on the desktop when GNOME switches. Plus the saved look
library's update / same-name helpers the app uses."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from fedoraglass import __main__ as cli
from fedoraglass import looks
from fedoraglass import settings as settings_mod
from fedoraglass import wallcolour
from fedoraglass.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
IFACE = ("org.gnome.desktop.interface", None)


# ---- settings -----------------------------------------------------------------------------
def test_the_picks_are_off_by_default_and_only_ever_a_look_id():
    assert Settings().look_for_light == "" and Settings().look_for_dark == ""
    for bad in ("../evil", "Night", "a/b", ".hidden", "x" * 49, 5, None, ["night"], "night.json", "-x"):
        n = Settings(look_for_light=bad, look_for_dark=bad).normalized()
        assert (n.look_for_light, n.look_for_dark) == ("", ""), bad
    n = Settings(look_for_light="morning-2", look_for_dark="night").normalized()
    assert (n.look_for_light, n.look_for_dark) == ("morning-2", "night")


def test_the_picks_survive_save_and_load_and_a_hand_edit_costs_only_them(tmp_path):
    path = tmp_path / "settings.json"
    settings_mod.save(Settings(frost=0.3, look_for_light="day", look_for_dark="night"), path)
    s = settings_mod.load(path)
    assert (s.look_for_light, s.look_for_dark, s.frost) == ("day", "night", 0.3)
    raw = json.loads(path.read_text())
    raw["look_for_dark"] = {"not": "an id"}
    path.write_text(json.dumps(raw))
    s = settings_mod.load(path)
    assert (s.look_for_light, s.look_for_dark, s.frost) == ("day", "", 0.3)


def test_the_picks_are_never_part_of_a_look():
    """They name looks on this PC: a shared look file must not carry them."""
    assert "look_for_light" not in looks.LOOK_KEYS and "look_for_dark" not in looks.LOOK_KEYS
    assert "look_for_dark" not in looks.pick(Settings(look_for_dark="night"))
    s = looks.apply_look(Settings(look_for_dark="night"), {"look_for_dark": "evil", "frost": 0.9})
    assert s.look_for_dark == "night" and s.frost == 0.9


# ---- the library: update, same names ------------------------------------------------------
def test_update_keeps_the_id_and_the_name(tmp_path):
    lib = looks.Library(tmp_path / "looks")
    look_id = lib.save("Evening blue", Settings(frost=0.2))
    assert lib.update(look_id, Settings(frost=0.8, tint="#112233")) == look_id
    got = lib.get(look_id)
    assert got["name"] == "Evening blue" and got["settings"]["frost"] == 0.8 and got["settings"]["tint"] == "#112233"
    assert [p.name for p in (tmp_path / "looks").glob("*.json")] == ["evening-blue.json"]
    with pytest.raises(looks.LookError):
        lib.update("gone", Settings())


def test_same_name_is_found_in_any_case_and_keep_both_numbers_it(tmp_path):
    lib = looks.Library(tmp_path / "looks")
    lib.save("Evening blue", Settings())
    assert lib.named("evening BLUE") == "evening-blue"
    assert lib.named("Morning") == "" and lib.named("   ") == ""
    assert lib.unique_name("Morning") == "Morning"
    assert lib.unique_name("evening blue") == "evening blue 2"
    lib.save("Evening blue 2", Settings())
    assert lib.unique_name("Evening blue") == "Evening blue 3"
    long = "L" * looks.NAME_MAX
    lib.save(long, Settings())
    assert lib.unique_name(long) == "L" * (looks.NAME_MAX - 2) + " 2"


# ---- the merge ------------------------------------------------------------------------------
def _lib_with(tmp_path, **named) -> looks.Library:
    lib = looks.Library(tmp_path / "looks")
    for name, s in named.items():
        lib.save(name, s)
    return lib


def test_day_night_puts_the_look_for_this_style_on_the_users_settings(tmp_path):
    lib = _lib_with(tmp_path, night=Settings(frost=0.9, tint="#102040", scheme="dark", radius=4),
                    day=Settings(frost=0.1, tint="#e0e8f0"))
    me = Settings(frost=0.5, look_for_light="day", look_for_dark="night", undo_on_remove=False,
                  targets={"gtk4": False}, lock_message="hi")
    dark = looks.day_night(me, True, lib)
    assert (dark.frost, dark.tint, dark.radius) == (0.9, "#102040", 4)
    assert dark.scheme == "auto", "the style keeps following GNOME, or no switch would come again"
    assert (dark.look_for_light, dark.look_for_dark) == ("day", "night")
    assert dark.undo_on_remove is False and dark.targets == {"gtk4": False} and dark.lock_message == "hi"
    light = looks.day_night(me, False, lib)
    assert (light.frost, light.tint) == (0.1, "#e0e8f0")


def test_day_night_does_nothing_without_a_pick_a_look_or_auto(tmp_path):
    lib = _lib_with(tmp_path, night=Settings(frost=0.9))
    assert looks.day_night(Settings(look_for_dark="night"), False, lib) is None, "nothing picked for light"
    assert looks.day_night(Settings(look_for_dark="gone"), True, lib) is None, "the look is gone"
    assert looks.day_night(Settings(look_for_dark="night", scheme="dark"), True, lib) is None, "Style is forced"
    (tmp_path / "looks/night.json").write_text("{ damaged")
    assert looks.day_night(Settings(look_for_dark="night"), True, lib) is None, "unreadable"


def test_day_night_keeps_the_users_own_colour_for_a_look_that_follows_the_wallpaper(tmp_path):
    lib = _lib_with(tmp_path, night=Settings(tint_from_wallpaper=True, tint="#334455"))
    s = looks.day_night(Settings(tint="#abcdef", look_for_dark="night"), True, lib)
    assert s.tint_from_wallpaper and s.tint_own == "#abcdef", "as picking the tile in the app does"


# ---- the watcher ------------------------------------------------------------------------------
class Eng:
    targets: tuple = ()

    def __init__(self, env, on=True):
        self.env, self.on, self.applied = env, on, []

    def look_on(self):
        return self.on

    def apply(self, s, only=None, if_applied=False, applied_only=False):
        self.applied.append({"frost": s.frost, "tint": s.tint, "only": only})
        return []


def _style(env, dark: bool) -> None:
    env.gs.setdefault(IFACE, {})["color-scheme"] = "'prefer-dark'" if dark else "'default'"


def _saved() -> Settings:
    return settings_mod.load_checked().settings


@pytest.fixture
def daynight(fake_env):
    """Applied: a light look with two saved looks picked for light and dark."""
    lib = looks.Library(looks.looks_dir())
    lib.save("Day", Settings(frost=0.1, tint="#e0e8f0"))
    lib.save("Night", Settings(frost=0.9, tint="#102040", scheme="dark"))
    settings_mod.save(Settings(frost=0.1, tint="#e0e8f0", look_for_light="day", look_for_dark="night"))
    _style(fake_env, False)
    eng = Eng(fake_env)
    w = cli.Watcher(eng)
    w.only = {"shell"}
    return fake_env, eng, w


def test_a_switch_to_dark_saves_and_applies_the_night_look_whole(daynight):
    env, eng, w = daynight
    path = settings_mod.settings_path()
    before = path.read_bytes()
    _style(env, True)
    w.changed({cli.SCHEME})
    s = _saved()
    assert (s.frost, s.tint, s.scheme) == (0.9, "#102040", "auto")
    assert (s.look_for_light, s.look_for_dark) == ("day", "night"), "the picks stay"
    assert eng.applied == [{"frost": 0.9, "tint": "#102040", "only": None}], "every part: it is another look"
    assert (path.parent / "settings.json.bak").read_bytes() == before, "saved the normal way, with its .bak"
    _style(env, False)
    w.changed({cli.SCHEME})
    assert (_saved().frost, _saved().tint) == (0.1, "#e0e8f0")
    assert eng.applied[-1] == {"frost": 0.1, "tint": "#e0e8f0", "only": None}


def test_a_switch_to_a_style_with_the_look_on_already_is_the_usual_one(daynight):
    env, eng, w = daynight
    path = settings_mod.settings_path()
    before = path.read_bytes()
    _style(env, False)
    w.changed({cli.SCHEME})          # light again, and the day look is on
    assert eng.applied == [{"frost": 0.1, "tint": "#e0e8f0", "only": {"shell"}}]
    assert path.read_bytes() == before


def test_a_missing_look_applies_as_before_and_keeps_the_pick(daynight):
    env, eng, w = daynight
    (looks.looks_dir() / "night.json").unlink()
    path = settings_mod.settings_path()
    before = path.read_bytes()
    _style(env, True)
    w.changed({cli.SCHEME})
    assert eng.applied == [{"frost": 0.1, "tint": "#e0e8f0", "only": {"shell"}}]
    assert path.read_bytes() == before and _saved().look_for_dark == "night"


def test_after_restore_original_nothing_happens(daynight):
    env, eng, w = daynight
    eng.on = False
    path = settings_mod.settings_path()
    before = path.read_bytes()
    _style(env, True)
    w.changed({cli.SCHEME})
    assert eng.applied == [] and path.read_bytes() == before


def test_with_style_forced_the_picks_do_nothing(daynight):
    env, eng, w = daynight
    settings_mod.save(replace(_saved(), scheme="light"))
    path = settings_mod.settings_path()
    before = path.read_bytes()
    _style(env, True)
    w.changed({cli.SCHEME})
    assert eng.applied == [] and path.read_bytes() == before


def test_a_high_contrast_switch_never_swaps_the_look(daynight):
    env, eng, w = daynight
    _style(env, True)
    w.changed({cli.CONTRAST})
    assert _saved().frost == 0.1 and eng.applied == [{"frost": 0.1, "tint": "#e0e8f0", "only": None}]


def test_a_damaged_settings_file_is_never_touched(daynight):
    env, eng, w = daynight
    path = settings_mod.settings_path()
    path.write_text("{ damaged")
    for p in path.parent.glob("settings.json.bak"):
        p.unlink()
    _style(env, True)
    w.changed({cli.SCHEME})
    assert eng.applied == []
    assert "#102040" not in "".join(p.read_text() for p in path.parent.glob("settings*"))


def test_a_failing_save_applies_nothing(daynight, monkeypatch, capsys):
    env, eng, w = daynight

    def full(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(cli.settings_mod, "save", full)
    _style(env, True)
    w.changed({cli.SCHEME})
    assert eng.applied == []
    assert "saving the look for this style failed" in capsys.readouterr().err


def test_a_night_look_that_follows_the_wallpaper_takes_the_dark_pictures_colour(daynight):
    env, eng, w = daynight
    from tests.test_watch_wallpaper import BLUE, RED, _pic, _reader, _show
    red, blue = _pic(env.home, "red.png"), _pic(env.home, "blue.png")
    _show(env, red, blue)                   # light: red, dark: blue
    w.read_pixels = _reader({"red.png": RED, "blue.png": BLUE})
    looks.Library(looks.looks_dir()).update("night", Settings(frost=0.9, tint_from_wallpaper=True, tint="#000000"))
    _style(env, True)
    w.changed({cli.SCHEME})
    s = _saved()
    assert s.frost == 0.9 and s.tint == wallcolour.as_tint(BLUE) and s.tint_own == "#e0e8f0"
    assert eng.applied == [{"frost": 0.9, "tint": wallcolour.as_tint(BLUE), "only": None}], "saved once, applied once"


def test_the_watcher_still_imports_without_pyside6():
    code = ("import sys; sys.modules['PySide6'] = None\n"
            "import fedoraglass.__main__, fedoraglass.looks\n"
            "assert not any(m.startswith('PySide6') and sys.modules[m] for m in sys.modules)\n")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_the_app_uses_the_same_looks_module():
    from fedoraglass.gui import looks as gui_looks
    assert gui_looks is looks
