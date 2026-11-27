"""The command line: a part id that isn't one is an error, never a quiet success."""
from __future__ import annotations

import json

from fedoraglass import __main__ as cli
from fedoraglass import settings as settings_mod
from fedoraglass.engine import Engine
from fedoraglass.settings import Settings
from fedoraglass.targets.gtk import Gtk3, Gtk4


def _use(monkeypatch, fake_env):
    eng = Engine(fake_env, [Gtk3(), Gtk4()])
    monkeypatch.setattr(cli, "_engine", lambda: eng)
    return eng


def test_apply_only_an_unknown_part_is_refused(fake_env, monkeypatch, capsys):
    eng = _use(monkeypatch, fake_env)
    assert cli.main(["apply", "--only", "gtk4,typo"]) == 2
    err = capsys.readouterr().err
    assert "typo" in err and "gtk4" in err, "names the bad one and the good ones"
    assert not eng.is_applied() and not settings_mod.settings_path().exists()
    assert cli.main(["apply", "--only", ","]) == 2


def test_revert_an_unknown_part_is_refused(fake_env, monkeypatch, capsys):
    eng = _use(monkeypatch, fake_env)
    eng.apply(Settings())
    assert cli.main(["revert", "typo"]) == 2
    assert "typo" in capsys.readouterr().err
    assert eng.is_applied()
    assert cli.main(["revert", "gtk4"]) == 0
    from fedoraglass.engine import Backup
    assert Backup(fake_env).targets_with_changes() == {"gtk3"}


def test_a_part_an_older_version_applied_can_still_be_restored(fake_env, monkeypatch):
    eng = _use(monkeypatch, fake_env)
    eng.apply(Settings())
    monkeypatch.setattr(cli, "_engine", lambda: Engine(fake_env, [Gtk4()]))   # gtk3 gone from this version
    assert cli.main(["revert", "gtk3"]) == 0


def test_apply_only_does_not_save_the_settings(fake_env, monkeypatch):
    _use(monkeypatch, fake_env)
    settings_mod.save(Settings(frost=0.2))
    assert cli.main(["apply", "--only", "gtk4", "--frost", "0.9"]) == 0
    assert json.loads(settings_mod.settings_path().read_text())["frost"] == 0.2
    assert cli.main(["apply", "--frost", "0.9"]) == 0
    assert settings_mod.load().frost == 0.9


# ---- `fedora-glass plan` ---------------------------------------------------------------------
def _plan(capsys, home) -> tuple[int, list[str]]:
    code = cli.main(["plan"])
    return code, capsys.readouterr().out.replace(str(home), "~").splitlines()


def test_plan_says_unchanged_for_files_apply_would_leave_alone(fake_env, monkeypatch, capsys):
    eng = _use(monkeypatch, fake_env)
    before = _plan(capsys, fake_env.home)
    assert before == (0, ["[gtk3]", "  write ~/.config/gtk-3.0/gtk.css",
                          "[gtk4]", "  write ~/.config/gtk-4.0/gtk.css", "  write ~/.config/gtk-4.0/gtk-dark.css"])
    eng.apply(Settings())
    assert _plan(capsys, fake_env.home) == (0, ["[gtk3]", "  unchanged ~/.config/gtk-3.0/gtk.css",
                                                "[gtk4]", "  unchanged ~/.config/gtk-4.0/gtk.css",
                                                "  unchanged ~/.config/gtk-4.0/gtk-dark.css"])
    # Changed by hand, or more open than Apply leaves it: Apply writes it again.
    (fake_env.config / "gtk-4.0/gtk.css").write_text("/* mine */")
    (fake_env.config / "gtk-3.0/gtk.css").chmod(0o666)
    assert _plan(capsys, fake_env.home) == (0, ["[gtk3]", "  write ~/.config/gtk-3.0/gtk.css",
                                                "[gtk4]", "  write ~/.config/gtk-4.0/gtk.css",
                                                "  unchanged ~/.config/gtk-4.0/gtk-dark.css"])


def test_plan_says_unchanged_for_a_setting_that_already_holds_its_value(fake_env, monkeypatch, capsys):
    from fedoraglass.targets import shell as ts
    from tests.test_shell import install
    install(fake_env, ts.USER_THEME)
    fake_env.gs[("org.gnome.shell.extensions.user-theme", None)] = {"name": "'FedoraGlass'"}
    monkeypatch.setattr(cli, "_engine", lambda: Engine(fake_env, [ts.GnomeShell()]))
    code, lines = _plan(capsys, fake_env.home)
    assert code == 0
    # The theme file is new, so User Themes is bounced to read it: a real change, said as one.
    assert "  set org.gnome.shell.extensions.user-theme name = ''" in lines
    assert "  set org.gnome.shell.extensions.user-theme name = 'FedoraGlass'" in lines
    fake_env.gs[("org.gnome.shell.extensions.user-theme", None)]["name"] = "''"
    _code, lines = _plan(capsys, fake_env.home)
    assert "  set org.gnome.shell.extensions.user-theme name = 'FedoraGlass'" in lines
    cli.main(["apply"])
    capsys.readouterr()
    _code, lines = _plan(capsys, fake_env.home)
    assert "  unchanged org.gnome.shell.extensions.user-theme name" in lines
    assert not any("user-theme name = " in line for line in lines)


def test_plan_says_why_apply_leaves_a_file_behind_a_link_in_an_apps_folder(fake_env, monkeypatch, capsys):
    from fedoraglass.targets import apps as ta
    from tests.test_links_in_app_folders import NOT_FOLLOWED, vencord
    v = vencord(fake_env.home)
    (v / "themes").rmdir()
    elsewhere = fake_env.home / "elsewhere"
    elsewhere.mkdir()
    (v / "themes").symlink_to(elsewhere)
    monkeypatch.setattr(cli, "_engine", lambda: Engine(fake_env, [ta.Discord()]))
    code, lines = _plan(capsys, fake_env.home)
    assert code == 0
    theme = [line for line in lines if "/themes/" in line]
    assert len(theme) == 1 and NOT_FOLLOWED in theme[0], lines
    assert "~/.var/app/com.discordapp.Discord/config/Vencord/themes is a link" in theme[0]
    assert not any(elsewhere.iterdir())
