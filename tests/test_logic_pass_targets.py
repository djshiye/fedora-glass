"""Alacritty keeps to the file Alacritty reads, a left-over Flatpak data folder is not an
install, and a terminal whose own file was not edited does not report "applied"."""
from __future__ import annotations

import pytest

from fedoraglass import palette
from fedoraglass.engine import Backup, Engine
from fedoraglass.settings import Settings
from fedoraglass.targets import apps as ta
from fedoraglass.targets import terminal as tt
from fedoraglass.targets.base import Command, Context, WriteFile


def ctx_for(env):
    s = Settings(scheme="dark")
    d, l = palette.build(s, dark=True), palette.build(s, dark=False)
    return Context(settings=s, tokens=d, dark=d, light=l, env=env)


@pytest.fixture
def alac(fake_env, monkeypatch):
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: "/usr/bin/alacritty" if n == "alacritty" else None)
    return fake_env


@pytest.mark.parametrize("rel", [".alacritty.toml", ".config/alacritty.toml"])
def test_alacritty_edits_the_file_it_reads_and_restore_undoes_it(alac, rel):
    main = alac.home / rel
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("[font]\nsize = 14\n")
    writes = [a.path for a in tt.Alacritty().plan(ctx_for(alac)) if isinstance(a, WriteFile)]
    assert main in writes
    assert alac.config / "alacritty/alacritty.toml" not in writes
    eng = Engine(alac, [tt.Alacritty()])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    assert "Fedora Glass" in main.read_text()
    assert not (alac.config / "alacritty/alacritty.toml").exists()
    assert eng.revert() == []
    assert main.read_text() == "[font]\nsize = 14\n"


def test_alacritty_first_file_in_its_order_wins(alac):
    (alac.config / "alacritty").mkdir(parents=True)
    (alac.config / "alacritty/alacritty.toml").write_text("")
    (alac.home / ".alacritty.toml").write_text("")
    assert tt.Alacritty().main_path(alac) == alac.config / "alacritty/alacritty.toml"


def test_alacritty_with_no_file_creates_the_default(alac):
    assert tt.Alacritty().main_path(alac) == alac.config / "alacritty/alacritty.toml"


@pytest.mark.parametrize("rel", [".alacritty.yml", ".config/alacritty.yml"])
def test_alacritty_old_yaml_elsewhere_is_left_alone(alac, rel):
    p = alac.home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("window: {}\n")
    assert tt.Alacritty().plan(ctx_for(alac)) == []


def test_terminal_with_an_import_list_of_its_own_says_one_manual_step(alac):
    main = alac.config / "alacritty/alacritty.toml"
    main.parent.mkdir(parents=True)
    main.write_text("[general]\nimport = [\"/x.toml\"]\n")
    r = Engine(alac, [tt.Alacritty()]).apply(Settings())[0]
    assert r.status == "info" and "import list" in r.message


def test_terminal_whose_file_is_a_link_says_one_manual_step(alac):
    d = alac.config / "alacritty"
    d.mkdir(parents=True)
    real = alac.home / "dots.toml"
    real.write_text("")
    (d / "alacritty.toml").symlink_to(real)
    r = Engine(alac, [tt.Alacritty()]).apply(Settings())[0]
    assert r.status == "info" and "link" in r.message


def test_terminal_whose_owner_added_our_file_by_hand_is_applied(alac):
    # They did the one manual step: nothing more to ask for, at this Apply or the next.
    main = alac.config / "alacritty/alacritty.toml"
    main.parent.mkdir(parents=True)
    own = alac.config / "alacritty/fedora-glass.toml"
    main.write_text(f'[general]\nimport = ["/x.toml", "{own}"]\n')
    eng = Engine(alac, [tt.Alacritty()])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    real = alac.home / "dots.toml"
    real.write_text(f'[general]\nimport = ["{own}"]\n')
    main.unlink()
    main.symlink_to(real)
    assert [r.status for r in eng.apply(Settings())] == ["applied"]


def _older_apply(env, monkeypatch):
    """An Apply as versions up to 1.6.0 did it: always ~/.config/alacritty/alacritty.toml."""
    with monkeypatch.context() as m:
        m.setattr(tt.Alacritty, "main_path", tt.IncludeTerminal.main_path)
        m.setattr(tt.Alacritty, "gives_back", lambda self, env: [])
        assert [r.status for r in Engine(env, [tt.Alacritty()]).apply(Settings())] == ["applied"]


MINE = "[font]\nsize = 13\n"


def test_alacritty_gives_back_the_file_an_older_version_made_in_front_of_the_users_own(alac, monkeypatch):
    mine = alac.home / ".alacritty.toml"
    mine.write_text(MINE)
    _older_apply(alac, monkeypatch)
    made = alac.config / "alacritty/alacritty.toml"
    assert made.is_file() and "[font]" not in made.read_text()      # Alacritty reads this one: theirs is hidden
    eng = Engine(alac, [tt.Alacritty()])
    for _apply in range(2):                                         # the second one finds it settled
        assert [r.status for r in eng.apply(Settings())] == ["applied"]
        assert not made.exists()
        assert mine.read_text().startswith(MINE) and "fedora-glass.toml" in mine.read_text()
    assert eng.revert() == []
    assert mine.read_text() == MINE
    assert not (alac.config / "alacritty").exists()


def test_alacritty_show_changes_takes_nothing_away(alac, monkeypatch):
    (alac.home / ".alacritty.toml").write_text(MINE)
    _older_apply(alac, monkeypatch)
    made = alac.config / "alacritty/alacritty.toml"
    before = made.read_bytes()
    alac.dry_run = True
    Engine(alac, [tt.Alacritty()]).apply(Settings())
    assert made.read_bytes() == before and (alac.home / ".alacritty.toml").read_text() == MINE


@pytest.mark.parametrize("case", ["the user's own empty file", "changed since", "no record of it"])
def test_alacritty_keeps_a_first_file_it_cannot_be_sure_it_made(alac, monkeypatch, case):
    first = alac.config / "alacritty/alacritty.toml"
    mine = alac.home / ".alacritty.toml"
    mine.write_text(MINE)
    if case == "the user's own empty file":
        first.parent.mkdir(parents=True)
        first.write_text("")
    _older_apply(alac, monkeypatch)
    if case == "changed since":
        first.write_text(first.read_text() + "\n")
    if case == "no record of it":
        b = Backup(alac)
        del b.data["files"][str(first)]
        b.save()
    eng = Engine(alac, [tt.Alacritty()])
    assert [r.status for r in eng.apply(Settings())] == ["applied"]
    # Still the file Alacritty reads, with our lines in it; the other one is not touched.
    assert first.is_file() and "fedora-glass.toml" in first.read_text()
    assert mine.read_text() == MINE
    if case == "the user's own empty file":
        assert eng.revert() == []
        assert first.read_text() == "" and mine.read_text() == MINE


@pytest.fixture
def no_apps(fake_env, monkeypatch, tmp_path):
    monkeypatch.setattr(type(fake_env), "which", lambda self, n: "/usr/bin/flatpak" if n == "flatpak" else None)
    monkeypatch.setattr(ta, "has_desktop_file", lambda env, d: False)
    monkeypatch.setenv("FLATPAK_SYSTEM_DIR", str(tmp_path / "system-flatpak"))
    return fake_env


def test_vscode_flatpak_leftover_data_is_not_an_install(no_apps):
    (no_apps.home / ".var/app/com.visualstudio.code/config/Code/User").mkdir(parents=True)
    t = ta.VSCode()
    assert not t.detect(no_apps).available
    assert not any(run[0] == "flatpak" for *_x, run in t.installs(no_apps))


def test_vscode_flatpak_counts_when_deployed_in_either_installation(no_apps, tmp_path, monkeypatch):
    (no_apps.data / "flatpak/app/com.visualstudio.code/current").mkdir(parents=True)
    assert ta.VSCode().detect(no_apps).available
    (tmp_path / "system-flatpak/app/com.vscodium.codium/current").mkdir(parents=True)
    assert ta.VSCodium().detect(no_apps).available
    monkeypatch.setenv("FLATPAK_USER_DIR", str(tmp_path / "other"))
    assert not ta.VSCode().detect(no_apps).available


def test_a_flatpak_app_with_a_second_branch_left_still_counts(no_apps):
    # Its `current` link went with the branch it pointed at; another branch is still there.
    app = no_apps.data / "flatpak/app/com.visualstudio.code"
    (app / "x86_64/beta").mkdir(parents=True)
    assert not no_apps.flatpak_installed("com.visualstudio.code"), "an empty branch folder is no install"
    (app / "x86_64/beta/active").symlink_to("0123abcd")
    assert no_apps.flatpak_installed("com.visualstudio.code")
    assert ta.VSCode().detect(no_apps).available


def test_restore_drops_the_record_of_a_flatpak_app_that_is_gone(no_apps):
    app = no_apps.data / "flatpak/app/com.visualstudio.code"
    (app / "current").mkdir(parents=True)
    fh = no_apps.home / ".var/app/com.visualstudio.code"
    (fh / "config/Code/User").mkdir(parents=True)
    eng = Engine(no_apps, [ta.VSCode()])
    eng.apply(Settings())
    assert any(isinstance(c, list) and c[:3] == ["flatpak", "run", "com.visualstudio.code"] for c in no_apps.commands)
    import shutil
    shutil.rmtree(app)                     # flatpak uninstall: the data folder stays
    no_apps.commands.clear()
    assert eng.revert() == []
    assert not any("--uninstall-extension" in c for c in no_apps.commands)
    assert Backup(no_apps).data["commands"] == {}
