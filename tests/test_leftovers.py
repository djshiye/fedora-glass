"""A source install (install.sh) left behind after switching to the package: its user
unit and menu entry win over the package's, so its older copy re-applies its older look
at login. The app finds them and cleans up only those files, on one click."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fedoraglass import leftovers

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def packaged(monkeypatch):
    monkeypatch.setattr(leftovers, "from_package", lambda: True)


def _source_install(env, tmp_path, *, package: bool = False, args: tuple[str, ...] = ()):
    """Run the real install.sh's file-writing steps: copy it with the package steps cut out.
    package=True: a package manager says the fedora-glass package is installed on this PC."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("needs bash")
    script = (ROOT / "install.sh").read_text()
    # Only the files it writes: no root check (the tests may run as root), no system
    # packages; systemctl and the cache tools do nothing.
    script = script.replace("if [[ $EUID -eq 0 ]]; then", "if false; then", 1)
    i, j = script.index("# ---- system packages"), script.index("# ---- the app")
    script = script[:i] + script[j:]
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir(exist_ok=True)
    for tool in ("systemctl", "gtk-update-icon-cache", "update-desktop-database"):
        (fake_bin / tool).write_text("#!/bin/sh\nexit 0\n")
        (fake_bin / tool).chmod(0o755)
    # Every package manager install.sh asks answers the same: installed, or not.
    for tool in ("rpm", "dpkg-query", "pacman"):
        (fake_bin / tool).write_text(f"#!/bin/sh\nexit {0 if package else 1}\n")
        (fake_bin / tool).chmod(0o755)
    copy = tmp_path / "src"
    if not copy.exists():
        shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "__pycache__", "tests", "qa"))
    (copy / "install.sh").write_text(script)
    environ = {"HOME": str(env.home), "PATH": f"{fake_bin}:/usr/bin:/bin",
               "XDG_DATA_HOME": str(env.data), "XDG_CONFIG_HOME": str(env.config)}
    r = subprocess.run([bash, str(copy / "install.sh"), "--no-gui", *args], env=environ, capture_output=True, text=True,
                       timeout=120, stdin=subprocess.DEVNULL)
    if package and "--alongside-package" not in args:
        return r                                  # refused: the caller looks at what it said
    assert r.returncode == 0, r.stdout + r.stderr
    # `systemctl --user enable` links the unit from the target that starts it.
    wants = env.config / "systemd/user/graphical-session.target.wants"
    wants.mkdir(parents=True, exist_ok=True)
    if not (wants / leftovers.UNIT).is_symlink():
        (wants / leftovers.UNIT).symlink_to(env.config / "systemd/user" / leftovers.UNIT)
    return r


def _theirs(env):
    """Files in the same folders that are not install.sh's: they must stay."""
    other = env.config / "systemd/user/other.service"
    other.write_text("[Service]\nExecStart=/usr/bin/true\n")
    app = env.data / "applications/org.example.App.desktop"
    app.write_text("[Desktop Entry]\nName=Example\nExec=example\n")
    tool = env.home / ".local/bin/mytool"
    tool.write_text("#!/bin/sh\necho hi\n")
    return [other, app, tool]


def test_finds_exactly_what_install_sh_left(fake_env, tmp_path, packaged):
    _source_install(fake_env, tmp_path)
    keep = _theirs(fake_env)
    found = leftovers.find(fake_env)
    unit = fake_env.config / "systemd/user" / leftovers.UNIT
    assert found == [
        fake_env.config / "systemd/user/graphical-session.target.wants" / leftovers.UNIT,
        unit,
        fake_env.data / "applications" / leftovers.DESKTOP,
        fake_env.home / ".local/bin/liquid-glass",
        fake_env.home / ".local/bin/fedora-glass",
    ]
    assert leftovers.clean_up(fake_env) == []
    assert not any(os.path.lexists(p) for p in found)
    assert all(p.exists() for p in keep), "touched a file that is not the old copy's"
    assert (fake_env.data / "liquid-glass/fedoraglass").is_dir(), "the old copy's code is left (nothing runs it now)"
    assert fake_env.commands[-2:] == [["systemctl", "--user", "daemon-reload"],
                                      ["systemctl", "--user", "restart", leftovers.UNIT]]
    assert leftovers.find(fake_env) == []


def test_nothing_is_found_when_the_app_is_not_the_package(fake_env, tmp_path, monkeypatch):
    _source_install(fake_env, tmp_path)
    monkeypatch.setattr(leftovers, "from_package", lambda: False)
    assert leftovers.find(fake_env) == []
    assert leftovers.clean_up(fake_env) == []
    assert (fake_env.config / "systemd/user" / leftovers.UNIT).exists()


def test_the_package_is_told_by_where_it_runs_from(monkeypatch):
    assert leftovers.from_package() is False             # this checkout
    monkeypatch.setattr(leftovers, "APP_DIR", Path(leftovers.__file__).resolve().parent.parent)
    assert leftovers.from_package() is True


def test_files_changed_by_the_user_or_another_app_are_left_alone(fake_env, packaged):
    units = fake_env.config / "systemd/user"
    units.mkdir(parents=True)
    # The same names, but not pointing at install.sh's copy.
    (units / leftovers.UNIT).write_text("[Unit]\nDescription=Fedora Glass: mine\n[Service]\nExecStart=/opt/fg/fedora-glass watch\n")
    apps = fake_env.data / "applications"
    apps.mkdir(parents=True)
    (apps / leftovers.DESKTOP).write_text("[Desktop Entry]\nName=Fedora Glass\nExec=fedora-glass gui --scheme dark\n")
    b = fake_env.home / ".local/bin"
    b.mkdir(parents=True)
    (b / "fedora-glass").write_text("#!/bin/sh\nexec /usr/bin/fedora-glass \"$@\"\n")
    # A planted link to some other file never counts as a regular file.
    elsewhere = fake_env.home / "notes.txt"
    elsewhere.write_text("[Unit]\nDescription=Fedora Glass: x\n[Service]\nExecStart=\"%s\" watch\n" % (b / "fedora-glass"))
    assert leftovers.find(fake_env) == []
    (units / leftovers.UNIT).unlink()
    (units / leftovers.UNIT).symlink_to(elsewhere)
    assert leftovers.find(fake_env) == []
    assert leftovers.clean_up(fake_env) == []
    assert elsewhere.exists() and (units / leftovers.UNIT).is_symlink()


def test_a_unit_from_the_liquid_glass_days_counts(fake_env, packaged):
    b = fake_env.home / ".local/bin"
    b.mkdir(parents=True)
    units = fake_env.config / "systemd/user"
    units.mkdir(parents=True)
    unit = units / leftovers.UNIT
    unit.write_text(f'[Unit]\nDescription=Liquid Glass: follow GNOME dark and light style\n\n[Service]\n'
                    f'ExecStart="{b}/liquid-glass" watch\n')
    assert leftovers.find(fake_env) == [unit]


# ---- the app ------------------------------------------------------------------------
def test_the_app_offers_the_clean_up_and_does_it_on_click(fake_env, tmp_path, packaged):
    QtGui = pytest.importorskip("PySide6.QtGui")
    QtGui.QGuiApplication.instance() or QtGui.QGuiApplication([])
    from fedoraglass.engine import Engine
    from fedoraglass.gui.backend import Backend
    _source_install(fake_env, tmp_path)
    b = Backend(env=fake_env, engine_factory=lambda: Engine(fake_env, []),
                settings_path=fake_env.config / "liquid-glass/settings.json", ui_dark=True, start=False)
    _KEEP.append(b)
    b.refreshTargets()
    assert b.waitIdle()
    assert b.property("hasOldCopy") is True
    assert (fake_env.config / "systemd/user" / leftovers.UNIT).exists(), "removed without a click"
    said = []
    b.noticed.connect(said.append)
    b.cleanUpOldCopy()
    assert b.waitIdle()
    assert said == ["Old copy cleaned up. Fedora Glass now runs from the package only."]
    assert b.property("hasOldCopy") is False
    assert not (fake_env.config / "systemd/user" / leftovers.UNIT).exists()


_KEEP: list = []


def test_the_banner_shows_with_an_old_copy(qml):
    from PySide6.QtCore import QObject, QUrl
    from PySide6.QtQml import QQmlComponent

    from fedoraglass.gui import app as gui_app
    probe = QQmlComponent(qml)
    probe.setData(b"import QtQuick\nimport FedoraGlass.Core\nQtObject { property var b: Backend }", QUrl())
    b = probe.create().property("b")
    comp = QQmlComponent(qml, QUrl.fromLocalFile(str(Path(gui_app.QML_DIR) / "Main.qml")))
    win = comp.create()
    assert win is not None, comp.errorString()
    banner = win.findChild(QObject, "oldCopyBanner")
    assert banner.property("shown") is False
    try:
        b._leftovers = [Path("/x")]
        b.targetsChanged.emit()
        assert banner.property("shown") is True
        assert win.findChild(QObject, "cleanUpOldCopy").property("text") == "Clean up old copy"
    finally:
        b._leftovers = []
        b.targetsChanged.emit()
        win.deleteLater()


def test_the_package_takes_an_old_source_install_out_of_the_way_at_login(fake_env, tmp_path, packaged, monkeypatch, capsys):
    """After install.sh and then the package, the app grid, the command and the watcher all ran
    the old copy, and the banner offering the clean-up could never show (only the package's app
    has it). `fedora-glass before-login` always runs as the package: it cleans up (Dino's choice,
    2026-11-20). Before the session is up, so the watcher is not restarted: systemd starts the
    package's own."""
    from fedoraglass import __main__ as cli
    from fedoraglass import env as env_mod

    _source_install(fake_env, tmp_path)
    keep = _theirs(fake_env)
    found = leftovers.find(fake_env)
    assert found
    monkeypatch.setattr(env_mod, "Env", lambda: fake_env)
    monkeypatch.setattr(cli, "update_glass_before_login", lambda eng: None)
    monkeypatch.setattr(cli, "_engine", lambda: None)
    assert cli.main(["before-login"]) == 0
    assert not any(os.path.lexists(p) for p in found)
    assert all(p.exists() for p in keep), "touched a file that is not the old copy's"
    assert (fake_env.data / "liquid-glass/fedoraglass").is_dir()
    assert ["systemctl", "--user", "daemon-reload"] in fake_env.commands
    assert ["systemctl", "--user", "restart", leftovers.UNIT] not in fake_env.commands
    assert "an old source install was in the way of the package" in capsys.readouterr().err
    # The next login: nothing left, nothing said.
    fake_env.commands.clear()
    assert cli.main(["before-login"]) == 0
    assert fake_env.commands == [] and capsys.readouterr().err == ""


def test_a_source_install_or_checkout_never_cleans_up_at_login(fake_env, tmp_path, monkeypatch):
    from fedoraglass import __main__ as cli
    from fedoraglass import env as env_mod

    _source_install(fake_env, tmp_path)
    monkeypatch.setattr(env_mod, "Env", lambda: fake_env)
    assert cli.drop_source_install() == []
    assert (fake_env.config / "systemd/user" / leftovers.UNIT).exists()


def _alongside_files(env):
    return [env.config / "systemd/user" / leftovers.UNIT, env.data / "applications" / leftovers.DESKTOP,
            env.home / ".local/bin/liquid-glass", env.home / ".local/bin/fedora-glass"]


def test_a_copy_installed_next_to_the_package_on_purpose_stays_at_login(fake_env, tmp_path, packaged, monkeypatch, capsys):
    """`./install.sh --alongside-package` (for working on Fedora Glass itself) says the copy
    takes the package's place until ./uninstall.sh. The package's step at each login took its
    command, menu entry and watcher away again, as if it were a forgotten old install. Such a
    copy is in charge: the package's login step leaves it alone, and does not put the
    package's own glass back over the copy's either."""
    from fedoraglass import __main__ as cli
    from fedoraglass import env as env_mod

    _source_install(fake_env, tmp_path, package=True, args=("--alongside-package",))
    files = _alongside_files(fake_env)
    assert all(os.path.lexists(p) for p in files)
    assert leftovers.kept_on_purpose(fake_env)
    assert leftovers.find(fake_env) == []
    monkeypatch.setattr(env_mod, "Env", lambda: fake_env)
    updated = []
    monkeypatch.setattr(cli, "update_glass_before_login", lambda eng: updated.append(eng))
    monkeypatch.setattr(cli, "_engine", lambda: None)
    assert cli.main(["before-login"]) == 0
    assert all(os.path.lexists(p) for p in files), "the copy's own files were taken away"
    assert updated == [], "the package put its own glass back over the copy's"
    assert fake_env.commands == [] and capsys.readouterr().err == ""
    # The app (the package's, opened by hand) offers no clean-up either.
    assert leftovers.clean_up(fake_env) == [] and all(os.path.lexists(p) for p in files)


def test_install_sh_refuses_next_to_a_package_without_being_asked(fake_env, tmp_path, packaged):
    r = _source_install(fake_env, tmp_path, package=True)
    assert r.returncode == 1 and "--alongside-package" in r.stdout
    assert not (fake_env.data / "liquid-glass").exists()


def test_a_plain_install_afterwards_is_an_ordinary_one_again(fake_env, tmp_path, packaged):
    """The mark is only for a copy put next to a package on purpose. The same copy installed
    again the plain way (no package then) loses it, so after a later switch to the package it
    is cleaned up like any old source install."""
    _source_install(fake_env, tmp_path, package=True, args=("--alongside-package",))
    assert leftovers.find(fake_env) == []
    _source_install(fake_env, tmp_path)
    assert not leftovers.kept_on_purpose(fake_env)
    assert set(_alongside_files(fake_env)) <= set(leftovers.find(fake_env))


def test_the_flag_without_a_package_leaves_no_mark(fake_env, tmp_path, packaged):
    _source_install(fake_env, tmp_path, args=("--alongside-package",))
    assert not leftovers.kept_on_purpose(fake_env)
    assert set(_alongside_files(fake_env)) <= set(leftovers.find(fake_env))


def test_the_mark_counts_only_as_a_real_file_next_to_a_real_copy(fake_env, tmp_path, packaged):
    _source_install(fake_env, tmp_path, package=True, args=("--alongside-package",))
    base = fake_env.data / "liquid-glass"
    mark = base / leftovers.ALONGSIDE
    assert mark.is_file() and not mark.is_symlink()
    # A link is not the mark install.sh writes.
    text = mark.read_text()
    mark.unlink()
    (tmp_path / "elsewhere").write_text(text)
    mark.symlink_to(tmp_path / "elsewhere")
    assert not leftovers.kept_on_purpose(fake_env) and leftovers.find(fake_env)
    mark.unlink()
    mark.write_text(text)
    assert leftovers.kept_on_purpose(fake_env)
    # The copy was deleted by hand, its launcher and unit were forgotten: leftovers again.
    shutil.rmtree(base / "fedoraglass")
    assert not leftovers.kept_on_purpose(fake_env)
    assert set(_alongside_files(fake_env)) <= set(leftovers.find(fake_env))


def test_uninstall_sh_takes_the_mark_with_the_copy():
    text = (ROOT / "uninstall.sh").read_text()
    assert 'rm -rf "$data/liquid-glass"' in text      # the mark lives in that folder
