"""Glass on the login screen (liquidglass/login_screen.py), the only part that runs as root.

The apply/undo tests build a small theme file with the real GLib tools in a temporary
folder that stands in for /usr/share/gnome-shell, so nothing outside it is touched.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from liquidglass import login_screen as ls

TOOLS = shutil.which("gresource") and shutil.which("glib-compile-resources")
needs_tools = pytest.mark.skipif(not TOOLS, reason="needs gresource and glib-compile-resources")

GDM = "#lockDialogGroup { background-color: #222226; }\n"
OTHER = b"<svg xmlns='http://www.w3.org/2000/svg'/>"


def make_theme(path: Path, gdm: str = GDM) -> None:
    src = path.parent / "src"
    (src / "org/gnome/shell/theme").mkdir(parents=True, exist_ok=True)
    (src / "org/gnome/shell/theme/gdm.css").write_text(gdm)
    (src / "org/gnome/shell/theme/icon.svg").write_bytes(OTHER)
    xml = src / "t.xml"
    xml.write_text('<gresources><gresource prefix="/"><file>org/gnome/shell/theme/gdm.css</file>'
                   '<file compressed="true">org/gnome/shell/theme/icon.svg</file></gresource></gresources>')
    subprocess.run(["glib-compile-resources", f"--sourcedir={src}", f"--target={path}", str(xml)], check=True)


@pytest.fixture
def dirs(tmp_path):
    shell, state = tmp_path / "gnome-shell", tmp_path / "state"
    shell.mkdir()
    make_theme(shell / "gnome-shell-theme.gresource")
    return str(shell), str(state)


def gdm_css(shell_dir: str) -> str:
    return ls.extract(ls.target(shell_dir), ls.GDM_CSS).decode()


# ---- values and the look ------------------------------------------------------------
@pytest.mark.parametrize("bad", [("3584e4", "#203050", 0.5), ("#3584e4", "#20305", 0.5), ("#3584e4", "#203050", 1.5),
                                 ("#3584e4", "#203050", "nan"), ("#3584e4}", "#203050", 0.5),
                                 ("#3584e4", "#203050; } * { color: red", 0.5), ("#3584e4", "#203050", -0.1)])
def test_only_checked_colours_and_numbers_reach_the_css(bad):
    with pytest.raises(ls.LoginScreenError):
        ls.css(*bad)


@pytest.mark.parametrize("frost", [0, 0.45, 1])
def test_css_is_one_marked_block_of_plain_rules(frost):
    text = ls.css("#3584E4", "#6a3fb5", frost)
    assert text.count(ls.MARK_START) == 1 and text.count(ls.MARK_END) == 1
    assert text.count("{") == text.count("}")
    assert "#3584e4" in text and "url(" not in text and "@import" not in text
    # Every pane stays faint white glass, so GNOME's white text keeps its contrast.
    alphas = [float(a) for a in __import__("re").findall(r"rgba\(255, 255, 255, ([0-9.]+)\)", text)]
    assert alphas and max(alphas) <= 0.30


def test_an_old_block_is_replaced_not_stacked():
    once = GDM + ls.css("#3584e4", "#6a3fb5", 0.4)
    assert ls.strip_block(once) == GDM
    assert ls.strip_block(GDM) == GDM


def test_the_theme_file_must_stay_in_the_shell_folder(tmp_path):
    shell = tmp_path / "gnome-shell"
    shell.mkdir()
    (shell / "gdm-theme.gresource").symlink_to(tmp_path / "elsewhere.gresource")
    with pytest.raises(ls.LoginScreenError):
        ls.target(str(shell))
    (shell / "gdm-theme.gresource").unlink()
    (shell / "gdm-theme.gresource").symlink_to("gnome-shell-theme.gresource")    # Ubuntu's way
    assert ls.target(str(shell)) == str((shell / "gnome-shell-theme.gresource").resolve())


def test_needs_root_and_takes_no_paths(capsys):
    if os.geteuid() == 0:
        pytest.skip("running as root")
    assert ls.main(["x", "apply", "#3584e4", "#6a3fb5", "0.4"]) == 77
    assert ls.main(["x", "undo"]) == 77
    assert ls.main(["x", "status", "/etc/shadow"]) == 77      # no extra arguments, ever
    assert ls.main(["x", "status"]) == 0


def test_runs_with_only_the_standard_library():
    """pkexec runs it as root with python3 -I -S: no liquidglass, no site packages."""
    src = Path(ls.__file__).read_text()
    assert src.startswith("#!/usr/bin/python3 -IS\n")
    imports = {l.split()[1].split(".")[0] for l in src.splitlines() if l.startswith(("import ", "from "))}
    assert imports <= {"__future__", "hashlib", "json", "os", "re", "shutil", "subprocess", "sys", "tempfile"}


# ---- apply and undo -------------------------------------------------------------------
@needs_tools
def test_apply_changes_only_gdm_css_and_undo_restores_every_byte(dirs):
    shell, state = dirs
    path = ls.target(shell)
    before = Path(path).read_bytes()
    assert ls.status(shell, state) == "off"
    ls.apply("#3584e4", "#6a3fb5", 0.4, shell, state)
    assert ls.status(shell, state) == "on"
    assert gdm_css(shell).startswith(GDM) and ls.MARK_START in gdm_css(shell)
    assert ls.extract(path, "/org/gnome/shell/theme/icon.svg") == OTHER
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
    # Turning it on again with other colours starts from the original: one block.
    ls.apply("#e62d42", "#203050", 1, shell, state)
    assert gdm_css(shell).count(ls.MARK_START) == 1 and "#e62d42" in gdm_css(shell)
    assert ls.undo(shell, state) == "the normal login screen is back"
    assert Path(path).read_bytes() == before
    assert ls.status(shell, state) == "off" and not os.listdir(state)
    assert ls.undo(shell, state) == "it was already off"


@needs_tools
def test_after_a_gnome_update_undo_leaves_the_new_file_alone(dirs, tmp_path):
    shell, state = dirs
    ls.apply("#3584e4", "#6a3fb5", 0.4, shell, state)
    make_theme(tmp_path / "new.gresource", gdm=GDM + "/* GNOME 50.2 */\n")
    shutil.copyfile(tmp_path / "new.gresource", ls.target(shell))      # what dnf does
    new = Path(ls.target(shell)).read_bytes()
    assert ls.status(shell, state) == "undone"
    assert "already" in ls.undo(shell, state)
    assert Path(ls.target(shell)).read_bytes() == new


@needs_tools
def test_never_saves_a_changed_file_as_the_original(dirs):
    shell, state = dirs
    ls.apply("#3584e4", "#6a3fb5", 0.4, shell, state)
    os.unlink(os.path.join(state, ls.BACKUP))
    with pytest.raises(ls.LoginScreenError, match="dnf reinstall"):
        ls.apply("#3584e4", "#6a3fb5", 0.4, shell, state)
    with pytest.raises(ls.LoginScreenError, match="dnf reinstall"):
        ls.undo(shell, state)


@needs_tools
def test_a_bad_theme_file_changes_nothing(dirs):
    shell, state = dirs
    path = ls.target(shell)
    Path(path).write_bytes(b"not a resource file")
    with pytest.raises(ls.LoginScreenError):
        ls.apply("#3584e4", "#6a3fb5", 0.4, shell, state)
    assert Path(path).read_bytes() == b"not a resource file"
    assert ls.status(shell, state) == "off"


@needs_tools
def test_state_file_holds_only_hashes(dirs):
    shell, state = dirs
    ls.apply("#3584e4", "#6a3fb5", 0.4, shell, state)
    s = json.loads(Path(state, ls.STATE).read_text())
    assert set(s) == {"original", "written", "target"}
    assert all(len(s[k]) == 64 for k in ("original", "written"))
