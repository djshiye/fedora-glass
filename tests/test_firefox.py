"""Firefox theme: opt-in, every profile found, the user's own files kept, and Restore
original puts every file back exactly."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fedoraglass import palette, unmerge
from fedoraglass.engine import Engine
from fedoraglass.render import apps as ra
from fedoraglass.settings import Settings
from fedoraglass.targets import apps as ta
from fedoraglass.targets.base import Context, WriteFile

ON = Settings(targets={"firefox-theme": True})


def toks(dark):
    return palette.build(Settings(), dark=dark)


def make_profile(root, name="abcd.default-release", ini_extra="", relative=True, path=None):
    """A profiles.ini under `root` that lists one profile folder, made too."""
    prof = path or root / name
    prof.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    ini = root / "profiles.ini"
    old = ini.read_text() if ini.exists() else "[General]\nStartWithLastProfile=1\nVersion=2\n"
    n = old.count("[Profile")
    old += (f"\n[Profile{n}]\nName={name}\nIsRelative={1 if relative else 0}\n"
            f"Path={name if relative else prof}\n{ini_extra}")
    ini.write_text(old)
    return prof


def engine(env):
    return Engine(env, [ta.Firefox()])


def snapshot(folder):
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()} | \
        {str(p.relative_to(folder)) + "/": b"" for p in folder.rglob("*") if p.is_dir()}


# ---- render ------------------------------------------------------------------------------
def test_chrome_css_has_both_palettes_opaque_and_both_property_names():
    css = ra.firefox_chrome_css(toks(True), toks(False))
    assert css.count("{") == css.count("}")
    assert "@media (prefers-color-scheme: dark)" in css and "@media (prefers-color-scheme: light)" in css
    # Current Firefox names and the ESR 140 ones.
    for name in ("--toolbox-background-color", "--toolbar-background-color", "--tab-background-color-selected",
                 "--toolbar-field-background-color", "--panel-background-color", "--lwt-accent-color",
                 "--toolbox-bgcolor", "--toolbar-bgcolor", "--tab-selected-bgcolor", "--arrowpanel-background",
                 "--toolbar-field-focus-background-color", "--urlbarView-highlight-background"):
        assert f"{name}:" in css, name
    decls = re.findall(r"(--[\w-]+): ([^;]+);", css)
    assert decls and all(v.endswith("!important") for _, v in decls)
    # Surfaces are solid: Firefox windows can't be see-through, so no fake transparency.
    for k, v in decls:
        if "background" in k or k in ("--lwt-accent-color", "--toolbox-bgcolor", "--toolbar-bgcolor"):
            if "hover" in k or "active" in k:
                continue      # a wash over a solid toolbar
            assert v.startswith("rgb("), (k, v)
    # Dark and light differ.
    dark, light = css.split("prefers-color-scheme: light")
    assert re.search(r"--toolbar-background-color: (rgb\([^)]*\))", dark).group(1) != \
        re.search(r"--toolbar-background-color: (rgb\([^)]*\))", light).group(1)


def test_content_css_only_touches_the_new_tab_page():
    css = ra.firefox_content_css(toks(True), toks(False))
    assert css.count("{") == css.count("}")
    assert '@-moz-document url("about:home"), url("about:newtab")' in css
    assert "--newtab-background-color:" in css and "prefers-color-scheme: light" in css


def test_import_block_goes_first_and_keeps_the_users_lines():
    mine = '@charset "UTF-8";\n#nav-bar { border: 0 }\n'
    out = ra.css_import_block(mine, "fedora-glass.css")
    lines = out.splitlines()
    assert lines[0] == '@charset "UTF-8";'
    assert lines[2] == '@import url("fedora-glass.css");'
    assert out.endswith("#nav-bar { border: 0 }\n")
    assert ra.css_import_block(out, "fedora-glass.css") == out          # again: no second block
    assert unmerge.unmerge(out, mine, ("block", ra.FIREFOX_BEGIN, ra.FIREFOX_END)) == mine
    assert ra.css_import_block("", "x.css").startswith("/* Fedora Glass: begin")


def test_userjs_pref_checks_and_block():
    p = ra.FIREFOX_PREF
    assert not ra.userjs_has_pref(None)
    assert ra.userjs_has_pref(f'user_pref("{p}", true);\n')
    assert not ra.userjs_has_pref(f'user_pref("{p}", true);\nuser_pref("{p}", false);\n')
    mine = 'user_pref("browser.startup.page", 3);'      # no newline at the end
    out = ra.userjs_block(mine)
    assert out.startswith(mine + "\n") and f'user_pref("{p}", true);' in out
    assert not ra.userjs_has_pref(out)        # our own line doesn't count as the user's
    assert ra.without_block(out, ra.FIREFOX_BEGIN, ra.FIREFOX_END) == mine + "\n"



def test_lost_end_marker_keeps_the_users_own_lines():
    # The user deleted our end marker: only our own lines go, never their rules below.
    p = ra.FIREFOX_PREF
    css = ra.css_import_block("#nav-bar { border: 0 }\n", "fedora-glass.css")
    css = css.replace(f"/* {ra.FIREFOX_END} */\n", "")
    assert ra.without_block(css, ra.FIREFOX_BEGIN, ra.FIREFOX_END) == "#nav-bar { border: 0 }\n"
    again = ra.css_import_block(css, "fedora-glass.css")
    assert again.count("@import") == 1 and again.endswith("#nav-bar { border: 0 }\n")
    js = ra.userjs_block('user_pref("a.b", 1);\n').replace(f"// {ra.FIREFOX_END}\n", "")
    js += 'user_pref("browser.startup.page", 3);\n'
    assert ra.without_block(js, ra.FIREFOX_BEGIN, ra.FIREFOX_END) == \
        'user_pref("a.b", 1);\nuser_pref("browser.startup.page", 3);\n'
    # A user's own line for the same pref, away from our begin line, stays.
    mine = f'// {ra.FIREFOX_BEGIN}\nuser_pref("x", 1);\nuser_pref("{p}", true);\n'
    assert ra.without_block(mine, ra.FIREFOX_BEGIN, ra.FIREFOX_END) == f'user_pref("x", 1);\nuser_pref("{p}", true);\n'
    assert unmerge.unmerge(css, "", ("block", ra.FIREFOX_BEGIN, ra.FIREFOX_END)) == "#nav-bar { border: 0 }\n"

# ---- opt-in --------------------------------------------------------------------------------
def test_off_until_turned_on(fake_env):
    make_profile(fake_env.home / ".mozilla/firefox")
    assert not Settings().target_enabled("firefox-theme")
    assert Settings().target_enabled("vscode")
    assert "firefox-theme" not in engine(fake_env).plan(Settings())
    assert "firefox-theme" in engine(fake_env).plan(ON)
    # Only a real true turns it on; a hand-typed "yes" or junk doesn't.
    for raw in ("yes", 1, "true", None):
        assert not Settings(targets={"firefox-theme": raw}).normalized().target_enabled("firefox-theme")
    assert Settings(targets={"firefox-theme": True}).normalized().target_enabled("firefox-theme")
    # The old "firefox" row's stored state means nothing for the theme.
    assert not Settings(targets={"firefox": True}).normalized().target_enabled("firefox-theme")


def test_apply_with_it_off_writes_nothing(fake_env):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    before = snapshot(prof)
    engine(fake_env).apply(Settings())
    assert snapshot(prof) == before


# ---- profiles ------------------------------------------------------------------------------
def test_profiles_from_every_place(fake_env, tmp_path):
    h = fake_env.home
    classic = make_profile(h / ".mozilla/firefox", "a.default")
    make_profile(h / ".mozilla/firefox", "b.work")
    xdg = make_profile(fake_env.config / "mozilla/firefox", "c.default")
    flat = make_profile(h / ".var/app/org.mozilla.firefox/.mozilla/firefox", "d.default")
    elsewhere = make_profile(h / ".mozilla/firefox", "e.disk", relative=False, path=tmp_path / "disk/e")
    # Listed but gone, and the same folder listed twice: neither counts twice or at all.
    (h / ".mozilla/firefox/profiles.ini").write_text(
        (h / ".mozilla/firefox/profiles.ini").read_text()
        + "\n[Profile9]\nName=gone\nIsRelative=1\nPath=gone.default\n"
        + "\n[Profile8]\nName=dup\nIsRelative=1\nPath=a.default\n")
    got = ta.firefox_profiles(fake_env)
    assert got == [classic, h / ".mozilla/firefox/b.work", elsewhere, xdg, flat]
    assert ta.Firefox().detect(fake_env).available


def test_detect_without_profiles(fake_env, monkeypatch):
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: "/usr/bin/firefox" if n == "firefox" else None)
    d = ta.Firefox().detect(fake_env)
    assert not d.available and "start Firefox once" in d.detail
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: None)
    assert ta.Firefox().detect(fake_env).detail == "Firefox is not installed"


def test_unreadable_profiles_ini_is_ignored(fake_env):
    root = fake_env.home / ".mozilla/firefox"
    root.mkdir(parents=True)
    (root / "profiles.ini").write_bytes(b"\xff\xfe not text")
    assert ta.firefox_profiles(fake_env) == []


# ---- apply and restore ------------------------------------------------------------------------
def test_plan_writes_only_our_files_and_marked_lines(fake_env):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    s = Settings()
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    plan = ta.Firefox().plan(Context(settings=ON, tokens=d, dark=d, light=l, env=fake_env))
    paths = {a.path.relative_to(prof): a for a in plan}
    assert set(map(str, paths)) == {"chrome/fedora-glass.css", "chrome/fedora-glass-content.css",
                                    "chrome/userChrome.css", "chrome/userContent.css", "user.js"}
    for name in ("chrome/userChrome.css", "chrome/userContent.css", "user.js"):
        assert paths[Path(name)].edits == ("block", ra.FIREFOX_BEGIN, ra.FIREFOX_END)
    assert all(isinstance(a, WriteFile) for a in plan)


def test_apply_then_restore_is_byte_identical(fake_env):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    chrome = prof / "chrome"
    chrome.mkdir()
    user_chrome = b"/* mine */\r\n#TabsToolbar { min-height: 30px !important; }\r\n"
    (chrome / "userChrome.css").write_bytes(user_chrome)
    (chrome / "my-other.css").write_bytes(b"a{}")
    (prof / "user.js").write_bytes(b'user_pref("browser.startup.page", 3);')
    (prof / "prefs.js").write_bytes(b'user_pref("x", 1);\n')
    before = snapshot(prof)
    eng = engine(fake_env)
    res = eng.apply(ON)
    assert [r.status for r in res] == ["applied"]
    uc = (chrome / "userChrome.css").read_bytes().decode()
    assert uc.startswith("/* Fedora Glass: begin") and '@import url("fedora-glass.css");' in uc
    assert uc.endswith(user_chrome.decode())          # the user's rules come after ours, so theirs win
    assert '@import url("fedora-glass-content.css");' in (chrome / "userContent.css").read_text()
    assert f'user_pref("{ra.FIREFOX_PREF}", true);' in (prof / "user.js").read_text()
    assert (chrome / "fedora-glass.css").read_text().startswith("/* Fedora Glass for Firefox")
    assert (prof / "prefs.js").read_bytes() == before["prefs.js"]      # never touched
    eng.apply(ON)                                                         # a second Apply changes nothing
    assert eng.revert() == []
    assert snapshot(prof) == before
    assert not eng.is_applied()


def test_restore_removes_the_chrome_folder_it_made(fake_env):
    prof = make_profile(fake_env.config / "mozilla/firefox")
    before = snapshot(prof)
    eng = engine(fake_env)
    eng.apply(ON)
    assert (prof / "chrome/userChrome.css").is_file() and (prof / "user.js").is_file()
    assert eng.revert() == []
    assert snapshot(prof) == before and not (prof / "chrome").exists()


def test_restore_keeps_what_the_user_wrote_since(fake_env):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    eng = engine(fake_env)
    eng.apply(ON)
    uc = prof / "chrome/userChrome.css"
    uc.write_text(uc.read_text() + "#urlbar { color: red }\n")
    ujs = prof / "user.js"
    ujs.write_text(ujs.read_text() + 'user_pref("mine", 1);\n')
    assert eng.revert() == []
    assert uc.read_text() == "#urlbar { color: red }\n"
    assert ujs.read_text() == 'user_pref("mine", 1);\n'
    assert not (prof / "chrome/fedora-glass.css").exists()
    assert not eng.is_applied()


def test_users_own_pref_line_is_kept_and_not_doubled(fake_env):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    mine = f'// my settings\nuser_pref("{ra.FIREFOX_PREF}", true);\n'
    (prof / "user.js").write_text(mine)
    eng = engine(fake_env)
    eng.apply(ON)
    assert (prof / "user.js").read_text() == mine
    assert eng.revert() == []
    assert (prof / "user.js").read_text() == mine


def test_flatpak_profile_apply_and_restore(fake_env):
    prof = make_profile(fake_env.home / ".var/app/org.mozilla.firefox/.mozilla/firefox", "x.default-release")
    before = snapshot(prof)
    eng = engine(fake_env)
    assert [r.status for r in eng.apply(ON)] == ["applied"]
    assert (prof / "chrome/fedora-glass.css").is_file()
    assert eng.revert() == []
    assert snapshot(prof) == before


def test_turning_it_off_and_applying_takes_it_away(fake_env):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    before = snapshot(prof)
    eng = engine(fake_env)
    eng.apply(ON)
    res = eng.apply(Settings(targets={"firefox-theme": False}))
    assert [r.status for r in res] == ["reverted"]
    assert snapshot(prof) == before


def test_linked_chrome_folder_is_left_alone(fake_env, tmp_path):
    prof = make_profile(fake_env.home / ".mozilla/firefox")
    dotfiles = tmp_path / "dotfiles/chrome"
    dotfiles.mkdir(parents=True)
    (dotfiles / "userChrome.css").write_text("/* dotfiles */\n")
    (prof / "chrome").symlink_to(dotfiles)
    s = Settings()
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    ctx = Context(settings=ON, tokens=d, dark=d, light=l, env=fake_env)
    assert ta.Firefox().plan(ctx) == []
    assert any("is a link" in n for n in ta.Firefox().live_notes(ctx))
    engine(fake_env).apply(ON)
    assert (dotfiles / "userChrome.css").read_text() == "/* dotfiles */\n"
    assert not (prof / "user.js").exists()


def test_notes_say_restart_firefox():
    assert any("Restart Firefox" in n for n in ta.Firefox().notes)
    assert not ta.Firefox().scheme_dependent       # both palettes are in the sheet


@pytest.mark.parametrize("dark", [True, False])
def test_text_readable_on_toolbar(dark):
    from fedoraglass.color import Color
    v = ra._firefox_vars(toks(dark))

    def c(s):
        r, g, b = (int(x) for x in re.match(r"rgba?\((\d+),(\d+),(\d+)", s).groups())
        return Color(r / 255, g / 255, b / 255)
    assert c(v["--toolbar-text-color"]).contrast(c(v["--toolbar-background-color"])) >= 4.5
    assert c(v["--panel-text-color"]).contrast(c(v["--panel-background-color"])) >= 4.5
