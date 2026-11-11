"""Feature stream "looks", the parts without Qt: saved and shared look files (untrusted
input), plain-language changes, the look before the last Apply, and the wallpaper colour."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict
from pathlib import Path

import pytest

from fedoraglass import settings as sm
from fedoraglass.gui import changes, looks, wallcolour
from fedoraglass.settings import Settings


# ---------------------------------------------------------------- 1. saved and shared looks

def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def test_a_look_holds_only_the_appearance_never_this_pcs_own_settings():
    s = Settings(frost=0.8, accent="purple", targets={"firefox": False}, undo_on_remove=False,
                 start_on_desktop=True, overview_off=True, glass_quality="lightest", lock_message="call me",
                 lock_widget_weather=True, terminal_colors=True, qt_gnome_titlebars=True)
    kept = looks.pick(s)
    assert kept["frost"] == 0.8 and kept["accent"] == "purple"
    for private in ("targets", "undo_on_remove", "start_on_desktop", "overview_off", "glass_quality",
                    "lock_message", "lock_widget_weather", "lock_weather_place", "lock_greeting",
                    "terminal_colors", "qt_gnome_titlebars", "tint_own", "accent_own", "wallpaper_match"):
        assert private not in kept, private


def test_saved_looks_are_private_files_written_whole(tmp_path):
    lib = looks.Library(tmp_path / "liquid-glass/looks")
    look_id = lib.save("Evening blue", Settings(frost=0.2, tint="#6f9be0"))
    assert look_id == "evening-blue"
    f = tmp_path / "liquid-glass/looks/evening-blue.json"
    assert _mode(f) == 0o600 and _mode(f.parent) == 0o700
    data = json.loads(f.read_text())
    assert data["format"] == "fedora-glass-look" and data["version"] == 1 and data["name"] == "Evening blue"
    assert data["settings"]["tint"] == "#6f9be0"
    assert not [p for p in f.parent.iterdir() if p.name.startswith(".")]     # no temp file left behind
    # Same name again: a second file, not an overwrite.
    assert lib.save("Evening blue", Settings()) == "evening-blue-2"
    assert [x["name"] for x in lib.list()] == ["Evening blue", "Evening blue"]


def test_rename_delete_and_export(tmp_path):
    lib = looks.Library(tmp_path / "looks")
    look_id = lib.save("Mint", Settings(frost=0.5, tint="#a0d0a0"))
    new_id = lib.rename(look_id, "Mint tea")
    assert new_id == "mint-tea" and not (tmp_path / "looks/mint.json").exists()
    assert lib.get("mint-tea")["settings"]["tint"] == "#a0d0a0"
    with pytest.raises(looks.LookError):
        lib.rename("mint-tea", "   ")
    out = tmp_path / "Documents/mint.json"
    out.parent.mkdir()
    lib.export("mint-tea", out)
    assert json.loads(out.read_text())["name"] == "Mint tea" and _mode(out) == 0o644
    lib.delete("mint-tea")
    assert lib.list() == []
    lib.delete("../../etc/passwd")      # never a path outside the folder
    with pytest.raises(looks.LookError, match="isn't there"):
        lib.export("mint-tea", out)


def _file(tmp_path, data, name="look.json") -> Path:
    p = tmp_path / name
    p.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode())
    return p


@pytest.mark.parametrize("data, words", [
    (b"\xff\xfe not text", "isn't text"),
    (b"{nope", "readable JSON"),
    ([1, 2, 3], "holds no settings"),
    ({"format": "something-else", "version": 1, "settings": {"frost": 1}}, "isn't a Fedora Glass look"),
    ({"format": "fedora-glass-look", "settings": {"frost": 1}}, "no version"),
    ({"format": "fedora-glass-look", "version": "1", "settings": {"frost": 1}}, "no version"),
    ({"format": "fedora-glass-look", "version": 1, "settings": [1]}, "holds no settings"),
    ({"format": "fedora-glass-look", "version": 1, "settings": {"targets": {"x": False}, "evil": 1}}, "none of the settings"),
    (b"[" * 100000 + b"]" * 100000, "too big"),
    # Deep nesting is refused either way: as unreadable where json gives up (RecursionError),
    # or as no settings where a newer Python parses it (3.14 on Fedora 44).
    (b"[" * 30000 + b"]" * 30000, "readable JSON|holds no settings"),
])
def test_a_bad_look_file_says_what_is_wrong(tmp_path, data, words):
    with pytest.raises(looks.LookError, match=words):
        looks.read_file(_file(tmp_path, data))


def test_an_imported_look_takes_only_known_keys_and_normalized_values(tmp_path):
    data = {"format": "fedora-glass-look", "version": 7, "name": "Hacker\n\x00look" + "x" * 200,
            "settings": {"frost": 99, "accent": "javascript:alert(1)", "tint": "#12345g", "radius": "lots",
                         "lock_slide_ms": 1e308, "motion": {"open": {"preset": "rm -rf", "speed": 50}},
                         "parts": {"panel": {"tint": "#ff0000", "radius": 900}, "../../x": {"tint": "#000000"}},
                         "targets": {"glass": False}, "undo_on_remove": False, "lock_message": "pwned",
                         "cursor_theme": "../../evil", "newer_setting": True}}
    name, values = looks.read_file(_file(tmp_path, data))
    assert "\n" not in name and "\x00" not in name and len(name) <= looks.NAME_MAX
    assert set(values) <= set(looks.LOOK_KEYS)
    lib = looks.Library(tmp_path / "looks")
    look_id = lib.add(name, values)
    kept = lib.get(look_id)["settings"]
    assert kept["frost"] == 1.0 and kept["accent"] == "system" and kept["tint"] == Settings.tint
    assert kept["radius"] == Settings.radius and kept["lock_slide_ms"] == 1200
    assert kept["parts"] == {"panel": {"tint": "#ff0000", "radius": 32}}
    assert kept["motion"] == {"open": {"speed": 2.0}} and kept["cursor_theme"] == "keep"
    # Picked: the user's own apps, removal choice and lock message stay theirs.
    mine = Settings(targets={"firefox": False}, undo_on_remove=True, lock_message="mine")
    s = looks.apply_look(mine, kept)
    assert s.targets == {"firefox": False} and s.undo_on_remove and s.lock_message == "mine"


def test_a_pointer_style_this_pc_does_not_have_keeps_the_users_own():
    look = {"cursor_theme": "fedora-glass-banana", "frost": 0.3}
    s = looks.apply_look(Settings(cursor_theme="fedora-glass-dark"), look, cursor_installed=lambda _id: False)
    assert s.cursor_theme == "fedora-glass-dark" and s.frost == 0.3
    s = looks.apply_look(Settings(), look, cursor_installed=lambda _id: True)
    assert s.cursor_theme == "fedora-glass-banana"


@pytest.mark.parametrize("editor", [
    Settings(), Settings(frost=0.3), Settings(frost=0.3004, scheme="dark"), Settings(frost=0.31),
    Settings(frost=0.3, cursor_theme="fedora-glass-dark"), Settings(frost=0.3, motion={"open": {"speed": 2.0}}),
])
@pytest.mark.parametrize("look", [
    {"frost": 0.3}, {"frost": "0.3", "scheme": "bogus", "radius": "x"}, {"frost": 0.3, "motion": {"open": {"speed": 2.0}}},
    {"frost": 0.3, "cursor_theme": "fedora-glass-banana"}, {},
])
def test_holding_a_look_worked_out_once_says_what_same_look_says(editor, look):
    for installed in (True, False):
        def has(_id, installed=installed):
            return installed
        want = looks.same_look(editor, looks.apply_look(editor, look, has))
        assert looks.holds(looks.look_values(look, has), editor) is want


def test_each_own_colour_is_kept_by_its_own_wallpaper_switch():
    mine = Settings(accent_from_wallpaper=True, accent_own="teal", tint_from_wallpaper=False, tint_own="#112233")
    s = looks.apply_look(mine, {"frost": 0.3})
    assert s.accent_own == "teal" and s.tint_own == ""
    mine = Settings(tint_from_wallpaper=True, tint_own="#112233", accent_own="teal")
    s = looks.apply_look(mine, {"frost": 0.3})
    assert s.tint_own == "#112233" and s.accent_own == ""


def test_a_look_name_loses_bidi_overrides_and_zero_width_characters():
    assert looks.clean_name("Evil\u202egpj.exe") == "Evilgpj.exe"
    assert looks.clean_name("\u200bNi\u200dght\ufeff \u2066blue\u2069") == "Night blue"
    assert looks.clean_name("\u200b\u200e") == ""
    assert looks.clean_name("Café 🌙") == "Café 🌙"


def test_reading_a_look_never_hangs_on_a_pipe_or_reads_a_device(tmp_path):
    fifo = tmp_path / "pipe.json"
    os.mkfifo(fifo)
    with pytest.raises(looks.LookError, match="isn't a file"):
        looks.read_file(fifo)
    with pytest.raises(looks.LookError, match="isn't there"):
        looks.read_file(tmp_path / "missing.json")


def test_files_in_the_looks_folder_that_are_not_looks_are_left_out(tmp_path):
    d = tmp_path / "looks"
    lib = looks.Library(d)
    lib.save("Good", Settings())
    (d / "broken.json").write_text("{")
    (d / "Upper Case.json").write_text(json.dumps(looks.look_data("x", Settings())))
    (d / "link.json").symlink_to(d / "good.json")
    assert [x["id"] for x in lib.list()] == ["good"]


# ---------------------------------------------------------------- 2. changes in plain words

def test_changes_read_as_plain_words_with_the_page_and_control():
    rows = changes.change_rows(Settings(frost=0.6, accent="purple", blur_app_windows=False),
                               Settings(accent="blue"), system_accent="blue")
    said = {r["label"]: (r["before"], r["after"], r["page"], r["name"]) for r in rows}
    assert said["Frost"] == ("45 %", "60 %", "glass", "glassFrost")
    assert said["Accent"] == ("Blue", "Purple", "colour", "accentRow")
    assert said["Window glass"] == ("On", "Off", "glass", "glassAppWindows")
    assert [r["page"] for r in rows] == ["colour", "glass", "glass"]     # in sidebar order
    sys_row = changes.change_rows(Settings(accent="system"), Settings(accent="#123456"), system_accent="teal")[0]
    assert (sys_row["before"], sys_row["after"]) == ("Custom (#123456)", "System (Teal)")


def test_every_difference_is_listed_even_a_tiny_one_or_an_unknown_setting():
    rows = changes.change_rows(Settings(frost=0.4501), Settings(frost=0.45))
    assert len(rows) == 1 and rows[0]["before"] != rows[0]["after"]
    # Every Settings field is either named in the table or hidden on purpose.
    from dataclasses import fields
    for f in fields(Settings):
        assert f.name in changes.FIELDS or f.name in changes.HIDDEN or f.name in ("motion", "parts", "targets"), f.name


def test_motion_parts_and_apps_changes():
    now = Settings(motion={ev: {"preset": p, "intensity": i} for ev, (p, i) in sm.MOTION_STYLES["playful"].items()},
                   parts={"panel": {"tint": "#ff0000"}}, targets={"firefox": False})
    rows = changes.change_rows(now, Settings(), target_names={"firefox": "Firefox"})
    said = {r["label"]: (r["before"], r["after"]) for r in rows}
    assert said["Motion style"] == ("Lively", "Playful")
    assert said["Panel: tint"] == ("Same as everywhere", "#FF0000")
    assert said["Firefox"] == ("Themed", "Left alone")
    one = Settings(motion={"open": {"preset": "bounce"}})
    assert {r["label"] for r in changes.change_rows(one, Settings())} == {"Open animation"}


# ---------------------------------------------------------------- 3. the look before the last Apply

def test_previous_look_is_its_own_private_file_and_leaves_the_backup_alone(tmp_path):
    path = tmp_path / "liquid-glass/settings.json"
    sm.save(Settings(frost=0.2), path)
    sm.save(Settings(frost=0.3), path)
    bak = (tmp_path / "liquid-glass/settings.json.bak").read_bytes()
    sm.save_previous(Settings(frost=0.2), 1_700_000_000.0, forward=False, path=path)
    prev = sm.load_previous(path)
    assert prev.settings.frost == 0.2 and prev.applied_at == 1_700_000_000.0 and not prev.forward
    p = tmp_path / "liquid-glass/settings.previous.json"
    assert _mode(p) == 0o600
    assert (tmp_path / "liquid-glass/settings.json.bak").read_bytes() == bak
    assert sm.load_checked(path).settings.frost == 0.3
    # Damaged or odd files are no way back, not a crash.
    p.write_text("{")
    assert sm.load_previous(path) is None
    p.write_text(json.dumps({"settings": {"frost": "x"}, "applied_at": "soon", "forward": "yes"}))
    prev = sm.load_previous(path)
    assert prev.settings.frost == Settings.frost and prev.applied_at == 0 and prev.forward is False


# ---------------------------------------------------------------- 4. colour from the wallpaper

def test_the_wallpaper_colour_skips_black_white_and_grey_and_prefers_saturated():
    pixels = [(5, 5, 8)] * 500 + [(250, 250, 250)] * 300 + [(128, 128, 130)] * 300 \
        + [(120, 60, 200)] * 80 + [(200, 120, 110)] * 20
    r, g, b = wallcolour.dominant(pixels)
    assert b > r > g        # the purple, not the black, white, grey or the dull pink
    assert wallcolour.dominant([(0, 0, 0), (255, 255, 255), (90, 90, 90)]) is None


def test_the_tint_is_soft_and_the_accent_clear():
    import colorsys
    tint = wallcolour.as_tint((255, 0, 0))
    accent = wallcolour.as_accent((255, 0, 0))
    rgb = lambda h: tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5))    # noqa: E731
    _h, l, s = colorsys.rgb_to_hls(*rgb(tint))
    assert 0.6 < l < 0.72 and s <= 0.51
    _h, l, s = colorsys.rgb_to_hls(*rgb(accent))
    assert 0.4 <= l <= 0.52 and s >= 0.5
    assert sm._is_hex(tint) and sm._is_hex(accent)


def test_a_slideshow_gives_only_a_plain_picture_file(tmp_path):
    pic = tmp_path / "a.png"
    pic.write_bytes(b"x")
    show = tmp_path / "s.xml"
    show.write_text(f"<background><static><file> {pic} </file></static></background>")
    assert wallcolour.slideshow_picture(str(show)) == str(pic)
    show.write_text(f"<background><static><file>{show}</file></static></background>")
    assert wallcolour.slideshow_picture(str(show)) == ""            # never another slideshow
    show.write_text("<background><static><file>a.png</file></static></background>")
    assert wallcolour.slideshow_picture(str(show)) == ""            # only a full path
    show.write_text("<background><static><file>")
    assert wallcolour.slideshow_picture(str(show)) == ""
    show.write_text("<b>" + "x" * (wallcolour.SLIDESHOW_MAX + 1) + "</b>")
    assert wallcolour.slideshow_picture(str(show)) == ""


def test_wallpaper_settings_are_normalized():
    s = Settings(tint_from_wallpaper="yes", accent_from_wallpaper=1, tint_own="red", accent_own="javascript:",
                 wallpaper_match="/a\nb|1|2" + "x" * 5000).normalized()
    assert s.tint_from_wallpaper is True and s.accent_from_wallpaper is True
    assert s.tint_own == "" and s.accent_own == ""
    assert "\n" not in s.wallpaper_match and len(s.wallpaper_match) == 4096
    assert asdict(Settings().normalized())["tint_from_wallpaper"] is False


def test_export_works_where_chmod_is_refused(tmp_path, monkeypatch):
    """A FAT/exFAT stick refuses chmod with EPERM: the export still has to work."""
    lib = looks.Library(tmp_path / "looks")
    look_id = lib.save("Mint", Settings(frost=0.5))
    out = tmp_path / "stick/mint.json"
    out.parent.mkdir()

    def no_chmod(*a, **k):
        raise PermissionError(1, "Operation not permitted")
    with monkeypatch.context() as m:
        m.setattr(os, "chmod", no_chmod)
        lib.export(look_id, out)
    assert json.loads(out.read_text())["name"] == "Mint"
    assert [p.name for p in out.parent.iterdir()] == ["mint.json"]     # no temp file left
