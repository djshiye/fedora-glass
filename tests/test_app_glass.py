"""Per-app glass strength: Settings.app_glass (id -> "clearer" or "solid") is checked like
the no-glass list, and rendered into shell-glass.json as windows.appGlass (lower-case ids)
and windows.appLooks (the windows' look made more solid or clearer, inside the readability
rules). The extension side runs in Node (tests/js/app-glass.test.mjs)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass import settings as settings_mod
from fedoraglass.palette import build
from fedoraglass.render import glass
from fedoraglass.settings import PRESETS, Settings

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")


def test_app_glass_is_validated_like_the_no_glass_list():
    raw = {"org.gnome.Nautilus": "solid", "  kitty  ": "clearer", "Kitty": "solid", "kitty": "solid", "": "solid",
           "x" * 200: "solid", "bad\x07id": "solid", "gimp": "normal", "code": 3, 7: "solid", "ok": None}
    s = Settings(app_glass=raw).normalized()
    assert s.app_glass == {"org.gnome.Nautilus": "solid", "kitty": "clearer", "Kitty": "solid"}, "trimmed"
    assert Settings(app_glass=["solid"]).normalized().app_glass == {}
    assert Settings(app_glass="solid").normalized().app_glass == {}
    many = {f"app{i}": "solid" for i in range(500)}
    assert len(Settings(app_glass=many).normalized().app_glass) == settings_mod.APP_GLASS_MAX == 200
    assert Settings().app_glass == {}, "normal glass for every app by default"


def test_app_glass_survives_a_save_and_a_damaged_value_costs_only_itself(tmp_path):
    p = tmp_path / "settings.json"
    settings_mod.save(Settings(app_glass={"org.gnome.Nautilus": "solid"}, no_glass_apps=["gimp"]), p)
    s = settings_mod.load(p)
    assert s.app_glass == {"org.gnome.Nautilus": "solid"} and s.no_glass_apps == ["gimp"]
    # An older settings file has no app_glass: nothing changes for it (no migration needed).
    p.write_text(json.dumps({"no_glass_apps": ["gimp"], "frost": 0.3}))
    s = settings_mod.load(p, fix=False)
    assert s.app_glass == {} and s.no_glass_apps == ["gimp"]
    p.write_text(json.dumps({"app_glass": {"a": "solid", "b": {"x": 1}}, "frost": 0.3}))
    s = settings_mod.load(p, fix=False)
    assert s.app_glass == {"a": "solid"} and s.frost == 0.3


def _windows(s: Settings, dark: bool) -> dict:
    return glass.config(s, build(s, dark=dark))["windows"]


def test_shell_glass_json_carries_lower_case_ids_without_the_no_glass_apps():
    s = Settings(app_glass={"org.gnome.Nautilus": "solid", "Kitty": "clearer", "GIMP": "solid"}, no_glass_apps=["gimp"])
    w = _windows(s, True)
    assert w["appGlass"] == {"org.gnome.nautilus": "solid", "kitty": "clearer"}, "the no-glass list wins"
    assert set(w["appLooks"]) == {"solid", "clearer"}
    assert _windows(Settings(), True)["appGlass"] == {}


def test_the_id_list_stays_small_enough_for_the_extension():
    s = Settings(app_glass={f"{'a' * 190}{i:03d}": "solid" for i in range(200)})
    text = glass.render_config(s, build(s, dark=True))
    assert len(text.encode()) < 48 * 1024, "config.js reads at most 64 KB"
    assert 0 < len(json.loads(text)["windows"]["appGlass"]) < 200


@pytest.mark.parametrize("preset", [None, *PRESETS])
@pytest.mark.parametrize("dark", [True, False])
def test_more_solid_and_clearer_stay_inside_the_readability_rules(preset, dark):
    s = settings_mod.apply_preset(Settings(), preset) if preset else Settings()
    w = _windows(s, dark)
    base, solid, clearer = w["look"], w["appLooks"]["solid"], w["appLooks"]["clearer"]
    # More solid: more frost, a calmer lens.
    assert solid["blur"] > base["blur"] and solid["blur"] >= glass.SOLID_BLUR_MIN
    assert solid["refraction"] < base["refraction"] and solid["bend"] < base["bend"]
    # Clearer: less frost and a wider lens, but never a sharp copy of what is behind.
    assert glass.CLEARER_BLUR_MIN <= clearer["blur"] <= base["blur"]
    assert clearer["refraction"] >= base["refraction"]
    if dark:
        # White text: the ceiling only ever comes down, and Clearer keeps the windows' one.
        assert base["ceiling"] == glass.WINDOW_CEILING
        assert solid["ceiling"] < base["ceiling"] and solid["haze"] > 0
        assert clearer["ceiling"] == base["ceiling"]
    else:
        # Dark text: light glass keeps its milk over dark backdrops, thicker when more solid.
        assert solid["lift"] >= base["lift"] and solid["floor"] > 0
        assert clearer["lift"] == base["lift"]
        assert "ceiling" not in solid and "ceiling" not in clearer


def test_only_the_shell_glass_changes_not_the_app_themes():
    """The themes are made from the tokens, which come out the same with or without
    per-app strengths; in shell-glass.json only windows.appGlass differs."""
    a, b = Settings(), Settings(app_glass={"org.gnome.Nautilus": "solid"})
    for dark in (True, False):
        ta, tb = build(a, dark=dark), build(b, dark=dark)
        assert ta == tb
        ca, cb = glass.config(a, ta), glass.config(b, tb)
        assert ca["windows"].pop("appGlass") == {} and cb["windows"].pop("appGlass")
        assert ca == cb


def test_see_changes_says_it_in_words_and_reset_all_keeps_it():
    from fedoraglass.gui import changes
    rows = changes.change_rows(Settings(app_glass={"gimp": "solid", "kitty": "clearer"}), Settings())
    row = next(r for r in rows if r["key"] == "app_glass")
    assert row["label"] == "Glass strength for apps" and row["page"] == "windows"
    assert row["before"] == "None" and row["after"] == "More solid: gimp; Clearer: kitty"
    rows = changes.change_rows(Settings(app_glass={"gimp": "clearer"}), Settings(app_glass={"gimp": "solid"}))
    row = next(r for r in rows if r["key"] == "app_glass")
    assert (row["before"], row["after"]) == ("More solid: gimp", "Clearer: gimp")


def test_saved_looks_do_not_carry_it():
    """Like the no-glass list, the apps picked are this PC's own: a look exported and
    imported elsewhere never brings them along."""
    from fedoraglass.gui import looks
    assert "app_glass" not in looks.LOOK_KEYS and "no_glass_apps" not in looks.LOOK_KEYS
    assert "app_glass" not in looks.pick(Settings(app_glass={"gimp": "solid"}))


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_the_extension_picks_the_app_look_after_the_no_glass_list_and_before_terminals():
    r = subprocess.run(
        [NODE, "--import", "./tests/js/register.mjs", "--test", "tests/js/app-glass.test.mjs"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
