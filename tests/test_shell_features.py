"""Shell features: lighter glass on battery, the user's apps without glass, and the Glass
switch in Quick Settings. Settings, the shell-glass.json they render into, and the
extension's own tests under the fake Shell (tests/js)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fedoraglass import palette, settings as sm
from fedoraglass.render import glass as rg
from fedoraglass.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
EXT = ROOT / "fedoraglass/data/extension/liquid-glass@djshiye.github.io"


def cfg(**kw) -> dict:
    s = Settings(**kw)
    return rg.config(s, palette.build(s.normalized(), dark=True))


# ---- settings -----------------------------------------------------------------------
def test_lighter_on_battery_is_on_and_reads_a_hand_edit_as_meant():
    assert Settings().lighter_on_battery is True
    assert Settings(lighter_on_battery="false").normalized().lighter_on_battery is False
    assert Settings(lighter_on_battery="maybe").normalized().lighter_on_battery is True


def test_quick_toggle_is_on_and_reads_a_hand_edit_as_meant():
    assert Settings().quick_toggle is True
    assert Settings(quick_toggle=0).normalized().quick_toggle is False
    assert Settings(quick_toggle=None).normalized().quick_toggle is True


def test_app_ids_are_cleaned():
    assert Settings().no_glass_apps == []
    raw = [" org.gnome.Nautilus ", "org.gnome.Nautilus", "", "a" * 200, "a" * 199, "bad\nid", "x\x00",
           7, None, ["Code"], "Code", "Fedora Glass"]
    assert Settings(no_glass_apps=raw).normalized().no_glass_apps == \
        ["org.gnome.Nautilus", "a" * 199, "Code", "Fedora Glass"]
    assert Settings(no_glass_apps="org.gnome.Nautilus").normalized().no_glass_apps == []
    assert Settings(no_glass_apps={"a": 1}).normalized().no_glass_apps == []
    many = [f"app.{i}" for i in range(400)]
    assert len(Settings(no_glass_apps=many).normalized().no_glass_apps) == sm.NO_GLASS_APPS_MAX


def test_all_three_saved_and_loaded(tmp_path):
    p = tmp_path / "settings.json"
    sm.save(Settings(lighter_on_battery=False, quick_toggle=False, no_glass_apps=["code", "Code"]), p)
    s = sm.load(p)
    assert (s.lighter_on_battery, s.quick_toggle, s.no_glass_apps) == (False, False, ["code", "Code"])
    # An older file without these keys gets the defaults.
    p.write_text(json.dumps({"frost": 0.3}))
    s = sm.load(p)
    assert (s.lighter_on_battery, s.quick_toggle, s.no_glass_apps) == (True, True, [])


def test_a_damaged_list_costs_only_that_setting(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"frost": 0.3, "no_glass_apps": 12}))
    s = sm.load(p)
    assert s.frost == 0.3 and s.no_glass_apps == []


# ---- shell-glass.json ----------------------------------------------------------------
def test_lighter_on_battery_is_rendered():
    assert cfg()["speed"] == {"quality": "auto", "lighterOnBattery": True}
    assert cfg(lighter_on_battery=False, glass_quality="full")["speed"] == {"quality": "full", "lighterOnBattery": False}


def test_quick_settings_switch_is_rendered():
    assert cfg()["quickToggle"] == {"enabled": True}
    assert cfg(quick_toggle=False)["quickToggle"] == {"enabled": False}
    # Reduce transparency takes the glass off, not the switch.
    assert cfg(reduce_transparency=True)["quickToggle"] == {"enabled": True}


def test_skip_has_the_built_in_apps_first_then_the_users():
    skip = cfg(no_glass_apps=["org.gnome.Nautilus", "steam", "Code", "org.gimp.GIMP"])["windows"]["skip"]
    assert skip[:len(rg.WINDOW_SKIP)] == list(rg.WINDOW_SKIP)
    assert skip[len(rg.WINDOW_SKIP):] == ["org.gnome.Nautilus", "org.gimp.GIMP"], "each id once"
    assert cfg()["windows"]["skip"] == list(rg.WINDOW_SKIP)


def test_skip_stays_inside_the_extensions_limits():
    s = Settings(no_glass_apps=[f"{'x' * 190}.{i}" for i in range(400)])
    skip = rg.config(s, palette.build(s.normalized(), dark=False))["windows"]["skip"]
    assert len(skip) <= 200 and all(isinstance(i, str) and 0 < len(i) < 200 for i in skip)
    assert skip[:len(rg.WINDOW_SKIP)] == list(rg.WINDOW_SKIP), "the built-in ones never pushed out"
    # The whole file stays under config.js's 64 KiB.
    text = rg.render_config(s, palette.build(s.normalized(), dark=True))
    assert len(text.encode()) < 64 * 1024


def test_built_in_video_players_match_windows_js():
    js = (EXT / "windows.js").read_text()
    m = re.search(r"^const NO_GLASS = /(.*)/i;$", js, re.M)
    assert m and m.group(1) == rg.WINDOW_NO_GLASS.pattern
    assert rg.always_without_glass("steam_app_570") and rg.always_without_glass("Code")
    assert not rg.always_without_glass("org.gnome.Nautilus")


# ---- the extension's files ---------------------------------------------------------------
def test_new_files_ship_with_the_extension():
    for name in ("power.js", "quicktoggle.js", "glass-symbolic.svg"):
        assert name in rg.FILES and (EXT / name).is_file()
    files = rg.extension_files()
    assert "QuickToggle" in files["quicktoggle.js"] and "new_for_bus" in files["power.js"]


def test_tile_icon_is_a_symbolic_svg():
    root = ET.fromstring((EXT / "glass-symbolic.svg").read_text())
    assert root.tag.endswith("svg") and root.get("viewBox") == "0 0 16 16"
    # Symbolic: one flat colour that GNOME recolours to its text colour.
    fills = {e.get("fill") for e in root.iter() if e.get("fill")}
    assert fills == {"#2e3436"}


def test_power_watch_polls_nothing_and_starts_no_service():
    js = (EXT / "power.js").read_text()
    assert "timeout_add" not in js and "DO_NOT_AUTO_START" in js and "_sync" not in js
    assert "net.hadess.PowerProfiles" in js and "org.freedesktop.UPower.PowerProfiles" in js


def test_paused_state_is_never_written():
    """The pause is for this session only: nothing in its path writes a file."""
    for name in ("quicktoggle.js",):
        js = re.sub(r"//.*", "", (EXT / name).read_text())
        assert not re.search(r"set_contents|replace_contents|Gio\.Settings|settings\.json", js)


# ---- under the fake Shell -------------------------------------------------------------------
@pytest.mark.skipif(NODE is None, reason="needs Node.js")
@pytest.mark.parametrize("name", ["power", "no-glass-apps", "quick-toggle", "extension-pause", "extension"])
def test_extension_logic_under_the_fake_shell(name):
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", "--test", f"tests/js/{name}.test.mjs"],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(NODE is None, reason="needs Node.js")
def test_rendered_skip_list_takes_glass_off_those_windows_in_the_extension(tmp_path):
    """What the app renders, read by the real config.js and matched by the real windows.js."""
    s = Settings(no_glass_apps=["org.gnome.Nautilus", "Code"])
    (tmp_path / "shell-glass.json").write_text(rg.render_config(s, palette.build(s.normalized(), dark=True)))
    script = tmp_path / "check.mjs"
    script.write_text(f"""
globalThis.fake = {{Actor: class {{ connect() {{ return 1; }} disconnect() {{}} }}, overview: {{visible: false}}}};
globalThis.fake.ui = new globalThis.fake.Actor();
globalThis.global = {{workspace_manager: {{get_active_workspace: () => ({{}})}}, get_window_actors: () => []}};
const fs = await import('node:fs');
const {{parse}} = await import({json.dumps((EXT / 'config.js').as_uri())});
const {{withoutGlass}} = await import({json.dumps((EXT / 'windows.js').as_uri())});
// The parts these features use (glass.js, with the looks' defaults, is a stub here).
const raw = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'shell-glass.json'))}, 'utf8'));
const c = parse(JSON.stringify({{windows: {{skip: raw.windows.skip}}, speed: raw.speed}}));
console.log(JSON.stringify({{
    nautilus: withoutGlass(['org.gnome.Nautilus'], c.windows.skip),
    code: withoutGlass(['Code', 'code'], c.windows.skip),
    ptyxis: withoutGlass(['org.gnome.Ptyxis'], c.windows.skip),
    steam: withoutGlass(['steam'], c.windows.skip),
    battery: c.speed.lighterOnBattery,
}}));
""")
    r = subprocess.run([NODE, "--import", "./tests/js/register.mjs", str(script)], cwd=ROOT,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads(r.stdout.strip().splitlines()[-1]) == \
        {"nautilus": True, "code": True, "ptyxis": False, "steam": True, "battery": True}
